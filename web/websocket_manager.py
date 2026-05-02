import asyncio
import json
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.log_connections: set[WebSocket] = set()
        self.task_connections: dict[str, set[WebSocket]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect_log(self, ws: WebSocket):
        await ws.accept()
        self.log_connections.add(ws)

    def disconnect_log(self, ws: WebSocket):
        self.log_connections.discard(ws)

    async def connect_task(self, task_id: str, ws: WebSocket):
        await ws.accept()
        if task_id not in self.task_connections:
            self.task_connections[task_id] = set()
        self.task_connections[task_id].add(ws)

    def disconnect_task(self, task_id: str, ws: WebSocket):
        if task_id in self.task_connections:
            self.task_connections[task_id].discard(ws)

    async def broadcast_log(self, entry: dict):
        dead = set()
        for ws in self.log_connections:
            try:
                await ws.send_json(entry)
            except Exception:
                dead.add(ws)
        self.log_connections -= dead

    async def broadcast_progress(self, task_id: str, entry: dict):
        conns = self.task_connections.get(task_id, set())
        dead = set()
        for ws in conns:
            try:
                await ws.send_json(entry)
            except Exception:
                dead.add(ws)
        conns -= dead

    def broadcast_log_sync(self, entry: dict):
        """Called from worker threads. Schedules the async broadcast."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast_log(entry), self._loop)

    def broadcast_progress_sync(self, task_id: str, entry: dict):
        """Called from worker threads. Schedules the async broadcast."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast_progress(task_id, entry), self._loop)
