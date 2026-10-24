"""
测试文件名与路径处理工具
验证 Windows 非法字符清洗、带点号文件名安全处理、超长文件名截断及模块间一致性
"""

from pathlib import Path
import pytest
from export_wiznotes.note_exporter import NoteExporter
from export_wiznotes.compare_notes_in_folders import get_valid_filename as compare_get_valid_filename


@pytest.fixture
def exporter():
    return NoteExporter(client=None)


@pytest.mark.unit
class TestFilenameUtils:
    """文件名合法化单元测试"""

    def test_clean_invalid_windows_chars(self, exporter):
        """测试清洗 Windows 非法字符: \\ / : * ? \" < > |"""
        raw_name = r'测试\文件名/包含:星号*问号?双引号"尖括号<大于>竖线|结束'
        cleaned = exporter._get_valid_filename(raw_name)
        for char in r'\/:*?"<>|':
            assert char not in cleaned
        assert cleaned == "测试_文件名_包含_星号_问号_双引号_尖括号_大于_竖线_结束"

    def test_filename_with_dots_preserved(self, exporter):
        """核心避坑原则：文件名中含有 '.' 时（如版本号、技术名词），不能被误截断或丢失扩展名"""
        version_title = "v1.0.2.Release_Notes"
        assert exporter._get_valid_filename(version_title) == "v1.0.2.Release_Notes"

        ip_title = "服务器IP 192.168.1.1 配置说明"
        assert exporter._get_valid_filename(ip_title) == "服务器IP 192.168.1.1 配置说明"

    def test_empty_or_whitespace_filename(self, exporter):
        """测试空白或全是空格的文件名兜底返回下划线"""
        assert exporter._get_valid_filename("") == "_"
        assert exporter._get_valid_filename("    ") == "_"
        assert exporter._get_valid_filename("///:::***") == "_________"

    def test_path_object_input_support(self, exporter):
        """测试输入为 Path 对象与 str 时的等价性"""
        str_res = exporter._get_valid_filename("普通笔记名称.txt")
        path_res = exporter._get_valid_filename(Path("some/folder/普通笔记名称.txt"))
        assert str_res == path_res == "普通笔记名称.txt"

    def test_overlong_filename_truncation_without_ext(self, exporter):
        """测试没有合法后缀的超长文件名截断为 200 字符内并追加 '...'"""
        long_name = "长" * 250
        truncated = exporter._get_valid_filename(long_name)
        assert len(truncated) <= 200
        assert truncated.endswith("...")
        assert truncated == "长" * 197 + "..."

    def test_overlong_filename_truncation_with_valid_ext(self, exporter):
        """测试带有短合法扩展名的超长文件名截断时保留扩展名"""
        long_base = "文档" * 110  # 220 字符
        long_name = f"{long_base}.markdown"
        truncated = exporter._get_valid_filename(long_name)
        assert len(truncated) <= 200
        assert truncated.endswith(".markdown")
        assert "..." in truncated

    def test_consistency_with_compare_module(self, exporter):
        """验证 NoteExporter._get_valid_filename 与 compare_notes_in_folders.get_valid_filename 行为完全一致"""
        test_cases = [
            "普通笔记标题",
            r"非法字符<>:\"/\\|?*",
            "Anthropic’s_$1B_to_$19B_growth_run.md",
            "Python 3.10.4 升级指南",
            "   前置空格和后置空格   ",
            "A" * 250,
            ("B" * 230) + ".txt",
            ""
        ]
        for case in test_cases:
            exporter_res = exporter._get_valid_filename(case)
            compare_res = compare_get_valid_filename(case)
            assert exporter_res == compare_res, f"不一致的测试用例: {case!r} (exporter: {exporter_res!r}, compare: {compare_res!r})"
