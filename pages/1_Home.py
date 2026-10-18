import streamlit as st

import fcm_client
import local_auth
from local_client import resolve_active_courses, fetch_recently_viewed, fetch_feed, search_courses
from ui_components import inject_base_css, resource_card, video_resource_card, course_tile_grid, wordmark, hub_banner, semester_fallback_notice, notification_optin

st.set_page_config(page_title="Home | Switch", page_icon="🟠", layout="centered", initial_sidebar_state="collapsed")
inject_base_css()

# Session fix: Home is a signed-in page. No valid session means the sign-in
# page (local_auth.require_user() redirects and never returns) --- it used
# to render as the "demo-student" guest right here, which is exactly what
# put the university root ("KIU" / "UNIV") where the student's own course
# units belong, with no hint anything was wrong.
user = local_auth.require_user()
student_id = user["user_id"]

# FCM opt-in hand-off: static/fcm.html registers the service worker and
# gets a device token, then reloads the top-level page with
# ?fcm_token=... (a static page cannot call back into Streamlit any other
# way). Save it against this signed-in user and strip it from the URL
# immediately so it doesn't linger in the address bar or history.
_incoming_push_token = st.query_params.get("fcm_token")
if _incoming_push_token:
    fcm_client.save_token(
        _incoming_push_token,
        user_id=student_id,
        username=user.get("username", ""),
    )
    st.query_params.pop("fcm_token", None)
    st.session_state["_push_token_just_saved"] = True
if st.session_state.pop("_push_token_just_saved", False):
    st.toast("Notifications enabled on this device")

# ---- 1. Header & persistent search ----
# Round 7: the Sign out button no longer lives in this header --- it moved
# to the bottom of the KIU Hub page (pages/7_KIU_Hub.py).
wordmark()

query = st.text_input(
    "Search",
    placeholder="Search course code, topic, or keyword, e.g. Pathophysiology",
    label_visibility="collapsed",
)

if query:
    # gap #6 fix: search_courses() now returns (node_results, link_results),
    # both carrying the hierarchy-aware tags TreeStore.search() computes ---
    # a course-unit-level match and a topic/link-title match are shown as
    # two distinct, labeled result groups rather than one flat list, since
    # they're genuinely different things (browse into a course vs. jump
    # straight to a specific resource).
    node_results, link_results = search_courses(query)
    if node_results:
        st.caption("Matching courses")
        for course in node_results:
            level_label = course.get("matched_level", "").replace("_", " ").title()
            if st.button(f"{course['name']} ({level_label})", key=f"searchres_{course['id']}", use_container_width=True):
                st.session_state["active_course"] = course
                local_auth.switch_page("pages/3_Course_Detail.py")
    if link_results:
        st.caption("Matching resources")
        for resource in link_results:
            if resource.get("file_type") == "video":
                video_resource_card(resource, key_prefix="searchlink")
            else:
                resource_card(resource, key_prefix="searchlink")
    if not node_results and not link_results:
        st.caption("No matches yet.")

st.divider()

# Combined-repo addition: the KIU Resource Hub entry point. Placed here
# --- after the search block, before the student's own courses --- so
# it's unconditionally visible on every Home load (not pushed around by
# whether a search is active) without competing with "My Active Courses"
# for the very first thing a returning user sees. See
# ui_components.hub_banner() for the card + button split.
hub_banner()

# Ads opt-in: renders nothing unless the Firebase web config + VAPID key
# are present (see fcm_client.py), and nothing once this user's device is
# already registered -- the card is for opting in, not a permanent notice.
# The card's button is real browser JS in a static iframe; the permission
# prompt only appears after a click.
notification_optin(student_id)

# ---- 2. Active Semester fast-lane ----
st.markdown("#### My Active Courses")
# gap #1 fix: student_id is now threaded through, so a signed-in user's
# stored semester (chosen once at signup --- see local_auth.py) resolves
# to real course-unit tiles instead of always falling back to the tree
# root. Tile grid replaces the old two-column st.button chip row.
# Combined-repo addition: each tile now gets a distinct background color
# (course_unit_tile()'s COURSE_TILE_PALETTE, picked by list position)
# instead of the plain-white .card look it used before --- the "colourful
# tiles" ask.
courses, courses_source = resolve_active_courses(student_id)
semester_fallback_notice(courses_source)  # only says anything on a fallback
if courses:
    # Round 7: image tiles that are themselves the button (no "Open"
    # label), fading in one after another --- see ui_components.course_tile_grid().
    course_tile_grid(courses, key_prefix="home", columns=2)
else:
    st.caption("No courses found for your semester yet.")

# gap #1 fix: student_id threaded through so this reflects the signed-in
# user's real history (local_history.py) instead of always being empty.
# Also fixes the r['id'] -> r['resource_id'] key mismatch flagged in the
# handoff doc (rule #5) --- local_history.record_opened() stores entries
# keyed resource_id, not id; this was previously unreachable dead code
# (fetch_recently_viewed() always returned [] with no student_id), so the
# wrong key never actually raised until now.
recent = fetch_recently_viewed(student_id=student_id)
if recent:
    st.markdown("###### Pick up where you left off")
    for r in recent:
        cols = st.columns([4, 1])
        cols[0].write(f"{r['title']} · {r['course_code']}")
        if cols[1].button("Open", key=f"recent_{r['resource_id']}"):
            st.session_state["active_resource_id"] = r["resource_id"]
            st.session_state["_last_opened_resource"] = r
            local_auth.switch_page("pages/6_Viewer.py")

st.divider()

# ---- 3. What's New on Campus feed ----
st.markdown("#### What's New on Campus")
feed = fetch_feed()
for resource in feed:
    resource_card(resource, key_prefix="feed")
