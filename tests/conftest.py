"""
Pytest 共享配置与 Fixtures
包含 Mock 客户端、临时工作区、示例数据、以及本机真实 WizNote 环境探测器
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path
import pytest
from dotenv import dotenv_values

# 将项目根目录加入模块搜索路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from export_wiznotes.wiz_client import WizNoteClient
from export_wiznotes.note_exporter import NoteExporter


@pytest.fixture
def temp_export_dir():
    """提供一个测试专用的临时导出目录，测试结束后自动清理"""
    temp_dir = tempfile.mkdtemp(prefix="wiznote_test_")
    path = Path(temp_dir)
    yield path
    shutil.rmtree(temp_dir, ignore_errors=True)


class MockWizNoteClient:
    """可用于单元测试的 WizNoteClient 模拟桩"""

    def __init__(self, username="test_user@example.com", password="test_password", server_url="https://as.wiz.cn"):
        self.server_url = server_url.rstrip('/')
        self.config = {
            "wiz": {
                "username": username,
                "password": password,
                "server_url": self.server_url
            }
        }
        self.token = "mock-token-initial-123456"
        self.kb_info = {
            "kbServer": "https://ks.wiz.cn",
            "kbGuid": "mock-kb-guid-8888",
            "userGuid": "mock-user-guid-9999"
        }
        self.login_call_count = 0
        self.download_note_call_count = 0

    def login(self):
        self.login_call_count += 1
        self.token = f"mock-token-refreshed-{self.login_call_count}"
        return {
            "token": self.token,
            "kbServer": self.kb_info["kbServer"],
            "kbGuid": self.kb_info["kbGuid"],
            "userGuid": self.kb_info["userGuid"]
        }

    def get_folders(self):
        return [
            "/My Notes/",
            "/My Drafts/",
            "/技术文档/",
            "/个人日志/"
        ]

    def get_all_tags(self):
        return {
            "tag-guid-1": "Python",
            "tag-guid-2": "工作笔记",
            "tag-guid-3": "待办"
        }

    def get_note_list(self, folder, count=100, max_notes=None):
        return [
            {
                "docGuid": "doc-guid-101",
                "title": "测试笔记1",
                "category": folder,
                "created": 1620000000,
                "modified": 1620003600
            },
            {
                "docGuid": "doc-guid-102",
                "title": "测试笔记2.md",
                "category": folder,
                "created": 1620007200,
                "modified": 1620010800
            }
        ]

    def _get_notes_by_order(self, folder, count=100, order="desc"):
        return self.get_note_list(folder, count)

    def download_note(self, doc_guid):
        self.download_note_call_count += 1
        return {
            "info": {
                "docGuid": doc_guid,
                "title": f"下载的笔记-{doc_guid}",
                "category": "/My Notes/",
                "created": 1620000000000,
                "modified": 1620003600000,
                "tags": "tag-guid-1*tag-guid-2",
                "type": "document"
            },
            "html": "<html><body><!--headTrap<body></body>--><h1>测试标题</h1><p>正文内容第一段。</p></body></html>",
            "resources": [],
            "type": "document"
        }

    def download_resource(self, doc_guid, resource_info, save_path):
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(b"mock binary resource content")
        return True

    def get_note_attachments(self, doc_guid):
        return []

    def download_attachment(self, doc_guid, att_guid, save_path):
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(b"mock binary attachment content")
        return True


@pytest.fixture
def mock_client():
    """提供一个标准的 Mock 客户端实例"""
    return MockWizNoteClient()


@pytest.fixture
def sample_collaboration_raw_dict():
    """提供一个符合为知笔记 WebSocket Delta 块格式的样例字典"""
    return {
        "data": {
            "data": {
                "blocks": [
                    {
                        "type": "text",
                        "id": "b1",
                        "heading": 1,
                        "text": [{"insert": "协作笔记主标题"}]
                    },
                    {
                        "type": "text",
                        "id": "b2",
                        "quoted": True,
                        "text": [{"insert": "这是一段引用文本"}]
                    },
                    {
                        "type": "text",
                        "id": "b3",
                        "text": [
                            {"insert": "普通文本带"},
                            {"insert": "粗体", "attributes": {"style-bold": True}},
                            {"insert": "与"},
                            {"insert": "行内代码", "attributes": {"style-code": True}},
                            {"insert": "以及"},
                            {"insert": "公式", "attributes": {"type": "math", "tex": "E=mc^2"}},
                            {"insert": "与"},
                            {"insert": "链接", "attributes": {"type": "wiki-link", "name": "目标笔记.md"}}
                        ]
                    },
                    {
                        "type": "list",
                        "id": "b4",
                        "ordered": False,
                        "checkbox": "checked",
                        "level": 1,
                        "text": [{"insert": "已完成任务"}]
                    },
                    {
                        "type": "list",
                        "id": "b5",
                        "ordered": False,
                        "checkbox": "unchecked",
                        "level": 1,
                        "text": [{"insert": "未完成任务"}]
                    },
                    {
                        "type": "code",
                        "id": "b6",
                        "language": "python",
                        "children": ["c1", "c2"]
                    },
                    {
                        "type": "table",
                        "id": "b7",
                        "cols": 2,
                        "children": ["t1", "t2", "t3", "t4"]
                    },
                    {
                        "type": "embed",
                        "id": "b8",
                        "embedType": "image",
                        "embedData": {"src": "test_image.png"}
                    },
                    {
                        "type": "embed",
                        "id": "b9",
                        "embedType": "hr"
                    }
                ],
                "c1": [{"text": [{"insert": "def hello():"}]}],
                "c2": [{"text": [{"insert": "    return "}, {"insert": "'world'"}]}],
                "t1": [{"text": [{"insert": "姓名"}]}],
                "t2": [{"text": [{"insert": "年龄"}]}],
                "t3": [{"text": [{"insert": "张三"}]}],
                "t4": [{"text": [{"insert": "18"}]}]
            }
        }
    }


@pytest.fixture(scope="session")
def real_wiznote_system_environment():
    """
    探测本机真实环境信息：
    - 是否安装了为知笔记客户端（路径、版本号）
    - 是否存在当前用户 Roaming 数据目录
    - 是否存在包含有效凭证的 .env 文件
    """
    env_info = {
        "installed": False,
        "install_path": None,
        "version": None,
        "roaming_dir": None,
        "has_real_credentials": False,
        "username": None
    }

    # 1. 检查客户端可执行程序
    common_paths = [
        Path(r"D:\Program Files\WizNote\WizNote.exe"),
        Path(r"C:\Program Files\WizNote\WizNote.exe"),
        Path(r"C:\Program Files (x86)\WizNote\WizNote.exe"),
    ]
    for p in common_paths:
        if p.exists():
            env_info["installed"] = True
            env_info["install_path"] = str(p)
            break

    # 2. 检查注册表版本 (Windows)
    if sys.platform == "win32":
        try:
            import winreg
            reg_key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\292a6a38-ef6a-571f-8505-902b7a7b3409"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key) as key:
                val, _ = winreg.QueryValueEx(key, "DisplayVersion")
                env_info["version"] = val
                env_info["installed"] = True
        except Exception:
            pass

    # 3. 检查 Roaming 数据目录
    roaming = os.environ.get("APPDATA")
    if roaming:
        wiz_roaming = Path(roaming) / "WizNote"
        if wiz_roaming.exists():
            env_info["roaming_dir"] = str(wiz_roaming)

    # 4. 检查 .env 真实凭证
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        env_vals = dotenv_values(env_path)
        u = env_vals.get("WIZ_USERNAME")
        p = env_vals.get("WIZ_PASSWORD")
        if u and p and not u.startswith("your_") and not p.startswith("your_"):
            env_info["has_real_credentials"] = True
            env_info["username"] = u

    return env_info
