import streamlit as st

import local_auth
from local_client import fetch_saved
from ui_components import inject_base_css, resource_card, video_resource_card

st.set_page_config(page_title="Saved | Switch", page_icon="🔖", layout="centered", initial_sidebar_state="collapsed")
inject_base_css()

st.markdown("### 🔖 Saved")
st.caption("Bookmarked notes for quick review.")

# gap #4 fix: student_id threaded through (same pattern as gaps #1/#2)
# so this shows a signed-in user's real per-user saved list
# (local_saved.py) instead of always falling back to the session-only
# guest list. Also dispatches by file_type now --- a saved video renders
# as a playable embed (video_resource_card) instead of a plain
# link-out card, matching how video/non-video resources are already
# dispatched together in pages/3_Course_Detail.py.
user = local_auth.current_user()
student_id = user["user_id"] if user else "demo-student"
saved = fetch_saved(student_id=student_id)
if not saved:
    st.info("Nothing saved yet. Tap 🔖 Save on any resource card to add it here.")
else:
    for resource in saved:
        if resource.get("file_type") == "video":
            video_resource_card(resource, key_prefix="saved")
        else:
            resource_card(resource, key_prefix="saved")
