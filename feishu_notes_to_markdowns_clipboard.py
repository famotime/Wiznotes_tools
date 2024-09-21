"""将剪贴板中飞书笔记链接下载为本地markdown文件（需要先安装feishu2md开源项目）"""
import pyperclip
import subprocess
import re
from pathlib import Path
import os

def extract_feishu_urls(text):
    pattern = r'https://waytoagi\.feishu\.cn\S+'
    return re.findall(pattern, text)

def process_urls(urls):
    current_dir = Path.cwd()
    feishu_dir = current_dir / 'feishu'
    feishu_dir.mkdir(exist_ok=True)
    # 更改工作目录到 feishu 子目录
    os.chdir(feishu_dir)

    failed_urls = []
    for url in urls:
        command = f'feishu2md dl "{url}"'
        try:
            subprocess.run(command, shell=True, check=True)
            print(f"Successfully processed: {url}")
        except subprocess.CalledProcessError as e:
            print(f"Error processing {url}: {e}")
            failed_urls.append(url)

    # 处理完成后，切回原来的工作目录
    os.chdir(current_dir)
    return failed_urls


def main():
    clipboard_content = pyperclip.paste()
    feishu_urls = extract_feishu_urls(clipboard_content)
    if not feishu_urls:
        print("No valid Feishu URLs found in clipboard.")
        return

    process_urls(feishu_urls)

if __name__ == "__main__":
    main()
