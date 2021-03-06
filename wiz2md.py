"""批量转换为知笔记.md.ziw文件为标准markdown文件"""
import pathlib
import zipfile
import re
import shutil
import time
from lxml import etree


def get_markdown_files(data_path):
    """获取.md.ziw文件列表"""
    md_files = list(data_path.glob('**/*.md*.ziw'))
    print(f'共发现{len(md_files)}个Markdown文件。')
    return md_files


def ziw2md(md_file, export_md_path, tmp_path, abs_img_path=False):
    """将.md.ziw文件转为标准md文件，导出图片和附件文件到本地目录"""
    ziw_zip = zipfile.ZipFile(md_file)
    ziw_zip.extractall(tmp_path)
    ziw_zip.close()

    print(f"正在转换《{md_file.stem}》……")
    export_md_file = export_md_path.joinpath(md_file.parent.stem, md_file.stem.replace('.md', '')+'.md')
    export_attachment_path = export_md_file.parent / export_md_file.stem   # 图片、附件保存目录

    with open(tmp_path / 'index.html', encoding='utf-16') as f1:
        content = f1.read()
        content = content.replace('</div>', '\n')
        content = content.replace('<br>', '\n')
        content = content.replace('<br/>', '\n')
        '''
        pattern1 = re.compile(r'<!doctype.*?</head>', re.DOTALL | re.IGNORECASE | re.MULTILINE)
        content = pattern1.sub('', content)
        pattern2 = re.compile(r'.*WizHtmlContentBegin-->', re.DOTALL | re.IGNORECASE | re.MULTILINE)
        content = pattern2.sub('', content)
        content = re.sub(r'<body.*?>', '', content)
        content = content.replace('&lt;', '<')
        content = content.replace('&gt;', '>')
        content = content.replace('&nbsp;', ' ')
        content = content.replace('<div>', '')
        content = content.replace('</div>', '\n')
        content = content.replace('<br/>', '\n')
        content = content.replace('<br>', '\n')
        content = content.replace('</body></html>', '')
        # content = html2text.html2text(content)
        content = content.replace(r'\---', '---').strip()
        content = re.sub(r'<ed_tag name="markdownimage" .*?</ed_tag>', '', content).strip()   # 替换包含图片链接文件的文末内容
        '''
        tree = etree.HTML(content)
        content = tree.xpath('//body')[0].xpath('string(.)')

        # 将图片文件链接改为相应目录
        if abs_img_path:
            content = content.replace('index_files', export_attachment_path)
        else:
            content = content.replace('index_files', export_attachment_path.stem)

    # 分目录输出markdown文件
    if not (export_md_path / md_file.parent.stem).exists():
        (export_md_path / md_file.parent.stem).mkdir()
    with open(export_md_file, 'w', encoding='utf-8') as f2:
        f2.write(content)
    print(f'已导出：{export_md_file}。')

    # 将index_files目录下图片文件复制到以markdown文件标题命名的目录
    if (tmp_path / 'index_files').exists():
        # shutil.copytree((tmp_path / 'index_files'), export_attachment_path, dirs_exist_ok=True)
        (tmp_path / 'index_files').rename(export_attachment_path)

    # 将附件目录下文件复制到以markdown文件标题命名的目录
    attachment_path = md_file.parent.joinpath(md_file.stem, '.md_Attachments')
    if attachment_path.exists():
        if not export_attachment_path.exists():
            export_attachment_path.mkdir()
        for attachment in attachment_path.glob('*.*'):
            shutil.copy2(attachment, export_attachment_path)
    # shutil.rmtree(tmp_path)


if __name__ == "__main__":
    wizdata_path = pathlib.Path(r'C:\QMDownload\Backup\Wiz Knowledge\Data\quincy.zou@gmail.com')
    export_md_path = pathlib.Path(r'C:\QMDownload\Backup\Wiz Knowledge\exported_md')
    tmp_path = export_md_path / 'temp'

    md_files = get_markdown_files(wizdata_path)
    for md_file in md_files:
        ziw2md(md_file, export_md_path, tmp_path, abs_img_path=False)
