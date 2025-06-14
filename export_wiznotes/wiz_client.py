"""
为知笔记客户端核心类
包含登录、获取文件夹、获取笔记列表、下载笔记等基础API操作
"""

import json
import requests
import logging
from pathlib import Path


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
                    try:
                        from .collaboration_parser import CollaborationParser
                    except ImportError:
                        from collaboration_parser import CollaborationParser

                    parser = CollaborationParser(self.kb_info)
                    collaboration_content = parser.get_collaboration_content(editor_token, doc_guid)

                    # 解析协作笔记内容为Markdown
                    markdown_content = parser.parse_collaboration_content(collaboration_content)

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