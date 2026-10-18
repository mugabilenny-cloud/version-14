import streamlit as st

import local_auth
from local_client import fetch_resource, save_bookmark, record_resource_opened
from ui_components import inject_base_css, file_type_chip, youtube_embed, drive_doc_embed

st.set_page_config(page_title="Viewer | Switch", page_icon="📄", layout="centered", initial_sidebar_state="collapsed")
inject_base_css()


def _clickable(candidate_url: str, fallback: str = "") -> str:
    """Best-effort absolute link for use inside a markdown [text](url).

    Round-3 finding from testing the importer end to end: it only
    strips whitespace from a url, it never adds a scheme -- so a
    spreadsheet cell like "docs.google.com/document/d/ID/edit" imports
    fine and even embeds fine (tree_store.drive_embed_url()'s regex
    doesn't require a scheme either), but used as-is in a markdown
    link it renders as a broken relative link (relative to this app's
    own url, not an absolute link to Google). Prepends https:// to a
    schemeless-but-present url; falls back to `fallback` (expected to
    already be absolute, e.g. an already-built drive_embed_url) only
    when there's no candidate url at all."""
    if candidate_url and candidate_url.lower().startswith(("http://", "https://")):
        return candidate_url
    if candidate_url:
        return f"https://{candidate_url}"
    return fallback

resource_id = st.session_state.get("active_resource_id")

if not resource_id:
    st.warning("No resource selected.")
    if st.button("← Back to Home"):
        local_auth.switch_page("pages/1_Home.py")
    st.stop()

resource = fetch_resource(resource_id)

# gap #5 fix: history recording. Guarded one-shot-per-session (rule #7 of
# the handoff doc) --- this page has its own buttons (fullscreen toggle,
# Save, Share) that rerun this exact script with the same resource_id
# still in session state, the same rerun-heavy risk already caught once
# in ui_components.video_resource_card(); an unconditional call here
# would re-log "just opened" on every one of those clicks, not just the
# actual navigation into the Viewer.
user = local_auth.current_user()
student_id = user["user_id"] if user else "demo-student"
recorded_key = f"_history_recorded_{resource_id}"
if not st.session_state.get(recorded_key):
    record_resource_opened(student_id, resource)
    st.session_state[recorded_key] = True

top = st.columns([1, 4, 1])
if top[0].button("✕ Close"):
    local_auth.switch_page("pages/1_Home.py")
top[1].markdown(f"**{resource.get('title', 'Resource')}**")
fullscreen = top[2].button("⛶")

st.markdown(file_type_chip(resource.get("file_type", "")), unsafe_allow_html=True)
st.caption(resource.get("course_code", ""))

# gap #5 fix: embed rendering. A youtube-kind resource now plays inline
# via the same youtube_embed() iframe used in
# ui_components.video_resource_card(), instead of falling into the
# generic placeholder box below --- no new embed logic invented here,
# reusing what gap #9 (done item, prior turn) already built and tested.
#
# Round 3 adds the same treatment for note/doc (drive_notes/
# drive_questions) resources, which is the "non-YouTube inline preview"
# item the round-2 README named as not done yet. Dispatches on the
# drive_embed_url tree_store already precomputed on the resource shape
# (see tree_store.link_to_resource_shape()) rather than re-parsing the
# url here, same split as the video branch above.
#
# The separately reported "drive_notes/drive_questions urls are dead/
# inaccessible" issue is a data problem this page can't repair --- the
# underlying Google Doc has to actually exist and be shared "Anyone
# with the link" for Google's own /preview embed to render for a
# viewer who isn't signed into the owner's account, and there's no way
# to tell a dead link from a permissions problem from here (both just
# mean the iframe won't show the real document). What this code does
# instead: never point an iframe at an empty/missing url, and always
# show a real, direct Open-in-Google-Docs link alongside the embed
# attempt rather than only when the embed is judged to have failed,
# since that failure can't be detected from here in the first place.
if resource.get("file_type") == "video" and resource.get("youtube_video_id"):
    youtube_embed(resource["youtube_video_id"], height=280 if fullscreen else 220)
elif resource.get("file_type") in ("note", "doc"):
    url = resource.get("url")
    embed_url = resource.get("drive_embed_url")
    if embed_url:
        drive_doc_embed(embed_url, height=500 if fullscreen else 400)
        open_link = _clickable(url, fallback=embed_url)
        st.caption(f"Having trouble viewing it above? [Open in Google Docs ↗]({open_link})")
    elif url:
        # Has a url, but it didn't match a recognized Google Docs/Drive
        # shape (tree_store.drive_embed_url() returned None) --- still a
        # real link, just not one this app knows how to embed, so it
        # gets a plain-link fallback rather than a blank/broken iframe.
        st.markdown(
            f"""
            <div style="border:1px solid #E5E7EB; border-radius:12px; padding: {"2rem" if fullscreen else "3rem"} 1rem;
                        text-align:center; background:#F5F6FA; margin-top: 0.6rem;">
                <div style="font-size:2.5rem;">{'📝' if resource.get('file_type') == 'note' else '📃'}</div>
                <div style="color:#6B7280; margin-top:0.5rem;">
                    This link isn't a recognized Google Docs/Drive address, so it
                    can't be previewed inline here.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(f"[Open the original link ↗]({_clickable(url)})")
    else:
        # No url at all (missing from the source data, or this is the
        # local_client "resource not found" fallback shape) --- nothing
        # to point an iframe or a link at, so say so plainly instead of
        # rendering a blank embed.
        st.markdown(
            """
            <div style="border:1px solid #E5E7EB; border-radius:12px; padding: 3rem 1rem;
                        text-align:center; background:#F5F6FA; margin-top: 0.6rem;">
                <div style="font-size:2.5rem;">⚠️</div>
                <div style="color:#6B7280; margin-top:0.5rem;">
                    No link is available for this resource.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        f"""
        <div style="border:1px solid #E5E7EB; border-radius:12px; padding: {"3rem" if fullscreen else "5rem"} 1rem;
                    text-align:center; background:#F5F6FA; margin-top: 0.6rem;">
            <div style="font-size:2.5rem;">{'📄' if resource.get('file_type') == 'pdf' else '📊' if resource.get('file_type') == 'ppt' else '📝'}</div>
            <div style="color:#6B7280; margin-top:0.5rem;">
                Inline preview placeholder --- this is where the real PDF/slide/text
                renderer mounts. No download forced to open this.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

cols = st.columns(3)
if cols[0].button("🔖 Save", use_container_width=True):
    # gap #5 fix: student_id threaded through, same pattern as gaps
    # #1/#2/#4.
    save_bookmark(resource, student_id=student_id)
    st.toast("Saved")
if cols[1].button("🔗 Copy Share Link", use_container_width=True):
    st.toast("Share links aren't available yet --- no deep-link scheme exists in this schema.")
cols[2].button("⬇️ Download", use_container_width=True, disabled=True, help="Intentionally de-emphasized per spec --- inline viewing is the default.")
