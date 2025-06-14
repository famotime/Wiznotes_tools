"""
协作笔记解析模块
包含WebSocket通信和协作笔记内容解析功能
"""

import json
import logging
import websocket


class CollaborationParser:
    def __init__(self, kb_info):
        self.kb_info = kb_info

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