"""
从为知笔记读取信息，导出单篇或批量导出笔记
"""

import sys
import logging
from pathlib import Path

# 导入各个模块
from export_wiznotes.wiz_client import WizNoteClient
from export_wiznotes.note_exporter import NoteExporter
from export_wiznotes.utils import setup_logging, list_folders_and_notes


def main():
    """主函数"""
    # 配置参数
    config_path = Path.cwd().parent / "account" / "web_accounts.json"
    export_dir = Path.cwd() / "export_wiznotes" / "output"
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