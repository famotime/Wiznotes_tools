from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from web.deps import templates
from web.models import CompareRequest
from web.services.stats_service import (
    scan_export_directory,
    compare_notes,
    list_export_logs,
    read_export_log,
    list_checkpoints,
)

router = APIRouter()


def _get_username(request: Request) -> str:
    client = request.app.state.wiz_client
    if client and hasattr(client, 'config'):
        return client.config.get('wiz', {}).get('username', '')
    return ''


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="stats.html",
        context={
            "current_page": "stats",
            "logged_in": request.app.state.wiz_client is not None,
            "username": _get_username(request),
        }
    )


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="history.html",
        context={
            "current_page": "history",
            "logged_in": request.app.state.wiz_client is not None,
            "username": _get_username(request),
        }
    )


@router.post("/api/stats/scan")
async def api_scan(request: Request):
    export_dir = request.app.state.config.get("export_dir")
    return await scan_export_directory(export_dir)


@router.post("/api/stats/compare")
async def api_compare(req: CompareRequest, request: Request):
    client = request.app.state.wiz_client
    if not client:
        raise HTTPException(status_code=401, detail="未登录")
    export_dir = request.app.state.config.get("export_dir")
    exclude = req.exclude_folders or request.app.state.config.get("exclude_folders", [])
    return await compare_notes(client, export_dir, exclude)


@router.get("/api/stats/logs")
async def api_list_logs(request: Request):
    log_dir = request.app.state.config.get("log_dir")
    return await list_export_logs(log_dir)


@router.get("/api/stats/logs/{filename}")
async def api_read_log(filename: str, request: Request):
    log_dir = request.app.state.config.get("log_dir")
    content = await read_export_log(log_dir, filename)
    if not content:
        raise HTTPException(status_code=404, detail="日志文件不存在")
    return {"filename": filename, "content": content}


@router.get("/api/stats/checkpoints")
async def api_checkpoints(request: Request):
    export_dir = request.app.state.config.get("export_dir")
    return await list_checkpoints(export_dir)
