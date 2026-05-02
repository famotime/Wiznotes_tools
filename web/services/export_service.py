import uuid
import time
import threading
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    task_id: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    folders: list[str] = field(default_factory=list)
    current_folder: str | None = None
    notes_exported: int = 0
    notes_total: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    elapsed_seconds: float = 0.0
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _start_time: float = 0.0

    def to_dict(self) -> dict:
        elapsed = time.time() - self._start_time if self._start_time else self.elapsed_seconds
        return {
            "task_id": self.task_id,
            "status": self.status,
            "folders": self.folders,
            "current_folder": self.current_folder,
            "notes_exported": self.notes_exported,
            "notes_total": self.notes_total,
            "errors": self.errors,
            "started_at": self.started_at,
            "elapsed_seconds": round(elapsed, 1),
        }


class TaskManager:
    def __init__(self):
        self.tasks: dict[str, TaskInfo] = {}

    def start_export(self, folders: list[str], config: dict, ws_manager) -> str:
        task_id = str(uuid.uuid4())[:8]
        task = TaskInfo(
            task_id=task_id,
            folders=folders,
            started_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        self.tasks[task_id] = task

        thread = threading.Thread(
            target=_run_export,
            args=(task, config, ws_manager),
            name=f"export-{task_id}",
            daemon=True,
        )
        thread.start()
        return task_id

    def cancel_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status == "running":
            task.cancel_event.set()
            return True
        return False

    def get_task(self, task_id: str) -> TaskInfo | None:
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> list[dict]:
        return [t.to_dict() for t in self.tasks.values()]


def _run_export(task: TaskInfo, config: dict, ws_manager):
    """Run export in a dedicated thread."""
    import tqdm as tqdm_module

    original_tqdm = tqdm_module.tqdm

    def noop_tqdm(iterable=None, *args, **kwargs):
        if iterable is not None:
            return iterable
        return original_tqdm(*args, **kwargs)

    # Suppress tqdm in web context
    tqdm_module.tqdm = noop_tqdm

    try:
        task.status = "running"
        task._start_time = time.time()
        logger.info(f"[WebExport] 任务 {task.task_id} 开始，文件夹: {task.folders}")

        from export_wiznotes import WizNoteClient, NoteExporter

        # Create client from config
        client = WizNoteClient.__new__(WizNoteClient)
        creds = config.get("_credentials", {})
        client.config = {"wiz": creds}
        client.token = None
        client.kb_info = None
        client.login()

        export_dir = config.get("export_dir", "export_wiznotes/output")
        max_notes = config.get("max_notes")
        reexport_dot = config.get("reexport_dot_files", False)

        for folder in task.folders:
            if task.cancel_event.is_set():
                task.status = "cancelled"
                return

            task.current_folder = folder
            logger.info(f"[WebExport] 开始导出文件夹: {folder}")

            try:
                exporter = NoteExporter(client)
                exporter.export_notes(
                    folder=folder,
                    export_dir=export_dir,
                    max_notes=max_notes,
                    resume=True,
                    reexport_dot_files=reexport_dot,
                )
            except Exception as e:
                err_msg = f"文件夹 {folder} 导出失败: {e}"
                task.errors.append(err_msg)
                logger.error(err_msg)

        task.status = "completed"
        task.elapsed_seconds = time.time() - task._start_time

    except Exception as e:
        task.status = "failed"
        task.errors.append(f"导出任务失败: {e}")
        logger.error(f"导出任务失败: {e}")
    finally:
        tqdm_module.tqdm = original_tqdm
        task.elapsed_seconds = time.time() - task._start_time if task._start_time else 0
