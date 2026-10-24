"""
从为知笔记读取信息，导出单篇或批量导出笔记
"""

import sys
import re
import argparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入各个模块
from export_wiznotes.wiz_client import WizNoteClient
from export_wiznotes.note_exporter import NoteExporter
from export_wiznotes.utils import setup_logging
from export_wiznotes.get_folders_and_notes_list import get_all_notes_in_folder


def read_folders_from_log(log_file):
    """
    从文件夹清单日志中读取并清洗文件夹路径列表
    自动容错兼容：
    1. 纯文件夹路径格式（每行一个 /xxx/）
    2. 兼容 folders & notes.txt 格式（如 '文件夹: /xxx/  笔记数: 64'）
    3. 自动忽略笔记标题行（如 '- 笔记标题'）及注释/空行
    """
    folders = []
    seen = set()
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            folder_path = None
            # 兼容带有 "文件夹: /Path/  笔记数: xx" 的格式（如直接使用 folders & notes.txt）
            if '文件夹:' in line:
                after_prefix = line.split('文件夹:')[1].strip()
                if '笔记数' in after_prefix:
                    folder_path = after_prefix.split('笔记数')[0].strip()
                else:
                    folder_path = after_prefix
            elif line.startswith('/') and line.endswith('/'):
                folder_path = line
            elif line.startswith('/'):
                folder_path = line + '/'
            else:
                # 忽略笔记行（如 - 标题）或其他非目录行
                continue

            if folder_path:
                folder_path = folder_path.strip()
                if folder_path and folder_path not in seen:
                    seen.add(folder_path)
                    folders.append(folder_path)
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


def retry_failed_notes_from_diff(diff_file: Path, client: WizNoteClient, export_dir: Path):
    """
    从 compare_diff.txt 中读取漏导的笔记，进行靶向补偿重导（无需重新遍历全量库）
    """
    if not diff_file.exists():
        logging.error(f"未找到差异对比文件: {diff_file}。请先运行 compare_notes_in_folders.py 生成该文件。")
        return

    logging.info(f"正在解析差异文件进行靶向补导: {diff_file}")
    missing_by_folder = {}
    current_folder = None
    in_online_section = False

    with open(diff_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('文件夹: '):
                current_folder = line.split('文件夹: ')[1].strip()
                in_online_section = False
            elif '仅在记录文件1（在线笔记）中:' in line:
                in_online_section = True
            elif '仅在记录文件2' in line:
                in_online_section = False
            elif in_online_section and line.startswith('- '):
                note_title = line[2:].strip()
                if current_folder:
                    missing_by_folder.setdefault(current_folder, set()).add(note_title)

    total_missing = sum(len(titles) for titles in missing_by_folder.values())
    if total_missing == 0:
        logging.info("差异文件中没有待补导的在线笔记！")
        return

    logging.info(f"共发现 {len(missing_by_folder)} 个文件夹下累计 {total_missing} 篇未成功导出的笔记，开始靶向补导...")
    exporter = NoteExporter(client)
    tag_map = client.get_all_tags()
    success_retry = 0

    for folder, titles in missing_by_folder.items():
        logging.info(f"正在获取文件夹 {folder} 的笔记列表...")
        notes = get_all_notes_in_folder(client, folder)
        folder_parts = folder.strip('/').split('/')
        current_path = export_dir
        for part in folder_parts:
            safe_part = exporter._get_valid_filename(Path(part))
            current_path = current_path / safe_part
        current_path.mkdir(parents=True, exist_ok=True)

        checkpoint_file = current_path / '.export_checkpoint.json'
        for note in notes:
            raw_title = note.get('title', 'Untitled')
            # 兼容带 .md 或不带 .md 的匹配
            cmp_title = raw_title[:-3] if raw_title.lower().endswith('.md') else raw_title
            safe_cmp = exporter._get_valid_filename(cmp_title)

            if raw_title in titles or cmp_title in titles or safe_cmp in titles:
                logging.info(f"🎯 靶向补导笔记: 《{raw_title}》 (文件夹: {folder})")
                try:
                    if exporter.export_single_note(note, current_path, tag_map):
                        success_retry += 1
                        # 记录到 checkpoint
                        try:
                            guids = set()
                            if checkpoint_file.exists():
                                with open(checkpoint_file, 'r', encoding='utf-8') as cf:
                                    guids = set(import_json := __import__('json').load(cf).get('exported_guids', []))
                            guids.add(note['docGuid'])
                            exporter._save_checkpoint(checkpoint_file, guids)
                        except Exception:
                            pass
                except Exception as e:
                    logging.error(f"补导笔记 《{raw_title}》 失败: {e}")

    logging.info(f"靶向补导完成！成功补导 {success_retry}/{total_missing} 篇笔记")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="为知笔记批量导出工具")
    parser.add_argument(
        "--retry-diff",
        action="store_true",
        help="根据 output/compare_diff.txt 中的差异清单，仅靶向补导漏导的笔记"
    )
    args = parser.parse_args()

    # ========== 配置参数 ==========
    export_dir = Path.cwd() / "export_wiznotes" / "output"
    max_notes = None  # 不限制笔记数量，自动处理超过1000条笔记的情况（通过双向查询和去重）
    log_file = export_dir / "为知笔记目录.log"
    diff_file = export_dir / "compare_diff.txt"

    # 修复选项：是否重新导出包含"."的文件名（用于修复之前的导出问题）
    reexport_dot_files = False

    # 性能配置
    max_workers = 10  # 配置并行下载的线程数

    try:
        # 设置日志
        setup_logging(export_dir)

        # 创建客户端并登录（从 .env 文件读取账号配置，支持自建服务器）
        client = WizNoteClient()
        client.login()

        # 模式一：针对漏导笔记的靶向补导
        if args.retry_diff:
            retry_failed_notes_from_diff(diff_file, client, export_dir)
            return

        # 模式二：常规批量导出
        # 容错：如果 log_file 不存在，自动从线上获取所有文件夹并保存，无需用户分步操作
        if log_file.exists():
            folders = read_folders_from_log(log_file)
            logging.info(f"从清单文件读取到 {len(folders)} 个待导出文件夹: {log_file}")
        else:
            logging.warning(f"未检测到文件夹列表文件 {log_file.name}，正在自动通过 API 获取全量文件夹...")
            folders = client.get_folders()
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(folders))
            logging.info(f"已自动获取 {len(folders)} 个文件夹，并保存到 {log_file}")

        if not folders:
            logging.warning("待导出的文件夹列表为空！请检查为知笔记账号中是否存在笔记文件夹。")
            return

        if reexport_dot_files:
            logging.info("已启用重新导出包含'.'的文件名功能，将修复之前的导出问题")

        # 准备导出参数
        export_args = [(folder, client, export_dir, max_notes, reexport_dot_files) for folder in folders]

        # 使用线程池并行导出
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_folder = {
                executor.submit(export_folder, export_arg): export_arg[0]
                for export_arg in export_args
            }

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
