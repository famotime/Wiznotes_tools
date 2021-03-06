"""将图片和对应OCR文本批量发送到为知笔记"""
import pathlib
import shutil
import yagmail
import wxnotes_mail_wiz


def txt_img_mail2wiz(txt_files, mailhost, mailuser, mailpassword, mailreceiver, txt_only=False):
    """将文本或图片及对应OCR文本批量发送到为知笔记"""
    for num, txt_file in enumerate(txt_files, 1):
        print(f'正在处理第{num}个文件：{txt_file.name}……')
        email_content = []
        try:
            with open(txt_file, encoding='utf-8') as f:
                email_content.append(f.read())
        except Exception:
            with open(txt_file, encoding='gbk') as f:
                email_content.append(f.read())

        email_title = txt_file.stem.replace('#', '')    # 删除'#'标识，否则相关内容会被为知笔记识别为tag
        email_to = [mailreceiver]
        if not txt_only:
            image_file = txt_file.with_suffix('.jpg') if txt_file.with_suffix('.jpg') else txt_file.with_suffix('.png')
            email_content.append(yagmail.inline(image_file))    # 图片嵌入邮件正文，而不是作为附件

        # 连接服务器，发送邮件
        yag_server = yagmail.SMTP(user=mailuser, password=mailpassword, host=mailhost)
        try:
            yag_server.send(email_to, email_title, email_content)
            # time.sleep(1)
            # 移动已处理文件到done文件夹
            if not pathlib.Path.exists(r'.\done'):
                pathlib.Path.mkdir(r'.\done')
            shutil.move(txt_file, '.\\done')
            if not txt_only:
                shutil.move(image_file, '.\\done')
        except Exception as e:
            print(e)
            # time.sleep(10)

        yag_server.close()


if __name__ == "__main__":
    account_path = r'C:\QMDownload\Python Programming\Python_Work\account\mail_accounts.json'    # 邮箱帐号信息保存路径
    mailhost = '189'

    mailhost, mailuser, mailpassword, mailreceiver = wxnotes_mail_wiz.read_mail_account(account_path, mailhost)

    path = pathlib.Path(r'C:\QMDownload\BaiduNet\手机截图2013-2020')      # 图片和对应OCR文本保存目录
    txt_files = path.glob('*.txt')

    txt_img_mail2wiz(txt_files, mailhost, mailuser, mailpassword, mailreceiver, txt_only=False)
