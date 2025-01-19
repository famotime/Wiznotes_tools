"""将图片和对应OCR文本批量发送到为知笔记

功能说明:
1. 读取指定目录下的txt文件(OCR文本)和对应的图片文件(jpg/png/gif)
2. 将文本内容和图片组合发送到为知笔记邮箱
3. 处理完成后将文件移动到done子目录

使用前提:
1. txt文件需与图片文件同名(仅后缀不同)
2. txt文件编码为utf-8或gbk
3. 图片格式支持jpg/png/gif
"""
import re
import pathlib
from datetime import datetime
import yagmail
import logging
import time
import wxnotes_mail_wiz

def setup_logger(log_dir):
    """配置日志记录器

    Args:
        log_dir: 日志目录路径
    Returns:
        logger: 配置好的日志记录器
    """
    # 创建logs目录
    log_dir.mkdir(parents=True, exist_ok=True)

    # 生成带日期的日志文件名
    current_date = datetime.now().strftime('%Y%m%d')
    log_file = log_dir / f'pic_yagmail_wiz_{current_date}.log'

    logger = logging.getLogger('pic_yagmail_wiz')
    logger.setLevel(logging.INFO)

    # 创建文件处理器
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.INFO)

    # 创建控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # 创建格式器
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # 添加处理器到记录器
    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger

def txt_img_mail2wiz(path, mailhost, mailuser, mailpassword, mailreceiver, number=False, txt_only=False):
    """将文本或图片及对应OCR文本批量发送到为知笔记

    Args:
        path: 源文件目录路径
        mailhost: 邮件服务器地址
        mailuser: 邮箱用户名
        mailpassword: 邮箱密码
        mailreceiver: 接收邮箱地址(为知笔记)
        number: 处理文件数量限制，默认False处理所有文件
        txt_only: 是否仅发送文本，默认False同时发送图片
    """
    # 设置日志记录器
    log_dir = path / 'logs'
    logger = setup_logger(log_dir)

    txt_files = list(path.glob('*.txt'))[:number] if number else list(path.glob('*.txt'))
    total_files = len(txt_files)
    if not txt_files:
        logger.warning(f"在{path}目录下未找到txt文件")
        return

    for num, txt_file in enumerate(txt_files, 1):
        logger.info(f'正在处理第{num}/{total_files}个文件：{txt_file.stem}')
        if not txt_file.exists():
            logger.error(f"文件{txt_file}不存在")
            continue

        email_content = []
        try:
            with open(txt_file, encoding='utf-8') as f:
                email_content.append(f.read())
        except UnicodeDecodeError:
            try:
                with open(txt_file, encoding='gbk') as f:
                    email_content.append(f.read())
            except Exception as e:
                logger.error(f"无法读取文件{txt_file}: {e}")
                continue

        date = re.search(r"_(\d{8})_", txt_file.stem)
        info = re.sub(r".*?【.{1,5}】\n?", '', email_content[0], count=1)   # 删除第1个【xx】前内容
        email_title = date.group(1) + '_' + info[:25] if date else info[:25]
        email_title = email_title.replace('#', '').split('\n')[0]    # 删除'#'标识，否则相关内容会被为知笔记识别为tag
        email_title = f"{email_title}_{txt_file.stem}"  # 添加原文件名作为后缀

        email_to = [mailreceiver]
        if not txt_only:
            image_file = None
            for suffix in ('.jpg', '.png', '.gif'):
                temp_file = txt_file.with_suffix(suffix)
                if temp_file.exists():
                    image_file = temp_file
                    break

            if not image_file:
                logger.warning(f"未找到{txt_file.stem}对应的图片文件")
                continue
            email_content.append(yagmail.inline(image_file))
        # print(email_content)

        # 连接服务器，发送邮件
        yag_server = yagmail.SMTP(user=mailuser, password=mailpassword, host=mailhost, encoding='utf-8')
        try:
            yag_server.send(email_to, email_title, email_content)
            logger.info(f"成功发送邮件：{email_title}\n")

            # 移动已处理文件到done文件夹
            done_folder = path / 'done'
            done_folder.mkdir(parents=True, exist_ok=True)

            try:
                txt_file.replace(done_folder / txt_file.name)
                if not txt_only and image_file:
                    image_file.replace(done_folder / image_file.name)
                # logger.info(f"成功移动文件到{done_folder}\n")
            except Exception as e:
                logger.error(f"移动文件失败: {e}\n")

        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
        finally:
            yag_server.close()
        time.sleep(0.5)


if __name__ == "__main__":
    account_path = r'..\account\mail_accounts.json'    # 邮箱帐号信息保存路径
    mailhost = '189'

    mailhost, mailuser, mailpassword, mailreceiver = wxnotes_mail_wiz.read_mail_account(account_path, mailhost)

    path = pathlib.Path(r'H:\个人图片及视频\手机截图')      # 图片和对应OCR文本保存目录
    number = 200     # 处理文件个数，默认False代表处理目录下全部文件

    txt_img_mail2wiz(path, mailhost, mailuser, mailpassword, mailreceiver, number, txt_only=False)
