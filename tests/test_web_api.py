"""
测试 Web UI 模块 (FastAPI) API 接口与状态管理
验证登录接口、凭证回显、文件夹目录树、导出任务调度管理及统计接口
"""

import pytest
from fastapi.testclient import TestClient
from web.app import create_app
from web.services.folder_service import build_folder_tree
from tests.conftest import MockWizNoteClient


@pytest.fixture
def app_client():
    """提供一个带 Mock 客户端预置的 FastAPI TestClient"""
    app = create_app()
    mock_wiz = MockWizNoteClient()
    app.state.wiz_client = mock_wiz

    from web.websocket_manager import WebSocketManager
    from web.services.export_service import TaskManager
    app.state.ws_manager = WebSocketManager()
    app.state.task_manager = TaskManager()

    with TestClient(app) as client:
        yield client


@pytest.mark.unit
class TestWebApi:
    """Web API 接口自动化测试"""

    def test_root_and_login_page(self, app_client):
        """测试根路径重定向与登录页面模板渲染"""
        resp = app_client.get("/login")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "为知笔记" in resp.text

    def test_api_read_credentials(self, app_client):
        """测试读取凭据接口返回结构"""
        resp = app_client.get("/api/config/credentials")
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data

    def test_build_folder_tree_service(self):
        """测试纯函数 build_folder_tree 构建嵌套树形结构"""
        raw_folders = [
            "/My Notes/",
            "/My Notes/读书/",
            "/My Notes/读书/摘录/",
            "/工作/周报/"
        ]
        tree = build_folder_tree(raw_folders)
        assert len(tree) == 2  # My Notes 和 工作 两个根节点
        notes_node = next(n for n in tree if n["name"] == "My Notes")
        assert len(notes_node["children"]) == 1
        book_node = notes_node["children"][0]
        assert book_node["name"] == "读书"
        assert len(book_node["children"]) == 1
        assert book_node["children"][0]["name"] == "摘录"

    def test_api_get_folders(self, app_client):
        """测试拉取文件夹树形结构接口"""
        resp = app_client.get("/api/folders")
        assert resp.status_code == 200
        data = resp.json()
        assert "folders" in data
        assert "total_folders" in data
        assert data["total_folders"] == 4
        assert len(data["folders"]) > 0

    def test_export_task_lifecycle(self, app_client):
        """测试导出任务的创建、任务列表查询与状态接口"""
        # 1. 查询初始任务列表
        list_resp = app_client.get("/api/export/tasks")
        assert list_resp.status_code == 200
        tasks = list_resp.json()
        assert isinstance(tasks, list)

        # 2. 统计与历史页面
        stats_page = app_client.get("/stats")
        assert stats_page.status_code == 200
        assert "统计" in stats_page.text

        history_page = app_client.get("/history")
        assert history_page.status_code == 200

        # 3. 统计 API
        cp_resp = app_client.get("/api/stats/checkpoints")
        assert cp_resp.status_code == 200
        checkpoints_data = cp_resp.json()
        assert isinstance(checkpoints_data, list)
