"""
Per-user saved/bookmarked resources --- file-backed (data/saved.json),
same reasoning and same shape as local_history.py: real accounts (see
local_auth.py) make a durable per-user save meaningful in a way
session-state-only save wasn't.

Shape: {user_id: [resource, resource, ...]} --- each resource is
whatever shape tree_store.link_to_resource_shape() or a session-state
resource dict already produces; this module doesn't reshape it, only
stores/dedupes/retrieves it, same division of responsibility as the
original save_bookmark()/fetch_saved() had with session_state.
"""
import json
import os
from pathlib import Path

SAVED_PATH = Path(__file__).parent / "data" / "saved.json"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp_path.write_text(json.dumps(data, indent=2))
    os.replace(tmp_path, path)


def saved_for_user(user_id: str) -> list[dict]:
    if not user_id:
        return []
    return _read_json(SAVED_PATH).get(user_id, [])


def save_for_user(user_id: str, resource: dict) -> None:
    if not user_id:
        return
    saved = _read_json(SAVED_PATH)
    user_saved = saved.get(user_id, [])
    if not any(r.get("id") == resource.get("id") for r in user_saved):
        user_saved.append(resource)
    saved[user_id] = user_saved
    _write_json_atomic(SAVED_PATH, saved)
