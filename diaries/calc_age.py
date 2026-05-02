'''计算精确年龄并替换文本'''
from datetime import datetime
import re
import pyperclip
import calendar


def calc_age_byhuman(birthday, today):
    '''计算出生至今日的年龄 (周岁、月、天)'''
    # 规范化日期字符串，去除横杠、点等分隔符
    today_norm = re.sub(r'\D', '', today)
    
    # 统一解析日期对象
    birth_dt = datetime.strptime(birthday, '%Y%m%d')
    today_dt = datetime.strptime(today_norm, '%Y%m%d')

    years = today_dt.year - birth_dt.year
    months = today_dt.month - birth_dt.month
    days = today_dt.day - birth_dt.day

    # 天数不足，向月份借位
    if days < 0:
        # 借用【上个月】的天数
        # 如果当前是1月，上个月就是去年的12月
        prev_month = today_dt.month - 1 if today_dt.month > 1 else 12
        prev_year = today_dt.year if today_dt.month > 1 else today_dt.year - 1
        _, days_in_prev_month = calendar.monthrange(prev_year, prev_month)
        
        days += days_in_prev_month
        months -= 1

    # 月份不足，向年份借位
    if months < 0:
        months += 12
        years -= 1

    age = f'({years}周岁{months}个月零{days}天)'
    print(age)
    return age


def calc_age_bynumber(birthday, today):
    '''计算出生至今日的精确年龄'''
    birthday_obj = datetime.strptime(birthday, '%Y%m%d')
    today_obj = datetime.strptime(today, '%Y%m%d')
    day_diff = today_obj - birthday_obj
    # print(day_diff)
    days = int(str(day_diff).split()[0])
    age = f'({days//365}周岁{days%365//31}个月零{days%365%31}天)'
    print(age)
    return age


def test_calc():
    # - [x] 设计改进方案
    #     - [x] 分析现有 `calc_age_byhuman` 的不足
    #     - [x] 编写 `implementation_plan.md`
    # - [/] 实施改进
    #     - [x] 修改 `calc_age_byhuman` 使用 `datetime` 和 `calendar` 库
    #     - [x] 优化字符串解析和错误处理
    # - [x] 验证改进
    #     - [x] 运行脚本测试不同日期的计算精度（如闰年、不同天数的月份）
    print("Testing improved calc_age_byhuman:")
    birthday = '20180527'
    # 正常测试
    assert calc_age_byhuman(birthday, '20240527') == '(6周岁0个月零0天)'
    # 跨月借位 (5月31日 - 5月27日 = 4天) -> 没超过 27
    assert calc_age_byhuman(birthday, '20240615') == '(6周岁0个月零19天)'
    # 跨月借位 (2024-03-15, 借2月天数)
    assert calc_age_byhuman(birthday, '20240315') == '(5周岁9个月零17天)' # 2024是闰年，2月有29天。15 + 29 - 27 = 17
    # 跨月借位 (2023-03-15, 借2月天数)
    assert calc_age_byhuman(birthday, '20230315') == '(4周岁9个月零16天)' # 2023非闰年，2月有28天。15 + 28 - 27 = 16
    print("All tests passed!")


if __name__ == "__main__":
    # test_calc() # 解开注释可运行测试
    # 获取剪贴板文本
    text = pyperclip.paste()

    # 在包含日期信息的内容中添加年龄信息 (支持 20250706, 2025-07-06, 2025.07.06 等)
    birthday = '20180527'
    text, count = re.subn(r'#+ .*?(\d{4}[-./]?\d{2}[-./]?\d{2})(?!\()', lambda x: x.group() + calc_age_byhuman(birthday, x.group(1)), text)
    print(f'共操作{count}次。')

    # 整理后文本拷贝到系统剪贴板
    pyperclip.copy(text)
    print(text)
