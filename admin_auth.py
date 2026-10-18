"""
Staff authentication for the ads dashboard.

Replaces the old shared password with Firebase Authentication
(email/password), still using only free resources:

  - Firebase Auth email/password is free on the Spark plan.
  - Sign-in happens in the browser with the same public Firebase web
    config the push client already uses (static/admin_auth.html).
  - The resulting Firebase ID token is verified here with google-auth's
    ``verify_firebase_token``, which checks Google's signature, issuer,
    audience and expiry. No Firebase Admin SDK, no Cloud Functions, no
    server-side session database.
  - Only emails listed in ``[ads_admin] emails`` (or the
    ADS_ADMIN_EMAILS environment variable) are accepted. Any other
    Firebase account -- including a student signing up with their own
    address -- is rejected.

Why the email must be verified: Firebase's public web API lets anyone
create an email/password account with any address (including someone
else's) without proving ownership. The allowlist alone would therefore
not be enough, so ``email_verified`` must be true as well. The sign-in
page sends the verification email and waits for the user to confirm it.

Configuration, in .streamlit/secrets.toml:

    [ads_admin]
    emails = ["staff@example.com", "another@example.com"]

or as a comma-separated ADS_ADMIN_EMAILS environment variable.
"""
import base64
import json
import os
from typing import Optional
from urllib.parse import quote

import streamlit as st

import fcm_client


def allowed_emails() -> list[str]:
    """Administrator addresses, lower-cased and de-duplicated. Both the
    TOML list form and a comma-separated string are accepted; an empty
    result means the dashboard is not configured yet."""
    raw: list[str] = []
    try:
        section = st.secrets.get("ads_admin")
        value = section.get("emails") if section else None
        if isinstance(value, str):
            raw.extend(value.split(","))
        elif isinstance(value, (list, tuple)):
            raw.extend(str(item) for item in value)
    except Exception:
        pass

    env = os.environ.get("ADS_ADMIN_EMAILS", "")
    if env:
        raw.extend(env.split(","))

    return sorted({item.strip().lower() for item in raw if item.strip()})


def is_configured() -> bool:
    return bool(fcm_client.web_config() and allowed_emails())


def configuration_problems() -> list[str]:
    problems = []
    if not fcm_client.web_config():
        problems.append("Firebase web config is missing (the [fcm] settings)")
    if not allowed_emails():
        problems.append('no admin emails are configured ([ads_admin] emails)')
    return problems


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def iframe_src(denied: bool = False, sign_out: bool = False) -> str:
    """URL for static/admin_auth.html, carrying the public Firebase web
    config. The ID token is never placed here; it only travels back via
    the one-time top-level redirect after a successful sign-in."""
    config = fcm_client.web_config()
    if not config:
        return ""
    payload = _b64url(json.dumps(config, separators=(",", ":")).encode("utf-8"))
    return (
        f"/app/static/admin_auth.html?config={quote(payload, safe='')}"
        f"&denied={1 if denied else 0}"
        f"&signout={1 if sign_out else 0}"
    )


def verify_id_token(id_token: str) -> tuple[Optional[dict], str]:
    """Verify a Firebase ID token and authorize its email.

    Returns (claims, "") on success, otherwise (None, reason). Never
    raises for an invalid token; the dashboard renders the reason."""
    id_token = (id_token or "").strip()
    if not id_token:
        return None, "No sign-in token was received."

    emails = allowed_emails()
    if not emails:
        return None, "No admin emails are configured yet."

    project = fcm_client.project_id()
    if not project:
        return None, "The Firebase project ID is not configured."

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_firebase_token(
            id_token, google_requests.Request(), audience=project
        )
    except Exception:
        # Expired, malformed, wrong project, or Google's cert endpoint
        # unreachable: all mean "sign in again", never "let them in".
        return None, "That sign-in could not be verified. Please sign in again."

    email = str(claims.get("email") or "").strip().lower()
    if not claims.get("email_verified"):
        return None, "Verify your email address, then sign in again."
    if email not in emails:
        return None, "This account is not authorized to manage ads."

    return claims, ""
