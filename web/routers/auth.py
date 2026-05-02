import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from dotenv import dotenv_values

from web.deps import templates
from web.models import LoginRequest, LoginResponse, ConfigUpdateRequest

router = APIRouter()


def _get_username(request: Request) -> str:
    client = request.app.state.wiz_client
    if client and hasattr(client, 'config'):
        return client.config.get('wiz', {}).get('username', '')
    return ''


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    if request.app.state.wiz_client:
        return RedirectResponse("/folders", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={
            "current_page": "login",
            "logged_in": request.app.state.wiz_client is not None,
            "username": _get_username(request),
        }
    )


@router.post("/api/login", response_model=LoginResponse)
async def api_login(req: LoginRequest, request: Request):
    def _do_login():
        from export_wiznotes import WizNoteClient
        client = WizNoteClient.__new__(WizNoteClient)
        client.config = {"wiz": {"username": req.username, "password": req.password}}
        client.token = None
        client.kb_info = None
        client.login()
        return client

    try:
        client = await asyncio.to_thread(_do_login)
        request.app.state.wiz_client = client
        return LoginResponse(
            success=True, message="登录成功",
            username=req.username,
            kb_server=client.kb_info.get('kbServer', ''),
        )
    except Exception as e:
        return LoginResponse(success=False, message=f"登录失败: {e}")


@router.get("/api/config/credentials")
async def api_read_credentials(request: Request):
    """从 .env 文件读取凭据并返回，用于填充登录表单"""
    env_path = request.app.state.config.get("env_path")
    try:
        env = dotenv_values(env_path)
        username = env.get("WIZ_USERNAME", "")
        password = env.get("WIZ_PASSWORD", "")
        if not username:
            return {"success": False, "message": ".env 文件中未找到 WIZ_USERNAME"}
        return {"success": True, "username": username, "password": password}
    except Exception as e:
        return {"success": False, "message": f"读取配置文件失败: {e}"}


@router.post("/api/logout")
async def api_logout(request: Request):
    request.app.state.wiz_client = None
    return {"success": True, "message": "已登出"}


@router.get("/api/status")
async def api_status(request: Request):
    client = request.app.state.wiz_client
    if client:
        return {
            "logged_in": True,
            "username": _get_username(request),
            "kb_server": client.kb_info.get('kbServer', '') if client.kb_info else '',
        }
    return {"logged_in": False, "username": None, "kb_server": None}


@router.get("/api/config")
async def api_get_config(request: Request):
    cfg = request.app.state.config.copy()
    cfg["env_file_exists"] = __import__('pathlib').Path(cfg["env_path"]).exists()
    return cfg


@router.patch("/api/config")
async def api_update_config(req: ConfigUpdateRequest, request: Request):
    cfg = request.app.state.config
    if req.export_dir is not None:
        cfg["export_dir"] = req.export_dir
    if req.max_workers is not None:
        cfg["max_workers"] = req.max_workers
    if req.max_notes is not None:
        cfg["max_notes"] = req.max_notes
    if req.reexport_dot_files is not None:
        cfg["reexport_dot_files"] = req.reexport_dot_files
    if req.exclude_folders is not None:
        cfg["exclude_folders"] = req.exclude_folders
    return cfg
