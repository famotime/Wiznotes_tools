"""
工具函数模块
包含日志配置、文件夹和笔记列表功能等通用工具函数
"""

import logging
from pathlib import Path
from datetime import datetime


def setup_logging(export_dir='export_wiznotes/output'):
    """配置日志输出"""
    # 创建logs目录，使用resolve()规范化路径，避免空格和路径错误
    log_dir = Path(export_dir).resolve().parent / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    # 生成日志文件名，包含时间戳
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'wiznotes_export_{timestamp}.log'

    # 清除现有的处理器
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 配置日志处理器
    # 文件处理器 - 记录DEBUG及以上级别的日志
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)

    # 控制台处理器 - 只记录INFO及以上级别的日志，使用简化的格式
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')  # 简化的格式
    console_handler.setFormatter(console_formatter)

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # 使用控制台格式打印日志文件位置
    print(f'日志文件保存在: {log_file}')
    return log_file


def list_folders_and_notes(client, target_folder=None, max_notes=1000):
    """列出文件夹和笔记内容

    Args:
        client: WizNoteClient实例
        target_folder: 指定要查询的文件夹路径，如果为None则列出所有文件夹信息（不获取笔记）
        max_notes: 最大获取笔记数量
    """
    try:
        # 如果指定了目标文件夹，则获取该文件夹下的笔记
        if target_folder:
            logging.info(f"\n开始获取文件夹 {target_folder} 的笔记")
            note_list = client.get_note_list(target_folder, max_notes=max_notes)
            logging.info(f"共获取到 {len(note_list)} 篇笔记:")
            for note in note_list:
                print(f"- {note.get('title', 'Untitled')}")
            return note_list

        else:        # 获取所有文件夹
            folders = client.get_folders()
            logging.info("获取到以下文件夹:")
            for folder in folders:
                print(folder)

        return None
    except Exception as e:
        logging.error(f"列出文件夹和笔记失败: {e}")
        raise