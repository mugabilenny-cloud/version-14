import streamlit as st

import local_auth
from local_client import fetch_children_as_resources
from ui_components import inject_base_css, course_banner, topic_section

st.set_page_config(page_title="Course | Switch", page_icon="🟠", layout="centered", initial_sidebar_state="collapsed")
inject_base_css()

course = st.session_state.get("active_course", {"code": "---", "name": "Unknown course"})

if st.button("← Back"):
    local_auth.switch_page("pages/1_Home.py")

course_banner(course)

# The real tree is 8 levels deep --- a node here may hold more nodes
# (keep drilling) or, at the bottom, real links (show them). The old
# version assumed every course had a flat resource list one click away;
# that assumption doesn't hold against a real multi-level tree, so this
# branches instead of flattening.
kind, items = fetch_children_as_resources(course.get("id"))

if kind == "nodes":
    # Folder-level (non-leaf) rendering --- unchanged. Rule #6 of the
    # handoff doc's agent instructions explicitly scopes gap #3's fix to
    # the leaf/links case only; this branch is not part of that gap.
    st.markdown("#### Browse further")
    for node in items:
        with st.container():
            st.markdown(
                f"""<div class="card"><div class="card-title">{node['code']} --- {node['name']}</div></div>""",
                unsafe_allow_html=True,
            )
            if st.button("Open", key=f"drill_{node['id']}", use_container_width=True):
                st.session_state["active_course"] = node
                st.rerun()
else:
    # Round 7: a course unit now opens straight onto its topics (the
    # pointless "Class" leaf step is skipped in fetch_children_as_resources),
    # each topic collapsed. Open one to see its video, notes and questions.
    st.markdown("#### Topics")
    if not items:
        st.info("No topics added here yet.")
    for i, (title, resources) in enumerate(items):
        topic_section((title or "").strip(), resources, key_prefix=f"topic{i}")
