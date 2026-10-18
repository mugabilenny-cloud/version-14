"""
Ads dashboard --- staff-only control panel for the FCM push-ad feature.

Access is Firebase Authentication (email/password), restricted to the
addresses listed in .streamlit/secrets.toml:

    [ads_admin]
    emails = ["staff@example.com"]

(or a comma-separated ADS_ADMIN_EMAILS environment variable). The
browser signs in with Firebase in a small same-origin iframe
(static/admin_auth.html) and hands the resulting ID token back once;
admin_auth.verify_id_token() checks the token's signature, audience,
expiry, verified email and the allowlist. No shared password, no
Firebase Admin SDK, no Cloud Functions.

This page deliberately does not use local_auth: it is not a student
account, it is a separate staff gate, and a signed-in student must not
reach it by virtue of having a session. The sidebar link is also hidden
by inject_base_css()'s CSS, but the token check -- not the hidden link --
is the actual access control.

What it does: compose a rich notification (small icon, title, message,
large image, click-through URL), preview it exactly as it will appear,
and send it to every device that opted in. Sending is a direct call to
FCM's HTTP v1 REST API using a Firebase service-account key; no Cloud
Functions and no paid services are involved. See fcm_client.py and the
"Push notifications (FCM) for ads" section of README.md for setup.
"""
import html
import time

import streamlit as st

import admin_auth
import fcm_client
from ui_components import inject_base_css

st.set_page_config(page_title="Ads Admin | Switch", page_icon="📣", layout="centered", initial_sidebar_state="collapsed")
inject_base_css()


# ---------------------------------------------------------------------------
# Staff gate
# ---------------------------------------------------------------------------

# The sign-in iframe reloads the top-level page once with ?admin_token=...
# (see static/admin_auth.html). Verify it here, keep the email in the
# Streamlit session, and strip the parameter immediately -- it is a
# short-lived credential and should not linger in the address bar.
_incoming_token = st.query_params.get("admin_token")
if _incoming_token:
    st.query_params.pop("admin_token", None)
    _claims, _error = admin_auth.verify_id_token(_incoming_token)
    if _claims:
        st.session_state["_ads_admin_email"] = _claims.get("email", "")
        st.session_state.pop("_ads_admin_error", None)
        st.session_state.pop("_ads_admin_denied", None)
        st.session_state.pop("_ads_admin_signout", None)
    else:
        st.session_state["_ads_admin_error"] = _error
        st.session_state["_ads_admin_denied"] = True


def _render_signin() -> None:
    st.markdown("### 📣 Ads dashboard")
    st.caption("Staff only. Students never see this page in the app's navigation.")

    problems = admin_auth.configuration_problems()
    if problems:
        st.error("Staff sign-in isn't ready: " + "; ".join(problems) + ".")
        with st.expander("Setup checklist"):
            st.markdown(
                "1. In the Firebase console, open **Authentication → Sign-in "
                "method**, enable **Email/Password**.\n"
                "2. Under **Authentication → Users**, add a user for each "
                "staff member (email + password).\n"
                "3. Add those email addresses to `[ads_admin] emails` in "
                "`.streamlit/secrets.toml` (or set `ADS_ADMIN_EMAILS`).\n"
                "4. On first sign-in Firebase sends a verification email; "
                "open it before continuing."
            )
        st.stop()

    src = admin_auth.iframe_src(
        denied=bool(st.session_state.get("_ads_admin_denied")),
        sign_out=bool(st.session_state.get("_ads_admin_signout")),
    )
    if not src:
        st.error("Staff sign-in is not configured.")
        st.stop()

    st.markdown(
        f'<iframe src="{src}" title="Staff sign-in" width="100%" height="300" '
        'style="border:0;display:block;width:100%;height:300px;max-width:100%;">'
        '</iframe>',
        unsafe_allow_html=True,
    )
    error = st.session_state.get("_ads_admin_error")
    if error:
        st.error(error)
    st.stop()


_admin_email = st.session_state.get("_ads_admin_email")
if not _admin_email:
    _render_signin()


# ---------------------------------------------------------------------------
# Dashboard header / status
# ---------------------------------------------------------------------------

header_left, header_right = st.columns([4, 1])
header_left.markdown("### 📣 Ads dashboard")
header_left.caption(f"Signed in as {_admin_email}")
if header_right.button("Lock", use_container_width=True):
    st.session_state.pop("_ads_admin_email", None)
    # The iframe signs the Firebase user out on the next render, so Lock
    # is a real sign-out rather than just hiding the dashboard.
    st.session_state["_ads_admin_signout"] = True
    st.rerun()

subscribers = fcm_client.token_count()
status_col, sendable_col = st.columns(2)
status_col.metric("Subscribed devices", subscribers)
sendable_col.metric("Ready to send", "Yes" if fcm_client.is_send_configured() else "Not configured")

if not fcm_client.is_send_configured():
    missing = fcm_client.missing_configuration()
    st.warning(
        "FCM isn't fully configured yet. Missing: "
        + (", ".join(missing) if missing else "settings")
        + "."
    )
    with st.expander("Setup checklist"):
        st.markdown(
            "1. Create a free Firebase project and add a **Web app** to it.\n"
            "2. In **Project settings → General**, copy the web app's config "
            "(`apiKey`, `authDomain`, `projectId`, `messagingSenderId`, `appId`).\n"
            "3. In **Cloud Messaging → Web Push certificates**, generate a key "
            "pair and copy the **VAPID key**.\n"
            "4. In **Project settings → Service accounts**, generate a new "
            "private key (JSON).\n"
            "5. Put all of the above under `[fcm]` in `.streamlit/secrets.toml` "
            "(see `.streamlit/secrets.toml.example`).\n\n"
            "Detailed steps and the exact key names are in README.md, "
            "\"Push notifications (FCM) for ads\"."
        )

st.divider()


# ---------------------------------------------------------------------------
# Compose + preview
# ---------------------------------------------------------------------------

st.markdown("#### Compose an ad")
st.caption(
    "The large image must be a publicly reachable http(s) URL — the phone "
    "fetches it directly when the notification is displayed."
)


def _render_preview(title: str, body: str, image_url: str, icon_url: str) -> None:
    """Mirrors the notification card in the requested design: app icon,
    app name, 'now', message, then the large image."""
    safe_title = html.escape(title or "Switch")
    safe_body = html.escape(body or "Your message appears here.")
    safe_icon = html.escape(icon_url or fcm_client.DEFAULT_ICON, quote=True)
    image_html = ""
    if image_url:
        image_html = (
            f'<img src="{html.escape(image_url, quote=True)}" alt="" '
            'style="width:100%;height:150px;object-fit:cover;border-radius:10px;'
            'margin-top:10px;display:block;background:#F3F4F6;">'
        )
    st.markdown(
        f"""
        <div style="max-width:380px;margin:0.2rem auto 0.8rem;background:#FFFFFF;
                    border:1px solid #E5E7EB;border-radius:18px;padding:14px 16px;
                    box-shadow:0 6px 18px rgba(0,0,0,0.08);">
            <div style="display:flex;align-items:center;gap:10px;">
                <img src="{safe_icon}" alt=""
                     style="width:36px;height:36px;border-radius:50%;object-fit:cover;background:#FBF3EC;">
                <div style="font-weight:700;font-size:14px;color:#1A1A2E;">{safe_title}</div>
                <div style="margin-left:auto;color:#6B7280;font-size:12px;">now</div>
            </div>
            <div style="font-size:13.5px;line-height:1.4;color:#1A1A2E;margin-top:8px;">{safe_body}</div>
            {image_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


title = st.text_input("Title", value="Switch", max_chars=80)
body = st.text_area(
    "Message",
    placeholder="e.g. New past papers just landed for PHA 2101. Open Switch to take a look.",
    height=100,
    max_chars=500,
)

# The three fields below are optional and stay collapsed so the everyday
# flow is just: title, message, send. Their defaults are unchanged --
# empty large image, "/" click-through, bundled Switch icon -- so a send
# from the collapsed state behaves exactly as before.
with st.expander("Advanced options", expanded=False):
    image_url = st.text_input(
        "Large image URL (optional)",
        placeholder="https://example.com/ad-banner.jpg",
        help="Shown below the message. Must be a public http(s) URL; Firebase does not host it for you.",
    )
    click_url = st.text_input(
        "Click-through URL",
        value="/",
        help="Where a tap should go. '/' opens Switch. Use a full https:// URL for an external page.",
    )
    icon_url = st.text_input(
        "Small icon URL",
        value=fcm_client.DEFAULT_ICON,
        help="Defaults to the bundled Switch icon in static/icons/.",
    )

st.caption("Preview")
_render_preview(title, body, image_url, icon_url)


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

problems = []
if not body.strip():
    problems.append("a message is required")
if image_url and not image_url.strip().startswith(("http://", "https://")):
    problems.append("the large image URL must start with http:// or https://")
if click_url and not (
    click_url.strip().startswith(("http://", "https://"))
    or click_url.strip().startswith("/")
):
    problems.append("the click-through URL must start with http(s):// or /")

if problems:
    st.caption("Before sending: " + "; ".join(problems) + ".")

send_clicked = st.button(
    f"Send to {subscribers} device{'s' if subscribers != 1 else ''}",
    type="primary",
    use_container_width=True,
    disabled=bool(problems) or subscribers == 0 or not fcm_client.is_send_configured(),
)

if send_clicked:
    with st.spinner("Sending notifications through Firebase…"):
        st.session_state["_ads_last_result"] = fcm_client.send_ad(
            title=title,
            body=body,
            image_url=image_url.strip(),
            click_url=click_url.strip(),
            icon_url=icon_url.strip(),
        )

result = st.session_state.get("_ads_last_result")
if result:
    if result.get("ok"):
        st.success(
            f"Sent to {result['sent']} device(s). "
            f"{result['failed']} failed. "
            f"{result['pruned']} stale registration(s) removed."
        )
    else:
        st.error(result.get("error") or "The send did not succeed.")
    if result.get("errors"):
        with st.expander("Delivery errors"):
            for error in result["errors"]:
                st.code(error, language=None)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

st.divider()
st.markdown("#### Sent ads")

history = fcm_client.ad_history()
if not history:
    st.caption("Nothing has been sent yet.")
else:
    for ad in history:
        sent_at = time.strftime("%d %b %Y, %H:%M", time.localtime(ad.get("sent_at", 0)))
        with st.expander(f"{ad.get('title', '(untitled)')} — {sent_at}"):
            st.write(ad.get("body", ""))
            st.caption(
                f"Sent {ad.get('sent', 0)} · Failed {ad.get('failed', 0)} · "
                f"Stale tokens removed {ad.get('pruned', 0)}"
            )
            if ad.get("image_url"):
                st.image(ad["image_url"], width=220)
            if ad.get("click_url"):
                st.caption(f"Click-through: {ad['click_url']}")
