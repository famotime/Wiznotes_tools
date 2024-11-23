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

    def get_note_list(self, folder, count=20, max_notes=1000):
        """获取指定文件夹下的笔记列表

        Args:
            folder: 文件夹路径
            count: 每页笔记数量
            max_notes: 最大获取笔记数量，防止超出API限制
        """
        try:
            note_list = []
            start = 0

            while True:
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

    def export_notes(self, folder, export_dir='wiznotes', max_notes=1000):
        """导出某文件夹下所有笔记"""
        try:
            # 创建导出目录
            export_path = Path(export_dir)
            export_path.mkdir(parents=True, exist_ok=True)

            # 创建文件夹对应目录
            folder_path = export_path / folder.strip('/')
            folder_path.mkdir(parents=True, exist_ok=True)

            # 获取文件夹下所有笔记
            note_list = self.get_note_list(folder, max_notes=max_notes)

            # 下载并保存笔记
            for note in note_list:
                try:
                    note_title = note.get('title', 'Untitled')
                    logging.info(f"开始下载笔记: {note_title}")

                    note_content = self.download_note(note['docGuid'])

                    # 判断笔记类型
                    is_markdown = (
                        note_title.lower().endswith('.md') or  # 标题以.md结尾
                        note_content.get('type') == 'markdown' or  # API返回的类型是markdown
                        '```' in note_content['html'] or  # 内容包含markdown代码块
                        '<body' not in note_content['html']  # 内容不包含body标签
                    )

                    # 根据类型设置文件扩展名和内容
                    if is_markdown:
                        ext = '.md'
                        content = note_content['html']
                    else:
                        ext = '.html'
                        content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{note_title}</title>
</head>
<body>
{note_content['html']}
</body>
</html>"""

                    # 设置文件路径
                    note_path = folder_path / f"{note_title}{ext}"
                    if note_title.lower().endswith(('.md', '.html')):
                        note_path = folder_path / note_title

                    # 确保文件名合法
                    note_path = self._get_valid_filename(note_path)

                    # 保存文件
                    with open(note_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    logging.info(f"导出笔记成功: {note_path}")

                except Exception as e:
                    logging.error(f"导出笔记 {note_title} 失败: {e}")
                    continue  # 继续处理下一篇笔记

        except Exception as e:
            logging.error(f"导出笔记失败: {e}")
            raise

    def _get_valid_filename(self, path):
        """确保文件名合法"""
        # 替换不允许的字符
        filename = path.name
        valid_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.'))
        return path.parent / valid_filename


if __name__ == '__main__':
    config_path = Path.cwd().parent / "account" / "web_accounts.json"
    export_dir = Path.cwd() / "wiznotes"
    max_notes = 20  # 最大获取笔记数量，20的倍数

    try:
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
        note_list = client.get_note_list(test_folder, max_notes=max_notes)
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

        # 导出某文件夹下所有笔记
        client.export_notes(test_folder, export_dir, max_notes=max_notes)

    except Exception as e:
        logging.error(f"程序执行失败: {e}")