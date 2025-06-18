"""
比较两个记录文件中各文件夹下的笔记，统计有差异的笔记，并保存到文件：
- 记录文件1（在线笔记）: folders & notes.txt
- 记录文件2（导出笔记）: exported_md_files.txt

"""

from pathlib import Path

def get_valid_filename(path):
    """确保文件名合法，仅替换 Windows 非法字符
    Args:
        path: 字符串或Path对象，包含文件名或文件夹名
    Returns:
        返回处理后的文件名或文件夹名字符串
    """
    if isinstance(path, str):
        path = Path(path)
    invalid_chars = r'\\/:*?"<>|'
    filename = str(path.name)
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    filename = filename.strip()
    if not filename:
        filename = '_'
    elif len(filename) > 200:
        base = filename
        ext = ''
        if '.' in filename:
            base, ext = filename.rsplit('.', 1)
            ext = '.' + ext
        filename = base[:196] + '...' + ext
    return filename

def parse_record_file(file_path: Path):
    """
    解析记录文件，返回 {文件夹路径: set(笔记名)}
    """
    folder_notes = {}
    current_folder = None
    with file_path.open(encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('文件夹: '):
                # 例如：文件夹: /My Drafts/  笔记数: 33
                parts = line.split('文件夹: ')[1].split('  笔记数:')
                current_folder = parts[0].strip()
                folder_notes[current_folder] = set()
            elif line.strip().startswith('- '):
                note = line.strip()[2:]
                # 去除 .md 后缀（有的没有）
                if note.endswith('.md'):
                    note = note[:-3]
                # 对笔记名进行合法化处理
                note = get_valid_filename(note)
                folder_notes[current_folder].add(note)
    return folder_notes


def compare_notes_in_folders(record_file1: Path, record_file2: Path, exclude_folders=None):
    """
    比较两个记录文件中各文件夹下的笔记，统计有差异的笔记，并保存到文件
    exclude_folders: 需要排除的文件夹路径列表
    """
    if exclude_folders is None:
        exclude_folders = []
    notes1 = parse_record_file(record_file1)
    notes2 = parse_record_file(record_file2)

    all_folders = set(notes1.keys()) | set(notes2.keys())
    diff_lines = []
    for folder in sorted(all_folders):
        if folder in exclude_folders:
            continue
        set1 = notes1.get(folder, set())
        set2 = notes2.get(folder, set())
        only_in_1 = set1 - set2
        only_in_2 = set2 - set1
        if only_in_1 or only_in_2:
            diff_lines.append(f'文件夹: {folder}')
            if only_in_1:
                diff_lines.append('  仅在记录文件1（在线笔记）中:')
                for note in sorted(only_in_1):
                    diff_lines.append(f'    - {note}')
            if only_in_2:
                diff_lines.append('  仅在记录文件2（导出笔记）中:')
                for note in sorted(only_in_2):
                    diff_lines.append(f'    - {note}')
            diff_lines.append('')
    # 保存到 output/compare_diff.txt
    output_file = record_file1.parent / 'compare_diff.txt'
    output_file.write_text('\n'.join(diff_lines), encoding='utf-8')


if __name__ == '__main__':
    # 默认对比 output 目录下的两个文件
    base_dir = Path(__file__).parent
    file1 = base_dir / 'output' / 'folders & notes.txt'
    file2 = base_dir / 'output' / 'exported_md_files.txt'

    # 排除文件夹清单
    exclude_folders = [
        '/My Drafts/',
        '/My Emails/',
    ]

    compare_notes_in_folders(file1, file2, exclude_folders)
    print('对比完成，结果已保存到 compare_diff.txt')


