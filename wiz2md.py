"""批量转换为知笔记.md.ziw文件为标准markdown文件"""
import os
import zipfile
import re
import shutil
import html2text


def get_markdown_files(data_path):
    """获取.md.ziw文件列表"""
    md_files = []
    for root, dirs, files in os.walk(data_path):
        for file in files:
            if file.endswith('.md.ziw'):
                md_files.append(os.path.join(root, file))
    print(f'共发现{len(md_files)}个Markdown文件。')
    return md_files


def ziw2md(md_file, export_md_path):
    """将.md.ziw文件转为标准md文件，导出图片和附件文件到本地目录"""
    ziw_zip = zipfile.ZipFile(md_file)
    ziw_zip.extractall(tmp_path)
    ziw_zip.close()

    filename = os.path.basename(md_file)[:-7]   # 不含扩展名的文件名称
    parent_folder_name = os.path.dirname(md_file).split('\\')[-1]   # 原md文件父目录名称
    export_md_file = os.path.join(export_md_path, parent_folder_name, filename + '.md')
    export_attachment_path = os.path.join(export_md_path, parent_folder_name, filename)   # 图片、附件保存目录

    with open(os.path.join(tmp_path, 'index.html'), encoding='utf-16') as f1:
        content = f1.read()
        '''
        content = content.replace('</body></html>', '')
        content = content.replace('&lt;', '<')
        content = content.replace('&gt;', '>')
        content = content.replace('&nbsp;', ' ')
        content = content.replace('<br/>', '\n')
        content = re.sub(r'<!DOCTYPE html><html><head>.*?</head><body>', '', content)
        '''
        content = re.sub(r'<ed_tag name="markdownimage" .*?</ed_tag>', '', content)   # 替换包含图片链接文件的文末内容
        content = html2text.html2text(content)
        content = content.replace(r'\---', '---')
        content = content.replace('index_files', filename)    # 将图片文件链接改为相应目录

    # 分目录输出markdown文件
    if not os.path.exists(os.path.join(export_md_path, parent_folder_name)):
        os.mkdir(os.path.join(export_md_path, parent_folder_name))
    with open(export_md_file, 'w', encoding='utf-8') as f2:
        f2.write(content)
    print(f'已导出：{export_md_file}。')

    # 将index_files目录下图片文件复制到以markdown文件标题命名的目录
    if os.path.exists(os.path.join(tmp_path, 'index_files')):
        shutil.copytree(os.path.join(tmp_path, 'index_files'), export_attachment_path, dirs_exist_ok=True)
    # 将附件目录下文件复制到以markdown文件标题命名的目录
    attachment_path = os.path.join(os.path.dirname(md_file), filename+'.md_Attachments')
    if os.path.exists(attachment_path):
        if not os.path.exists(export_attachment_path):
            os.mkdir(export_attachment_path)
        for attachment in os.listdir(attachment_path):
            shutil.copy2(os.path.join(attachment_path, attachment), export_attachment_path)
    shutil.rmtree(tmp_path)


if __name__ == "__main__":
    wizdata_path = r'C:\QMDownload\Backup\Wiz Knowledge\Data\quincy.zou@gmail.com'
    export_md_path = r'C:\QMDownload\Backup\Wiz Knowledge\exported_md'
    tmp_path = os.path.join(export_md_path, 'temp')

    md_files = get_markdown_files(wizdata_path)
    for md_file in md_files:
        ziw2md(md_file, export_md_path)
