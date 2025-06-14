"""
从为知笔记读取信息，导出单篇或批量导出笔记

功能：
1. 登录为知笔记Web版
2. 获取指定文件夹下的笔记列表
3. 下载笔记内容并根据内容类型导出为markdown或html格式
4. 支持断点续传，避免重复下载
5. 自动处理文件名中的非法字符

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
1. 为知笔记API限制单次最多获取1000篇笔记；
2. 超过1000篇的文件夹会自动进行两次查询；
3. 导出过程支持断点续传，可以随时中断后继续；
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
                'kbGuid': result['kbGuid']
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

            # 直接从result中获取所需信息
            note_info = result.get('info', {})
            html_content = result.get('html', '')
            resources = result.get('resources', [])

            if resources:
                logging.info(f"笔记包含 {len(resources)} 个资源文件")
                for resource in resources:
                    logging.debug(f"资源文件: {resource.get('name')} ({resource.get('size')} bytes)")

            return {
                'info': note_info,
                'html': html_content,
                'resources': resources
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
                        logging.debug(f"跳过已导出的笔记: {note_title}")
                        exported_count += 1
                        continue

                    logging.info(f"\n开始下载笔记: {note_title}")
                    note_content = self.download_note(doc_guid)

                    # 创建资源目录（同时用于保存资源文件和附件）
                    safe_title = self._get_valid_filename(Path(note_title))
                    if safe_title.lower().endswith('.md'):
                        safe_title = safe_title[:-3]  # 去掉 .md 后缀
                    note_assets_dir = current_path / f"{safe_title}_assets"

                    # 处理HTML内容
                    html_content = note_content['html']

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
                    if note_title.lower().endswith('.md'):
                        note_path = note_path.with_suffix('.md')
                        # 在笔记内容开头删除冗余文本
                        redundant_header = '''<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <head></head>
  </head>
  <body>
    <pre>'''
                        if redundant_header in html_content:
                            html_content = html_content.replace(redundant_header, '')

                        redundant_footer = '''</pre>
  </body>
</html>'''
                        if redundant_footer in html_content:
                            html_content = html_content.replace(redundant_footer, '')
                    else:
                        note_path = note_path.with_suffix('.html')

                    with open(note_path, 'w', encoding='utf-8') as f:
                        if note_title.lower().endswith('.md'):
                            f.write(html_content)
                        else:
                            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{safe_title}</title>
</head>
<body>
{html_content}
</body>
</html>""")

                    # 更新导出状态
                    exported_guids.add(doc_guid)
                    exported_count += 1
                    logging.info(f"导出笔记成功: {note_path.name}")

                    # 每导出10篇笔记保存一次断点
                    if exported_count % 10 == 0:
                        self._save_checkpoint(checkpoint_file, exported_guids)

                    # 添加延时避免请求过快
                    time.sleep(0.5)

                except Exception as e:
                    logging.error(f"导出笔记 {note_title} 失败: {e}")
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