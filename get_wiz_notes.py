"""
从为知笔记读取信息，导出单篇或批量导出笔记

功能：
1. 登录为知笔记Web版
2. 获取指定文件夹下的笔记列表
3. 下载笔记内容并根据内容类型导出为markdown或html格式
4. 支持断点续传，避免重复下载
5. 自动处理文件名中的非法字符
6. 支持协作笔记的导出

使用方法：
1. 配置文件 "../account/web_accounts.json" 格式如下：
{
    "wiz": {
        "username": "your_email@example.com",
        "password": "your_password"
    }
}

2. 运行脚本：
python get_wiz_notes.py

参数说明：
- config_path: 配置文件路径，默认为 "../account/web_accounts.json"
- export_dir: 导出目录，默认为 "./wiznotes"
- max_notes: 每个文件夹最大获取笔记数量

注意事项：
1. 为知笔记API限制单次最多获取1000篇笔记，超过1000篇笔记的文件夹会自动进行两次查询；
2. 导出过程支持断点续传，可以随时中断后继续；如果需要覆盖已导出文件，请删除导出目录下checkpoint文件；
3. 协作笔记使用WebSocket通信，需要确保网络连接稳定；
"""

import json
import requests
from pathlib import Path
import logging
import time
from datetime import datetime
import os
import sys
import re
import markdownify
import websocket
import threading
import queue
import uuid

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class WizNoteClient:
    AS_URL = 'https://as.wiz.cn'

    def __init__(self, config_path='config.json'):
        self.config = self._load_config(config_path)
        self.token = None
        self.kb_info = None

    def _load_config(self, config_path):
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"加载配置文件失败: {e}")
            raise

    def _request(self, method, url, data=None, token=None, headers=None):
        """统一请求处理"""
        try:
            _headers = {}
            if token:
                _headers['X-Wiz-Token'] = token
            if headers:
                _headers.update(headers)

            response = requests.request(
                method=method,
                url=url,
                json=data if data else None,
                headers=_headers if _headers else None
            )

            result = response.json()
            if result['returnCode'] != 200:
                raise Exception(f"API错误: {result['returnMessage']}")

            return result['result']

        except Exception as e:
            logging.error(f"请求失败: {e}")
            raise

    def login(self):
        """登录获取token"""
        try:
            data = {
                'userId': self.config['wiz']['username'],
                'password': self.config['wiz']['password']
            }

            result = self._request('POST', f"{self.AS_URL}/as/user/login", data)
            self.token = result['token']
            self.kb_info = {
                'kbServer': result['kbServer'],
                'kbGuid': result['kbGuid'],
                'userGuid': result.get('userGuid', '')  # 添加userGuid
            }
            logging.info("登录成功")
            return result

        except Exception as e:
            logging.error(f"登录失败: {e}")
            raise

    def get_folders(self):
        """获取笔记文件夹列表"""
        try:
            url = f"{self.kb_info['kbServer']}/ks/category/all/{self.kb_info['kbGuid']}"
            return self._request('GET', url, token=self.token)
        except Exception as e:
            logging.error(f"获取文件夹列表失败: {e}")
            raise

    def get_note_list(self, folder, count=100, max_notes=None):
        """获取指定文件夹下的笔记列表

        Args:
            folder: 文件夹路径
            count: 每页笔记数量，默认100
            max_notes: 最大获取笔记数量，如果超过1000则会自动进行两次查询
        """
        try:
            note_list = []
            seen_guids = set()  # 用于去重的GUID集合

            # 如果max_notes大于1000，需要进行两次查询
            if max_notes and max_notes > 1000:
                # 第一次查询：降序获取前1000条
                desc_notes = self._get_notes_with_order(folder, count, 1000, "desc")
                for note in desc_notes:
                    if note['docGuid'] not in seen_guids:
                        note_list.append(note)
                        seen_guids.add(note['docGuid'])

                # 第二次查询：升序获取剩余笔记
                remaining = max_notes - 1000
                if remaining > 0:
                    asc_notes = self._get_notes_with_order(folder, count, remaining, "asc")
                    for note in asc_notes:
                        if note['docGuid'] not in seen_guids:
                            note_list.append(note)
                            seen_guids.add(note['docGuid'])
            else:
                # 单次查询足够
                max_to_fetch = min(1000, max_notes) if max_notes else 1000
                note_list = self._get_notes_with_order(folder, count, max_to_fetch, "desc")

            logging.info(f"共获取到 {len(note_list)} 篇笔记")
            return note_list

        except Exception as e:
            logging.error(f"获取笔记列表失败: {e}")
            raise

    def _get_notes_with_order(self, folder, count, max_notes, order):
        """获取指定顺序的笔记列表

        Args:
            folder: 文件夹路径
            count: 每页笔记数量
            max_notes: 最大获取笔记数量
            order: 排序方式，"asc" 或 "desc"
        """
        notes = []
        start = 0

        while True:
            if start >= max_notes:
                break

            # 获取指定文件夹下的笔记列表
            # get /ks/note/list/category/:kbGuid?category=:folder&withAbstract=true|false&start=:start&count=:count&orderBy=title|created|modified&ascending=asc|desc
            url = (f"{self.kb_info['kbServer']}/ks/note/list/category/{self.kb_info['kbGuid']}"
                  f"?start={start}&count={count}&category={folder}"
                  f"&orderBy=modified&ascending={order}")

            sub_notes = self._request('GET', url, token=self.token)
            if not sub_notes:
                break

            notes.extend(sub_notes)
            logging.info(f"已获取 {len(notes)} 篇笔记 (order={order})")

            if len(sub_notes) < count:
                break

            start += count

        return notes

    def download_note(self, doc_guid):
        """下载指定笔记内容"""
        try:
            # 使用download接口获取笔记详情，这个接口会返回笔记类型
            url = (f"{self.kb_info['kbServer']}/ks/note/download/{self.kb_info['kbGuid']}/{doc_guid}"
                  "?downloadInfo=1&downloadData=1")
            response = requests.get(
                url,
                headers={'X-Wiz-Token': self.token}
            )

            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")

            try:
                result = json.loads(response.content.decode('utf-8'))
                logging.debug(f"笔记下载响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            except json.JSONDecodeError:
                logging.error("JSON解析失败，返回内容：")
                logging.error(response.content)
                raise

            if result.get('returnCode') != 200:
                raise Exception(f"API错误: {result.get('returnMessage')}")

            # 从result中获取笔记信息和类型
            note_info = result.get('info', {})
            html_content = result.get('html', '')
            resources = result.get('resources', [])
            note_type = note_info.get('type', 'document')  # 从info中获取type字段

            logging.info(f"笔记类型: {note_type}, 笔记标题: {note_info.get('title', 'Unknown')}")

            # 如果是协作笔记，使用WebSocket获取数据
            if note_type == 'collaboration':
                logging.info("检测到协作笔记，使用WebSocket获取数据")
                try:
                    # 获取协作笔记token
                    token_url = f"{self.kb_info['kbServer']}/ks/note/{self.kb_info['kbGuid']}/{doc_guid}/tokens"
                    token_response = requests.post(token_url, headers={'X-Wiz-Token': self.token})

                    if token_response.status_code != 200:
                        raise Exception(f"获取协作笔记token失败: {token_response.status_code}")

                    token_result = token_response.json()
                    if token_result.get('returnCode') != 200:
                        raise Exception(f"获取协作笔记token失败: {token_result.get('returnMessage')}")

                    editor_token = token_result['result']['editorToken']
                    logging.info("成功获取协作笔记token")

                    # 使用WebSocket获取协作笔记内容
                    collaboration_content = self.get_collaboration_content(editor_token, doc_guid)

                    # 解析协作笔记内容为Markdown
                    markdown_content = self.parse_collaboration_content(collaboration_content)

                    return {
                        'info': note_info,
                        'html': markdown_content,
                        'resources': resources,
                        'type': 'collaboration',
                        'editor_token': editor_token
                    }

                except Exception as e:
                    logging.error(f"处理协作笔记失败: {e}")
                    # 如果协作笔记处理失败，回退到普通笔记处理
                    logging.info("回退到普通笔记处理方式")

            # 处理普通笔记或协作笔记处理失败的情况
            if resources:
                logging.info(f"笔记包含 {len(resources)} 个资源文件")
                for resource in resources:
                    logging.debug(f"资源文件: {resource.get('name')} ({resource.get('size')} bytes)")

            return {
                'info': note_info,
                'html': html_content,
                'resources': resources,
                'type': note_type
            }

        except Exception as e:
            logging.error(f"下载笔记失败: {e}")
            raise

    def get_collaboration_content(self, editor_token, doc_guid):
        """获取协作笔记内容，使用WebSocket协议"""
        try:
            import websocket
            import json

            # 获取域名（去掉https://前缀）
            domain = self.kb_info['kbServer'].replace('https://', '')
            wss_url = f"wss://{domain}/editor/{self.kb_info['kbGuid']}/{doc_guid}"

            logging.info(f"连接WebSocket: {wss_url}")

            # 准备WebSocket请求
            hs_request = {
                "a": "hs",
                "id": None,
                "auth": {
                    "appId": self.kb_info['kbGuid'],
                    "docId": doc_guid,
                    "userId": self.kb_info.get('userGuid', ''),
                    "permission": "w",
                    "token": editor_token
                }
            }

            f_request = {
                "a": "f",
                "c": self.kb_info['kbGuid'],
                "d": doc_guid,
                "v": None
            }

            s_request = {
                "a": "s",
                "c": self.kb_info['kbGuid'],
                "d": doc_guid,
                "v": None
            }

            # 建立WebSocket连接
            ws = websocket.create_connection(wss_url)

            # 发送握手请求（需要发送3次）
            hs = json.dumps(hs_request)
            f = json.dumps(f_request)
            s = json.dumps(s_request)

            ws.send(hs)
            response1 = ws.recv()
            logging.debug(f"握手响应1: {response1}")

            ws.send(hs)
            response2 = ws.recv()
            logging.debug(f"握手响应2: {response2}")

            ws.send(hs)
            response3 = ws.recv()
            logging.debug(f"握手响应3: {response3}")

            # 发送获取内容请求
            ws.send(f)
            response4 = ws.recv()
            logging.debug(f"获取内容响应: {response4}")

            # 获取实际内容
            content = ws.recv()
            logging.info(f"获取到协作笔记内容，长度: {len(content)}")

            # 发送状态请求
            ws.send(s)
            ws.recv()

            ws.close()
            return content

        except Exception as e:
            logging.error(f"获取协作笔记内容失败: {e}")
            raise

    def parse_collaboration_content(self, content):
        """解析协作笔记内容为Markdown格式"""
        try:
            # 协作笔记内容通常是JSON格式
            if isinstance(content, str):
                try:
                    content_data = json.loads(content)
                except json.JSONDecodeError:
                    logging.warning("协作笔记内容不是有效的JSON格式，直接返回")
                    return content
            else:
                content_data = content

            logging.info(f"开始解析协作笔记，数据结构: {type(content_data)}")

            # 根据wiz2obsidian项目的数据结构解析
            if isinstance(content_data, dict) and 'data' in content_data:
                data_section = content_data['data']
                if 'data' in data_section and 'blocks' in data_section['data']:
                    blocks = data_section['data']['blocks']
                    logging.info(f"找到 {len(blocks)} 个块需要解析")

                    # 使用完整的数据上下文进行解析
                    full_data = data_section['data']
                    markdown_lines = []

                    for block in blocks:
                        block_markdown = self._parse_collaboration_block(full_data, block)
                        if block_markdown:
                            markdown_lines.append(block_markdown)

                    result = ''.join(markdown_lines)
                    logging.info(f"协作笔记解析完成，生成Markdown长度: {len(result)}")
                    return result
                else:
                    logging.warning("协作笔记数据结构不符合预期")
                    return json.dumps(content_data, ensure_ascii=False, indent=2)
            else:
                logging.warning("协作笔记数据格式不符合预期")
                return str(content_data)

        except Exception as e:
            logging.error(f"解析协作笔记内容失败: {e}")
            return str(content)

    def _parse_collaboration_block(self, full_data, block):
        """解析单个协作笔记块"""
        try:
            block_type = block.get('type', '')
            block_id = block.get('id', '')

            logging.debug(f"解析块: type={block_type}, id={block_id}")

            if block_type == 'text':
                return self._parse_text_block(block)
            elif block_type == 'list':
                return self._parse_list_block(block)
            elif block_type == 'code':
                return self._parse_code_block(full_data, block)
            elif block_type == 'table':
                return self._parse_table_block(full_data, block)
            elif block_type == 'embed':
                return self._parse_embed_block(block)
            else:
                logging.warning(f"未知的块类型: {block_type}")
                return f"\n<!-- 未知块类型: {block_type} -->\n"

        except Exception as e:
            logging.error(f"解析块失败: {e}")
            return f"\n<!-- 块解析失败: {str(e)} -->\n"

    def _parse_text_block(self, block):
        """解析文本块"""
        text_content = self._parse_text_array(block.get('text', []))

        # 处理标题
        if block.get('heading'):
            level = block.get('heading', 1)
            return f"\n{'#' * level} {text_content}\n\n"

        # 处理引用
        elif block.get('quoted'):
            return f"\n> {text_content}\n\n"

        # 普通文本
        else:
            return f"\n{text_content}\n"

    def _parse_list_block(self, block):
        """解析列表块"""
        text_content = self._parse_text_array(block.get('text', []))
        level = block.get('level', 1)
        indent = '  ' * (level - 1)

        # 处理复选框
        checkbox = block.get('checkbox')
        if checkbox:
            if checkbox == 'checked':
                checkbox_mark = '[x] '
            elif checkbox == 'unchecked':
                checkbox_mark = '[ ] '
            else:
                checkbox_mark = ''
        else:
            checkbox_mark = ''

        # 处理有序/无序列表
        if block.get('ordered'):
            start = block.get('start', 1)
            return f"{indent}{start}. {checkbox_mark}{text_content}\n"
        else:
            return f"{indent}- {checkbox_mark}{text_content}\n"

    def _parse_code_block(self, full_data, block):
        """解析代码块"""
        language = block.get('language', '')
        children = block.get('children', [])

        code_lines = []
        for child_id in children:
            if child_id in full_data:
                child_data = full_data[child_id]
                if isinstance(child_data, list) and child_data:
                    text_obj = child_data[0]
                    if 'text' in text_obj and text_obj['text']:
                        code_lines.append(text_obj['text'][0].get('insert', ''))
                    else:
                        code_lines.append('')  # 空行

        code_content = '\n'.join(code_lines)
        return f"\n```{language}\n{code_content}\n```\n\n"

    def _parse_table_block(self, full_data, block):
        """解析表格块"""
        cols = block.get('cols', 0)
        children = block.get('children', [])

        # 提取所有单元格内容
        cell_contents = []
        for child_id in children:
            if child_id in full_data:
                child_data = full_data[child_id]
                if isinstance(child_data, list) and child_data:
                    text_obj = child_data[0]
                    if 'text' in text_obj and text_obj['text']:
                        cell_contents.append(text_obj['text'][0].get('insert', ''))
                    else:
                        cell_contents.append('')
            else:
                cell_contents.append('')

        if not cell_contents or cols == 0:
            return "\n<!-- 空表格 -->\n"

        # 构建Markdown表格
        markdown_lines = []

        # 表头
        headers = cell_contents[:cols]
        markdown_lines.append('| ' + ' | '.join(headers) + ' |')
        markdown_lines.append('| ' + ' | '.join(['---'] * cols) + ' |')

        # 表格内容
        body_cells = cell_contents[cols:]
        for i in range(0, len(body_cells), cols):
            row = body_cells[i:i+cols]
            # 确保行有足够的列
            while len(row) < cols:
                row.append('')
            markdown_lines.append('| ' + ' | '.join(row) + ' |')

        return '\n' + '\n'.join(markdown_lines) + '\n\n'

    def _parse_embed_block(self, block):
        """解析嵌入块"""
        embed_type = block.get('embedType', '')
        embed_data = block.get('embedData', {})

        if embed_type == 'image':
            src = embed_data.get('src', '')
            return f"\n![图片]({src})\n\n"
        elif embed_type == 'hr':
            return "\n---\n\n"
        elif embed_type == 'toc':
            return "\n[TOC]\n\n"
        elif embed_type == 'office':
            file_name = embed_data.get('fileName', '附件')
            src = embed_data.get('src', '')
            return f"\n[{file_name}](wiz-collab-attachment://{src})\n\n"
        else:
            return f"\n<!-- 嵌入内容: {embed_type} -->\n\n"

    def _parse_text_array(self, text_array):
        """解析文本数组"""
        if not text_array:
            return ''

        result_parts = []
        for text_obj in text_array:
            text_part = self._parse_text_object(text_obj)
            result_parts.append(text_part)

        return ''.join(result_parts)

    def _parse_text_object(self, text_obj):
        """解析单个文本对象"""
        insert_text = text_obj.get('insert', '')
        attributes = text_obj.get('attributes', {})

        if not attributes:
            return insert_text

        # 处理各种文本样式和链接
        if attributes.get('type') == 'wiki-link':
            name = attributes.get('name', '')
            # 移除.md后缀
            if name.endswith('.md'):
                name = name[:-3]
            return f'[[{name}]]'

        elif attributes.get('type') == 'math':
            tex = attributes.get('tex', '')
            return f'${tex.strip()}$'

        elif attributes.get('link'):
            link_url = attributes.get('link')
            return f'[{insert_text}]({link_url})'

        elif attributes.get('style-bold'):
            return f'**{insert_text}**'

        elif attributes.get('style-italic'):
            return f'*{insert_text}*'

        elif attributes.get('style-code'):
            return f'`{insert_text}`'

        elif attributes.get('style-strikethrough'):
            return f'~~{insert_text}~~'

        else:
            # 忽略其他样式，直接返回文本
            return insert_text

    def download_resource(self, doc_guid, resource_info, save_path):
        """下载笔记资源文件"""
        try:
            # 使用资源信息中的URL直接下载
            url = resource_info.get('url')
            if not url:
                logging.error(f"资源文件缺少URL: {resource_info}")
                return False

            logging.debug(f"开始下载资源: {url}")
            response = requests.get(url, headers={'X-Wiz-Token': self.token})

            if response.status_code == 200:
                # 确保父目录存在
                save_path.parent.mkdir(parents=True, exist_ok=True)

                with open(save_path, 'wb') as f:
                    f.write(response.content)
                logging.info(f"成功下载资源: {save_path}")
                return True
            else:
                logging.error(f"资源下载失败 ({response.status_code}): {url}")
                return False

        except Exception as e:
            logging.error(f"下载资源失败: {e}")
            return False

    def get_note_attachments(self, doc_guid):
        """获取笔记的附件列表"""
        try:
            url = f"{self.kb_info['kbServer']}/ks/note/attachments/{self.kb_info['kbGuid']}/{doc_guid}"
            response = requests.get(
                url,
                headers={'X-Wiz-Token': self.token}
            )

            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")

            result = response.json()
            if result.get('returnCode') != 200:
                raise Exception(f"API错误: {result.get('returnMessage')}")

            attachments = result.get('result', [])
            logging.debug(f"笔记附件列表: {json.dumps(attachments, ensure_ascii=False, indent=2)}")
            return attachments

        except Exception as e:
            logging.error(f"获取笔记附件列表失败: {e}")
            return []

    def get_attachment_history(self, doc_guid, att_guid):
        """获取附件的历史版本列表"""
        try:
            url = (f"{self.kb_info['kbServer']}/ks/history/list/{self.kb_info['kbGuid']}/{doc_guid}"
                  f"?objType=attachment&objGuid={att_guid}")
            response = requests.get(
                url,
                headers={'X-Wiz-Token': self.token}
            )

            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")

            result = response.json()
            if result.get('returnCode') != 200:
                raise Exception(f"API错误: {result.get('returnMessage')}")

            history = result.get('history', [])
            logging.debug(f"附件历史版本: {json.dumps(history, ensure_ascii=False, indent=2)}")
            return history

        except Exception as e:
            logging.error(f"获取附件历史版本失败: {e}")
            return []

    def download_attachment(self, doc_guid, att_guid, save_path):
        """下载附件"""
        try:
            # 推荐用官方接口
            url = (f"{self.kb_info['kbServer']}/ks/attachment/download/"
                   f"{self.kb_info['kbGuid']}/{doc_guid}/{att_guid}")
            response = requests.get(
                url,
                headers={'X-Wiz-Token': self.token}
            )

            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")

            # 检查返回类型，避免写入json错误信息
            if response.headers.get('Content-Type', '').startswith('application/json'):
                logging.error(f"下载附件失败，返回内容: {response.text}")
                return False

            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(response.content)

            logging.info(f"成功下载附件: {save_path}")
            return True

        except Exception as e:
            logging.error(f"下载附件失败: {e}")
            return False

    def get_all_tags(self):
        """获取所有标签，返回tagId到标签名的映射字典"""
        try:
            url = f"{self.kb_info['kbServer']}/ks/tag/all/{self.kb_info['kbGuid']}"
            response = requests.get(url, headers={'X-Wiz-Token': self.token})
            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")
            result = response.json()
            if result.get('returnCode') != 200:
                raise Exception(f"API错误: {result.get('returnMessage')}")
            tags = result.get('result', [])
            tag_map = {tag['tagGuid']: tag['name'] for tag in tags}
            return tag_map
        except Exception as e:
            logging.error(f"获取标签列表失败: {e}")
            return {}

    def export_notes(self, folder, export_dir='wiznotes', max_notes=1000, resume=True):
        """导出某文件夹下所有笔记，支持断点续传

        Args:
            folder: 文件夹路径
            export_dir: 导出目录
            max_notes: 最大获取笔记数量
            resume: 是否启用断点续传
        """
        try:
            # 创建导出目录
            export_path = Path(export_dir)
            export_path.mkdir(parents=True, exist_ok=True)

            # 修改文件夹路径处理逻辑
            folder_parts = folder.strip('/').split('/')
            current_path = export_path
            for part in folder_parts:
                # 处理文件夹名中的特殊字符
                safe_part = self._get_valid_filename(Path(part))
                current_path = current_path / safe_part
                current_path.mkdir(parents=True, exist_ok=True)

            # 检查断点续传文件
            checkpoint_file = current_path / '.export_checkpoint.json'
            exported_guids = set()

            if resume and checkpoint_file.exists():
                try:
                    with open(checkpoint_file, 'r', encoding='utf-8') as f:
                        checkpoint_data = json.load(f)
                        exported_guids = set(checkpoint_data.get('exported_guids', []))
                    logging.info(f"从断点恢复，已导出 {len(exported_guids)} 篇笔记")
                except Exception as e:
                    logging.warning(f"读取断点文件失败: {e}")

            # 获取所有标签映射
            tag_map = self.get_all_tags()

            # 获取文件夹下所有笔记
            note_list = self.get_note_list(folder, max_notes=max_notes)
            total_notes = len(note_list)
            exported_count = 0

            # 使用tqdm显示进度
            from tqdm import tqdm
            for note in tqdm(note_list, desc="导出笔记", unit="篇"):
                try:
                    doc_guid = note['docGuid']
                    note_title = note.get('title', 'Untitled')

                    # 检查是否已导出
                    if doc_guid in exported_guids:
                        logging.debug(f"跳过已导出的笔记: 《{note_title}》")
                        exported_count += 1
                        continue

                    logging.info(f"\n开始下载笔记:《{note_title}》")
                    note_content = self.download_note(doc_guid)

                    # 创建资源目录（同时用于保存资源文件和附件）
                    safe_title = self._get_valid_filename(Path(note_title))
                    if safe_title.lower().endswith('.md'):
                        safe_title = safe_title[:-3]  # 去掉 .md 后缀
                    note_assets_dir = current_path / f"{safe_title}_assets"

                    # 处理HTML内容
                    html_content = note_content['html']
                    note_type = note_content.get('type', 'document')

                    # 处理资源文件
                    resources = note_content.get('resources', [])
                    if resources:
                        note_assets_dir.mkdir(exist_ok=True)

                        for resource in resources:
                            resource_name = resource.get('name')
                            if not resource_name:
                                continue

                            resource_path = note_assets_dir / resource_name
                            if self.download_resource(doc_guid, resource, resource_path):
                                # 替换HTML中的资源链接为相对路径
                                old_url = f"index_files/{resource_name}"
                                new_path = f'{note_assets_dir.name}/{resource_name}'
                                html_content = html_content.replace(old_url, new_path)

                    # 处理附件
                    attachments = self.get_note_attachments(doc_guid)
                    if attachments:
                        note_assets_dir.mkdir(exist_ok=True)

                        for attachment in attachments:
                            att_name = attachment.get('name')
                            att_guid = attachment.get('attGuid')
                            if not att_name or not att_guid:
                                continue

                            # 下载附件到assets目录
                            att_path = note_assets_dir / att_name
                            if self.download_attachment(doc_guid, att_guid, att_path):
                                logging.info(f"成功下载附件: {att_name}")

                                # 在笔记中添加附件链接
                                att_link = f'<p>附件: <a href="{note_assets_dir.name}/{att_name}">{att_name}</a></p>'
                                html_content = html_content.replace('</body>', f'{att_link}</body>')

                    # 保存笔记内容
                    note_path = current_path / safe_title
                    if note_type == 'collaboration' or note_title.lower().endswith('.md'):
                        note_path = note_path.with_suffix('.md')
                        # 对于协作笔记，内容已经是Markdown格式
                        if note_type == 'collaboration':
                            # print(f"协作笔记: {note_title}:{html_content}")
                            content = html_content
                        else:
                            # 提取<body>标签内的内容
                            body_match = re.search(r'<body[^>]*>([\s\S]*?)</body>', html_content, re.IGNORECASE)
                            if body_match:
                                html_content = body_match.group(1)
                            # 清除所有html标签
                            html_content = re.sub(r'<[^>]+>', '', html_content)
                            # 替换&nbsp;为普通空格，&gt;为>
                            html_content = html_content.replace('&nbsp;', ' ').replace('&gt;', '>')
                            # 去除首尾空白
                            content = html_content.strip()
                    else:
                        note_path = note_path.with_suffix('.html')
                        content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{safe_title}</title>
</head>
<body>
{html_content}
</body>
</html>"""

                    with open(note_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    # 额外保存md文件，保留格式
                    md_path = note_path.with_suffix('.md')
                    if note_type != 'collaboration':  # 协作笔记已经保存为md，不需要再次转换
                        body_match = re.search(r'<body[^>]*>([\s\S]*?)</body>', html_content, re.IGNORECASE)
                        md_content = html_content
                        if body_match:
                            md_content = body_match.group(1)
                        # 用markdownify转换，保留格式
                        md_content = markdownify.markdownify(md_content, heading_style="ATX")
                        # 添加元信息作为YAML front matter
                        note_info = note_content.get('info', {})
                        def parse_timestamp(ts):
                            try:
                                ts = int(ts)
                                if ts > 1e12:  # 毫秒级
                                    ts = ts // 1000
                                return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                            except Exception:
                                return ts
                        front_matter = []
                        front_matter.append("---")
                        front_matter.append(f"title: {note_info.get('title', '')}")
                        front_matter.append(f"docGuid: {note_info.get('docGuid', '')}")
                        front_matter.append(f"category: {note_info.get('category', '')}")
                        front_matter.append(f"url: {note_info.get('url', '')}")
                        front_matter.append(f"author: {note_info.get('author', '')}")
                        front_matter.append(f"keywords: {note_info.get('keywords', '')}")
                        created = note_info.get('created', '')
                        modified = note_info.get('modified', '')
                        accessed = note_info.get('accessed', '')
                        front_matter.append(f"created: {parse_timestamp(created) if created else ''}")
                        front_matter.append(f"modified: {parse_timestamp(modified) if modified else ''}")
                        front_matter.append(f"accessed: {parse_timestamp(accessed) if accessed else ''}")
                        tags = note_info.get('tags', '')
                        tag_names = []
                        if tags:
                            tag_ids = tags.split('*') if isinstance(tags, str) else tags
                            for tag_id in tag_ids:
                                tag_name = tag_map.get(tag_id, tag_id)
                                tag_names.append(tag_name)
                            front_matter.append(f"tags: [{', '.join(tag_names)}]")
                        else:
                            front_matter.append("tags: []")
                        resources = note_info.get('resources', [])
                        if resources:
                            if isinstance(resources, list):
                                front_matter.append(f"resources: [{', '.join([str(r) for r in resources])}]")
                            else:
                                front_matter.append(f"resources: {resources}")
                        else:
                            front_matter.append("resources: []")
                        front_matter.append(f"abstract: {note_info.get('abstract', '')}")
                        front_matter.append(f"version: {note_info.get('version', '')}")
                        front_matter.append(f"readCount: {note_info.get('readCount', 0)}")
                        front_matter.append(f"attachmentCount: {note_info.get('attachmentCount', 0)}")
                        front_matter.append("---")
                        # 组合front matter和内容
                        md_content = "\n".join(front_matter) + "\n\n" + md_content
                        with open(md_path, 'w', encoding='utf-8') as f:
                            f.write(md_content)

                    # 更新导出状态
                    exported_guids.add(doc_guid)
                    exported_count += 1
                    logging.info(f"导出笔记成功: 《{note_title}》")

                    # 每导出10篇笔记保存一次断点
                    if exported_count % 10 == 0:
                        self._save_checkpoint(checkpoint_file, exported_guids)

                    # 添加延时避免请求过快
                    time.sleep(0.5)

                except Exception as e:
                    logging.error(f"导出笔记 《{note_title}》 失败: {e}")
                    continue

            # 导出完成后保存最终断点
            self._save_checkpoint(checkpoint_file, exported_guids)

            logging.info(f"导出完成，共导出 {exported_count}/{total_notes} 篇笔记")

        except Exception as e:
            logging.error(f"导出笔记失败: {e}")
            raise

    def _save_checkpoint(self, checkpoint_file, exported_guids):
        """保存断点信息"""
        try:
            checkpoint_data = {
                'exported_guids': list(exported_guids),
                'timestamp': datetime.now().isoformat()
            }
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"保存断点失败: {e}")

    def _get_valid_filename(self, path):
        """确保文件名合法，仅替换 Windows 非法字符

        Args:
            path: 字符串或Path对象，包含文件名或文件夹名
        Returns:
            返回处理后的文件名或文件夹名字符串
        """
        # 如果输入是字符串，先转换为Path对象
        if isinstance(path, str):
            path = Path(path)

        # Windows 文件名不能包含以下字符: \ / : * ? " < > |
        invalid_chars = r'\/:*?"<>|'
        filename = str(path.name)
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        # 处理特殊情况
        filename = filename.strip()
        if not filename:  # 如果处理后为空
            filename = '_'
        elif len(filename) > 200:  # 如果文件名过长
            base, ext = os.path.splitext(filename)
            filename = base[:196] + '...' + ext  # 保留文件扩展名

        return filename

def setup_logging(export_dir='wiznotes'):
    """配置日志输出"""
    # 创建logs目录
    log_dir = Path(export_dir) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    # 生成日志文件名，包含时间戳
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'wiznotes_export_{timestamp}.log'

    # 清除现有的处理器
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 配置日志处理器
    # 文件处理器 - 记录DEBUG及以上级别的日志
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # 控制台处理器 - 只记录INFO及以上级别的日志，使用简化的格式
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')  # 简化的格式
    console_handler.setFormatter(console_formatter)

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 使用控制台格式打印日志文件位置
    print(f'日志文件保存在: {log_file}')
    return log_file

def list_folders_and_notes(client, target_folder=None, max_notes=1000):
    """列出文件夹和笔记内容

    Args:
        client: WizNoteClient实例
        target_folder: 指定要查询的文件夹路径，如果为None则列出所有文件夹信息（不获取笔记）
        max_notes: 最大获取笔记数量
    """
    try:
        # 如果指定了目标文件夹，则获取该文件夹下的笔记
        if target_folder:
            logging.info(f"\n开始获取文件夹 {target_folder} 的笔记")
            note_list = client.get_note_list(target_folder, max_notes=max_notes)
            logging.info(f"共获取到 {len(note_list)} 篇笔记:")
            for note in note_list:
                print(f"- {note.get('title', 'Untitled')}")
            return note_list

        else:        # 获取所有文件夹
            folders = client.get_folders()
            logging.info("获取到以下文件夹:")
            for folder in folders:
                print(folder)


        return None
    except Exception as e:
        logging.error(f"列出文件夹和笔记失败: {e}")
        raise


if __name__ == '__main__':
    config_path = Path.cwd().parent / "account" / "web_accounts.json"
    export_dir = Path.cwd() / "wiznotes"
    max_notes = 1000  # 文件夹下所有笔记数量，为知笔记API限制的单次获取最大值为1000，超过1000但少于2000需要分两次获取

    # notes_folder = r"/My Drafts/"
    notes_folder = r"/导出测试/"

    try:
        # 设置日志
        log_file = setup_logging(export_dir)
        client = WizNoteClient(config_path)
        client.login()

        # list_folders_and_notes(client)    # 列出所有文件夹
        note_list = list_folders_and_notes(client, notes_folder, max_notes)  # 列出指定文件夹下的笔记

        # 下载单篇笔记
        # if note_list:
        #     first_note = note_list[0]
        #     logging.info(f"测试下载笔记: {first_note['title']}")
        #     note_content = client.download_note(first_note['docGuid'])
        #     print("下载成功，内容预览:")
        #     print(note_content['html'][:200] + "...")  # 只显示前200个字符

        # 批量导出笔记（启用断点续传）
        client.export_notes(
            folder=notes_folder,
            export_dir=export_dir,
            max_notes=max_notes,
            resume=True
        )

    except KeyboardInterrupt:
        logging.info("程序被用户中断")
        sys.exit(0)
    except Exception as e:
        logging.error(f"程序执行失败: {e}")