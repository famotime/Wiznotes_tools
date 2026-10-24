"""
结合本机安装的 WizNote 客户端及真实云端服务环境的集成测试套件
验证本机客户端安装路径、注册表版本、AppData 数据目录、真实账号登录与API交互、以及本地已导出数据健康度
"""

import os
import sys
from pathlib import Path
import pytest
from export_wiznotes.wiz_client import WizNoteClient
from export_wiznotes.compare_notes_in_folders import parse_record_file


@pytest.mark.real_env
class TestRealWizNoteEnvironment:
    """真实本机环境测试集"""

    def test_local_wiznote_desktop_installation(self, real_wiznote_system_environment):
        """测试本机为知笔记桌面客户端安装环境检测"""
        env = real_wiznote_system_environment
        if not env["installed"]:
            pytest.skip("本机未检测到为知笔记客户端安装")

        install_path = Path(env["install_path"])
        assert install_path.exists(), f"客户端程序不存在: {install_path}"
        assert install_path.is_file(), f"客户端不是有效文件: {install_path}"
        assert install_path.stat().st_size > 0, "客户端执行程序文件为空"

        # 如果检测到了注册表版本信息
        if env["version"]:
            assert env["version"] == "0.1.107"

    def test_local_wiznote_appdata_directory(self, real_wiznote_system_environment):
        """测试本机当前用户 AppData Roaming 中的 WizNote 用户配置与缓存目录"""
        env = real_wiznote_system_environment
        if not env["roaming_dir"]:
            pytest.skip("未找到本机 WizNote Roaming 目录")

        roaming_dir = Path(env["roaming_dir"])
        assert roaming_dir.exists() and roaming_dir.is_dir()

        # 检查关键数据文件或子目录
        expected_items = ["blob_storage", "Cache", "Local Storage", "Preferences"]
        found = [name for name in expected_items if (roaming_dir / name).exists()]
        assert len(found) >= 2, f"WizNote Roaming 目录结构不完整: 仅找到 {found}"

    def test_real_server_login_and_kb_info(self, real_wiznote_system_environment):
        """结合本机真实 .env 凭证，测试连接官方为知笔记云服务的登录与鉴权"""
        env = real_wiznote_system_environment
        if not env["has_real_credentials"]:
            pytest.skip("本机未配置真实有效 .env 凭据")

        client = WizNoteClient()
        login_res = client.login()

        assert client.token is not None and len(client.token) > 10
        assert client.kb_info is not None
        assert "kbServer" in client.kb_info
        assert "kbGuid" in client.kb_info
        assert "userGuid" in client.kb_info
        assert client.config["wiz"]["username"] == env["username"]

    def test_real_server_get_folders_and_tags(self, real_wiznote_system_environment):
        """在真实服务环境下获取在线文件夹列表及全量标签"""
        env = real_wiznote_system_environment
        if not env["has_real_credentials"]:
            pytest.skip("本机未配置真实有效 .env 凭据")

        client = WizNoteClient()
        client.login()

        # 1. 验证获取文件夹列表
        folders = client.get_folders()
        assert isinstance(folders, list)
        assert len(folders) > 0, "真实账号中应至少包含一个笔记文件夹"
        # 常见默认文件夹断言
        assert any("My Notes" in f or "My Drafts" in f or "My Emails" in f for f in folders)

        # 2. 验证获取标签映射
        tag_map = client.get_all_tags()
        assert isinstance(tag_map, dict)
        assert len(tag_map) > 0, "真实账号应能拉取到已有标签"

    def test_real_server_fetch_notes_sample(self, real_wiznote_system_environment):
        """测试从真实服务的 /My Drafts/ 文件夹拉取笔记列表"""
        env = real_wiznote_system_environment
        if not env["has_real_credentials"]:
            pytest.skip("本机未配置真实有效 .env 凭据")

        client = WizNoteClient()
        client.login()

        notes = client.get_note_list("/My Drafts/", count=5)
        assert isinstance(notes, list)
        if len(notes) > 0:
            first_note = notes[0]
            assert "docGuid" in first_note
            assert "title" in first_note

    def test_local_output_artifacts_health(self):
        """检查工作区中实际已导出的笔记与目录清单健康度"""
        project_root = Path(__file__).resolve().parent.parent
        output_dir = project_root / "export_wiznotes" / "output"

        if not output_dir.exists():
            pytest.skip("未找到本地 export_wiznotes/output 目录")

        # 1. 检查为知笔记目录.log
        log_file = output_dir / "为知笔记目录.log"
        if log_file.exists():
            folders = [line.strip() for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            assert len(folders) > 0
            assert all(f.startswith("/") for f in folders)

        # 2. 检查已导出笔记的 YAML Front Matter
        # 搜索 output 下的一个真实已导出的 .md 文件
        md_files = list(output_dir.glob("*/*.md"))
        if md_files:
            sample_md = md_files[0]
            content = sample_md.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{sample_md.name} 缺少开头的 YAML 分隔符 ---"
            assert "docGuid:" in content, f"{sample_md.name} 缺少 docGuid 元数据"
            assert "title:" in content, f"{sample_md.name} 缺少 title 元数据"
