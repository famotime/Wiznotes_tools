"""
测试断点续传与文件截断清理机制
验证 .export_checkpoint.json 保存与读取、跳过已导出笔记、点号文件重新导出判定与安全清理
"""

import json
from pathlib import Path
import pytest
from export_wiznotes.note_exporter import NoteExporter


@pytest.fixture
def exporter(mock_client):
    return NoteExporter(client=mock_client)


@pytest.mark.unit
class TestCheckpointAndCleanup:
    """断点与清理单元测试"""

    def test_save_and_load_checkpoint(self, exporter, temp_export_dir):
        """测试保存与加载断点文件"""
        cp_file = temp_export_dir / ".export_checkpoint.json"
        test_guids = {"guid-001", "guid-002", "guid-003"}

        exporter._save_checkpoint(cp_file, test_guids)
        assert cp_file.exists()

        data = json.loads(cp_file.read_text(encoding="utf-8"))
        assert set(data["exported_guids"]) == test_guids
        assert "timestamp" in data

    def test_extract_doc_guid_from_file(self, exporter, temp_export_dir):
        """测试从 Markdown 文件的 YAML Front Matter 中准确提取 docGuid"""
        test_file = temp_export_dir / "sample_note.md"
        content = (
            "---\n"
            "title: 示例文档\n"
            "docGuid: 5724309e-d1a6-11e1-a88b-00237def97cc\n"
            "category: /My Notes/\n"
            "---\n\n"
            "# 正文内容"
        )
        test_file.write_text(content, encoding="utf-8")

        guid = exporter._extract_doc_guid_from_file(test_file)
        assert guid == "5724309e-d1a6-11e1-a88b-00237def97cc"

        # 空文件或无 guid 的文件测试
        no_guid_file = temp_export_dir / "no_guid.md"
        no_guid_file.write_text("无元数据的纯文本", encoding="utf-8")
        assert exporter._extract_doc_guid_from_file(no_guid_file) is None

    def test_cleanup_old_truncated_files_safety(self, exporter, temp_export_dir):
        """测试清理旧截断文件：仅当 docGuid 一致时安全删除，不一致时绝不误删"""
        same_guid = "5724309e-d1a6-11e1-a88b-00237def97cc"
        diff_guid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        # 场景一：docGuid 一致的截断文件（应被清理）
        # 完整文件: "v1.0.2 发布日志.md"
        # 截断文件: "v1.md"
        full_file = temp_export_dir / "v1.0.2 发布日志.md"
        truncated_file = temp_export_dir / "v1.md"

        full_file.write_text(f"---\ntitle: v1.0.2 发布日志\ndocGuid: {same_guid}\n---\n", encoding="utf-8")
        truncated_file.write_text(f"---\ntitle: v1\ndocGuid: {same_guid}\n---\n", encoding="utf-8")

        assert truncated_file.exists()
        exporter._cleanup_old_truncated_files(temp_export_dir, "v1.0.2 发布日志")
        assert not truncated_file.exists(), "docGuid 一致的截断文件应被成功删除"

        # 场景二：docGuid 不一致（属于两篇不同笔记，严禁误删）
        other_truncated_file = temp_export_dir / "v2.md"
        other_full_file = temp_export_dir / "v2.0.0 升级指南.md"

        other_full_file.write_text(f"---\ntitle: v2.0.0 升级指南\ndocGuid: {same_guid}\n---\n", encoding="utf-8")
        other_truncated_file.write_text(f"---\ntitle: v2 真实独立笔记\ndocGuid: {diff_guid}\n---\n", encoding="utf-8")

        exporter._cleanup_old_truncated_files(temp_export_dir, "v2.0.0 升级指南")
        assert other_truncated_file.exists(), "docGuid 不匹配的不同笔记文件绝不可被误删！"

    def test_export_notes_skips_already_exported_and_reexports_dot_files(self, exporter, temp_export_dir, monkeypatch):
        """测试 export_notes 遇到已在 checkpoint 的笔记时能够跳过，并在开启 reexport_dot_files 时重新导出带点笔记"""
        notes = [
            {"docGuid": "g1", "title": "普通笔记已导出"},
            {"docGuid": "g2", "title": "版本号_v1.0.1_重要升级"},
            {"docGuid": "g3", "title": "轻量笔记.md"}
        ]
        folder_dir = temp_export_dir / "测试目录"
        folder_dir.mkdir(parents=True, exist_ok=True)
        cp_file = folder_dir / ".export_checkpoint.json"
        exporter._save_checkpoint(cp_file, {"g1", "g2", "g3"})

        monkeypatch.setattr(
            "export_wiznotes.note_exporter.get_all_notes_in_folder",
            lambda client, folder: notes
        )

        exported_calls = []
        monkeypatch.setattr(
            exporter,
            "export_single_note",
            lambda note, path, tag_map, reexport_dot_files=False: (exported_calls.append(note["docGuid"]) or True)
        )

        # 1. 默认情况下全部跳过
        exporter.export_notes(folder="/测试目录/", export_dir=str(temp_export_dir), resume=True, reexport_dot_files=False)
        assert len(exported_calls) == 0, "全部在 checkpoint 中的笔记应被跳过"

        # 2. 开启 reexport_dot_files=True 时，只有带有 '.' 且非 .md 的笔记会被重新导出
        exported_calls.clear()
        exporter.export_notes(folder="/测试目录/", export_dir=str(temp_export_dir), resume=True, reexport_dot_files=True)
        assert exported_calls == ["g2"], "只有含点号且非标准扩展名的 g2 应该被重新触发导出"
