"""
从为知笔记读取信息，导出单篇或批量笔记

功能：
1. 登录为知笔记Web版
2. 获取指定文件夹下的笔记列表
3. 下载笔记内容并根据内容类型导出为markdown或html格式

使用方法：
1. 配置文件 web_accounts.json 格式如下：
{
    "username": "your_email@example.com",
    "password": "your_password"
}

2. 运行脚本：
python get_wiz_notes.py

参数说明：
- config_path: 配置文件路径，默认为 "../account/web_accounts.json"
- export_dir: 导出目录，默认为 "./wiznotes"
- max_notes: 每个文件夹最大获取笔记数量，默认为20
"""

import json
import requests
from pathlib import Path
import logging
import time
from datetime import datetime
import os
import sys

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

    def get_note_list(self, folder, count=100, max_notes=1000):
        """获取指定文件夹下的笔记列表

        Args:
            folder: 文件夹路径
            count: 每页笔记数量，默认100
            max_notes: 最大获取笔记数量，默认1000（API限制）
        """
        try:
            note_list = []
            start = 0

            while True:
                # API限制：start参数最大值为1000
                if start >= 1000:
                    logging.warning(f"已达到API限制（start最大值1000），停止获取更多笔记")
                    break

                # 检查是否达到最大获取数量
                if start >= max_notes:
                    logging.warning(f"已达到最大获取数量 {max_notes}，停止获取更多笔记")
                    break

                url = (f"{self.kb_info['kbServer']}/ks/note/list/category/{self.kb_info['kbGuid']}"
                      f"?start={start}&count={count}&category={folder}&orderBy=created")

                sub_notes = self._request('GET', url, token=self.token)
                if not sub_notes:  # 如果返回空列表，说明已经获取完所有笔记
                    break

                note_list.extend(sub_notes)
                logging.info(f"已获取 {folder} 文件夹下 {len(note_list)} 篇笔记")

                if len(sub_notes) < count:  # 如果返回数量小于请求数量，说明已经是最后一页
                    break

                start += count

            return note_list

        except Exception as e:
            logging.error(f"获取笔记列表失败: {e}")
            raise

    def download_note(self, doc_guid):
        """下载指定笔记内容"""
        try:
            url = (f"{self.kb_info['kbServer']}/ks/note/download/{self.kb_info['kbGuid']}/{doc_guid}"
                  "?downloadInfo=1&downloadData=1")
            response = requests.get(
                url,
                headers={'X-Wiz-Token': self.token}
            )

            # 检查响应状态码
            if response.status_code != 200:
                raise Exception(f"HTTP错误: {response.status_code}")

            result = response.json()
            if result.get('returnCode') != 200:
                raise Exception(f"API错误: {result.get('returnMessage')}")

            # 如果返回数据中没有 result 字段，直接使用整个响应内容
            note_content = result.get('result', result)

            # 检查必要的字段
            if 'html' not in note_content:
                logging.warning(f"笔记内容格式异常: {note_content}")
                # 尝试其他可能的字段名
                content = (note_content.get('html') or
                          note_content.get('content') or
                          note_content.get('data', ''))
                note_content = {'html': content}

            # 在笔记内容开头删除冗余文本
            html_content = note_content['html']
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

            note_content['html'] = html_content.strip()
            return note_content

        except Exception as e:
            logging.error(f"下载笔记失败: {e}")
            raise

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

                    logging.info(f"开始下载笔记: {note_title}")
                    note_content = self.download_note(doc_guid)

                    # 判断笔记类型
                    is_markdown = (
                        note_title.lower().endswith('.md') or
                        note_content.get('type') == 'markdown' or
                        '```' in note_content['html'] or
                        '<body' not in note_content['html']
                    )

                    # 设置文件扩展名和内容
                    ext = '.md' if is_markdown else '.html'

                    # 处理文件名（移除所有路径分隔符）
                    safe_title = note_title.replace('/', '_').replace('\\', '_')
                    if not safe_title.lower().endswith(('.md', '.html')):
                        safe_title = safe_title + ext

                    # 设置文件路径（直接保存在当前文件夹下）
                    note_path = current_path / self._get_valid_filename(safe_title)

                    # 保存文件
                    with open(note_path, 'w', encoding='utf-8') as f:
                        if is_markdown:
                            f.write(note_content['html'])
                        else:
                            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{safe_title}</title>
</head>
<body>
{note_content['html']}
</body>
</html>""")

                    # 更新断点信息
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

        # 仅替换 Windows 不允许的字符
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

def setup_logging(export_dir):
    """配置日志输出

    Args:
        export_dir: 导出目录路径，日志文件将保存在此目录下的 logs 子目录中
    """
    # 创建日志目录
    log_dir = Path(export_dir) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    # 生成日志文件名，包含时间戳
    log_file = log_dir / f'wiznotes_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'

    # 配置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 配置文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)

    # 配置控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info(f"日志文件保存在: {log_file}")
    return log_file

if __name__ == '__main__':
    config_path = Path.cwd().parent / "account" / "web_accounts.json"
    export_dir = Path.cwd() / "wiznotes"
    max_notes = 1000  # 为知笔记API限制的最大值为1000

    try:
        # 设置日志
        log_file = setup_logging(export_dir)

        client = WizNoteClient(config_path)
        client.login()

        # 获取文件夹列表
        # folders = client.get_folders()
        # logging.info("获取到以下文件夹:")
        # for folder in folders:
        #     print(folder)

        # 获取指定文件夹的笔记列表
        test_folder = "/兴趣爱好/读书观影/书单/"
        logging.info(f"开始获取文件夹 {test_folder} 的笔记")

        # note_list = client.get_note_list(test_folder, max_notes=max_notes)
        # logging.info(f"共获取到 {len(note_list)} 篇笔记:")
        # for note in note_list:
        #     print(f"- {note.get('title', 'Untitled')}")

        # 下载单篇笔记
        # if note_list:
        #     first_note = note_list[0]
        #     logging.info(f"测试下载笔记: {first_note['title']}")
        #     note_content = client.download_note(first_note['docGuid'])
        #     print("下载成功，内容预览:")
        #     print(note_content['html'][:200] + "...")  # 只显示前200个字符

        # 导出笔记（启用断点续传）
        client.export_notes(
            folder=test_folder,
            export_dir=export_dir,
            max_notes=max_notes,
            resume=True
        )

    except KeyboardInterrupt:
        logging.info("程序被用户中断")
        sys.exit(0)
    except Exception as e:
        logging.error(f"程序执行失败: {e}")