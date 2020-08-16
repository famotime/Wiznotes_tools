"""找到未成功发送到为知笔记的文件，重新移入待处理文件夹"""
import shutil
import os
import re


def process(text):
    """处理原始文件名便于跟wiz文件名比较"""
    text = re.sub(r'_\d.ziw', '', text)
    match_obj = re.match(r'(.*?)#', text)
    if match_obj:
        text = match_obj.group(1)

    replace_words = ['.ziw','.jpg','.png', '-', ',', '%',"'", '_', ' ']
    for word in replace_words:
        text = text.replace(word, '')
    text = text.strip()

    return text[:30]


def get_undone_files(wiz_path, img_done_path):
    """获取未成功纳入为知笔记的图片和对应OCR文本文件"""
    wiz_files = [file for file in os.listdir(wiz_path) if file.endswith('.ziw')]
    wiz_files_processed = [process(file) for file in wiz_files]
    img_done_files = [file for file in os.listdir(img_done_path) if (file.endswith('.jpg') or file.endswith('.png'))]   # 已发送的图片（实际有部分图片未成功发送到为知笔记）

    # 整理后的图片文件名若未在为知笔记目录中找到相同文件名，则视为未发送成功
    img_undone_files = []
    for file in img_done_files:
        if process(file) not in wiz_files_processed:
            img_undone_files.append(os.path.join(img_done_path, file))
    txt_undone_files = [file[:-4]+'.txt' for file in img_undone_files]

    print(len(img_undone_files))
    print('\n'.join(img_undone_files))

    return img_undone_files, txt_undone_files


def move_undone_files(img_undone_files, txt_undone_files, todo_path):
    """将未成功采集的图片和文本文件移到待处理文件夹"""
    for img in img_undone_files:
        shutil.move(img, todo_path)
    for txt in txt_undone_files:
        shutil.move(txt, todo_path)


if __name__ == "__main__":
    wiz_path = r'C:\QMDownload\Backup\Wiz Knowledge\Data\quincy.zou@gmail.com\知识点滴\思考&写作\图卦笔记'
    img_done_path = r'C:\QMDownload\BaiduNet\手机截图2013-2020\done'
    todo_path = r'C:\QMDownload\BaiduNet\手机截图2013-2020'

    img_undone_files, txt_undone_files = get_undone_files(wiz_path, img_done_path)
    move_undone_files(img_undone_files, txt_undone_files, todo_path)
