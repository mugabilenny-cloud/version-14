"""
Per-user "recently opened" history --- file-backed (data/history.json),
same reasoning as local_auth.py for why this can't be st.session_state:
anonymous session state doesn't survive a closed tab, and "recently
opened" is meaningless if it resets every time the user reopens the app
--- which is exactly the case auth (local_auth.py) now makes possible to
track correctly.

Shape: {user_id: [ {resource_id, title, file_type, course_code, url,
                     youtube_video_id, opened_at}, ... ]} newest first,
capped at MAX_HISTORY_PER_USER entries (oldest silently dropped past
the cap --- this is a recency list, not an archive).

youtube_video_id added for gap #8 of the handoff doc: without it, a
recently-opened video couldn't be re-embedded from the history section
without re-deriving the id from its url every time it's displayed.
Carried straight through from whatever the caller passed in (already
computed once by tree_store.link_to_resource_shape() at import/search
time) rather than re-derived here, so this file doesn't duplicate that
extraction logic --- None for any non-video resource, same as the
resource shapes elsewhere in the app that only set this field for
youtube-kind links.
"""
import json
import os
import time
from pathlib import Path

HISTORY_PATH = Path(__file__).parent / "data" / "history.json"
MAX_HISTORY_PER_USER = 20


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


def record_opened(user_id: str, resource: dict) -> None:
    """Call when a resource (doc or video) is actually opened in the
    Viewer --- not on hover, not on card render, only on the real
    open-click, so this reflects what was genuinely viewed."""
    if not user_id:
        return
    history = _read_json(HISTORY_PATH)
    user_history = history.get(user_id, [])

    # Move-to-front on repeat opens rather than duplicate entries ---
    # reopening something you already have in history should refresh
    # its position, not clutter the list with two copies of the same item.
    user_history = [h for h in user_history if h.get("resource_id") != resource.get("id")]

    entry = {
        "resource_id": resource.get("id"),
        "title": resource.get("title", "Untitled"),
        "file_type": resource.get("file_type", "link"),
        "course_code": resource.get("course_code", ""),
        "url": resource.get("url"),
        "youtube_video_id": resource.get("youtube_video_id"),
        "opened_at": time.time(),
    }
    user_history.insert(0, entry)
    history[user_id] = user_history[:MAX_HISTORY_PER_USER]
    _write_json_atomic(HISTORY_PATH, history)


def recent_for_user(user_id: str, limit: int = 5) -> list[dict]:
    if not user_id:
        return []
    history = _read_json(HISTORY_PATH)
    return history.get(user_id, [])[:limit]
