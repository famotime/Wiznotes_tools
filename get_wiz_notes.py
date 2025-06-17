"""
从为知笔记读取信息，导出单篇或批量导出笔记
"""

import sys
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入各个模块
from export_wiznotes.wiz_client import WizNoteClient
from export_wiznotes.note_exporter import NoteExporter
from export_wiznotes.utils import setup_logging, list_folders_and_notes


def read_folders_from_log(log_file):
    """从日志文件中读取文件夹列表"""
    folders = []
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            folder = line.strip()
            if folder and not folder.startswith('#'):
                folders.append(folder)
    return folders


def export_folder(args):
    """导出单个文件夹的笔记"""
    folder, client, export_dir, max_notes, reexport_dot_files = args
    try:
        exporter = NoteExporter(client)
        logging.info(f"开始导出文件夹: {folder}")
        exporter.export_notes(
            folder=folder,
            export_dir=export_dir,
            max_notes=max_notes,
            resume=True,
            reexport_dot_files=reexport_dot_files
        )
        logging.info(f"文件夹 {folder} 导出完成")
        return True
    except Exception as e:
        logging.error(f"导出文件夹 {folder} 时出错: {e}")
        return False


def main():
    """主函数"""
    # ========== 配置参数 ==========
    # 基础配置
    config_path = Path.cwd().parent / "account" / "web_accounts.json"
    export_dir = Path.cwd() / "export_wiznotes" / "output"
    max_notes = None  # 不限制笔记数量，自动处理超过1000条笔记的情况（通过双向查询和去重）
    log_file = export_dir / "为知笔记目录.log"

    # 修复选项：是否重新导出包含"."的文件名（用于修复之前的导出问题）
    # 如果之前导出时遇到文件名截断问题，设置为True；正常情况下设置为False
    reexport_dot_files = True  # 设置为True来修复之前的导出问题

    # 性能配置
    max_workers = 10  # 配置并行下载的线程数

    try:
        # 设置日志
        setup_logging(export_dir)

        # 创建客户端并登录
        client = WizNoteClient(config_path)
        client.login()

        # 读取所有文件夹
        folders = read_folders_from_log(log_file)
        logging.info(f"共读取到 {len(folders)} 个文件夹")

        if reexport_dot_files:
            logging.info("已启用重新导出包含'.'的文件名功能，将修复之前的导出问题")

        # 准备导出参数
        export_args = [(folder, client, export_dir, max_notes, reexport_dot_files) for folder in folders]

        # 使用线程池并行导出
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_folder = {
                executor.submit(export_folder, export_arg): export_arg[0]
                for export_arg in export_args
            }

            # 处理完成的任务
            success_count = 0
            for future in as_completed(future_to_folder):
                folder = future_to_folder[future]
                try:
                    if future.result():
                        success_count += 1
                except Exception as e:
                    logging.error(f"处理文件夹 {folder} 时发生异常: {e}")

        logging.info(f"导出完成，成功导出 {success_count}/{len(folders)} 个文件夹")

    except KeyboardInterrupt:
        logging.info("程序被用户中断")
        sys.exit(0)
    except Exception as e:
        logging.error(f"程序执行失败: {e}")


if __name__ == '__main__':
    main()