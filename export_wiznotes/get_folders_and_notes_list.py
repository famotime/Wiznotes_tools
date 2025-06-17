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
    导出为知笔记的文件夹结构和笔记清单

    Args:
        config_path: 配置文件路径，默认为相对路径
        export_notes: True-导出笔记清单，False-仅导出目录
    """
    # 配置文件路径
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "account" / "web_accounts.json"

    # 初始化客户端
    client = WizNoteClient(config_path)
    client.login()

    # 获取所有文件夹
    folders = client.get_folders()

    output_lines = []

    if export_notes:
        # 导出详细的笔记清单
        total_notes = 0
        folder_count = 0

        for folder in folders:
            folder_count += 1
            try:
                # 使用新的获取方法，处理超过1000条笔记的情况
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

        # 保存到文件
        output_path = Path(__file__).parent / "output" / "folders & notes.txt"
        output_filename = "folders & notes.txt"
    else:
        # 仅导出目录，每行一条目录信息
        for folder in folders:
            output_lines.append(folder)

        # 保存到文件
        output_path = Path(__file__).parent / "output" / "为知笔记目录.log"
        output_filename = "为知笔记目录.log"

    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 保存文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))

    print(f"信息已保存到 {output_path}")

    if export_notes:
        # 获取并打印所有文件夹
        print("所有文件夹：")
        list_folders_and_notes(client)

    return output_path

if __name__ == "__main__":
    # 仅导出目录
    # export_wiznotes_structure(export_notes=False)

    # 导出目录及笔记清单
    export_wiznotes_structure(export_notes=True)
