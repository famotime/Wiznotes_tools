import json
import time
import asyncio
from pathlib import Path
from collections import defaultdict


async def scan_export_directory(export_dir: str) -> dict:
    """Scan the local export directory for md files."""
    root = Path(export_dir)

    def _scan():
        start = time.time()
        md_files = [f for f in root.rglob('*.md') if '_assets' not in str(f)]

        folder_dict = defaultdict(list)
        for f in md_files:
            folder_dict[f.parent].append(f)

        all_folders = []
        for folder in root.rglob('*'):
            if folder.is_dir() and '_assets' not in str(folder):
                all_folders.append(folder)

        folder_infos = []
        for folder in all_folders:
            files = folder_dict.get(folder, [])
            rel = folder.relative_to(root).as_posix()
            folder_infos.append({
                "path": "/" + rel + "/",
                "md_count": len(files),
                "md_files": [f.name for f in sorted(files)],
            })

        folder_infos.sort(key=lambda x: x["path"])
        elapsed = time.time() - start

        return {
            "folders": folder_infos,
            "total_folders": len(folder_infos),
            "total_md_files": len(md_files),
            "scan_time_seconds": round(elapsed, 2),
        }

    return await asyncio.to_thread(_scan)


async def compare_notes(client, export_dir: str, exclude_folders: list[str]) -> dict:
    """Compare online notes vs local exported files."""
    def _compare():
        # Get online inventory
        folders = client.get_folders()
        online_notes = {}
        for folder in folders:
            if folder in exclude_folders:
                continue
            try:
                from export_wiznotes.get_folders_and_notes_list import get_all_notes_in_folder
                notes = get_all_notes_in_folder(client, folder)
                names = set()
                for n in notes:
                    title = n.get('title', 'Untitled')
                    # Sanitize like compare_notes_in_folders.py
                    from export_wiznotes.compare_notes_in_folders import get_valid_filename
                    name = get_valid_filename(title)
                    if name.endswith('.md'):
                        name = name[:-3]
                    names.add(name)
                online_notes[folder] = names
            except Exception:
                continue

        # Get local inventory
        root = Path(export_dir)
        local_notes = defaultdict(set)
        for md_file in root.rglob('*.md'):
            if '_assets' in str(md_file):
                continue
            folder_path = '/' + md_file.parent.relative_to(root).as_posix() + '/'
            name = md_file.stem
            local_notes[folder_path].add(name)

        # Compute diff
        all_folders = set(online_notes.keys()) | set(local_notes.keys())
        diffs = []
        total_missing_local = 0
        total_missing_online = 0

        for folder in sorted(all_folders):
            if folder in exclude_folders:
                continue
            online = online_notes.get(folder, set())
            local = local_notes.get(folder, set())
            only_online = sorted(online - local)
            only_local = sorted(local - online)
            if only_online or only_local:
                diffs.append({
                    "folder": folder,
                    "only_online": only_online,
                    "only_local": only_local,
                })
                total_missing_local += len(only_online)
                total_missing_online += len(only_local)

        return {
            "diffs": diffs,
            "total_missing_local": total_missing_local,
            "total_missing_online": total_missing_online,
        }

    return await asyncio.to_thread(_compare)


async def list_export_logs(log_dir: str) -> list[dict]:
    """List available export log files."""
    log_path = Path(log_dir)
    if not log_path.exists():
        return []

    logs = []
    for f in sorted(log_path.glob('wiznotes_export_*.log'), reverse=True):
        logs.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
        })
    return logs


async def read_export_log(log_dir: str, filename: str) -> str:
    """Read a specific export log file."""
    # Security: only allow expected filename pattern
    if not filename.startswith('wiznotes_export_') or not filename.endswith('.log'):
        return ""
    log_path = Path(log_dir) / filename
    if not log_path.exists():
        return ""

    def _read():
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        return ''.join(lines[-500:])

    return await asyncio.to_thread(_read)


async def list_checkpoints(export_dir: str) -> list[dict]:
    """List all checkpoint files."""
    root = Path(export_dir)
    if not root.exists():
        return []

    def _list():
        checkpoints = []
        for cp_file in root.rglob('.export_checkpoint.json'):
            try:
                with open(cp_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                folder_path = '/' + cp_file.parent.relative_to(root).as_posix() + '/'
                checkpoints.append({
                    "folder_path": folder_path,
                    "exported_count": len(data.get('exported_guids', [])),
                    "timestamp": data.get('timestamp', ''),
                })
            except Exception:
                continue
        return checkpoints

    return await asyncio.to_thread(_list)
