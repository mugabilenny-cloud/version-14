import streamlit as st

import local_auth
from tree_store import get_store
from ui_components import inject_base_css, onboarding_carousel, wordmark

st.set_page_config(page_title="Sign in | Switch", page_icon="🟠", layout="centered", initial_sidebar_state="collapsed")
inject_base_css()

# Combined-repo addition: the brand-photo carousel is the first thing on
# this screen, above the wordmark --- the literal "at sign up" ask, and
# the first colorful thing anyone new to the app sees, before they've
# signed up or logged in. See ui_components.onboarding_carousel() for
# why this is a components.html() iframe rather than st.markdown.
onboarding_carousel()

wordmark()
st.caption("Sign up or log in to see your courses.")

store = get_store()
semester_nodes = store.nodes_of_type("semester")
# Display label vs stored value are different on purpose: the stored
# value is the full "Univ/Faculty/Dept/Year/Semester" path (unambiguous
# --- see tree_store.find_node_by_path_label()'s docstring on why a bare
# "Semester 1" can't be used, since this data has two of them), but
# showing that whole path in the picker is noisy. The label collapses
# it to "Department · Year · Semester" instead.
semester_options = {}
for node in semester_nodes:
    full_path = store.node_path_label(node)
    year_node = store.node_by_id(node["parent_id"])
    dept_node = store.node_by_id(year_node["parent_id"]) if year_node else None
    label = f"{dept_node['name'] if dept_node else '?'} · {year_node['name'] if year_node else '?'} · {node['name']}"
    semester_options[label] = full_path

tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

with tab_login:
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", use_container_width=True)
    if submitted:
        ok, result = local_auth.verify_login(username, password)
        if ok:
            # Session fix: start_session() signs this browser tab in right
            # now (session_state + URL), so Home doesn't depend on the URL
            # param surviving the page switch --- it doesn't, unless
            # local_auth.switch_page() re-attaches it. See local_auth.py.
            local_auth.start_session(result)
            local_auth.switch_page("pages/1_Home.py")
        else:
            st.error(result)

with tab_signup:
    if not semester_options:
        st.warning("No semesters found in the current data --- check data/tree.json was generated from repo_5.xlsx.")
    with st.form("signup_form"):
        new_username = st.text_input("Choose a username")
        new_password = st.text_input("Choose a password", type="password")
        semester_label = st.selectbox(
            "Which semester are you currently in?",
            options=list(semester_options.keys()) or ["--- none available ---"],
            help="This decides which course units show under My Active Courses on Home. You can't change it later in this build.",
        )
        signup_submitted = st.form_submit_button("Sign up", use_container_width=True)
    if signup_submitted:
        if not semester_options:
            st.error("Can't sign up without at least one semester in the data.")
        else:
            semester_path = semester_options[semester_label]
            ok, result = local_auth.create_user(new_username, new_password, semester=semester_path)
            if ok:
                local_auth.start_session(result)  # same as login above
                local_auth.switch_page("pages/1_Home.py")
            else:
                st.error(result)

st.caption("You'll stay signed in on this device for up to 3 days.")
