"""
获取为知笔记的文件夹和每个目录的笔记清单
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from wiz_client import WizNoteClient
from utils import list_folders_and_notes

def get_all_notes_in_folder(client, folder):
    """
    获取文件夹中的所有笔记，处理超过1000条的情况

    Args:
        client: WizNoteClient实例
        folder: 文件夹路径

    Returns:
        list: 去重后的笔记列表
    """
    try:
        # 首先获取1000条笔记（降序，获取最新的笔记）
        desc_notes = client.get_note_list(folder, max_notes=1000)

        # 如果获取到的笔记数量等于1000，说明可能还有更多笔记
        if len(desc_notes) == 1000:
            print(f"文件夹 {folder} 包含超过1000条笔记，执行双向查询...")

            # 升序获取1000条笔记（获取最旧的笔记）
            asc_notes = client._get_notes_with_order(folder, count=100, max_notes=1000, order="asc")

            # 使用GUID进行去重
            seen_guids = set()
            all_notes = []

            # 添加降序笔记（最新的）
            for note in desc_notes:
                guid = note.get('docGuid')
                if guid and guid not in seen_guids:
                    all_notes.append(note)
                    seen_guids.add(guid)

            # 添加升序笔记（最旧的，去重）
            new_notes_count = 0
            for note in asc_notes:
                guid = note.get('docGuid')
                if guid and guid not in seen_guids:
                    all_notes.append(note)
                    seen_guids.add(guid)
                    new_notes_count += 1

            total_unique = len(all_notes)
            duplicate_count = len(desc_notes) + len(asc_notes) - total_unique

            print(f"文件夹 {folder}: 降序{len(desc_notes)}条 + 升序{len(asc_notes)}条，去重{duplicate_count}条，最终{total_unique}条")

            # 如果去重后的数量仍然接近2000，可能还有更多笔记未获取到
            if total_unique >= 1800:
                print(f"警告：文件夹 {folder} 可能包含超过2000条笔记，当前方法无法获取全部")

            return all_notes
        else:
            # 少于1000条，直接返回
            return desc_notes

    except Exception as e:
        print(f"获取文件夹 {folder} 的笔记时出错: {e}")
        return []

def export_wiznotes_structure(config_path=None, export_notes=True):
    """
    导出为知笔记的文件夹结构和笔记清单。
    优化：默认自动同时生成「为知笔记目录.log」（供导出脚本读取）以及「folders & notes.txt」（详细清单），
    无需用户反复修改代码注释运行。

    Args:
        config_path: 配置文件路径，为 None 时从 .env 读取
        export_notes: True-同时获取并导出详细笔记清单；False-仅生成目录列表
    """
    # 初始化客户端
    client = WizNoteClient(config_path)
    client.login()

    # 获取所有文件夹
    folders = client.get_folders()
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 始终自动生成「为知笔记目录.log」，作为批量导出的文件夹索引
    log_path = output_dir / "为知笔记目录.log"
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(folders))
    print(f"✅ 文件夹列表已保存到: {log_path} (共 {len(folders)} 个文件夹)")

    if not export_notes:
        return log_path

    # 2. 导出详细笔记清单到「folders & notes.txt」
    print("正在拉取各目录下的详细笔记清单...")
    output_lines = []
    total_notes = 0
    folder_count = 0

    for folder in folders:
        folder_count += 1
        try:
            notes = get_all_notes_in_folder(client, folder)
        except Exception as e:
            output_lines.append(f"文件夹: {folder}  获取笔记失败: {e}")
            output_lines.append("")
            continue
        note_count = len(notes)
        total_notes += note_count
        output_lines.append(f"文件夹: {folder}  笔记数: {note_count}")
        for note in notes:
            title = note.get('title', 'Untitled')
            output_lines.append(f"    - {title}")
        output_lines.append("")

    output_lines.append(f"总文件夹数: {folder_count}")
    output_lines.append(f"总笔记数: {total_notes}")

    notes_list_path = output_dir / "folders & notes.txt"
    with open(notes_list_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"✅ 详细笔记清单已保存到: {notes_list_path} (共 {total_notes} 篇笔记)")
    return notes_list_path

if __name__ == "__main__":
    # 默认执行：一次性生成「为知笔记目录.log」与「folders & notes.txt」
    export_wiznotes_structure(export_notes=True)
