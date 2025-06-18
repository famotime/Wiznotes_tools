"""
统计每个文件夹下的md文件数量，文件清单，并保存到文件
"""

from pathlib import Path
import time
from collections import defaultdict

def count_md_files_in_folders(root_dir: Path, result_file: Path, export_md_list: bool = False):
    """
    递归统计每个文件夹下的md文件数量，并将结果写入文件。
    :param root_dir: 需要统计的根目录
    :param result_file: 结果输出文件路径
    :param export_md_list: 是否导出每个目录下的md文件清单
    """
    print(f"开始扫描目录: {root_dir}")
    start_time = time.time()

    # 使用更高效的方式：直接查找所有md文件，然后按目录分组
    print("正在查找所有md文件...")
    md_files = []
    for md_file in root_dir.rglob('*.md'):
        # 跳过_assets目录中的文件
        if "_assets" not in str(md_file):
            md_files.append(md_file)

    print(f"找到 {len(md_files)} 个md文件")

    # 按目录分组
    print("正在按目录分组...")
    folder_md_dict = defaultdict(list)

    for md_file in md_files:
        folder = md_file.parent
        folder_md_dict[folder].append(md_file)

    # 获取所有目录（包括没有md文件的目录）
    print("正在获取所有目录...")
    all_folders = []
    folder_count = 0
    for folder in root_dir.rglob('*'):
        if folder.is_dir() and "_assets" not in str(folder):
            all_folders.append(folder)
            folder_count += 1

    print(f"找到 {folder_count} 个目录")

    # 处理每个目录
    print("正在处理目录信息...")
    folder_infos = []
    total_md_count = 0
    processed_count = 0

    for folder in all_folders:
        processed_count += 1
        if processed_count % 50 == 0 or processed_count == len(all_folders):
            print(f"处理进度: {processed_count}/{len(all_folders)} ({processed_count/len(all_folders)*100:.1f}%)")

        md_files_in_folder = folder_md_dict.get(folder, [])
        md_count = len(md_files_in_folder)
        total_md_count += md_count

        if export_md_list:
            md_file_names = [f.name for f in md_files_in_folder]
        else:
            md_file_names = []

        rel_folder = folder.relative_to(root_dir).as_posix()
        folder_infos.append((rel_folder, md_count, md_file_names))

    # 按路径排序
    print("正在排序...")
    folder_infos.sort(key=lambda x: x[0])

    # 生成输出内容
    print("正在生成输出内容...")
    lines = []
    actual_folder_count = 0
    for folder, md_count, md_file_names in folder_infos:
        actual_folder_count += 1
        folder_display = f"/{folder}/" if not folder.startswith('/') else f"{folder}/"
        lines.append(f"文件夹: {folder_display}  笔记数: {md_count}")
        if export_md_list and md_file_names:
            for name in md_file_names:
                lines.append(f"    - {name}")
        lines.append("")

    lines.append(f"总文件夹数: {actual_folder_count}")
    lines.append(f"总md文件数: {total_md_count}")

    # 写入文件
    print(f"正在写入结果到: {result_file}")
    result_file.write_text('\n'.join(lines), encoding='utf-8')

    elapsed_time = time.time() - start_time
    print(f"统计完成！")
    print(f"处理时间: {elapsed_time:.2f} 秒")
    print(f"统计结果已写入: {result_file}")
    print(f"总文件夹数: {actual_folder_count}")
    print(f"总md文件数: {total_md_count}")

if __name__ == "__main__":
    output_dir = Path(__file__).parent / 'output'
    result_path = Path(__file__).parent / 'output' / 'exported_md_files.txt'
    export_md_list = True  # 设置为True导出md文件清单，False则只统计数量
    if not output_dir.exists():
        print(f"目录不存在: {output_dir}")
    else:
        print(f"统计目录: {output_dir}\n")
        count_md_files_in_folders(output_dir, result_path, export_md_list)