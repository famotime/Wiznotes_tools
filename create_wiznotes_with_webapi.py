"""
将文件内容保存到为知笔记：
1. 将指定文件夹下的所有文件内容保存到为知笔记指定目录，文件名作为笔记标题；
2. 若有同名文件，则合并创建一个图文笔记，文本文件内容作为笔记内容，同名图片文件插入笔记末尾；
"""
import json
import aiohttp
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
import logging
import sys
import re

class WizNoteAPI:
    AS_URL = 'https://as.wiz.cn'

    def __init__(self, config_path: Path = Path('../account/web_accounts.json')):
        """初始化API客户端

        Args:
            config_path: 配置文件路径,默认为 '../account/web_accounts.json'
        """
        self.config = self._load_config(config_path)
        self.token = None
        self.kb_server = None
        self.kb_guid = None

    def _load_config(self, config_path: Path) -> dict:
        """加载配置文件

        Args:
            config_path: 配置文件路径

        Returns:
            配置信息字典

        Raises:
            Exception: 加载配置文件失败
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"加载配置文件失败: {e}")
            raise

    async def login(self) -> None:
        """登录为知笔记

        Raises:
            Exception: 登录失败
        """
        try:
            data = {
                'userId': self.config['wiz']['username'],
                'password': self.config['wiz']['password']
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.AS_URL}/as/user/login",
                                      json=data) as resp:
                    result = await resp.json()
                    if result['returnCode'] != 200:
                        raise Exception(f"API错误: {result['returnMessage']}")

                    self.token = result['result']['token']
                    self.kb_server = result['result']['kbServer']
                    self.kb_guid = result['result']['kbGuid']
                    logging.info("登录成功")

        except Exception as e:
            logging.error(f"登录失败: {e}")
            raise

    def _get_valid_folder_name(self, folder_name: str) -> str:
        """处理文件夹名称中的特殊字符

        Args:
            folder_name: 原始文件夹名称

        Returns:
            处理后的文件夹名称
        """
        # 为知笔记不允许文件夹名包含这些字符: /\?*?&%!'"
        invalid_chars = r'/\?*&%!\'"'
        result = folder_name
        for char in invalid_chars:
            result = result.replace(char, '_')
        return result.strip()

    async def create_folder(self, parent: str, folder: str) -> None:
        """创建文件夹

        Args:
            parent: 父文件夹路径，例如 "/"
            folder: 要创建的文件夹名称
        """
        try:
            # 处理文件夹名称中的特殊字符
            safe_folder = self._get_valid_folder_name(folder)

            headers = {"X-Wiz-Token": self.token}
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.kb_server}/ks/category/create/{self.kb_guid}",
                                      headers=headers,
                                      json={"parent": parent, "child": safe_folder}) as resp:
                    data = await resp.json()
                    if data["returnCode"] != 200:
                        raise Exception(f"创建文件夹失败: {data['returnMessage']}")
                    # logging.info(f"成功创建文件夹: {safe_folder}")
        except Exception as e:
            logging.error(f"创建文件夹失败: {e}")
            raise

    async def upload_image(self, doc_guid: str, image_path: Path) -> Dict:
        """上传图片"""
        try:
            headers = {"X-Wiz-Token": self.token}

            # 检查文件大小
            file_size = image_path.stat().st_size
            max_size = 50 * 1024 * 1024  # 50MB
            if file_size > max_size:
                raise Exception(f"图片文件过大: {file_size / 1024 / 1024:.1f}MB > 50MB")

            # 设置文件类型
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif'
            }
            content_type = mime_types.get(image_path.suffix.lower(), 'application/octet-stream')

            # 添加重试机制
            max_retries = 3
            retry_delay = 1

            for attempt in range(max_retries):
                try:
                    data = aiohttp.FormData()
                    data.add_field("kbGuid", self.kb_guid)
                    data.add_field("docGuid", doc_guid)
                    data.add_field("data",
                                 open(image_path, "rb"),
                                 filename=image_path.name,
                                 content_type=content_type)

                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{self.kb_server}/ks/resource/upload/{self.kb_guid}/{doc_guid}",
                            headers=headers,
                            data=data,
                            timeout=60  # 60秒超时
                        ) as resp:
                            if resp.status != 200:
                                raise Exception(f"HTTP错误: {resp.status}")

                            data = await resp.json()
                            if data["returnCode"] != 200:
                                raise Exception(f"API错误: {data['returnMessage']}")
                            return data["result"]

                except Exception as e:
                    if attempt < max_retries - 1:
                        logging.warning(f"上传图片失败(尝试 {attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    raise

        except Exception as e:
            logging.error(f"上传图片失败: {e}")
            raise

    def _get_content_type(self, file_path: Path) -> str:
        """根据文件扩展名获取MIME类型"""
        ext = file_path.suffix.lower()
        content_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif'
        }
        return content_types.get(ext, 'application/octet-stream')

    async def create_note(self, title: str, folder: str, html: str,
                         resources: Optional[List[str]] = None) -> Dict:
        """创建笔记"""
        try:
            headers = {"X-Wiz-Token": self.token}
            note = {
                "kbGuid": self.kb_guid,
                "title": title,
                "category": folder,
                "html": html
            }
            if resources:
                note["resources"] = resources

            # 增加重试次数和延迟时间
            max_retries = 1
            retry_delay = 1

            for attempt in range(max_retries):
                try:
                    async with aiohttp.ClientSession() as session:
                        # 添加超时设置
                        timeout = aiohttp.ClientTimeout(total=30)
                        async with session.post(
                            f"{self.kb_server}/ks/note/create/{self.kb_guid}",
                            headers=headers,
                            json=note,
                            timeout=timeout
                        ) as resp:
                            # 详细记录错误信息
                            if resp.status != 200:
                                error_text = await resp.text()
                                logging.error(f"服务器响应: {error_text}")

                                if resp.status == 500:
                                    if attempt < max_retries - 1:
                                        wait_time = retry_delay * (2 ** attempt)  # 指数退避
                                        logging.warning(f"创建笔记失败(尝试 {attempt + 1}/{max_retries}), "
                                                  f"将在 {wait_time} 秒后重试...")
                                        await asyncio.sleep(wait_time)
                                        continue

                                raise Exception(f"HTTP错误: {resp.status}, 响应: {error_text}")

                            data = await resp.json()
                            if data["returnCode"] != 200:
                                raise Exception(f"API错误: {data['returnMessage']}")

                            # logging.info(f"成功创建笔记: {title}")
                            return data["result"]

                except aiohttp.ClientError as e:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        logging.warning(f"网络错误(尝试 {attempt + 1}/{max_retries}): {e}, "
                                      f"将在 {wait_time} 秒后重试...")
                        await asyncio.sleep(wait_time)
                        continue
                    raise

        except Exception as e:
            logging.error(f"创建笔记失败: {e}")
            raise

    async def create_note_with_image(self, title: str, folder: str, image_paths: List[Path], text_content: Optional[str] = None) -> Dict:
        """创建图文笔记"""
        try:
            # 创建空笔记
            note = await self.create_note(
                title=title,
                folder=folder,
                html="<html><head></head><body><h1>正在处理图片，请稍候...</h1></body></html>"
            )

            doc_guid = note['docGuid']
            resources = []
            image_infos = []

            # 上传所有图片
            for idx, image_path in enumerate(image_paths, 1):
                logging.info(f"正在上传第 {idx}/{len(image_paths)} 张图片: {image_path.name}")
                image_info = await self.upload_image(doc_guid, image_path)
                resources.append(image_info['name'])
                image_infos.append(image_info)

            # 构建HTML内容
            text_html = ""
            if text_content:
                text_html = f"""
                <div class="text-content">
                    <pre>{text_content}</pre>
                </div>
                """

            images_html = ""
            for image_info in image_infos:
                images_html += f"""
                <div class="image-container">
                    <img src="index_files/{image_info['name']}" style="max-width:100%;height:auto;" />
                </div>
                """

            html_content = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <title>{title}</title>
            </head>
            <body>
                <h1>{title}</h1>
                {text_html}
                {images_html}
            </body>
            </html>
            """

            # 使用 PUT 请求更新笔记
            headers = {
                "X-Wiz-Token": self.token,
                "Content-Type": "application/json"
            }

            update_data = {
                "kbGuid": self.kb_guid,
                "docGuid": doc_guid,
                "html": html_content,
                "resources": resources
            }

            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.kb_server}/ks/note/save/{self.kb_guid}/{doc_guid}",
                    headers=headers,
                    json=update_data
                ) as resp:
                    if resp.status != 200:
                        raise Exception(f"HTTP错误: {resp.status}")

                    data = await resp.json()
                    if data["returnCode"] != 200:
                        raise Exception(f"API错误: {data['returnMessage']}")

                    logging.info(f"成功更新笔记: {title}\n")
                    return data["result"]

        except Exception as e:
            logging.error(f"创建图文笔记失败: {e}")
            raise

async def main(config_path, source_dir, target_folder):
    logging.basicConfig(level=logging.INFO,
                       format='%(asctime)s - %(levelname)s - %(message)s')

    def get_note_title(base_name: str, text_file: Optional[Path]) -> str:
        """获取笔记标题：文本文件第一行(最多25字符) + 文件名"""
        if text_file and text_file.exists():
            try:
                with open(text_file, 'r', encoding='utf-8') as f:
                    # first_line = f.readline().strip()
                    # if first_line:
                    #     # 取第一行的前25个字符
                    #     preview = first_line[:25]
                    #     return f"{preview} - {base_name}"
                    info = re.sub(r".*?【.{1,5}】\n?", '', f.read(), count=1)   # 删除第1个【xx】前内容
                    title = info.split('\n')[0][:25]  + '_' +  base_name  # 添加原文件名作为后缀
                    return title
            except Exception as e:
                logging.warning(f"读取文本文件失败: {e}")
        return base_name

    try:
        wiz = WizNoteAPI(config_path)
        await wiz.login()

        # 处理目标文件夹路径
        folder_parts = target_folder.strip('/').split('/')
        current_path = "/"
        for part in folder_parts:
            if part:
                await wiz.create_folder(current_path, part)
                current_path = f"{current_path}{part}/"

        # 按文件名（不含扩展名）分组收集文件
        files_by_name = {}
        source_path = Path(source_dir)
        for file_path in source_path.glob("*"):
            if file_path.is_file():
                base_name = file_path.stem
                if base_name not in files_by_name:
                    files_by_name[base_name] = {'images': [], 'text': None}

                if file_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif'}:
                    files_by_name[base_name]['images'].append(file_path)
                else:
                    files_by_name[base_name]['text'] = file_path

        # 处理每组文件
        for base_name, files in files_by_name.items():
            text_file = files['text']
            image_files = files['images']

            # 获取笔记标题
            note_title = get_note_title(base_name, text_file)

            if image_files:
                # 处理包含图片的笔记
                logging.info(f"处理图文笔记: {note_title}")
                text_content = None
                if text_file:
                    with open(text_file, 'r', encoding='utf-8') as f:
                        text_content = f.read()
                await wiz.create_note_with_image(note_title, target_folder, image_files, text_content)

            elif text_file:
                # 只有文本文件
                logging.info(f"处理纯文本笔记: {note_title}")
                with open(text_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                html_content = f"""
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>{note_title}</title>
                </head>
                <body>
                    <h1>{note_title}</h1>
                    <pre>{content}</pre>
                </body>
                </html>
                """

                await wiz.create_note(
                    title=note_title,
                    folder=target_folder,
                    html=html_content
                )

    except KeyboardInterrupt:
        logging.info("程序被用户中断")
        sys.exit(0)
    except Exception as e:
        logging.error(f"程序执行失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    config_path = Path(r"..\account\web_accounts.json")
    source_dir = Path(r"H:\个人图片及视频\手机截图\todo")  # 源文件目录
    target_folder = "/知识点滴/思考&写作/图卦笔记/"   # 为知笔记目标文件夹
    print(f"开始处理文件夹: {source_dir} 到为知笔记: {target_folder}")

    asyncio.run(main(config_path, source_dir, target_folder))
