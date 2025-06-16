"""
统计每个文件夹下的md文件数量，文件清单，并保存到文件
"""

from pathlib import Path

def count_md_files_in_folders(root_dir: Path, result_file: Path, export_md_list: bool = False):
    """
    递归统计每个文件夹下的md文件数量，并将结果写入文件。
    :param root_dir: 需要统计的根目录
    :param result_file: 结果输出文件路径
    :param export_md_list: 是否导出每个目录下的md文件清单
    """
    folder_infos = []
    total_md_count = 0
    for folder in root_dir.rglob('*'):
        if folder.is_dir() and "_assets" not in str(folder):
            md_files = list(folder.glob('*.md'))
            md_count = len(md_files)
            total_md_count += md_count
            if export_md_list:
                md_file_names = [f.name for f in md_files]
            else:
                md_file_names = []
            rel_folder = folder.relative_to(root_dir).as_posix()
            folder_infos.append((rel_folder, md_count, md_file_names))
    # 按路径排序
    folder_infos.sort(key=lambda x: x[0])
    lines = []
    folder_count = 0
    for folder, md_count, md_file_names in folder_infos:
        folder_count += 1
        folder_display = f"/{folder}/" if not folder.startswith('/') else f"{folder}/"
        lines.append(f"文件夹: {folder_display}  笔记数: {md_count}")
        if export_md_list and md_file_names:
            for name in md_file_names:
                lines.append(f"    - {name}")
        lines.append("")
    lines.append(f"总文件夹数: {folder_count}")
    lines.append(f"总md文件数: {total_md_count}")
    result_file.write_text('\n'.join(lines), encoding='utf-8')
    print(f"统计结果已写入: {result_file}")

if __name__ == "__main__":
    output_dir = Path(__file__).parent / 'output'
    result_path = Path(__file__).parent / 'output' / 'exported_md_files.txt'
    export_md_list = True  # 设置为True导出md文件清单，False则只统计数量
    if not output_dir.exists():
        print(f"目录不存在: {output_dir}")
    else:
        print(f"统计目录: {output_dir}\n")
        count_md_files_in_folders(output_dir, result_path, export_md_list)