"""
测试目录日志读取、本地与在线笔记比对分析、以及基于差异清单的靶向补导
"""

from pathlib import Path
import pytest
from get_wiz_notes import read_folders_from_log, retry_failed_notes_from_diff
from export_wiznotes.compare_notes_in_folders import compare_notes_in_folders, parse_record_file


@pytest.mark.unit
class TestCompareAndDiff:
    """差异对比与靶向重试单元测试"""

    def test_read_folders_from_log_multi_format_tolerant(self, temp_export_dir):
        """测试 read_folders_from_log 兼容纯路径、统计文本、自动忽略笔记行及注释"""
        log_content = """
        # 这是为知笔记目录导出日志注释
        /My Notes/
        /My Drafts

        # 兼容 folders & notes.txt 格式:
        文件夹: /工作/周报/  笔记数: 15
        - 2024-05-01 周报
        - 2024-05-08 周报

        文件夹: /个人/读书笔记/
        - 深入理解计算机系统

        /My Notes/
        """
        log_path = temp_export_dir / "为知笔记目录.log"
        log_path.write_text(log_content, encoding="utf-8")

        folders = read_folders_from_log(log_path)

        # 验证提取出的文件夹路径且无重复
        expected_folders = [
            "/My Notes/",
            "/My Drafts/",
            "/工作/周报/",
            "/个人/读书笔记/"
        ]
        assert folders == expected_folders

    def test_compare_notes_in_folders_diff_generation(self, temp_export_dir):
        """测试比对在线笔记清单与本地导出笔记清单，验证 compare_diff.txt 生成"""
        online_file = temp_export_dir / "folders & notes.txt"
        exported_file = temp_export_dir / "exported_md_files.txt"

        online_content = (
            "文件夹: /项目A/  笔记数: 2\n"
            "- 设计方案.md\n"
            "- 会议纪要.md\n"
            "\n"
            "文件夹: /项目B/  笔记数: 1\n"
            "- 架构总览.md\n"
        )
        # 本地导出的清单中，/项目A/ 缺少了 '会议纪要'（即漏导）
        # /项目B/ 多了一个 '遗留旧文件'
        exported_content = (
            "文件夹: /项目A/  笔记数: 1\n"
            "- 设计方案.md\n"
            "\n"
            "文件夹: /项目B/  笔记数: 2\n"
            "- 架构总览.md\n"
            "- 遗留旧文件.md\n"
        )

        online_file.write_text(online_content, encoding="utf-8")
        exported_file.write_text(exported_content, encoding="utf-8")

        compare_notes_in_folders(online_file, exported_file)

        diff_file = temp_export_dir / "compare_diff.txt"
        assert diff_file.exists()

        diff_text = diff_file.read_text(encoding="utf-8")
        assert "文件夹: /项目A/" in diff_text
        assert "仅在记录文件1（在线笔记）中:" in diff_text
        assert "- 会议纪要" in diff_text

        assert "文件夹: /项目B/" in diff_text
        assert "仅在记录文件2（导出笔记）中:" in diff_text
        assert "- 遗留旧文件" in diff_text

    def test_retry_failed_notes_from_diff(self, temp_export_dir, mock_client, monkeypatch):
        """测试靶向补导：根据 compare_diff.txt 精准补导漏导笔记"""
        diff_file = temp_export_dir / "compare_diff.txt"
        diff_content = (
            "文件夹: /测试目录/\n"
            "  仅在记录文件1（在线笔记）中:\n"
            "    - 漏导的重要笔记\n"
            "\n"
        )
        diff_file.write_text(diff_content, encoding="utf-8")

        # Mock 获取文件夹下在线笔记
        online_notes = [
            {"docGuid": "g-normal", "title": "已导出的笔记"},
            {"docGuid": "g-missing", "title": "漏导的重要笔记"}
        ]
        monkeypatch.setattr(
            "get_wiz_notes.get_all_notes_in_folder",
            lambda client, folder: online_notes
        )

        # 跟踪导出的 docGuid
        exported_guid_calls = []
        monkeypatch.setattr(
            "export_wiznotes.note_exporter.NoteExporter.export_single_note",
            lambda self, note, path, tag_map: (exported_guid_calls.append(note["docGuid"]) or True)
        )

        retry_failed_notes_from_diff(diff_file, mock_client, temp_export_dir)

        # 验证只有漏导的笔记 g-missing 被靶向补导
        assert exported_guid_calls == ["g-missing"]

        # 验证 checkpoint 正确记录补导的笔记
        target_cp_file = temp_export_dir / "测试目录" / ".export_checkpoint.json"
        assert target_cp_file.exists()
