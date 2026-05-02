from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse

from web.deps import templates
from web.models import ExportRequest
from web.services.export_service import TaskManager

router = APIRouter()


def _get_username(request: Request) -> str:
    client = request.app.state.wiz_client
    if client and hasattr(client, 'config'):
        return client.config.get('wiz', {}).get('username', '')
    return ''


@router.get("/export", response_class=HTMLResponse)
async def export_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="export.html",
        context={
            "current_page": "export",
            "logged_in": request.app.state.wiz_client is not None,
            "username": _get_username(request),
        }
    )


@router.post("/api/export")
async def api_start_export(req: ExportRequest, request: Request):
    client = request.app.state.wiz_client
    if not client:
        raise HTTPException(status_code=401, detail="未登录")

    task_mgr = request.app.state.task_manager
    ws_mgr = request.app.state.ws_manager

    # Build config with credentials for the export thread
    config = request.app.state.config.copy()
    config["_credentials"] = client.config.get("wiz", {})
    if req.max_notes is not None:
        config["max_notes"] = req.max_notes
    if req.max_workers is not None:
        config["max_workers"] = req.max_workers
    if req.reexport_dot_files is not None:
        config["reexport_dot_files"] = req.reexport_dot_files

    task_id = task_mgr.start_export(req.folders, config, ws_mgr)
    return {"task_id": task_id, "status": "pending", "message": "导出任务已启动"}


@router.get("/api/export/tasks")
async def api_list_tasks(request: Request):
    task_mgr = request.app.state.task_manager
    return task_mgr.get_all_tasks()


@router.get("/api/export/tasks/{task_id}")
async def api_get_task(task_id: str, request: Request):
    task_mgr = request.app.state.task_manager
    task = task_mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.to_dict()


@router.post("/api/export/tasks/{task_id}/cancel")
async def api_cancel_task(task_id: str, request: Request):
    task_mgr = request.app.state.task_manager
    if task_mgr.cancel_task(task_id):
        return {"success": True, "message": "取消请求已发送"}
    raise HTTPException(status_code=404, detail="任务不存在或不在运行中")


@router.websocket("/ws/export/{task_id}")
async def ws_export_progress(websocket: WebSocket, task_id: str):
    ws_mgr = websocket.app.state.ws_manager
    task_mgr = websocket.app.state.task_manager

    await ws_mgr.connect_task(task_id, websocket)

    # Send initial state
    task = task_mgr.get_task(task_id)
    if task:
        await websocket.send_json({"type": "status", **task.to_dict()})

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_mgr.disconnect_task(task_id, websocket)


@router.websocket("/ws/logs")
async def ws_log_stream(websocket: WebSocket):
    ws_mgr = websocket.app.state.ws_manager
    await ws_mgr.connect_log(websocket)

    # Send recent log buffer
    log_handler = websocket.app.state.log_handler
    if log_handler:
        for entry in list(log_handler.log_buffer)[-50:]:
            await websocket.send_json(entry)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_mgr.disconnect_log(websocket)
