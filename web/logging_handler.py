import re
import logging
import threading
from datetime import datetime
from collections import deque

from web.websocket_manager import WebSocketManager


class WebLogHandler(logging.Handler):
    """Captures log messages and broadcasts them via WebSocket."""

    PATTERNS = [
        (re.compile(r'开始获取文件夹\s+(.+?)\s+下的所有笔记'), 'folder_start', lambda m: {'folder': m.group(1)}),
        (re.compile(r'共获取到\s+(\d+)\s+篇笔记'), 'total', lambda m: {'notes_total': int(m.group(1))}),
        (re.compile(r'开始下载笔记:《(.+?)》'), 'note_start', lambda m: {'note_title': m.group(1)}),
        (re.compile(r'导出笔记成功:\s*《(.+?)》'), 'note_done', lambda m: {'note_title': m.group(1)}),
        (re.compile(r'导出笔记\s*《(.+?)》\s*失败'), 'note_error', lambda m: {'note_title': m.group(1)}),
        (re.compile(r'导出完成，共导出\s+(\d+)/(\d+)'), 'folder_done', lambda m: {'notes_exported': int(m.group(1)), 'notes_total': int(m.group(2))}),
        (re.compile(r'文件夹\s+(.+?)\s+导出完成'), 'folder_finished', lambda m: {'folder': m.group(1)}),
    ]

    def __init__(self, ws_manager: WebSocketManager, task_manager=None):
        super().__init__()
        self.ws_manager = ws_manager
        self.task_manager = task_manager
        self.log_buffer = deque(maxlen=2000)

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            thread_name = threading.current_thread().name
            task_id = None
            if thread_name.startswith('export-'):
                task_id = thread_name[len('export-'):]

            entry = {
                "type": "log",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "level": record.levelname,
                "message": msg,
                "task_id": task_id,
            }
            self.log_buffer.append(entry)
            self.ws_manager.broadcast_log_sync(entry)

            # Parse progress events and update TaskInfo
            for pattern, event, extractor in self.PATTERNS:
                match = pattern.search(msg)
                if match:
                    data = extractor(match)
                    progress = {
                        "type": "progress",
                        "event": event,
                        "task_id": task_id,
                        "timestamp": entry["timestamp"],
                        "level": record.levelname,
                        "message": msg,
                        **data,
                    }

                    # Update TaskInfo
                    if task_id and self.task_manager:
                        task = self.task_manager.get_task(task_id)
                        if task:
                            if event == 'total':
                                task.notes_total = data.get('notes_total', task.notes_total)
                            elif event == 'note_done':
                                task.notes_exported += 1
                            elif event == 'folder_start':
                                task.current_folder = data.get('folder', task.current_folder)
                            elif event == 'folder_done':
                                task.notes_exported = data.get('notes_exported', task.notes_exported)
                                task.notes_total = data.get('notes_total', task.notes_total)

                            # Include updated counts in progress message
                            progress['notes_exported'] = task.notes_exported
                            progress['notes_total'] = task.notes_total
                            progress['current_folder'] = task.current_folder

                    if task_id:
                        self.ws_manager.broadcast_progress_sync(task_id, progress)
                    break

        except Exception:
            self.handleError(record)
