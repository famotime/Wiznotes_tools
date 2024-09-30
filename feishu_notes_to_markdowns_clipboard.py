"""将剪贴板中飞书笔记链接下载为本地markdown文件（需要先安装feishu2md开源项目）"""
import pyperclip
import subprocess
import re
from pathlib import Path
import os


def extract_feishu_urls(text):
    pattern = r'https://waytoagi\.feishu\.cn\S+'
    return re.findall(pattern, text)


def add_url_to_md(md_file, url):
    """将链接添加到md文件标题后面一行"""
    # print(f'开始处理文件 {md_file.name}，添加链接...')
    with md_file.open('r+', encoding='utf-8') as f:
        content = f.read()
        lines = content.splitlines()
    if lines and lines[0].startswith('# '):
        lines.insert(1, url)
    else:
        lines.insert(0, url)
    with md_file.open('w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    # print(f'已成功添加链接到文件 {md_file.name}')


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
            result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)

            # 解析输出，获取md文件名
            output = result.stdout
            md_file_name = re.search(r'Downloaded markdown file to (.+)\.md', output)
            if md_file_name:
                file_name = md_file_name.group(1)
            else:
                print("未能从输出中解析出 Markdown 文件名")
                file_name = None

            print(f"成功处理: {url}")

            # 查找对应的md文件并添加链接
            for file in feishu_dir.iterdir():
                if file.is_file() and file.suffix.lower() == '.md' and file.stem == file_name:
                    add_url_to_md(file, url)
                    break
            else:
                print(f"警告: 未找到与URL对应的Markdown文件: {url}")
        except subprocess.CalledProcessError as e:
            print(f"处理 {url} 时出错: {e}")
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

    failed_urls = process_urls(feishu_urls)
    if failed_urls:
        print(f'未将{len(failed_urls)}条飞书笔记下载为本地markdown文件。')

if __name__ == "__main__":
    main()
