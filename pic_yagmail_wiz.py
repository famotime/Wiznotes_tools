"""将图片和对应OCR文本批量发送到为知笔记"""
import re
import pathlib
import yagmail
import wxnotes_mail_wiz


def txt_img_mail2wiz(path, mailhost, mailuser, mailpassword, mailreceiver, number=False, txt_only=False):
    """将文本或图片及对应OCR文本批量发送到为知笔记"""
    txt_files = list(path.glob('*.txt'))[: number] if number else path.glob('*.txt')
    for num, txt_file in enumerate(txt_files, 1):
        print(f'正在处理第{num}个文件：{txt_file.stem}……')
        email_content = []
        try:
            with open(txt_file, encoding='utf-8') as f:
                email_content.append(f.read())
        except Exception:
            with open(txt_file, encoding='gbk') as f:
                email_content.append(f.read())

        date = re.search(r"_(\d{8})_", txt_file.stem)
        info = re.sub(r".*?【.{1,5}】\n?", '', email_content[0])
        email_title = date.group(1) + '_' + info[:25] if date else info[:25]
        email_title = email_title.replace('#', '')    # 删除'#'标识，否则相关内容会被为知笔记识别为tag

        email_to = [mailreceiver]
        if not txt_only:
            image_file = txt_file.with_suffix('.jpg') if txt_file.with_suffix('.jpg') else txt_file.with_suffix('.png') if txt_file.with_suffix('.png') else txt_file.with_suffix('.gif')
            email_content.append(yagmail.inline(image_file))    # 图片嵌入邮件正文，而不是作为附件

        # 连接服务器，发送邮件
        yag_server = yagmail.SMTP(user=mailuser, password=mailpassword, host=mailhost)
        try:
            yag_server.send(email_to, email_title, email_content)
            # time.sleep(1)
            # 移动已处理文件到done文件夹
            done_folder = path / 'done'
            done_folder.mkdir(parents=True, exist_ok=True)
            txt_file.rename(done_folder / txt_file.name)
            if not txt_only:
                image_file.rename(done_folder / image_file.name)
        except Exception as e:
            print(e)
            # time.sleep(10)

        yag_server.close()


if __name__ == "__main__":
    account_path = r'..\account\mail_accounts.json'    # 邮箱帐号信息保存路径
    mailhost = '189'

    mailhost, mailuser, mailpassword, mailreceiver = wxnotes_mail_wiz.read_mail_account(account_path, mailhost)

    path = pathlib.Path(r'E:\Download\HNR320T相册\Screenshots')      # 图片和对应OCR文本保存目录
    number = 100     # 处理文件个数，默认False代表处理目录下全部文件

    txt_img_mail2wiz(path, mailhost, mailuser, mailpassword, mailreceiver, number, txt_only=False)
