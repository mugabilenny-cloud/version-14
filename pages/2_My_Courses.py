import streamlit as st

import local_auth
from local_client import resolve_active_courses
from ui_components import inject_base_css, wordmark, semester_fallback_notice

st.set_page_config(page_title="My Courses | Switch", page_icon="🟠", layout="centered", initial_sidebar_state="collapsed")
inject_base_css()

# Session fix: same guard as Home, and placed before anything is drawn so a
# signed-out visitor is redirected instead of glimpsing the page first. It
# used to fall back to the "demo-student" guest here, which showed the
# university root ("KIU" / "UNIV") in place of the student's course units.
user = local_auth.require_user()

wordmark(size="1.1rem")
st.markdown("### My Courses")
st.caption("Browse into your course tree.")

# gap #2 fix: same missing-student_id problem as Home (gap #1) --- see
# that page's comment for the full rationale. No other change to this
# page's layout/cards; gap #2's text scopes this fix to the missing
# argument only.
courses, courses_source = resolve_active_courses(user["user_id"])
semester_fallback_notice(courses_source)  # only says anything on a fallback
for course in courses:
    count = course.get('resource_count')
    count_label = f"{count} resources" if count is not None else "Tap to browse"
    with st.container():
        st.markdown(
            f"""
            <div class="card">
                <div class="card-title">{course['code']} --- {course['name']}</div>
                <div class="card-meta">{count_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("View resources", key=f"mycourse_{course['id']}", use_container_width=True):
            st.session_state["active_course"] = course
            local_auth.switch_page("pages/3_Course_Detail.py")
