"""
Pure UI building blocks. Save persists per-user via local_client.save_
bookmark() once someone's signed in (local_auth.current_user()), falling
back to session-only save for a logged-out/guest view --- see that
function's docstring for the full per-user-vs-session split.

Combined-repo addition: onboarding_carousel() / brand_image_data_uri() /
hub_banner() below are new in this round, added alongside the existing
building blocks rather than in a separate module --- this file was
already "shared widgets" per README.md's project layout, and the brand
photos are used by pages/0_Auth.py, pages/1_Home.py, and
pages/7_KIU_Hub.py, so a shared home for them (with the shared image-
loading cache) avoids three copies of the same base64-encoding logic.
"""
import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import fcm_client
import local_auth
from local_client import save_bookmark, record_resource_opened

ONBOARDING_DIR = Path(__file__).parent / "assets" / "onboarding"

FILE_TYPE_STYLE = {
    "video": {"color": "#DC2626", "label": "VIDEO", "icon": "▶️"},  # red, per request --- notes/docs already get their own distinct color below; video gets red the same way
    "ppt":  {"color": "#F97316", "label": "PPT",  "icon": "📊"},
    "pdf":  {"color": "#EF4444", "label": "PDF",  "icon": "📄"},
    "note": {"color": "#3B82F6", "label": "NOTE", "icon": "📝"},
    "doc":  {"color": "#3B82F6", "label": "DOC",  "icon": "📃"},
}
DEFAULT_STYLE = {"color": "#6B7280", "label": "FILE", "icon": "📎"}

# Combined-repo addition: per-tile background colors for the "My Active
# Courses" grid (course_unit_tile() below) --- a deliberately different
# palette from FILE_TYPE_STYLE above rather than reusing those colors,
# so a colored course tile never gets misread as meaning the same thing
# a colored file-type chip does elsewhere in the app (red already means
# "video", blue already means "note/doc", etc.). All eight are roughly
# the same depth/saturation as the FILE_TYPE_STYLE colors specifically
# so white text sits on them with the same contrast those chips already
# rely on.
COURSE_TILE_PALETTE = [
    "#E85D2C",  # brand orange
    "#2563EB",  # blue
    "#7C3AED",  # violet
    "#0D9488",  # teal
    "#DB2777",  # rose
    "#D97706",  # amber
    "#059669",  # emerald
    "#4F46E5",  # indigo
]


def inject_base_css():
    st.markdown(
        """
        <style>
        .card {
            border: 1px solid #E5E7EB;
            border-radius: 12px;
            padding: 0.9rem 1rem;
            margin-bottom: 0.6rem;
            background: #FFFFFF;
        }
        .card-title { font-weight: 600; font-size: 0.98rem; margin-bottom: 0.15rem; }
        .card-meta { color: #6B7280; font-size: 0.8rem; }
        .type-chip {
            display: inline-block;
            font-size: 0.7rem;
            font-weight: 700;
            padding: 0.1rem 0.5rem;
            border-radius: 6px;
            color: white;
            margin-right: 0.4rem;
        }
        .course-chip {
            display: inline-block;
            border: 1px solid #E85D2C;
            color: #E85D2C;
            border-radius: 999px;
            padding: 0.3rem 0.9rem;
            margin-right: 0.5rem;
            font-weight: 600;
            font-size: 0.85rem;
        }
        [class*="st-key-reslink_"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.5rem; }
        [class*="st-key-reslink_"] [data-testid="stColumn"] { min-width: 0 !important; }
        .switch-wordmark {
            font-weight: 800;
            letter-spacing: -0.02em;
            color: #E85D2C;
        }
        .switch-wordmark .dot { color: #1A1A2E; }
        /* The ads dashboard is password-gated (pages/8_Ads_Admin.py).
           Hiding its sidebar entry only keeps it out of students' way ---
           the password, not this rule, is the access control. */
        [data-testid="stSidebarNav"] a[href*="Ads_Admin"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _fcm_runtime_iframe()


def _fcm_runtime_iframe(has_token: bool = False, auto_sync: bool = False):
    """A zero-size, invisible copy of static/fcm.html on every page.

    In its normal form it keeps the foreground onMessage handler alive
    app-wide: FCM delivers messages to the page's onMessage handler
    whenever a visible client exists; if no handler is mounted, an ad
    sent while someone is browsing (rather than with the app
    backgrounded) can be swallowed.

    auto_sync=True is the Home-only copy: when the browser already
    allows notifications but the server lost the token (a restart or
    redeploy wipes data/push_tokens.json), it re-fetches the token and
    hands it back through the one-time reload, so a user who already
    opted in never sees a card again. It does not mount onMessage, so
    foreground messages still have a single handler. Renders nothing
    until the FCM web config exists."""
    try:
        src = fcm_client.registration_iframe_src(
            mode="runtime", has_token=has_token, auto_sync=auto_sync
        )
    except Exception:
        return
    if not src:
        return
    st.markdown(
        f'<iframe src="{src}" title="Notification runtime" '
        'aria-hidden="true" tabindex="-1" width="0" height="0" '
        'style="position:absolute;width:0;height:0;border:0;visibility:hidden;">'
        '</iframe>',
        unsafe_allow_html=True,
    )


def notification_optin(user_id: str = ""):
    """Home's notification control.

    The visible card lives in static/fcm.html because
    Notification.requestPermission() and service-worker registration
    both need real browser JS in a same-origin document. The card is
    only shown while the browser's notification permission is
    undecided: once it is granted (or denied) the card removes itself,
    so a student who opted in never sees it again. The Firebase web
    config is passed in the iframe URL; the service-account secret
    never leaves the server.

    Browsers require a user gesture for the permission prompt, so an
    "auto request" is impossible -- the card is that gesture. What can
    be automatic is registration: when permission is already granted
    but the server has no token (token store wiped by a restart), the
    hidden runtime copy re-registers silently. Renders nothing when FCM
    isn't configured."""
    registered = False
    if user_id:
        try:
            registered = fcm_client.has_token_for_user(user_id)
        except Exception:
            registered = False

    _fcm_runtime_iframe(has_token=registered, auto_sync=True)

    try:
        src = fcm_client.registration_iframe_src(mode="ui", has_token=registered)
    except Exception:
        return
    if not src:
        return
    st.markdown(
        f'<iframe src="{src}" title="Enable campus notifications" '
        'width="100%" height="176" '
        'style="border:0;display:block;width:100%;height:176px;max-width:100%;">'
        '</iframe>',
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def _all_onboarding_data_uris() -> list[str]:
    """Base64 data-URIs for every image in assets/onboarding/, read once
    and cached for the running app's lifetime --- these are static
    bundled assets that never change at runtime, so re-reading and
    re-encoding them from disk on every Streamlit rerun (which happens
    on every button click anywhere on the page) would be pure waste.
    Embedding as data URIs (rather than plain file paths) is what makes
    onboarding_carousel() below work inside components.html()'s iframe
    without depending on how Streamlit happens to serve static files in
    a given environment --- local run and Streamlit Community Cloud have
    both been known to differ there, and a data URI sidesteps the
    question entirely. Returns [] (not an error) if the folder is
    missing or empty, so a repo checked out without the assets/
    directory degrades to "no carousel" rather than a crash."""
    if not ONBOARDING_DIR.exists():
        return []
    uris = []
    for path in sorted(ONBOARDING_DIR.glob("*.jpg")):
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        uris.append(f"data:image/jpeg;base64,{encoded}")
    return uris


@st.cache_data(show_spinner=False)
def brand_image_data_uri(filename: str) -> str:
    """Same caching/data-URI reasoning as _all_onboarding_data_uris()
    above, for call sites that want exactly one named brand photo
    (hub_banner() below, and pages/7_KIU_Hub.py's header) rather than
    the full set. Returns "" if the file doesn't exist so callers can
    fall back to a plain color instead of a broken image."""
    path = ONBOARDING_DIR / filename
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def onboarding_carousel(height: int = 230):
    """Auto-advancing, swipeable strip of the brand photos for the sign-
    up/login screen --- the literal "dynamic, swiping from one to the
    next" ask. Rendered via components.html() (a real sandboxed iframe)
    rather than st.markdown(unsafe_allow_html=True): the swipe/autoplay
    behavior needs actual <script> execution, and Streamlit's markdown
    renderer doesn't reliably run injected scripts the way a genuine
    iframe does --- every other custom-HTML block in this file
    (youtube_embed, drive_doc_embed, resource cards) is static markup
    with no JS, which is exactly why those stayed on st.markdown while
    this one didn't.

    The swipe gesture itself is plain CSS (scroll-snap on a horizontally
    scrolling flex row) --- that part works with no JS at all and is
    what makes a manual swipe feel native on a touchscreen. The JS layer
    on top only adds autoplay (advance every 3.2s) and the dot
    indicator, and pauses autoplay while a touch/mouse interaction is in
    progress so it never fights a swipe the person is mid-gesture on.

    Renders nothing (not a broken placeholder) if assets/onboarding/ is
    empty --- see _all_onboarding_data_uris()."""
    images = _all_onboarding_data_uris()
    if not images:
        return

    slides_html = "".join(
        f'<div class="swc-slide"><img src="{src}" alt="Switch"></div>' for src in images
    )
    dots_html = "".join(
        f'<div class="swc-dot{" active" if i == 0 else ""}"></div>' for i in range(len(images))
    )

    html = f"""
    <style>
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      .swc-track {{
        display: flex;
        overflow-x: auto;
        scroll-snap-type: x mandatory;
        -webkit-overflow-scrolling: touch;
        border-radius: 18px;
        scrollbar-width: none;
        -ms-overflow-style: none;
      }}
      .swc-track::-webkit-scrollbar {{ display: none; }}
      .swc-slide {{
        flex: 0 0 100%;
        scroll-snap-align: center;
      }}
      .swc-slide img {{
        width: 100%;
        height: {height}px;
        object-fit: cover;
        display: block;
      }}
      .swc-dots {{
        display: flex;
        justify-content: center;
        gap: 6px;
        margin-top: 10px;
      }}
      .swc-dot {{
        width: 7px; height: 7px; border-radius: 50%;
        background: #E5D9CE;
        transition: background 0.25s ease, transform 0.25s ease;
      }}
      .swc-dot.active {{ background: #E85D2C; transform: scale(1.3); }}
    </style>
    <div class="swc-track" id="swcTrack">{slides_html}</div>
    <div class="swc-dots" id="swcDots">{dots_html}</div>
    <script>
    (function() {{
      var track = document.getElementById('swcTrack');
      var dots = document.getElementById('swcDots').children;
      var n = track.children.length;
      var idx = 0;
      var interacting = false;
      var resumeTimer = null;

      function updateDots() {{
        for (var i = 0; i < n; i++) {{
          dots[i].className = 'swc-dot' + (i === idx ? ' active' : '');
        }}
      }}
      function goTo(i) {{
        idx = (i + n) % n;
        track.scrollTo({{ left: idx * track.clientWidth, behavior: 'smooth' }});
        updateDots();
      }}
      var timer = setInterval(function() {{
        if (!interacting) goTo(idx + 1);
      }}, 3200);

      track.addEventListener('scroll', function() {{
        if (track.clientWidth === 0) return;
        var i = Math.round(track.scrollLeft / track.clientWidth);
        if (i !== idx) {{ idx = i; updateDots(); }}
      }}, {{ passive: true }});

      ['touchstart', 'mousedown'].forEach(function(evt) {{
        track.addEventListener(evt, function() {{
          interacting = true;
          clearTimeout(resumeTimer);
        }}, {{ passive: true }});
      }});
      ['touchend', 'mouseup'].forEach(function(evt) {{
        track.addEventListener(evt, function() {{
          resumeTimer = setTimeout(function() {{ interacting = false; }}, 2600);
        }}, {{ passive: true }});
      }});
    }})();
    </script>
    """
    components.html(html, height=height + 26)


def hub_banner():
    """Colorful entry-point card for the KIU Resource Hub, shown near the
    top of Home --- the "access the second app from the main app's UX"
    ask, made into an actual visible, branded doorway rather than a bare
    link. Image + gradient is static markup (st.markdown is fine here,
    unlike onboarding_carousel --- no JS involved), followed by a real
    st.button for the actual navigation: the same card-renders-then-a-
    real-button-underneath split resource_card() and course_unit_tile()
    above already use, not a new pattern invented for just this card.
    Falls back to a plain gradient (no broken image) if the named photo
    is missing --- see brand_image_data_uri()."""
    image = brand_image_data_uri("switch-04.jpg")
    if image:
        background = (
            f"background-image: linear-gradient(180deg, rgba(26,26,46,0.05) 35%, "
            f"rgba(26,26,46,0.82) 100%), url('{image}'); background-size: cover; "
            f"background-position: center;"
        )
    else:
        background = "background: linear-gradient(135deg, #1F6F5C, #E85D2C);"

    st.markdown(
        f"""
        <div style="border-radius:16px; overflow:hidden; {background}
                    padding:1.4rem 1.1rem 1rem; margin-bottom:0.6rem; min-height:132px;
                    display:flex; flex-direction:column; justify-content:flex-end;">
            <div style="color:#FFFFFF; font-weight:700; font-size:1.05rem;">🎓 KIU Resource Hub</div>
            <div style="color:#F3F1EC; font-size:0.85rem; margin-top:0.15rem;">
                Hostels, jobs &amp; scholarships for KIU students
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Explore the Hub →", key="hub_banner_cta", use_container_width=True):
        local_auth.switch_page("pages/7_KIU_Hub.py")


def wordmark(size: str = "1.4rem"):
    """Renders the 'switch.' wordmark --- lowercase, bold, trailing dot in ink not orange."""
    st.markdown(
        f'<div class="switch-wordmark" style="font-size:{size};">switch<span class="dot">.</span></div>',
        unsafe_allow_html=True,
    )


def file_type_chip(file_type: str) -> str:
    style = FILE_TYPE_STYLE.get(file_type, DEFAULT_STYLE)
    return f'<span class="type-chip" style="background:{style["color"]}">{style["icon"]} {style["label"]}</span>'


def resource_card(resource: dict, key_prefix: str):
    """Renders one feed/list card. Returns the button-click routing signal, if any."""
    style = FILE_TYPE_STYLE.get(resource.get("file_type"), DEFAULT_STYLE)
    with st.container():
        st.markdown(
            f"""
            <div class="card" style="border-left: 4px solid {style['color']};">
                <div>{file_type_chip(resource.get('file_type', ''))}
                    <span class="card-meta">{resource.get('course_code', '')}</span>
                </div>
                <div class="card-title">{resource.get('title', 'Untitled')}</div>
                <div class="card-meta">
                    {resource.get('uploader', '')}{' · ' if resource.get('uploader') else ''}{resource.get('uploaded_at', '')}
                    {' · ▲ ' + str(resource['upvotes']) if 'upvotes' in resource else ''}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cols = st.columns([1, 1, 1])
        open_clicked = cols[0].button("Open", key=f"{key_prefix}_open_{resource['id']}", use_container_width=True)
        save_clicked = cols[1].button("🔖 Save", key=f"{key_prefix}_save_{resource['id']}", use_container_width=True)
        share_clicked = cols[2].button("🔗 Share", key=f"{key_prefix}_share_{resource['id']}", use_container_width=True)

        if open_clicked:
            st.session_state["active_resource_id"] = resource["id"]
            st.session_state["_last_opened_resource"] = resource
            local_auth.switch_page("pages/6_Viewer.py")
        if save_clicked:
            user = local_auth.current_user()
            save_bookmark(resource, student_id=user["user_id"] if user else "demo-student")
            st.toast(f"Saved \"{resource.get('title')}\"")
        if share_clicked:
            st.toast("Share link copied (placeholder --- wire to real deep-link generation later)")


def youtube_embed(video_id: str, height: int = 220):
    """Renders an actual playable YouTube iframe embed (not just a link
    or a thumbnail-with-click-through) --- this is the literal 'embed
    the videos' ask. Wrapped in a rounded container matching .card's
    styling so it sits visually consistent with the rest of the UI
    rather than looking like a bare unstyled iframe."""
    st.markdown(
        f"""
        <div style="border-radius:12px; overflow:hidden; border:1px solid #E5E7EB;">
            <iframe width="100%" height="{height}"
                src="https://www.youtube.com/embed/{video_id}"
                title="YouTube video player"
                loading="lazy"
                frameborder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen>
            </iframe>
        </div>
        """,
        unsafe_allow_html=True,
    )


def drive_doc_embed(embed_url: str, height: int = 400):
    """Round 3: renders a Google Docs/Sheets/Slides/Drive-file inline
    preview via an iframe pointed at Google's own /preview (or /embed,
    for Slides) address --- the note/doc (drive_notes/drive_questions)
    equivalent of youtube_embed() above, same wrapping/styling
    treatment. `embed_url` is the already-built address from
    tree_store.drive_embed_url(); this function only renders it,
    matching youtube_embed()'s own split between building the address
    (tree_store) and rendering it (here).

    Google's /preview endpoint renders its own "you need access" page
    inside the iframe for a document that isn't shared "Anyone with
    the link" --- there's no way to tell that apart from a real
    document loading correctly from here, since the iframe's contents
    are cross-origin. That's why the Viewer (pages/6_Viewer.py) always
    shows a direct Open-in-Google-Docs link alongside this embed, not
    only when this is judged to have failed."""
    st.markdown(
        f"""
        <div style="border-radius:12px; overflow:hidden; border:1px solid #E5E7EB;">
            <iframe src="{embed_url}" width="100%" height="{height}" loading="lazy" frameborder="0"></iframe>
        </div>
        """,
        unsafe_allow_html=True,
    )


def video_resource_card(resource: dict, key_prefix: str):
    """Like resource_card(), but for file_type == 'video': renders the
    actual playable embed inline (via youtube_embed()) instead of an
    Open button that navigates away, since the point of embedding is
    not having to leave the card to watch. Save/Share stay as buttons
    below the embed --- Open is dropped since there's nothing further
    for a click-through 'Open' to do once the video is already playing
    right there."""
    style = FILE_TYPE_STYLE.get("video", DEFAULT_STYLE)
    video_id = resource.get("youtube_video_id")
    with st.container():
        st.markdown(
            f"""
            <div class="card" style="border-left: 4px solid {style['color']}; padding-bottom:0.5rem;">
                <div>{file_type_chip('video')}
                    <span class="card-meta">{resource.get('course_code', '')}</span>
                </div>
                <div class="card-title">{resource.get('title', 'Untitled')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if video_id:
            youtube_embed(video_id)
        else:
            # A youtube-kind link whose url didn't match the expected
            # pattern (see tree_store.youtube_video_id) --- fall back to
            # a plain link rather than an iframe pointed at nothing.
            st.caption(f"Couldn't embed this video. [Open on YouTube]({resource.get('url', '')})")

        cols = st.columns([1, 1])
        save_clicked = cols[0].button("🔖 Save", key=f"{key_prefix}_save_{resource['id']}", use_container_width=True)
        share_clicked = cols[1].button("🔗 Share", key=f"{key_prefix}_share_{resource['id']}", use_container_width=True)
        if save_clicked:
            user = local_auth.current_user()
            save_bookmark(resource, student_id=user["user_id"] if user else "demo-student")
            st.toast(f"Saved \"{resource.get('title')}\"")
        if share_clicked:
            st.toast("Share link copied (placeholder --- wire to real deep-link generation later)")

        # Recorded here (not just from the Viewer page) because embedded
        # videos are now watched in-place and may never route through
        # 6_Viewer.py at all --- history would silently miss every
        # embedded view otherwise. Guarded to fire once per Streamlit
        # session per resource: Streamlit reruns this whole page on ANY
        # button click anywhere on it (e.g. clicking Save on a
        # different card), and without this guard every such rerun
        # would re-record this video as "just opened" even though the
        # person didn't touch it that time --- reaching Course Detail
        # at all already required an explicit navigation click, so
        # that's the real "opened" signal; re-renders after that within
        # the same session aren't.
        if video_id:
            recorded_key = f"_history_recorded_{resource['id']}"
            if not st.session_state.get(recorded_key):
                user = local_auth.current_user()
                if user:
                    record_resource_opened(user["user_id"], resource)
                st.session_state[recorded_key] = True


def _css_url(url: str) -> str:
    """Quote a url for use inside CSS url("...") --- only the characters
    that could end the string or the declaration early."""
    return url.replace("\\", "%5C").replace('"', "%22").replace("\n", "").replace("<", "%3C")


def _tile_css(course: dict, key: str, index: int) -> str:
    """CSS that turns the st.button with this key into the tile itself:
    the course-tile image fills the button, the course name sits on a dark
    gradient at the bottom, and the whole thing fades in (staggered by
    `index`). There is no separate "Open" button --- the tile is the
    button, so a click anywhere on it is the click.

    Layer order (top to bottom): dark gradient for text legibility, the
    image, then a solid palette colour. If the image is missing from the
    sheet --- or Drive refuses to serve it because the file isn't shared
    "Anyone with the link" --- the bottom layer shows instead, so a tile
    never ends up blank or with a broken-image icon."""
    color = COURSE_TILE_PALETTE[index % len(COURSE_TILE_PALETTE)]
    image = course.get("tile_image")
    shade = "linear-gradient(180deg, rgba(15,15,30,0) 38%, rgba(15,15,30,0.82) 100%)"
    layers = [shade]
    if image:
        layers.append(f'url("{_css_url(image)}") center / cover no-repeat')
    layers.append(color)
    background = ", ".join(layers)
    sel = f".st-key-{key}"
    delay = round(0.08 * index, 2)
    return f"""
    {sel} {{ animation: swTileFade 0.7s ease-out {delay}s both; }}
    {sel} button,
    {sel} button:hover,
    {sel} button:focus,
    {sel} button:active {{
        background: {background};
        color: #FFFFFF;
        border: none;
        outline: none;
        box-shadow: 0 1px 4px rgba(0,0,0,0.18);
    }}
    {sel} button {{
        width: 100%;
        height: auto;
        aspect-ratio: 16 / 11;
        min-height: 130px;
        border-radius: 14px;
        padding: 0.7rem 0.8rem;
        display: flex;
        align-items: flex-end;
        justify-content: flex-start;
        text-align: left;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    {sel} button:hover {{ transform: translateY(-2px); box-shadow: 0 6px 14px rgba(0,0,0,0.22); }}
    {sel} button:active {{ transform: scale(0.98); }}
    {sel} button > div,
    {sel} button span,
    {sel} button [data-testid="stMarkdownContainer"] {{
        width: 100%;
        justify-content: flex-start !important;
        text-align: left !important;
    }}
    {sel} button p {{
        color: #FFFFFF;
        font-weight: 700;
        font-size: 0.95rem;
        line-height: 1.25;
        text-align: left;
        margin: 0;
        text-shadow: 0 1px 3px rgba(0,0,0,0.5);
    }}
    """


_TILE_KEYFRAMES = "@keyframes swTileFade { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }"


def _tile_button(course: dict, key_prefix: str, target_page: str) -> bool:
    key = f"{key_prefix}_tile_{course['id']}"
    clicked = st.button(course.get("name", "Untitled"), key=key, use_container_width=True)
    if clicked:
        st.session_state["active_course"] = course
        local_auth.switch_page(target_page)
    return clicked


def course_tile_grid(courses: list, key_prefix: str, columns: int = 2, target_page: str = "pages/3_Course_Detail.py"):
    """The 'My Active Courses' grid. All tile CSS is emitted in ONE style
    block (one st.markdown, so no extra gap per tile), then each course
    gets a button that IS the tile --- see _tile_css(). Tiles fade in as
    the page opens, one after another."""
    css = _TILE_KEYFRAMES + "".join(
        _tile_css(c, f"{key_prefix}_tile_{c['id']}", i) for i, c in enumerate(courses)
    )
    # Streamlit stacks st.columns into one column below ~640px, which on a
    # phone would turn this into a long single-file list of huge tiles.
    # The grid keeps its columns side by side at any width; scoped to this
    # one keyed container so no other columns block in the app is touched.
    grid_key = f"{key_prefix}_tilegrid"
    css += f"""
    .st-key-{grid_key} [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: 0.7rem; }}
    .st-key-{grid_key} [data-testid="stColumn"] {{ min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }}
    """
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    with st.container(key=grid_key):
        cols = st.columns(columns)
        for i, course in enumerate(courses):
            with cols[i % columns]:
                _tile_button(course, key_prefix, target_page)


def course_unit_tile(course: dict, key_prefix: str, index: int = 0, target_page: str = "pages/3_Course_Detail.py"):
    """Single-tile version of course_tile_grid(), kept for any caller that
    renders one tile on its own. Returns True if clicked this run."""
    css = _TILE_KEYFRAMES + _tile_css(course, f"{key_prefix}_tile_{course['id']}", index)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    return _tile_button(course, key_prefix, target_page)


def course_banner(course: dict):
    """Header banner for the Course Detail page: the same tile image (or
    palette colour if there is none) with the course name over it."""
    color = COURSE_TILE_PALETTE[0]
    image = course.get("tile_image")
    layers = ["linear-gradient(180deg, rgba(15,15,30,0.05) 30%, rgba(15,15,30,0.85) 100%)"]
    if image:
        # Single quotes: this goes inside a double-quoted style="..." attribute.
        layers.append(f"url('{_css_url(image).replace(chr(39), '%27')}') center / cover no-repeat")
    layers.append(color)
    st.markdown(
        f"""
        <div style="border-radius:14px; overflow:hidden; background:{', '.join(layers)};
                    min-height:140px; padding:1rem; display:flex; align-items:flex-end;
                    margin-bottom:0.6rem; animation: swTileFade 0.6s ease-out both;">
            <div style="color:#FFFFFF; font-weight:800; font-size:1.3rem; line-height:1.2;
                        text-shadow:0 1px 3px rgba(0,0,0,0.5);">{course.get('name', 'Course')}</div>
        </div>
        <style>{_TILE_KEYFRAMES}</style>
        """,
        unsafe_allow_html=True,
    )


def _open_in_viewer(resource: dict):
    st.session_state["active_resource_id"] = resource["id"]
    st.session_state["_last_opened_resource"] = resource
    local_auth.switch_page("pages/6_Viewer.py")


def _resource_row(resource: dict, label: str, key_prefix: str):
    """One notes/questions item inside a topic: a wide Open button (to the
    Viewer) and a Save button."""
    # Keyed container -> inject_base_css() keeps these two columns side by
    # side on a phone instead of letting Streamlit stack them.
    with st.container(key=f"reslink_{key_prefix}_{resource['id']}"):
        cols = st.columns([4, 1])
        if cols[0].button(label, key=f"{key_prefix}_open_{resource['id']}", use_container_width=True):
            _open_in_viewer(resource)
        if cols[1].button("🔖", key=f"{key_prefix}_save_{resource['id']}", help="Save", use_container_width=True):
            user = local_auth.current_user()
            save_bookmark(resource, student_id=user["user_id"] if user else "demo-student")
            st.toast(f"Saved \"{resource.get('title')}\"")


def topic_section(title: str, resources: list, key_prefix: str):
    """One topic as a collapsed accordion. Open it to see its three
    slots --- Video, Notes, Questions --- always all three, with a quiet
    "not added yet" line for any the spreadsheet has no link for, so a
    gap in the data reads as a gap rather than the app being broken.

    The video plays inline (lazy iframe: the browser doesn't load it
    until the accordion is actually opened). Unlike video_resource_card(),
    this does NOT record a history entry on render: with a whole list of
    collapsed topics all rendering on one page load, that would mark
    every video on the page as 'just watched'."""
    videos = [r for r in resources if r.get("file_type") == "video"]
    notes = [r for r in resources if r.get("file_type") == "note"]
    questions = [r for r in resources if r.get("file_type") == "doc"]
    others = [r for r in resources if r.get("file_type") not in ("video", "note", "doc")]

    with st.expander(title or "Untitled topic"):
        st.markdown("**🎥 Video**")
        if videos:
            for r in videos:
                if r.get("youtube_video_id"):
                    youtube_embed(r["youtube_video_id"])
                else:
                    st.caption(f"Couldn't embed this video. [Open on YouTube]({r.get('url', '')})")
        else:
            st.caption("No video added yet.")

        st.markdown("**📝 Notes**")
        if notes:
            for r in notes:
                _resource_row(r, "Open notes", key_prefix)
        else:
            st.caption("No notes added yet.")

        st.markdown("**❓ Questions**")
        if questions:
            for r in questions:
                _resource_row(r, "Open questions", key_prefix)
        else:
            st.caption("No questions added yet.")

        for r in others:
            _resource_row(r, "Open link", key_prefix)


def semester_fallback_notice(source: str):
    """Shown above the course tile(s) when local_client.resolve_active_courses()
    couldn't resolve the signed-in user's own stored semester --- i.e. that
    path no longer matches anything in the current course data (say,
    repo_5.xlsx was edited) --- and fell back to a different, real course
    unit instead (source "any"; never the university root, which this app
    doesn't show any more regardless). Draws nothing on a normal load
    (source "semester" or "home_node")."""
    if source == "any":
        st.info("Your saved semester isn't in the current course data, so this shows a different semester's course units instead.")
