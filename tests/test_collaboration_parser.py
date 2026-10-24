"""
测试协作笔记（Collaboration Note）WebSocket Delta 块解析器
验证标题、引用、列表、多行代码块、表格、嵌入元素及富文本样式的 Markdown 转换精度
"""

import json
import pytest
from export_wiznotes.collaboration_parser import CollaborationParser


@pytest.fixture
def parser():
    kb_info = {
        "kbServer": "https://ks.wiz.cn",
        "kbGuid": "mock-kb-guid",
        "userGuid": "mock-user-guid"
    }
    return CollaborationParser(kb_info)


@pytest.mark.unit
class TestCollaborationParser:
    """协作笔记解析器单元测试"""

    def test_parse_heading_and_quotes(self, parser):
        """测试文本块的标题层级与引用块"""
        h1_block = {"type": "text", "heading": 1, "text": [{"insert": "一级标题"}]}
        h3_block = {"type": "text", "heading": 3, "text": [{"insert": "三级标题"}]}
        quote_block = {"type": "text", "quoted": True, "text": [{"insert": "这是一条引用"}]}

        assert parser._parse_text_block(h1_block).strip() == "# 一级标题"
        assert parser._parse_text_block(h3_block).strip() == "### 三级标题"
        assert parser._parse_text_block(quote_block).strip() == "> 这是一条引用"

    def test_parse_list_blocks(self, parser):
        """测试无序列表、有序列表及带复选框的任务清单"""
        # 无序普通列表
        bullet = {"type": "list", "ordered": False, "level": 1, "text": [{"insert": "条目A"}]}
        assert parser._parse_list_block(bullet) == "- 条目A\n"

        # 二级缩进列表
        sub_bullet = {"type": "list", "ordered": False, "level": 2, "text": [{"insert": "二级条目"}]}
        assert parser._parse_list_block(sub_bullet) == "  - 二级条目\n"

        # 有序列表
        ordered = {"type": "list", "ordered": True, "start": 3, "level": 1, "text": [{"insert": "第三步"}]}
        assert parser._parse_list_block(ordered) == "3. 第三步\n"

        # 待办复选框任务（已勾选与未勾选）
        task_checked = {"type": "list", "ordered": False, "checkbox": "checked", "level": 1, "text": [{"insert": "已完成事项"}]}
        task_unchecked = {"type": "list", "ordered": False, "checkbox": "unchecked", "level": 1, "text": [{"insert": "待办事项"}]}
        assert parser._parse_list_block(task_checked) == "- [x] 已完成事项\n"
        assert parser._parse_list_block(task_unchecked) == "- [ ] 待办事项\n"

    def test_parse_code_block_with_multiple_delta_inserts(self, parser):
        """核心修复验证：测试同一行包含多个 delta insert 片段以及多行代码的拼接"""
        full_data = {
            "c1": [{"text": [{"insert": "def "}, {"insert": "calculate(x, y):"}]}],
            "c2": [{"text": [{"insert": "    # 计算总和\n    return x + y"}]}],
            "c3": [{"text": [{"insert": "print('done')"}]}]
        }
        code_block = {
            "type": "code",
            "language": "python",
            "children": ["c1", "c2", "c3"]
        }
        result = parser._parse_code_block(full_data, code_block)

        assert result.startswith("\n```python\n")
        assert result.endswith("\n```\n\n")
        assert "def calculate(x, y):" in result
        assert "# 计算总和" in result
        assert "print('done')" in result

    def test_parse_table_block(self, parser):
        """测试 Markdown 表格解析与列补齐"""
        full_data = {
            "h1": [{"text": [{"insert": "商品"}]}],
            "h2": [{"text": [{"insert": "价格"}]}],
            "r1": [{"text": [{"insert": "苹果"}]}],
            "r2": [{"text": [{"insert": "￥5"}]}],
            "r3": [{"text": [{"insert": "香蕉"}]}],
            "r4": [{"text": [{"insert": "￥3"}]}],
        }
        table_block = {
            "type": "table",
            "cols": 2,
            "children": ["h1", "h2", "r1", "r2", "r3", "r4"]
        }
        table_md = parser._parse_table_block(full_data, table_block)

        assert "| 商品 | 价格 |" in table_md
        assert "| --- | --- |" in table_md
        assert "| 苹果 | ￥5 |" in table_md
        assert "| 香蕉 | ￥3 |" in table_md

    def test_parse_embed_blocks(self, parser):
        """测试嵌入元素：图片、分割线、目录、附件链接"""
        img_block = {"type": "embed", "embedType": "image", "embedData": {"src": "photo.jpg"}}
        hr_block = {"type": "embed", "embedType": "hr", "embedData": {}}
        toc_block = {"type": "embed", "embedType": "toc", "embedData": {}}
        att_block = {"type": "embed", "embedType": "office", "embedData": {"fileName": "报告.docx", "src": "guid-att-123"}}

        assert parser._parse_embed_block(img_block).strip() == "![图片](photo.jpg)"
        assert parser._parse_embed_block(hr_block).strip() == "---"
        assert parser._parse_embed_block(toc_block).strip() == "[TOC]"
        assert parser._parse_embed_block(att_block).strip() == "[报告.docx](wiz-collab-attachment://guid-att-123)"

    def test_parse_inline_rich_text_styles(self, parser):
        """测试粗体、斜体、行内代码、删除线、超链接、双链与公式"""
        # 双向链接
        wiki_obj = {"insert": "链接文本", "attributes": {"type": "wiki-link", "name": "设计架构.md"}}
        assert parser._parse_text_object(wiki_obj) == "[[设计架构]]"

        # 数学公式
        math_obj = {"insert": " ", "attributes": {"type": "math", "tex": "a^2 + b^2 = c^2"}}
        assert parser._parse_text_object(math_obj) == "$a^2 + b^2 = c^2$"

        # 超链接
        link_obj = {"insert": "百度", "attributes": {"link": "https://baidu.com"}}
        assert parser._parse_text_object(link_obj) == "[百度](https://baidu.com)"

        # 文本样式
        bold_obj = {"insert": "加粗文本", "attributes": {"style-bold": True}}
        assert parser._parse_text_object(bold_obj) == "**加粗文本**"

        italic_obj = {"insert": "斜体文本", "attributes": {"style-italic": True}}
        assert parser._parse_text_object(italic_obj) == "*斜体文本*"

        code_obj = {"insert": "console.log()", "attributes": {"style-code": True}}
        assert parser._parse_text_object(code_obj) == "`console.log()`"

        strike_obj = {"insert": "划掉的内容", "attributes": {"style-strikethrough": True}}
        assert parser._parse_text_object(strike_obj) == "~~划掉的内容~~"

    def test_full_collaboration_content_parsing(self, parser, sample_collaboration_raw_dict):
        """测试从完整字典或 JSON 字符串端到端解析协作笔记"""
        # 测试字典形式输入
        result_from_dict = parser.parse_collaboration_content(sample_collaboration_raw_dict)
        assert "# 协作笔记主标题" in result_from_dict
        assert "> 这是一段引用文本" in result_from_dict
        assert "**粗体**" in result_from_dict
        assert "`行内代码`" in result_from_dict
        assert "$E=mc^2$" in result_from_dict
        assert "[[目标笔记]]" in result_from_dict
        assert "- [x] 已完成任务" in result_from_dict
        assert "- [ ] 未完成任务" in result_from_dict
        assert "def hello():" in result_from_dict
        assert "| 姓名 | 年龄 |" in result_from_dict
        assert "![图片](test_image.png)" in result_from_dict

        # 测试 JSON 字符串形式输入
        json_str = json.dumps(sample_collaboration_raw_dict, ensure_ascii=False)
        result_from_str = parser.parse_collaboration_content(json_str)
        assert result_from_str == result_from_dict

    def test_invalid_or_non_json_fallback(self, parser):
        """测试非 JSON 格式或异常数据结构时的优雅降级"""
        plain_text = "这不是一个有效的 JSON 结构"
        res = parser.parse_collaboration_content(plain_text)
        assert res == plain_text
