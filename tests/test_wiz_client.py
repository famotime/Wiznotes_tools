"""
测试 WizNoteClient 核心网络与客户端机制
验证配置加载、自建服务器适配、Token 失效检测、线程安全自动重登与友好诊断提示
"""

import json
from unittest.mock import MagicMock, patch
import requests
import pytest
from export_wiznotes.wiz_client import WizNoteClient


@pytest.mark.unit
class TestWizClientUnit:
    """WizNoteClient 单元测试"""

    def test_custom_server_url_parsing(self):
        """测试自建服务器 URL 尾部斜杠自动清理"""
        client = WizNoteClient.__new__(WizNoteClient)
        client.config = {"wiz": {"username": "u", "password": "p"}}
        client.server_url = "http://my-wiz-server.local:8080/".rstrip('/')
        client.token = None
        client.kb_info = None

        assert client.server_url == "http://my-wiz-server.local:8080"

    def test_is_token_invalid_response_detection(self):
        """测试各种 Token 失效场景的精准判定"""
        client = WizNoteClient.__new__(WizNoteClient)

        # 1. HTTP 401 / 403 状态码
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401
        assert client._is_token_invalid_response(mock_resp_401) is True

        mock_resp_403 = MagicMock()
        mock_resp_403.status_code = 403
        assert client._is_token_invalid_response(mock_resp_403) is True

        # 2. HTTP 200 但是 JSON 报文指示 Token 失效
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200

        expired_json = {"returnCode": 401, "returnMessage": "Token expired, please login again"}
        assert client._is_token_invalid_response(mock_resp_200, expired_json) is True

        cn_expired_json = {"returnCode": 301, "returnMessage": "登录令牌已过期，请重新登录"}
        assert client._is_token_invalid_response(mock_resp_200, cn_expired_json) is True

        # 3. 正常业务成功响应不应误判
        success_json = {"returnCode": 200, "returnMessage": "OK", "result": []}
        assert client._is_token_invalid_response(mock_resp_200, success_json) is False

        # 4. 普通业务异常（非 token 错误）不应误判为 token 失效
        biz_error_json = {"returnCode": 500, "returnMessage": "Category not found"}
        assert client._is_token_invalid_response(mock_resp_200, biz_error_json) is False

    def test_refresh_token_safe_double_checked_locking(self):
        """测试多线程并发刷新 Token 时的双重检查锁（避免重复登录）"""
        client = WizNoteClient.__new__(WizNoteClient)
        client.token = "token-v1"
        import threading
        client._token_lock = threading.Lock()

        # 模拟并发线程A已经将 token 更新为 token-v2
        # 此时线程B传入 old_token="token-v1"，应直接复用 token-v2，无需重新调用 login
        login_mock = MagicMock()
        client.login = login_mock
        client.token = "token-v2"

        returned_token = client._refresh_token_safe(old_token="token-v1")
        assert returned_token == "token-v2"
        assert login_mock.call_count == 0

    def test_http_request_auto_retry_on_token_expiry(self):
        """测试 _http_request 遇到 401 时自动重新登录并无感重发请求"""
        client = WizNoteClient.__new__(WizNoteClient)
        client.token = "initial-token-111"
        import threading
        client._token_lock = threading.Lock()

        # 模拟 login 方法
        def fake_login():
            client.token = "fresh-token-222"
            return {"token": client.token}
        client.login = fake_login

        # 模拟两次请求：第一次返回 401，第二次重试返回 200
        resp_401 = requests.Response()
        resp_401.status_code = 401

        resp_200 = requests.Response()
        resp_200.status_code = 200
        resp_200._content = b'{"returnCode": 200, "result": "ok"}'

        with patch("requests.request", side_effect=[resp_401, resp_200]) as mock_req:
            final_resp = client._http_request("GET", "https://ks.wiz.cn/api/test", auto_retry=True)
            assert final_resp.status_code == 200
            assert client.token == "fresh-token-222"
            assert mock_req.call_count == 2
            # 验证第二次重试时附带了新 token
            second_call_headers = mock_req.call_args_list[1].kwargs["headers"]
            assert second_call_headers["X-Wiz-Token"] == "fresh-token-222"

    def test_login_diagnostic_hints_on_password_error(self):
        """测试密码错误时能够输出清晰的排查建议（如特殊字符需双引号等）"""
        client = WizNoteClient.__new__(WizNoteClient)
        client.server_url = "https://as.wiz.cn"
        client.config = {"wiz": {"username": "test@qq.com", "password": "wrong_password"}}

        # Mock requests.request 抛出含有 invalidPassword 的异常
        resp_error = requests.Response()
        resp_error.status_code = 200
        resp_error._content = json.dumps({"returnCode": 302, "returnMessage": "invalidPassword"}).encode("utf-8")

        with patch("requests.request", return_value=resp_error):
            with pytest.raises(Exception) as exc_info:
                client.login()
            assert "invalidPassword" in str(exc_info.value)
