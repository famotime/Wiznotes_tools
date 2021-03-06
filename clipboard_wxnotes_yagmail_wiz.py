"""从剪贴板文本中分离提取出微信公众号文章链接和其他内容，批量保存到为知笔记"""
import json
import time
import pyperclip
import yagmail
import pathlib


def read_mail_account(account_path, mailhost):
    """从json文件读取邮箱帐号信息，mailhost可取['189', '163', '139', 'qq']之一"""
    with open(account_path) as f:
        mail_accounts = json.load(f)
    mail_account = mail_accounts[mailhost]
    return mail_account['host'], mail_account['user'], mail_account['password'], mail_accounts['receiver']


def split_notes(clipboard_notes):
    """分离微信文章链接和其他笔记内容"""
    weixin_links = []
    other_notes = ''
    for line in clipboard_notes.split('\n'):
        if line.startswith("https://mp.weixin.qq.com"):
            weixin_links.append(line)
        elif line.strip():
            other_notes += line + '\n'
    return weixin_links, other_notes


if __name__ == "__main__":
    account_path = pathlib.Path.cwd().parent / 'account/mail_accounts.json'    # 邮箱帐号信息保存路径
    mailhost = '189'    # mailhost可取['189', '163', '139', 'qq']之一

    mailhost, mailuser, mailpassword, mailreceiver = read_mail_account(account_path, mailhost)

    clipboard_notes = pyperclip.paste()
    weixin_links, other_notes = split_notes(clipboard_notes)
    print(f'发现{len(weixin_links)}条微信公众号链接。')
    weixin_links.append(other_notes)

    # 将微信公众号链接和其他文本分批发送到为知笔记
    date = time.strftime("%Y%m%d", time.localtime())
    yag_server = yagmail.SMTP(user=mailuser, password=mailpassword, host=mailhost)
    for count, weixin_link in enumerate(weixin_links, 1):
        yag_server.send(to=mailreceiver, subject=f'碎笔记{date}', contents=[weixin_link])
        print(f'已发送{count}/{len(weixin_links)}封邮件到为知笔记({weixin_link.strip()})……')
    yag_server.close()
    print(f'已发送全部{len(weixin_links)}封邮件。')
