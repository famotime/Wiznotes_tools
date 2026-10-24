"""
测试 HTML 与 Markdown 内容转换与清洗逻辑
包含 body 提取、HTML 转文本、Markdownify 转义修复、外层代码块剥离及 YAML Front Matter 注入
"""

import pytest
from export_wiznotes.note_exporter import NoteExporter


@pytest.fixture
def exporter():
    return NoteExporter(client=None)


@pytest.mark.unit
class TestHtmlMarkdownProcessing:
    """HTML与Markdown处理测试集"""

    def test_extract_body_content_with_headtrap_comment(self, exporter):
        """测试为知笔记特有的 headTrap 注释不会导致非贪婪提前截断"""
        html_with_headtrap = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <!--headTrap<body></body><style class="wiz-custom-style">body{font-size:14px;}</style>-->
        </head>
        <body style="margin: 0;">
            <h1>真实笔记主标题</h1>
            <p>这是正文的第一段内容，不能被截断丢弃。</p>
        </body>
        </html>
        """
        extracted = exporter._extract_body_content(html_with_headtrap)
        assert "真实笔记主标题" in extracted
        assert "这是正文的第一段内容" in extracted
        assert "headTrap" not in extracted
        assert "<body style=" not in extracted
        assert "</body>" not in extracted

    def test_extract_body_content_fallback_when_no_body_tag(self, exporter):
        """测试没有 <body> 标签时原样返回内容"""
        fragment = "<div>单纯的 HTML 片段</div>"
        assert exporter._extract_body_content(fragment) == fragment
        assert exporter._extract_body_content("") == ""
        assert exporter._extract_body_content(None) == ""

    def test_fix_html_to_text_conversion(self, exporter):
        """测试 HTML 转纯文本，包括实体解析、块级标签换行和空行压缩"""
        html_doc = """
        <h1>主标题&amp;副标题</h1>
        <p>第一段文本&nbsp;&nbsp;含有&gt;大于号与&lt;小于号。</p>
        <br>
        <div>
            <ul>
                <li>列表条目 1</li>
                <li>列表条目 2</li>
            </ul>
        </div>
        """
        text = exporter._fix_html_to_text_conversion(html_doc)
        assert "主标题&副标题" in text
        assert "第一段文本  含有>大于号与<小于号。" in text
        assert "列表条目 1" in text
        assert "列表条目 2" in text
        # 确保没有残留 HTML 标签
        assert "<p>" not in text
        assert "<li>" not in text
        assert "<div>" not in text

    def test_fix_markdown_escapes(self, exporter):
        """测试修复 markdownify 自动转义图片和超链接中的下划线"""
        raw_md = (
            "这里是前文内容。\n\n"
            "![示例图片](assets/my\\_note\\_assets\\_pic\\_1.png)\n\n"
            "参考链接: [项目地址](https://github.com/my\\_org/my\\_repo\\_tools)\n"
        )
        fixed_md = exporter._fix_markdown_escapes(raw_md)
        assert "![示例图片](assets/my_note_assets_pic_1.png)" in fixed_md
        assert "[项目地址](https://github.com/my_org/my_repo_tools)" in fixed_md
        assert r"\_" not in fixed_md

    def test_clean_markdown_wrapping_removes_outer_fence(self, exporter):
        """测试当协作笔记被错误地包裹在外层 ``` 中时，能够智能剥离外层代码块"""
        fenced_md = """```markdown
# 笔记大标题

- 列表项一
- 列表项二

[参考链接](https://example.com)
```"""
        cleaned = exporter._clean_markdown_wrapping(fenced_md)
        assert not cleaned.startswith("```")
        assert not cleaned.endswith("```")
        assert "# 笔记大标题" in cleaned
        assert "- 列表项一" in cleaned

    def test_clean_markdown_wrapping_preserves_pure_code(self, exporter):
        """测试纯代码段不包含常见 markdown 标记时不应被误剥离"""
        pure_code = """```python
import os
import sys

def main():
    print("Hello World")
```"""
        cleaned = exporter._clean_markdown_wrapping(pure_code)
        # 纯代码块没有标题/列表/链接等富文本标记，应保留代码块包装
        assert cleaned.startswith("```")
        assert cleaned.endswith("```")

    def test_add_front_matter(self, exporter):
        """测试 YAML Front Matter 生成及元数据转换"""
        note_info = {
            "title": "测试元数据笔记",
            "docGuid": "test-guid-12345",
            "category": "/工作/项目A/",
            "url": "https://example.com/source",
            "author": "Alice",
            "keywords": "测试, 质量",
            "created": 1620000000000,   # 毫秒时间戳: 2021-05-03
            "modified": 1620003600000,  # 毫秒时间戳
            "accessed": 1620007200,     # 秒级时间戳
            "tags": "t1*t2",
            "resources": ["res1.png", "res2.pdf"],
            "abstract": "笔记摘要概述",
            "version": 3,
            "readCount": 12,
            "attachmentCount": 1
        }
        tag_map = {
            "t1": "核心架构",
            "t2": "后端开发"
        }
        md_body = "## 章节一\n\n正文在此。"
        result = exporter._add_front_matter(md_body, note_info, tag_map)

        assert result.startswith("---\n")
        assert "title: 测试元数据笔记" in result
        assert "docGuid: test-guid-12345" in result
        assert "category: /工作/项目A/" in result
        assert "author: Alice" in result
        assert "tags: [核心架构, 后端开发]" in result
        assert "resources: [res1.png, res2.pdf]" in result
        assert "abstract: 笔记摘要概述" in result
        assert "version: 3" in result
        assert "readCount: 12" in result
        assert "attachmentCount: 1" in result
        # 验证时间戳已转换成格式化日期
        assert "2021-" in result
        # 验证正文在 Front Matter 之后
        assert "---\n\n## 章节一\n\n正文在此。" in result
