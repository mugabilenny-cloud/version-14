"""
FCM web-push support for the ads notification feature.

This is the server half of the feature. The browser half lives in
static/fcm.html (the opt-in card + a hidden "runtime" copy that keeps
foreground notifications working on every page) and
static/firebase-messaging-sw.js (the service worker that receives data
messages and shows them as rich notifications).

Everything here uses only free resources:

  - Firebase Cloud Messaging itself is free, on every Firebase plan.
  - No Cloud Functions. The admin dashboard calls FCM's HTTP v1 REST API
    directly, authenticated with a normal Firebase service-account key
    (google-auth creates the OAuth2 token locally/in-process).
  - No database. Device registration tokens live in data/push_tokens.json
    and sent-ad history in data/ads.json, the same file-backed pattern
    local_auth.py / local_saved.py / local_history.py already use.

Same storage limitation as those modules, stated plainly: on Streamlit
Community Cloud the container disk is wiped on every reboot and redeploy,
so push tokens collected at runtime do not survive a restart. Everyone
has to opt in again after a redeploy. Fixing that needs storage outside
the container; it is not fixed here.

Configuration (environment variables for local runs, or the same names
under a [fcm] table in .streamlit/secrets.toml):

  FCM_API_KEY / api_key
  FCM_AUTH_DOMAIN / auth_domain                    (optional but recommended)
  FCM_PROJECT_ID / project_id
  FCM_MESSAGING_SENDER_ID / messaging_sender_id
  FCM_APP_ID / app_id
  FCM_VAPID_KEY / vapid_key                        (Web Push certificate key)
  FCM_SERVICE_ACCOUNT_JSON / service_account_json  (the downloaded private key)

The web config values above are public by design (they are shipped to
the browser by Firebase). The service-account JSON is a real secret and
must never be committed -- it is the only thing that can actually send
messages to the project.
"""
import base64
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import streamlit as st

PUSH_TOKENS_PATH = Path(__file__).parent / "data" / "push_tokens.json"
ADS_HISTORY_PATH = Path(__file__).parent / "data" / "ads.json"

# Root-relative on purpose: Streamlit serves the project's static/ folder
# at /app/static/<file>, and notification resources are resolved from the
# app's own origin. See static/icons/.
DEFAULT_ICON = "/app/static/icons/switch-192.png"
DEFAULT_BADGE = "/app/static/icons/switch-96.png"

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
MAX_AD_HISTORY = 50
MAX_ERRORS_RETURNED = 12

# FCM registration tokens are URL-safe base64-ish with a colon separator,
# e.g. "dQw...:APA91b...". Rejecting anything else keeps a crafted
# ?fcm_token= URL (see pages/1_Home.py) from writing arbitrary junk into
# the token store. The colon is required deliberately: every FCM
# registration token has one, and without it a plain long string would
# satisfy the length/charset check alone.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-.:]{40,4096}$")

# Writes from several Streamlit sessions (and the sender's worker
# threads) can interleave. The read-modify-write of the JSON files is
# guarded in-process; cross-process locking is out of scope here, same
# as the rest of the app's file-backed stores.
_store_lock = threading.Lock()
_credentials_lock = threading.Lock()
_cached_credentials = None
_cached_expiry = 0.0


# ---------------------------------------------------------------------------
# Small file helpers (same shape as local_saved.py / local_history.py)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp_path.write_text(json.dumps(data, indent=2))
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _setting(key: str, env_name: str) -> str:
    """Read one FCM setting: environment first (handy for local runs),
    then the [fcm] table in st.secrets. Returns "" when absent.

    st.secrets raises when no secrets.toml exists at all, which is a
    perfectly normal state for a local checkout -- every lookup is
    defensive so a missing file means "not configured", not a crash.
    """
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    try:
        section = st.secrets.get("fcm")
        if section:
            raw = section.get(key)
            if raw:
                return str(raw).strip()
    except Exception:
        pass
    return ""


def service_account_info() -> Optional[dict]:
    """The service-account JSON as a dict, or None. Accepts either a JSON
    string (service_account_json) or a nested TOML table
    ([fcm.service_account]), because both are reasonable in secrets.toml."""
    raw = _setting("service_account_json", "FCM_SERVICE_ACCOUNT_JSON")
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return info if isinstance(info, dict) else None

    try:
        section = st.secrets.get("fcm")
        table = section.get("service_account") if section else None
        if table:
            return dict(table)
    except Exception:
        pass
    return None


def project_id() -> str:
    pid = _setting("project_id", "FCM_PROJECT_ID")
    if pid:
        return pid
    info = service_account_info() or {}
    return str(info.get("project_id", "")).strip()


def vapid_key() -> str:
    return _setting("vapid_key", "FCM_VAPID_KEY")


def web_config() -> Optional[dict]:
    """The Firebase web-app config handed to the browser SDK. None unless
    every field the SDK actually requires is present."""
    config = {
        "apiKey": _setting("api_key", "FCM_API_KEY"),
        "authDomain": _setting("auth_domain", "FCM_AUTH_DOMAIN"),
        "projectId": project_id(),
        "messagingSenderId": _setting("messaging_sender_id", "FCM_MESSAGING_SENDER_ID"),
        "appId": _setting("app_id", "FCM_APP_ID"),
    }
    required = ("apiKey", "projectId", "messagingSenderId", "appId")
    if not all(config[field] for field in required):
        return None
    return {key: value for key, value in config.items() if value}


def is_client_configured() -> bool:
    """Enough config for the opt-in card / service worker in the browser."""
    return bool(web_config() and vapid_key())


def is_send_configured() -> bool:
    """Enough config for the admin dashboard to actually send."""
    return bool(is_client_configured() and service_account_info() and project_id())


def missing_configuration() -> list[str]:
    """Human-readable list of what an admin still needs to supply, used by
    the dashboard's setup notice. Never raises."""
    missing = []
    config = web_config()
    if not config:
        for label, key, env in (
            ("API key", "api_key", "FCM_API_KEY"),
            ("Project ID", "project_id", "FCM_PROJECT_ID"),
            ("Messaging sender ID", "messaging_sender_id", "FCM_MESSAGING_SENDER_ID"),
            ("Web app ID", "app_id", "FCM_APP_ID"),
        ):
            if not _setting(key, env):
                missing.append(label)
    if not vapid_key():
        missing.append("Web Push certificate (VAPID) key")
    if not service_account_info():
        missing.append("Service account JSON")
    return missing


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def registration_iframe_src(
    mode: str = "ui", has_token: bool = False, auto_sync: bool = False
) -> str:
    """URL for static/fcm.html, with the public Firebase config and VAPID
    key carried in the query string. Firebase's web config is public;
    the service-account key never appears here.

    The page is loaded in a plain (unsandboxed) same-origin iframe by
    ui_components.py -- a service worker cannot be registered from an
    opaque-origin sandboxed iframe, and the whole point is the SW.

    has_token tells the page whether the server already has a
    registration token for the signed-in user. auto_sync marks a hidden
    Home-only copy that, when the browser already allows notifications
    but the server has no token (restart/redeploy wiped the store),
    fetches one and hands it back through the same one-time reload the
    opt-in card uses. Returns "" when the client side is not configured."""
    config = web_config()
    vapid = vapid_key()
    if not config or not vapid:
        return ""
    payload = _b64url(json.dumps(config, separators=(",", ":")).encode("utf-8"))
    return (
        f"/app/static/fcm.html?mode={quote(mode)}"
        f"&has_token={1 if has_token else 0}"
        f"&auto={1 if auto_sync else 0}"
        f"&config={quote(payload, safe='')}&vapid={quote(vapid, safe='')}"
    )


# ---------------------------------------------------------------------------
# Device registration tokens
# ---------------------------------------------------------------------------

def _tokens() -> dict:
    data = _read_json(PUSH_TOKENS_PATH)
    return data if isinstance(data, dict) else {}


def save_token(token: str, user_id: str = "", username: str = "") -> bool:
    """Insert/refresh one device token. Returns True if it is new.

    FCM tokens are stable for a device+browser until they are rotated or
    the app is reinstalled, so re-saving is an upsert, not a duplicate."""
    token = (token or "").strip()
    if not _TOKEN_RE.match(token) or ":" not in token:
        return False
    now = time.time()
    with _store_lock:
        records = _tokens()
        is_new = token not in records
        record = records.get(token, {})
        record["created_at"] = record.get("created_at", now)
        record["last_seen_at"] = now
        if user_id:
            record["user_id"] = user_id
        if username:
            record["username"] = username
        records[token] = record
        _write_json_atomic(PUSH_TOKENS_PATH, records)
    return is_new


def remove_token(token: str) -> None:
    with _store_lock:
        records = _tokens()
        if token in records:
            del records[token]
            _write_json_atomic(PUSH_TOKENS_PATH, records)


def all_tokens() -> list[dict]:
    """Every registered device, newest first, without exposing the token
    as the dict key in callers' logs/history."""
    records = _tokens()
    rows = []
    for token, record in records.items():
        row = dict(record)
        row["token"] = token
        rows.append(row)
    rows.sort(key=lambda row: row.get("last_seen_at", 0), reverse=True)
    return rows


def token_count() -> int:
    return len(_tokens())


def has_token_for_user(user_id: str) -> bool:
    if not user_id:
        return False
    return any(record.get("user_id") == user_id for record in _tokens().values())


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def _access_token() -> str:
    """OAuth2 access token for the FCM HTTP v1 API, refreshed in-process.

    google-auth is imported lazily so a checkout that has not installed
    the (small, free) dependency yet can still run the rest of the app;
    only an actual send attempt raises."""
    global _cached_credentials, _cached_expiry

    info = service_account_info()
    if not info:
        raise RuntimeError("No Firebase service-account key is configured.")

    with _credentials_lock:
        now = time.time()
        if _cached_credentials is None or now >= _cached_expiry - 120:
            from google.auth.transport.requests import Request as GoogleAuthRequest
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_info(
                info, scopes=[FCM_SCOPE]
            )
            credentials.refresh(GoogleAuthRequest())
            _cached_credentials = credentials
            expiry = credentials.expiry
            # google-auth's expiry is a naive datetime in UTC. Treating it
            # as local time would refresh at the wrong moment (or, west of
            # UTC, keep using an already-expired token).
            _cached_expiry = (
                expiry.replace(tzinfo=timezone.utc).timestamp()
                if expiry
                else now + 3000
            )
        return _cached_credentials.token


def _message_payload(token: str, data: dict) -> dict:
    """One HTTP v1 message. Data-only on purpose: notification payloads
    would be auto-displayed by the FCM SDK *and* by our service worker,
    which produces two notifications. The worker shows this data itself
    (static/firebase-messaging-sw.js), which is what makes the large
    image and custom click-through work exactly like the design."""
    message = {
        "token": token,
        "data": data,
        "webpush": {
            "headers": {"Urgency": "high", "TTL": "86400"},
        },
    }
    click_url = data.get("click_url") or ""
    # fcm_options.link must be an absolute web URL (it is also used by
    # browser-native click handling). Root-relative click targets still
    # work through the service worker's data.click_url.
    if click_url.startswith("http://") or click_url.startswith("https://"):
        message["webpush"]["fcm_options"] = {"link": click_url}
    return {"message": message}


def _classify_failure(status_code: int, body: str) -> tuple[bool, str]:
    """Returns (should_prune_token, human_readable_error). Only a
    registration token the backend has permanently rejected is pruned;
    auth, quota and 5xx errors are transient and must not delete a
    device's registration."""
    try:
        error = json.loads(body).get("error", {})
    except (json.JSONDecodeError, AttributeError):
        error = {}

    status = str(error.get("status", ""))
    message = str(error.get("message", ""))
    error_code = ""
    for detail in error.get("details") or []:
        if isinstance(detail, dict) and detail.get("errorCode"):
            error_code = str(detail["errorCode"])
            break

    prune = (
        error_code == "UNREGISTERED"
        or status == "NOT_FOUND"
        or (
            status == "INVALID_ARGUMENT"
            and (
                "registration token" in message.lower()
                or "not a valid" in message.lower()
            )
        )
    )
    label = f"HTTP {status_code}"
    if status:
        label += f" {status}"
    if message:
        label += f": {message}"
    return prune, label[:300]


def _send_one(token: str, data: dict, access_token: str, project: str) -> tuple[str, dict]:
    """Send one message. Returns (token, result) where result has
    ok/prune/error keys. Never raises for a per-device failure."""
    import requests

    url = FCM_SEND_URL.format(project_id=project)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            url,
            headers=headers,
            json=_message_payload(token, data),
            timeout=20,
        )
    except Exception as exc:  # network failure: retryable, never prune
        return token, {"ok": False, "prune": False, "error": f"network error: {exc}"}

    if 200 <= response.status_code < 300:
        return token, {"ok": True, "prune": False, "error": ""}

    prune, error = _classify_failure(response.status_code, response.text)
    return token, {"ok": False, "prune": prune, "error": error}


def record_ad(ad: dict) -> dict:
    """Append a sent ad to data/ads.json, newest first, capped."""
    entry = dict(ad)
    entry.setdefault("id", uuid.uuid4().hex[:12])
    entry.setdefault("sent_at", time.time())
    with _store_lock:
        history = _read_json(ADS_HISTORY_PATH)
        rows = history if isinstance(history, list) else []
        rows.insert(0, entry)
        _write_json_atomic(ADS_HISTORY_PATH, rows[:MAX_AD_HISTORY])
    return entry


def ad_history(limit: int = 20) -> list[dict]:
    history = _read_json(ADS_HISTORY_PATH)
    if not isinstance(history, list):
        return []
    return history[:limit]


def send_ad(
    title: str,
    body: str,
    image_url: str = "",
    click_url: str = "",
    icon_url: str = "",
) -> dict:
    """Send one rich ad notification to every registered device.

    Returns a summary dict; it never raises for expected problems (no
    subscribers, missing config, FCM errors) so the dashboard can render
    the outcome instead of a Streamlit stack trace."""
    title = (title or "").strip()
    body = (body or "").strip()
    image_url = (image_url or "").strip()
    click_url = (click_url or "").strip() or "/"
    icon_url = (icon_url or "").strip() or DEFAULT_ICON

    empty_result = {
        "ok": False,
        "error": "",
        "sent": 0,
        "failed": 0,
        "pruned": 0,
        "errors": [],
        "entry": None,
    }

    if not title or not body:
        empty_result["error"] = "A notification title and message are required."
        return empty_result

    if not is_send_configured():
        missing = ", ".join(missing_configuration()) or "FCM settings"
        empty_result["error"] = f"FCM is not configured. Missing: {missing}."
        return empty_result

    records = all_tokens()
    if not records:
        empty_result["error"] = "No devices have enabled notifications yet."
        return empty_result

    project = project_id()
    try:
        access_token = _access_token()
    except Exception as exc:
        empty_result["error"] = f"Could not authenticate with Firebase: {exc}"
        return empty_result

    data = {
        "title": title,
        "body": body,
        "image": image_url,
        "icon": icon_url,
        "click_url": click_url,
    }

    tokens = [row["token"] for row in records]
    results: list[tuple[str, dict]] = []
    workers = max(1, min(8, len(tokens)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_send_one, token, data, access_token, project)
            for token in tokens
        ]
        for future in as_completed(futures):
            results.append(future.result())

    sent = sum(1 for _, result in results if result["ok"])
    failed = len(results) - sent
    pruned_tokens = [token for token, result in results if result.get("prune")]
    for token in pruned_tokens:
        remove_token(token)

    errors = []
    for _token, result in results:
        if not result["ok"] and result["error"]:
            errors.append(result["error"])
            if len(errors) >= MAX_ERRORS_RETURNED:
                break

    entry = record_ad(
        {
            "title": title,
            "body": body,
            "image_url": image_url,
            "click_url": click_url,
            "icon_url": icon_url,
            "sent": sent,
            "failed": failed,
            "pruned": len(pruned_tokens),
        }
    )

    return {
        "ok": sent > 0,
        "error": "" if sent else "FCM rejected every send. See the errors below.",
        "sent": sent,
        "failed": failed,
        "pruned": len(pruned_tokens),
        "errors": errors,
        "entry": entry,
    }
