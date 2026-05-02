import asyncio
from typing import Optional


def build_folder_tree(folders: list[str]) -> list[dict]:
    """Build a nested tree from a flat list of folder paths.

    Input:  ["/My Drafts/", "/My Notes/", "/My Notes/读书/", "/My Notes/读书/摘录/"]
    Output: [{"path": "/My Drafts/", "name": "My Drafts", "children": []}, ...]
    """
    root = []

    for folder_path in folders:
        parts = [p for p in folder_path.strip('/').split('/') if p]
        current_level = root
        built_path = ""

        for i, part in enumerate(parts):
            built_path += "/" + part
            is_leaf = (i == len(parts) - 1)

            # Find existing node
            node = None
            for child in current_level:
                if child["name"] == part:
                    node = child
                    break

            if node is None:
                full_path = built_path + "/"
                node = {
                    "path": full_path,
                    "name": part,
                    "children": [],
                }
                current_level.append(node)

            if not is_leaf:
                current_level = node["children"]

    return root


async def fetch_folder_tree(client, include_note_counts: bool = False) -> dict:
    """Fetch the folder tree from WizNote API."""
    def _fetch():
        folders = client.get_folders()
        tree = build_folder_tree(folders)
        total = len(folders)
        return {"folders": tree, "total_folders": total, "raw_folders": folders}

    result = await asyncio.to_thread(_fetch)
    return {
        "folders": result["folders"],
        "total_folders": result["total_folders"],
    }


async def fetch_notes_in_folder(client, folder: str) -> list[dict]:
    """Fetch note list for a specific folder."""
    def _fetch():
        from export_wiznotes.get_folders_and_notes_list import get_all_notes_in_folder
        notes = get_all_notes_in_folder(client, folder)
        return [{"docGuid": n.get("docGuid", ""), "title": n.get("title", "Untitled")} for n in notes]

    return await asyncio.to_thread(_fetch)
