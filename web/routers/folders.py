from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from web.deps import templates
from web.services.folder_service import fetch_folder_tree, fetch_notes_in_folder

router = APIRouter()


@router.get("/folders", response_class=HTMLResponse)
async def folders_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="folders.html",
        context={
            "current_page": "folders",
            "logged_in": request.app.state.wiz_client is not None,
            "username": _get_username(request),
        }
    )


@router.get("/api/folders")
async def api_get_folders(request: Request):
    client = request.app.state.wiz_client
    if not client:
        raise HTTPException(status_code=401, detail="未登录")
    return await fetch_folder_tree(client)


@router.get("/api/folders/{folder_path:path}/notes")
async def api_get_notes(folder_path: str, request: Request):
    client = request.app.state.wiz_client
    if not client:
        raise HTTPException(status_code=401, detail="未登录")
    # Ensure folder path has leading and trailing slashes
    if not folder_path.startswith('/'):
        folder_path = '/' + folder_path
    if not folder_path.endswith('/'):
        folder_path = folder_path + '/'
    return await fetch_notes_in_folder(client, folder_path)


def _get_username(request: Request) -> str:
    client = request.app.state.wiz_client
    if client and hasattr(client, 'config'):
        return client.config.get('wiz', {}).get('username', '')
    return ''
