"""从剪贴板文本中分离提取出微信公众号、头条号、小红书、网页文章链接和其他内容，批量保存到为知笔记"""
import json
import time
import re
import requests
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
    """分离微信、头条、小红书文章链接和其他笔记内容"""
    article_links = []
    other_notes = ''
    for line in clipboard_notes.split('\n'):
        if line.startswith("https://mp.weixin.qq.com") and line not in article_links:
            article_links.append(line)
        elif line.startswith("https://m.toutiao.com") and line not in article_links:
            line = '"' + re.sub(r"\?=.*", "", line) + '"'
            article_links.append(line)
        elif "http://xhslink" in line and line not in article_links:
            line = re.search(r"(http://xhslink.*?)，", line).group(1)
            url = requests.get(line).url    # 获取重定向后网址
            article_links.append(url)
        elif line.startswith("https://") and line not in article_links:
            article_links.append(line)
        elif line.strip():
            other_notes += line + '\n'
    return article_links, other_notes


if __name__ == "__main__":
    account_path = pathlib.Path.cwd().parent / 'account/mail_accounts.json'    # 邮箱帐号信息保存路径
    mailhost = '189'    # mailhost可取['189', 'qq', '139']之一

    mailhost, mailuser, mailpassword, mailreceiver = read_mail_account(account_path, mailhost)

    clipboard_notes = pyperclip.paste()
    article_links, other_notes = split_notes(clipboard_notes)
    print(f'发现{len(article_links)}条文章链接。')
    if other_notes.strip():
        article_links.append(other_notes)

    # 将文章链接和其他文本分批发送到为知笔记
    date = time.strftime("%Y%m%d", time.localtime())
    yag_server = yagmail.SMTP(user=mailuser, password=mailpassword, host=mailhost)
    count = 1
    while count <= len(article_links):
        try:
            if article_links[count-1].strip():
                yag_server.send(to=mailreceiver, subject=f'碎笔记{date}', contents=[article_links[count-1]])
                print(f'已发送{count}/{len(article_links)}封邮件到为知笔记({article_links[count-1].strip()})……')
                time.sleep(0.5)
                count += 1
        except Exception as e:
            print(e)
            yag_server = yagmail.SMTP(user=mailuser, password=mailpassword, host=mailhost)
    yag_server.close()
    pyperclip.copy(article_links[-1])  # 文本内容复制到剪贴板作为备份，规避敏感词等问题导致邮件发送不成功
    print(f'已发送全部{len(article_links)}封邮件，并将碎笔记文本内容复制到剪贴板。')
