"""将图片和对应OCR文本批量发送到为知笔记"""
import os
import shutil
import time
import json
import yagmail


def txt_img_mail2wiz(txt_files, mailhost, mailuser, mailpassword, mailreceiver, txt_only=False, ):
    """将文本或图片及对应OCR文本批量发送到为知笔记"""
    for num, txt_file in enumerate(txt_files[:], 1):
        print(f'正在处理第{num}个文件：{txt_file[:-4]}……')
        email_content = []
        try:
            with open(txt_file, encoding='utf-8') as f:
                email_content.append(f.read())
        except Exception:
            with open(txt_file, encoding='gbk') as f:
                email_content.append(f.read())

        email_title = txt_file[:-4].replace('#', '')    # 删除'#'标识，否则相关内容会被为知笔记识别为tag
        email_to = [mailreceiver]
        if not txt_only:
            image_file = (txt_file[:-3] + 'jpg') if os.path.exists(txt_file[:-3] + 'jpg') else (txt_file[:-3] + 'png')
            email_content.append(yagmail.inline(image_file))    # 图片嵌入邮件正文，而不是作为附件

        # 连接服务器，发送邮件
        yag_server = yagmail.SMTP(user=mailuser, password=mailpassword, host=mailhost)
        try:
            yag_server.send(email_to, email_title, email_content)
            # time.sleep(1)
            shutil.move(txt_file, '.\\done')
            if not txt_only:
                shutil.move(image_file, '.\\done')
        except Exception as e:
            print(e)
            # time.sleep(10)

        yag_server.close()


if __name__ == "__main__":
    # 从json文件读取邮箱帐号信息
    with open('mail_accounts.json') as f:
        mail_accounts = json.load(f)
    mail_account = mail_accounts['189']
    # mail_account = mail_accounts['163']
    # mail_account = mail_accounts['139']
    # mail_account = mail_accounts['qq']
    mailhost, mailuser, mailpassword, mailreceiver = mail_account['host'], mail_account['user'], mail_account['password'], mail_accounts['receiver']

    path = r'c:\QMDownload\BaiduNet\手机截图2013-2020'      # 图片和对应OCR文本保存目录
    os.chdir(path)
    txt_files = [x for x in os.listdir() if x.endswith('.txt')]

    txt_img_mail2wiz(txt_files, mailhost, mailuser, mailpassword, mailreceiver, txt_only=False)
