"""从文本中分离提取出微信公众号文章链接，批量保存到为知笔记"""
import time
import json
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr


def send_mail(subject, mailhost, mailuser, mailpassword, my_nick, mailreceiver, to_nick, mail_msg):
    """发送email"""
    msg = MIMEText(mail_msg, 'html', 'utf-8')       # 将邮件内容做一次MIME的转换
    msg['From'] = formataddr([my_nick, mailuser])
    msg['To'] = formataddr([to_nick, mailreceiver])
    msg['Subject'] = subject

    # 配置与SMTP邮件服务器的连接通道
    server = smtplib.SMTP_SSL(mailhost, 465)
    server.login(mailuser, mailpassword)
    server.sendmail(mailuser, [mailreceiver, ], msg.as_string())
    server.quit()


def split_notes(clipboard_notes, weixin_notes, other_notes):
    """将微信文章链接和其他笔记内容分开保存到文件"""
    with open(clipboard_notes, encoding='utf-8') as f1:
        with open(weixin_notes, 'w', encoding='utf-8') as f2:
            with open(other_notes, 'w', encoding='utf-8') as f3:
                for line in f1:
                    if line.startswith("https://mp.weixin.qq.com"):
                        f2.write(line)
                    elif line.strip():
                        f3.write(line)


def read_mail_account(account_path, mailhost):
    """从json文件读取邮箱帐号信息，mailhost可取['189', '163', '139', 'qq']之一"""
    with open(account_path) as f:
        mail_accounts = json.load(f)
    mail_account = mail_accounts[mailhost]
    return mail_account['host'], mail_account['user'], mail_account['password'], mail_accounts['receiver']


if __name__ == "__main__":
    clipboard_notes = "clipboard_notes.txt"     # 原始文本笔记（含微信文章链接）
    account_path = r'..\account\mail_accounts.json'    # 邮箱帐号信息保存路径
    mailhost = '189'

    split_notes("clipboard_notes.txt", "weixin_notes.txt", "other_notes.txt")
    mailhost, mailuser, mailpassword, mailreceiver = read_mail_account(account_path, mailhost)

    my_nick = "famo"
    to_nick = "test"
    subject = "微信公众号文章"

    # 微信公众号文章链接发送到为知笔记
    with open("weixin_notes.txt", encoding='utf-8') as f:
        lines = set(f.readlines())
        print(f"共发现{len(lines)}篇微信笔记！")
        count = 0
        for mail_msg in lines:
            try:
                send_mail(subject, mailhost, mailuser, mailpassword, my_nick, mailreceiver, to_nick, mail_msg)
                count += 1
                print(f'第{count}封邮件发送成功！内容：{mail_msg}')
                # time.sleep(5)
            except Exception as e:
                print(f'第{count + 1}封邮件发送失败！相关链接：{mail_msg}\n错误信息：{e}。')
        else:
            print(f'共{count}篇微信文章发送成功！\n')

    # 其他非微信链接的摘录文字发送到为知笔记
    with open("other_notes.txt", encoding='utf-8') as f:
        mail_msg = f.read()
    date = time.strftime("%Y%m%d", time.localtime())
    try:
        send_mail(f'碎笔记{date}', mailhost, mailuser, mailpassword, my_nick, mailreceiver, to_nick, mail_msg)
        print(f'“碎笔记{date}”邮件发送成功！')
    except Exception as e:
        print(f'“碎笔记{date}”邮件发送失败！错误信息：{e}。')
