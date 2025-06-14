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


class NoteExporter:
    def __init__(self, client):
        self.client = client

    def export_notes(self, folder, export_dir='export_wiznotes/output', max_notes=1000, resume=True):
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
            tag_map = self.client.get_all_tags()

            # 获取文件夹下所有笔记
            note_list = self.client.get_note_list(folder, max_notes=max_notes)
            total_notes = len(note_list)
            exported_count = 0

            # 使用tqdm显示进度
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
                    note_content = self.client.download_note(doc_guid)

                    # 创建资源目录（同时用于保存资源文件和附件）
                    safe_title = self._get_valid_filename(Path(note_title))
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
                            # 为协作笔记添加front matter
                            note_info = note_content.get('info', {})
                            content = self._add_front_matter(html_content, note_info, tag_map)
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
                        md_content = self._add_front_matter(md_content, note_info, tag_map)
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

    def _add_front_matter(self, md_content, note_info, tag_map):
        """添加YAML front matter到Markdown内容"""
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
                logging.info(f"成功下载协作笔记资源: {filename}")
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
            import os
            base, ext = os.path.splitext(filename)
            filename = base[:196] + '...' + ext  # 保留文件扩展名

        return filename