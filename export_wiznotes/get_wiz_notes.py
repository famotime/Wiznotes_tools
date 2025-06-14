"""
从为知笔记读取信息，导出单篇或批量导出笔记

功能：
1. 登录为知笔记Web版
2. 获取指定文件夹下的笔记列表
3. 下载笔记内容并根据内容类型导出为markdown或html格式
4. 支持断点续传，避免重复下载
5. 自动处理文件名中的非法字符
6. 支持协作笔记的导出

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
- export_dir: 导出目录，默认为 "./output"
- max_notes: 每个文件夹最大获取笔记数量

注意事项：
1. 为知笔记API限制单次最多获取1000篇笔记，超过1000篇笔记的文件夹会自动进行两次查询；
2. 导出过程支持断点续传，可以随时中断后继续；如果需要覆盖已导出文件，请删除导出目录下checkpoint文件；
3. 协作笔记使用WebSocket通信，需要确保网络连接稳定；
"""

import sys
import logging
from pathlib import Path

# 导入各个模块
from wiz_client import WizNoteClient
from note_exporter import NoteExporter
from utils import setup_logging, list_folders_and_notes


def main():
    """主函数"""
    # 配置参数
    config_path = Path.cwd().parent.parent / "account" / "web_accounts.json"
    export_dir = Path.cwd() / "output"
    max_notes = 1000  # 文件夹下所有笔记数量，为知笔记API限制的单次获取最大值为1000，超过1000但少于2000需要分两次获取

    # notes_folder = r"/My Drafts/"
    notes_folder = r"/导出测试/"

    try:
        # 设置日志
        log_file = setup_logging(export_dir)

        # 创建客户端并登录
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
        exporter = NoteExporter(client)
        exporter.export_notes(
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


if __name__ == '__main__':
    main()