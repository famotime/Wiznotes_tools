"""
从为知笔记导出笔记：
1. 从json配置文件获取帐号密码并登录为知笔记
2. 获取笔记文件夹列表
3. 获取指定文件夹笔记列表
4. 导出笔记为md文件
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

    def get_notes(self, folder, count=50, max_notes=1000):
        """获取指定文件夹下的笔记列表

        Args:
            folder: 文件夹路径
            count: 每页笔记数量
            max_notes: 最大获取笔记数量，防止超出API限制
        """
        try:
            notes = []
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

                notes.extend(sub_notes)
                logging.info(f"已获取 {folder} 文件夹下 {len(notes)} 篇笔记")

                if len(sub_notes) < count:  # 如果返回数量小于请求数量，说明已经是最后一页
                    break

                start += count

            return notes

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

            return note_content

        except Exception as e:
            logging.error(f"下载笔记失败: {e}")
            raise

    def export_notes(self, export_dir='notes'):
        """导出所有笔记"""
        try:
            # 创建导出目录
            export_path = Path(export_dir)
            export_path.mkdir(parents=True, exist_ok=True)

            # 获取所有文件夹
            folders = self.get_folders()

            for folder in folders:
                # 创建文件夹对应目录
                folder_path = export_path / folder.strip('/')
                folder_path.mkdir(parents=True, exist_ok=True)

                # 获取文件夹下所有笔记
                notes = self.get_notes(folder)

                # 下载并保存笔记
                for note in notes:
                    try:
                        note_title = note.get('title', 'Untitled')
                        logging.info(f"开始下载笔记: {note_title}")

                        note_content = self.download_note(note['docGuid'])
                        note_path = folder_path / f"{note_title}.md"

                        # 确保文件名合法
                        note_path = self._get_valid_filename(note_path)

                        with open(note_path, 'w', encoding='utf-8') as f:
                            f.write(note_content['html'])

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

    try:
        client = WizNoteClient(config_path)
        client.login()

        # 获取文件夹列表
        folders = client.get_folders()
        logging.info("获取到以下文件夹:")
        for folder in folders:
            print(folder)

        # 获取指定文件夹的笔记列表
        test_folder = "/兴趣爱好/读书观影/书单/"
        logging.info(f"开始获取文件夹 {test_folder} 的笔记")
        notes = client.get_notes(test_folder, count=20, max_notes=100)

        logging.info(f"共获取到 {len(notes)} 篇笔记:")
        for note in notes:
            print(f"- {note.get('title', 'Untitled')}")

        # 测试下载单篇笔记
        if notes:
            first_note = notes[0]
            logging.info(f"测试下载笔记: {first_note['title']}")
            note_content = client.download_note(first_note['docGuid'])
            print("下载成功，内容预览:")
            print(note_content['html'][:200] + "...")  # 只显示前200个字符

    except Exception as e:
        logging.error(f"程序执行失败: {e}")