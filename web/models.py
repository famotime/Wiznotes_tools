from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    username: Optional[str] = None
    kb_server: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    export_dir: Optional[str] = None
    max_workers: Optional[int] = None
    max_notes: Optional[int] = None
    reexport_dot_files: Optional[bool] = None
    exclude_folders: Optional[list[str]] = None


class ExportRequest(BaseModel):
    folders: list[str]
    max_notes: Optional[int] = None
    max_workers: Optional[int] = None
    reexport_dot_files: Optional[bool] = None


class CompareRequest(BaseModel):
    exclude_folders: Optional[list[str]] = None
