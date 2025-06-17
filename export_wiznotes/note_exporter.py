"""
笔记导出模块
包含笔记导出、文件处理、断点续传等功能
"""

import json
import logging
import time
import re
import requests
from pathlib import Path
from datetime import datetime
import markdownify
from tqdm import tqdm

# 导入处理超过1000条笔记的函数
try:
    from .get_folders_and_notes_list import get_all_notes_in_folder
except ImportError:
    from get_folders_and_notes_list import get_all_notes_in_folder


class NoteExporter:
    def __init__(self, client):
        self.client = client

    def export_notes(self, folder, export_dir='export_wiznotes/output', max_notes=1000, resume=True, reexport_dot_files=False):
        """导出某文件夹下所有笔记，支持断点续传

        Args:
            folder: 文件夹路径
            export_dir: 导出目录
            max_notes: 最大获取笔记数量
            resume: 是否启用断点续传
            reexport_dot_files: 是否强制重新导出文件名中包含"."的笔记（用于修复之前的导出问题）
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
            tag_map = self.client.get_all_tags()

            # 获取文件夹下所有笔记（自动处理超过1000条笔记的情况）
            logging.info(f"开始获取文件夹 {folder} 下的所有笔记...")
            note_list = get_all_notes_in_folder(self.client, folder)
            total_notes = len(note_list)
            exported_count = 0
            logging.info(f"共获取到 {total_notes} 篇笔记")

            # 使用tqdm显示进度
            for note in tqdm(note_list, desc="导出笔记", unit="篇"):
                try:
                    doc_guid = note['docGuid']
                    note_title = note.get('title', 'Untitled')

                    # 检查是否已导出
                    skip_export = False
                    if doc_guid in exported_guids:
                        # 如果启用了重新导出包含"."的文件名，且文件名包含"."，则不跳过
                        if reexport_dot_files and '.' in note_title:
                            # 检查"."是否为真正的文件扩展名
                            if note_title.lower().endswith(('.md', '.txt', '.html', '.htm')):
                                # 如果以常见扩展名结尾，跳过（已经是真正的扩展名）
                                skip_export = True
                            else:
                                # 包含"."但不是真正的扩展名，强制重新导出
                                logging.info(f"强制重新导出包含'.'的笔记: 《{note_title}》")
                                skip_export = False

                                # 清理可能存在的旧的截断文件
                                self._cleanup_old_truncated_files(current_path, note_title)
                        else:
                            skip_export = True

                    if skip_export:
                        logging.debug(f"跳过已导出的笔记: 《{note_title}》")
                        exported_count += 1
                        continue

                    logging.info(f"\n开始下载笔记:《{note_title}》")
                    note_content = self.client.download_note(doc_guid)

                    # 创建资源目录（同时用于保存资源文件和附件）
                    safe_title = self._get_valid_filename(note_title)
                    if safe_title.lower().endswith('.md'):
                        safe_title = safe_title[:-3]  # 去掉 .md 后缀
                    note_assets_dir = current_path / f"{safe_title}_assets"

                    # 处理HTML内容
                    html_content = note_content['html']
                    note_type = note_content.get('type', 'document')

                    # 根据笔记类型处理资源
                    if note_type == 'collaboration':
                        # 协作笔记的资源处理
                        html_content = self._process_collaboration_resources(doc_guid, html_content, note_assets_dir)
                    else:
                        # 普通笔记的资源处理
                        # 处理资源文件
                        resources = note_content.get('resources', [])
                        if resources:
                            note_assets_dir.mkdir(exist_ok=True)

                            for resource in resources:
                                resource_name = resource.get('name')
                                if not resource_name:
                                    continue

                                resource_path = note_assets_dir / resource_name
                                if self.client.download_resource(doc_guid, resource, resource_path):
                                    # 替换HTML中的资源链接为相对路径
                                    old_url = f"index_files/{resource_name}"
                                    new_path = f'{note_assets_dir.name}/{resource_name}'
                                    html_content = html_content.replace(old_url, new_path)

                        # 处理附件
                        attachments = self.client.get_note_attachments(doc_guid)
                        if attachments:
                            note_assets_dir.mkdir(exist_ok=True)

                            for attachment in attachments:
                                att_name = attachment.get('name')
                                att_guid = attachment.get('attGuid')
                                if not att_name or not att_guid:
                                    continue

                                # 下载附件到assets目录
                                att_path = note_assets_dir / att_name
                                if self.client.download_attachment(doc_guid, att_guid, att_path):
                                    # logging.info(f"成功下载附件: {att_name}")

                                    # 在笔记中添加附件链接
                                    att_link = f'<p>附件: <a href="{note_assets_dir.name}/{att_name}">{att_name}</a></p>'
                                    html_content = html_content.replace('</body>', f'{att_link}</body>')

                    # 保存笔记内容
                    note_path = current_path / safe_title
                    if note_type == 'collaboration' or note_title.lower().endswith('.md'):
                        # 修复：避免with_suffix在点号处截断文件名，直接拼接扩展名
                        note_path = current_path / f"{safe_title}.md"
                        # 对于协作笔记，内容已经是Markdown格式
                        if note_type == 'collaboration':
                            # 为协作笔记添加front matter
                            note_info = note_content.get('info', {})
                            # 清理可能的错误代码块包装
                            html_content = self._clean_markdown_wrapping(html_content)
                            content = self._add_front_matter(html_content, note_info, tag_map)
                        else:
                            # 提取<body>标签内的内容
                            body_match = re.search(r'<body[^>]*>([\s\S]*?)</body>', html_content, re.IGNORECASE)
                            if body_match:
                                html_content = body_match.group(1)
                            # 修复HTML转文本的换行符处理
                            content = self._fix_html_to_text_conversion(html_content)
                            # 清理可能的错误代码块包装
                            content = self._clean_markdown_wrapping(content)
                    else:
                        # 修复：避免with_suffix在点号处截断文件名，直接拼接扩展名
                        note_path = current_path / f"{safe_title}.html"
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
                    # 修复：避免with_suffix在点号处截断文件名，直接拼接扩展名
                    md_path = current_path / f"{safe_title}.md"
                    if note_type != 'collaboration':  # 协作笔记已经保存为md，不需要再次转换
                        # 对于lite/markdown类型的笔记，不需要markdownify处理，直接使用已处理的内容
                        if note_type == 'lite/markdown' or note_title.lower().endswith('.md'):
                            # lite/markdown类型的笔记已经在前面处理过了，只需要添加front matter
                            note_info = note_content.get('info', {})
                            md_content = self._add_front_matter(content, note_info, tag_map)
                        else:
                            # 对于普通HTML笔记，使用markdownify转换
                            body_match = re.search(r'<body[^>]*>([\s\S]*?)</body>', html_content, re.IGNORECASE)
                            md_content = html_content
                            if body_match:
                                md_content = body_match.group(1)
                            # 用markdownify转换，保留格式
                            md_content = markdownify.markdownify(md_content, heading_style="ATX")
                            # 修复markdownify转义产生的问题：去掉图片路径中的反斜杠转义
                            md_content = self._fix_markdown_escapes(md_content)
                            # 清理可能的错误代码块包装
                            md_content = self._clean_markdown_wrapping(md_content)
                            # 添加元信息作为YAML front matter
                            note_info = note_content.get('info', {})
                            md_content = self._add_front_matter(md_content, note_info, tag_map)

                        with open(md_path, 'w', encoding='utf-8') as f:
                            f.write(md_content)

                    # 更新导出状态
                    exported_guids.add(doc_guid)
                    exported_count += 1
                    logging.info(f"导出笔记成功: 《{note_title}》\n")

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

    def _add_front_matter(self, md_content, note_info, tag_map):
        """添加YAML front matter到Markdown内容"""
        # 确保md_content不为None
        if md_content is None:
            md_content = ""

        # 首先清理可能的错误代码块包装
        md_content = self._clean_markdown_wrapping(md_content)

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
        return "\n".join(front_matter) + "\n\n" + md_content

    def _process_collaboration_resources(self, doc_guid, markdown_content, note_assets_dir):
        """处理协作笔记的资源（图片和附件）"""
        # 处理图片链接 ![图片](filename.png)
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        images = re.findall(image_pattern, markdown_content)

        if images:
            note_assets_dir.mkdir(exist_ok=True)

            # 获取协作笔记token
            try:
                token = self._get_collaboration_token(doc_guid)
            except Exception as e:
                logging.error(f"获取协作笔记token失败: {e}")
                return markdown_content

            for alt_text, image_src in images:
                # 下载图片资源
                if self._download_collaboration_image(doc_guid, image_src, note_assets_dir, token):
                    # 替换图片链接为相对路径
                    old_link = f'![{alt_text}]({image_src})'
                    new_link = f'![{alt_text}]({note_assets_dir.name}/{image_src})'
                    markdown_content = markdown_content.replace(old_link, new_link)

        # 处理附件链接 [filename](wiz-collab-attachment://guid)
        attachment_pattern = r'\[([^\]]+)\]\(wiz-collab-attachment://([^)]+)\)'
        attachments = re.findall(attachment_pattern, markdown_content)

        if attachments:
            note_assets_dir.mkdir(exist_ok=True)

            # 获取协作笔记token（如果之前没有获取）
            try:
                if 'token' not in locals():
                    token = self._get_collaboration_token(doc_guid)
            except Exception as e:
                logging.error(f"获取协作笔记token失败: {e}")
                return markdown_content

            for att_name, att_guid in attachments:
                # 下载附件（使用相同的图片下载接口）
                if self._download_collaboration_image(doc_guid, att_guid, note_assets_dir, token, att_name):
                    logging.info(f"成功下载协作笔记附件: {att_name}")
                    # 替换附件链接为相对路径
                    old_link = f'[{att_name}](wiz-collab-attachment://{att_guid})'
                    new_link = f'[{att_name}]({note_assets_dir.name}/{att_name})'
                    markdown_content = markdown_content.replace(old_link, new_link)

        return markdown_content

    def _get_collaboration_token(self, doc_guid):
        """获取协作笔记token"""
        url = f"{self.client.kb_info['kbServer']}/ks/note/{self.client.kb_info['kbGuid']}/{doc_guid}/tokens"
        response = requests.post(url, headers={'X-Wiz-Token': self.client.token})

        if response.status_code != 200:
            raise Exception(f'获取协作笔记token失败: http状态码为:{response.status_code}')

        data = response.json()
        if data['returnCode'] != 200:
            raise Exception(f'获取协作笔记token失败: 为知响应报文为:{data}')

        return data['result']['editorToken']

    def _download_collaboration_image(self, doc_guid, resource_name, save_dir, editor_token, save_name=None):
        """下载协作笔记的图片资源"""
        try:
            # 使用正确的协作笔记资源下载接口
            url = f"{self.client.kb_info['kbServer']}/editor/{self.client.kb_info['kbGuid']}/{doc_guid}/resources/{resource_name}"

            # 使用特殊的cookie认证方式
            headers = {
                'cookie': f'x-live-editor-token={editor_token}',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }

            logging.debug(f"下载协作笔记资源: {url}")
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                # 使用提供的文件名或原始资源名
                filename = save_name if save_name else resource_name
                save_path = save_dir / filename
                save_path.parent.mkdir(parents=True, exist_ok=True)

                with open(save_path, 'wb') as f:
                    f.write(response.content)
                # logging.info(f"成功下载协作笔记资源: {filename}")
                return True
            else:
                logging.error(f"下载协作笔记资源失败 ({response.status_code}): {resource_name}")
                return False

        except Exception as e:
            logging.error(f"下载协作笔记资源失败: {e}")
            return False

    def _download_collaboration_resource(self, doc_guid, resource_name, save_dir):
        """下载协作笔记的资源文件（已弃用，使用_download_collaboration_image代替）"""
        # 这个方法保留是为了向后兼容，实际使用新的方法
        try:
            token = self._get_collaboration_token(doc_guid)
            return self._download_collaboration_image(doc_guid, resource_name, save_dir, token)
        except Exception as e:
            logging.error(f"下载协作笔记资源失败: {e}")
            return False

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

    def _fix_html_to_text_conversion(self, html_content):
        """修复HTML转文本时的换行符处理

        Args:
            html_content: HTML内容
        Returns:
            修复后的文本内容
        """
        # 确保输入不为None
        if html_content is None:
            return ""

        # 先处理HTML实体
        html_content = html_content.replace('&nbsp;', ' ').replace('&gt;', '>').replace('&lt;', '<').replace('&amp;', '&')

        # 将块级元素和换行元素替换为换行符
        block_elements = [
            'p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'ul', 'ol', 'li', 'blockquote', 'pre', 'hr'
        ]

        for element in block_elements:
            # 处理自闭合标签（如<br>、<hr>）
            html_content = re.sub(f'<{element}[^>]*/?>', '\n', html_content, flags=re.IGNORECASE)
            # 处理闭合标签（如</p>、</div>）
            html_content = re.sub(f'</{element}>', '\n', html_content, flags=re.IGNORECASE)

        # 清除剩余的HTML标签
        html_content = re.sub(r'<[^>]+>', '', html_content)

        # 清理多余的空行和空白
        # 将多个连续换行符替换为最多两个
        html_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', html_content)

        # 去除每行首尾的空白
        lines = html_content.split('\n')
        # lines = [line.strip() for line in lines]

        # 去除完全空白的行，但保留有意义的空行
        result_lines = []
        prev_empty = False
        for line in lines:
            if line:  # 非空行
                result_lines.append(line)
                prev_empty = False
            elif not prev_empty:  # 空行，但前一行不是空行
                result_lines.append('')
                prev_empty = True
            # 连续的空行只保留一个

        # 去除开头和结尾的空行
        while result_lines and result_lines[0] == '':
            result_lines.pop(0)
        while result_lines and result_lines[-1] == '':
            result_lines.pop()

        return '\n'.join(result_lines)

    def _fix_markdown_escapes(self, md_content):
        """修复markdownify转义产生的问题

        markdownify库会自动转义一些字符，但在某些情况下这是不必要的，
        比如图片路径中的下划线不需要转义

        Args:
            md_content: Markdown内容
        Returns:
            修复后的Markdown内容
        """
        # 确保输入不为None
        if md_content is None:
            return ""

        # 修复图片链接中的转义下划线
        # 匹配格式: ![alt_text](path\_with\_underscores.jpg)
        image_pattern = r'!\[([^\]]*)\]\(([^)]*)\\_([^)]*)\)'

        def fix_image_path(match):
            alt_text = match.group(1)
            path_before = match.group(2)
            path_after = match.group(3)
            # 将转义的下划线替换为普通下划线
            fixed_path = path_before + '_' + path_after
            return f'![{alt_text}]({fixed_path})'

        # 循环处理，因为一个路径中可能有多个转义下划线
        while re.search(image_pattern, md_content):
            md_content = re.sub(image_pattern, fix_image_path, md_content)

        # 修复链接中的转义下划线
        # 匹配格式: [link_text](url\_with\_underscores)
        link_pattern = r'\[([^\]]*)\]\(([^)]*)\\_([^)]*)\)'

        def fix_link_path(match):
            link_text = match.group(1)
            path_before = match.group(2)
            path_after = match.group(3)
            # 将转义的下划线替换为普通下划线
            fixed_path = path_before + '_' + path_after
            return f'[{link_text}]({fixed_path})'

        # 循环处理，因为一个路径中可能有多个转义下划线
        while re.search(link_pattern, md_content):
            md_content = re.sub(link_pattern, fix_link_path, md_content)

        return md_content

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
            # 保留原来的逻辑，使用splitext来分离真正的扩展名
            # 从后往前找最后一个点，确保是真正的文件扩展名
            if '.' in filename:
                last_dot_pos = filename.rfind('.')
                # 如果最后一个点后面的内容看起来像扩展名（短且为字母数字）
                potential_ext = filename[last_dot_pos:]
                if len(potential_ext) <= 10 and potential_ext[1:].replace('_', '').replace('-', '').isalnum():
                    # 保留真正的扩展名
                    base = filename[:last_dot_pos]
                    filename = base[:196] + '...' + potential_ext
                else:
                    # 没有真正的扩展名，直接截断
                    filename = filename[:197] + '...'
            else:
                # 没有扩展名，直接截断
                filename = filename[:197] + '...'

        return filename

    def _clean_markdown_wrapping(self, md_content):
        """清理错误的代码块包装

        有时协作笔记的内容会被错误地包装在```代码块中，
        这个方法会检测并移除外层的错误包装，但保留内容中正确的代码块

        Args:
            md_content: Markdown内容
        Returns:
            清理后的Markdown内容
        """
        # 确保输入不为None
        if md_content is None:
            return ""

        # 移除开头和结尾多余的空行
        content = md_content.strip()

        # 检查是否整个内容被包装在代码块中
        # 特征：开头是```（可能有语言标识），结尾是```
        if content.startswith('```') and content.endswith('```'):
            lines = content.split('\n')

            # 检查第一行是否是代码块开始标记
            first_line = lines[0].strip()
            if first_line == '```' or (first_line.startswith('```') and len(first_line) <= 20):
                # 检查最后一行是否是代码块结束标记
                last_line = lines[-1].strip()
                if last_line == '```':
                    # 移除第一行和最后一行
                    inner_content = '\n'.join(lines[1:-1])

                    # 验证移除后的内容是否合理（不应该是单纯的代码）
                    # 如果内容包含markdown标记（如标题#、列表-、链接[]等），则认为是被错误包装的
                    if (re.search(r'^#+\s', inner_content, re.MULTILINE) or  # 标题
                        re.search(r'^\s*[-*+]\s', inner_content, re.MULTILINE) or  # 列表
                        re.search(r'\[.*?\]\(.*?\)', inner_content) or  # 链接
                        re.search(r'!\[.*?\]\(.*?\)', inner_content)):  # 图片

                        logging.info("检测到错误的代码块包装，已清理")
                        return inner_content.strip()

        # 默认返回原内容
        return content

    def _extract_doc_guid_from_file(self, file_path):
        """从markdown文件的front matter中提取docGuid

        Args:
            file_path: 文件路径

        Returns:
            str: docGuid字符串，如果未找到则返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            # 查找docGuid行
            match = re.search(r'docGuid:\s*([a-f0-9\-]+)', content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
            return None
        except Exception as e:
            logging.debug(f"读取文件 {file_path} 时出错: {e}")
            return None

    def _cleanup_old_truncated_files(self, current_path, note_title):
        """清理可能存在的旧的截断文件

        只有当新文件和旧文件的docGuid一致时才删除旧文件，确保安全性

        Args:
            current_path: 当前导出路径
            note_title: 完整的笔记标题
        """
        try:
            if '.' not in note_title:
                return

            # 生成完整文件名和截断文件名
            first_dot_pos = note_title.find('.')
            if first_dot_pos <= 0:
                return

            truncated_title = note_title[:first_dot_pos]
            safe_full_title = self._get_valid_filename(note_title)
            safe_truncated_title = self._get_valid_filename(truncated_title)

            # 如果处理后的文件名相同，则无需处理
            if safe_full_title == safe_truncated_title:
                return

            # 准备完整文件名的文件路径
            full_md_file = current_path / f"{safe_full_title}.md"

            # 检查可能存在的截断文件
            truncated_files_to_check = [
                current_path / f"{safe_truncated_title}.md",
                current_path / f"{safe_truncated_title}.html",
            ]

            removed_files = []
            for truncated_file in truncated_files_to_check:
                if truncated_file.exists():
                    # 比较docGuid
                    full_guid = self._extract_doc_guid_from_file(full_md_file) if full_md_file.exists() else None
                    truncated_guid = self._extract_doc_guid_from_file(truncated_file)

                    if full_guid and truncated_guid and full_guid == truncated_guid:
                        try:
                            truncated_file.unlink()
                            removed_files.append(truncated_file.name)
                            logging.info(f"  删除重复的截断文件: {truncated_file.name} (docGuid: {truncated_guid})")
                        except Exception as e:
                            logging.warning(f"无法删除旧文件 {truncated_file}: {e}")
                    elif full_guid and truncated_guid and full_guid != truncated_guid:
                        logging.info(f"  保留不同笔记的文件: {truncated_file.name} (docGuid不匹配)")
                    else:
                        logging.debug(f"  无法比较docGuid，保留文件: {truncated_file.name}")

            if removed_files:
                logging.info(f"  已清理 {len(removed_files)} 个重复的截断文件")

        except Exception as e:
            logging.warning(f"清理旧截断文件时出错: {e}")