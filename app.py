import streamlit as st

import local_auth
from local_client import get_or_create_device_token, register_device

st.set_page_config(
    page_title="Switch",
    page_icon="🟠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    '<link rel="manifest" href="assets/manifest.json"><meta name="theme-color" content="#E85D2C">',
    unsafe_allow_html=True,
)

# Device bootstrap --- legacy from the pre-auth anonymous build (see
# local_client.py's module docstring); kept so nothing that still reads
# device_token from session_state breaks.
device_token = get_or_create_device_token()
st.session_state["device_token"] = device_token
register_device(device_token, home_node_id=st.session_state.get("home_node_id"))

# Auth gate: local_auth.current_user() resolves the "session" query
# param to a real, non-expired user via local_auth.resolve_session()
# (3-day TTL --- see that module's SESSION_TTL_SECONDS). A valid session
# skips straight to Home, silently, with no re-prompt --- that's the
# literal "access for up to three days without logging" ask. Only a
# missing/unknown/expired session falls through to the sign-up/login
# gate, which is also the literal "prompting them to sign up on opening
# platform" ask --- it's shown on open, not on every navigation, because
# this check only runs once here in app.py. Home and My Courses ALSO
# guard themselves now (local_auth.require_user()), so opening one of
# those directly --- a bookmark, or a browser reload while on it --- no
# longer skips this gate and silently renders as a guest.
# Session fix: navigate with local_auth.switch_page(), never
# st.switch_page() --- the bare call drops the ?session= token.
if local_auth.current_user():
    local_auth.switch_page("pages/1_Home.py")
else:
    local_auth.switch_page("pages/0_Auth.py")
