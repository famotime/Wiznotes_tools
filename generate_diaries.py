"""逐月生成日记模板"""
import pathlib
from datetime import date, datetime
import calendar


year = 2023
path = pathlib.Path.cwd() / 'diaries'
template = path / 'diary_template.md'

with open(template, encoding='utf-8') as f:
    lines = f.readlines()
    base_content = ''.join(lines[1:])

for month in range(1, 13):
    day_count = calendar.monthrange(year, month)[1]
    month_content = f'# {year}年{month}月日记\n\n'
    for day in range(1, day_count+1):
        today = date(year, month, day)
        first_line = f"## {today} {datetime.strftime(today, '%A')[:3]} 晴\n"
        content = first_line + base_content + '\n\n'
        month_content += content

    with open(path / f'{year}-{month:0>2d}.md', 'w', encoding='utf-8') as f:
        f.write(month_content)

print(f"已在{path.absolute()}目录下生成{year}年每月日记模板。")
