"""
Raw tree access over the local JSON file --- the local equivalent of the
"Raw tree access (used internally by the shims below)" section of
supabase_client.py, plus the two _node_to_*/_link_to_* reshaping
functions from that file (made public here since local_client.py and
tools/import_content.py both need them, and there's no module-private
convention worth enforcing across a two-file local package).

Loaded once per Streamlit session via @st.cache_resource --- data/tree.json
is small (24 nodes / 157 links from the current repo_5.xlsx import) and
read-only at runtime, so caching avoids re-parsing it on every rerun
without needing any actual database engine.

Three additions beyond the original build:
  - youtube_video_id() --- extracts the 11-char video id from a
    youtube.com/watch?v=... url, for embedding (see local_client.py's
    docstring for why embedding needed this at all).
  - drive_embed_url() --- round 3 addition, same purpose as
    youtube_video_id() but for drive_notes/drive_questions links:
    turns a docs.google.com or drive.google.com url into the matching
    Google /preview (or /embed, for Slides) address the Viewer can
    point an iframe at, instead of the static placeholder box those
    file types fell into before. Returns None on a url that doesn't
    match a recognized Google Docs/Drive shape --- the same "didn't
    match" contract youtube_video_id() already uses --- which is not
    the same thing as the url being dead; this function only looks at
    the url's shape, never fetches it.
  - links_for_node_grouped() --- the source spreadsheet's "leaf" level
    is a single literal "Class" node per course unit (see
    tools/import_content.py's docstring), so every link for e.g.
    Pathophysiology --- 14+ of them across Epilepsy, Meningitis, Stroke,
    etc --- shares one node_id. The tree structure alone can't tell them
    apart; only each link's own `title` field (forward-filled from the
    source's "Class Title" column) can. This groups by that field so
    Course Detail can render topic sub-sections instead of one flat
    unlabeled pile.
  - search() rewritten to be hierarchy-aware: it now tags each node hit
    with which level matched (faculty/department/course_unit/etc, per
    Data_Model_and_retrieval_Complexity.docx's named hierarchy levels)
    and each link hit with its resource kind, instead of returning two
    undifferentiated flat lists.
"""
import json
import re
from pathlib import Path
from typing import Optional

import streamlit as st

DATA_PATH = Path(__file__).parent / "data" / "tree.json"

_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})"
)


def youtube_video_id(url: str) -> Optional[str]:
    """Extracts the 11-char video id from a youtube url, or None if the
    url doesn't match a known youtube link shape. Checked against all 30
    real youtube urls in the current data import --- every one matches
    the watch?v= pattern, but youtu.be/ and /embed/ are also handled
    since those are common enough alternate forms to be worth covering."""
    if not isinstance(url, str):
        return None
    m = _YOUTUBE_ID_RE.search(url)
    return m.group(1) if m else None


# Round 3: three separate single-purpose patterns (matching _YOUTUBE_ID_RE's
# own style above) rather than one combined regex --- easier to verify each
# url shape independently, and to extend later if a new shape shows up.
_GOOGLE_DOC_RE = re.compile(r"docs\.google\.com/(document|spreadsheets|presentation)/d/([a-zA-Z0-9_-]+)")
_DRIVE_FILE_RE = re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)")
_DRIVE_ID_PARAM_RE = re.compile(r"drive\.google\.com/(?:open|uc)\?.*?\bid=([a-zA-Z0-9_-]+)")

# Google serves an iframe-embeddable preview at these fixed paths per doc
# type --- /preview for Docs/Sheets/generic Drive files, /embed for Slides.
# This only builds the address; it never fetches it, so it can't tell a
# real document from one that will 404 or show Google's own "you need
# access" page once actually loaded in a browser.
_EMBED_TEMPLATES = {
    "document": "https://docs.google.com/document/d/{id}/preview",
    "spreadsheets": "https://docs.google.com/spreadsheets/d/{id}/preview",
    "presentation": "https://docs.google.com/presentation/d/{id}/embed",
    "file": "https://drive.google.com/file/d/{id}/preview",
}


def drive_embed_url(url: str) -> Optional[str]:
    """Extracts a Google Docs/Sheets/Slides/Drive file id from a url and
    returns the matching iframe-embeddable /preview (or /embed) address,
    or None if the url doesn't match a recognized Google Docs/Drive shape
    --- the drive_notes/drive_questions equivalent of youtube_video_id()
    above, called from the same place (link_to_resource_shape()) the
    same way. Handles the shapes real link data is expected to use:
    docs.google.com/{document,spreadsheets,presentation}/d/ID/..., a
    direct drive.google.com/file/d/ID/... share link, and the older
    drive.google.com/open?id=ID / uc?id=ID forms.

    A None return means this code doesn't recognize the url as a Google
    Docs/Drive link at all --- it is NOT a check of whether the url is
    reachable or the document is shared publicly. A url can match here
    and still fail to load for a real viewer if the underlying document
    isn't shared "Anyone with the link" --- that's a sharing-settings
    problem on the document itself, not something a url pattern match
    can detect or fix."""
    if not isinstance(url, str):
        return None
    m = _GOOGLE_DOC_RE.search(url)
    if m:
        return _EMBED_TEMPLATES[m.group(1)].format(id=m.group(2))
    m = _DRIVE_FILE_RE.search(url)
    if m:
        return _EMBED_TEMPLATES["file"].format(id=m.group(1))
    m = _DRIVE_ID_PARAM_RE.search(url)
    if m:
        return _EMBED_TEMPLATES["file"].format(id=m.group(1))
    return None


def tile_image_url(url) -> Optional[str]:
    """Turns the sheet's "course tile" cell into something an <img> / CSS
    background can load. A Google Drive share link
    (drive.google.com/file/d/ID/view) is NOT an image address -- it's a
    viewer page -- so it's rewritten to Drive's thumbnail endpoint, which
    serves the actual image bytes (the file must be shared "Anyone with
    the link", same requirement as the notes/doc embeds). Any other
    http(s) url is used as-is (a direct .png/.jpg link). None for blank or
    unusable values, so callers fall back to a plain colour tile instead
    of a broken image. Shape-only, like drive_embed_url(): never fetches."""
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    m = _DRIVE_FILE_RE.search(url) or _DRIVE_ID_PARAM_RE.search(url)
    if m:
        return f"https://drive.google.com/thumbnail?id={m.group(1)}&sz=w1000"
    if url.lower().startswith(("http://", "https://")):
        return url
    return None


class TreeStore:
    def __init__(self, nodes: list[dict], links: list[dict]):
        self._nodes_by_id = {n["id"]: n for n in nodes}
        self._links_by_id = {l["id"]: l for l in links}
        self._children_by_parent: dict[Optional[str], list[dict]] = {}
        for n in nodes:
            self._children_by_parent.setdefault(n["parent_id"], []).append(n)
        for bucket in self._children_by_parent.values():
            bucket.sort(key=lambda n: n["sort_order"])
        self._links_by_node: dict[str, list[dict]] = {}
        for l in links:
            self._links_by_node.setdefault(l["node_id"], []).append(l)

    # -- raw access -----------------------------------------------------

    def roots(self) -> list[dict]:
        return list(self._children_by_parent.get(None, []))

    def children_of(self, parent_id: str) -> list[dict]:
        return list(self._children_by_parent.get(parent_id, []))

    def node_by_id(self, node_id: str) -> Optional[dict]:
        return self._nodes_by_id.get(node_id)

    def link_by_id(self, link_id: str) -> Optional[dict]:
        return self._links_by_id.get(link_id)

    def links_for_node(self, node_id: str) -> list[dict]:
        return list(self._links_by_node.get(node_id, []))

    def node_path_label(self, node: dict) -> str:
        """Slash-joined ancestor chain, used for search-result labeling ---
        the local stand-in for the real schema's node_path column."""
        parts = [node["name"]]
        cur = node
        while cur.get("parent_id"):
            cur = self._nodes_by_id.get(cur["parent_id"])
            if not cur:
                break
            parts.append(cur["name"])
        return "/".join(reversed(parts))

    def nodes_of_type(self, node_type: str) -> list[dict]:
        """All nodes at a given level (e.g. "semester"), for building
        pickers --- specifically the signup semester picker, where a
        bare node name like "Semester 1" is ambiguous (this data has TWO
        semester nodes both named "Semester 1", one under Year 2 and one
        under Year 3 --- see node_path_label() for the disambiguating
        full path each one needs to be shown with)."""
        return [n for n in self._nodes_by_id.values() if n.get("node_type") == node_type]

    def first_node_of_type(self, node_type: str) -> Optional[dict]:
        """The first node of a given type in display order --- a proper
        top-down, sort_order-respecting walk from roots() via
        children_of(), not nodes_of_type()'s dict-iteration order (which
        reflects data/tree.json's own node order, not the tree's actual
        shape). Used as the last-resort "pick one real course unit, never
        the university root" fallback in local_client.resolve_active_courses().
        None only if the type doesn't occur anywhere in the tree. Called
        with "semester" as the last-resort "pick ONE real semester, show
        its course units" fallback in local_client.resolve_active_courses()."""
        stack = list(reversed(self.roots()))
        while stack:
            node = stack.pop()
            if node.get("node_type") == node_type:
                return node
            stack.extend(reversed(self.children_of(node["id"])))
        return None

    def find_node_by_path_label(self, path_label: str) -> Optional[dict]:
        """Reverse of node_path_label() --- given a "Segment/Segment/..."
        string, finds the node whose full ancestor chain matches it
        exactly. Used to resolve a user's stored semester choice (saved
        as a path_label string at signup) back to a real node_id at
        Home-tile render time."""
        for n in self._nodes_by_id.values():
            if self.node_path_label(n) == path_label:
                return n
        return None

    def links_for_node_grouped(self, node_id: str) -> list[tuple[Optional[str], list[dict]]]:
        """Links at a node, grouped by each link's own `title` field and
        ordered by first appearance --- the fix for the "Class" leaf
        problem (see module docstring). A group's key is None only if
        every link at this node genuinely has no title (the source row's
        Class Title was blank even after forward-fill); those are kept
        as their own untitled group rather than silently merged into
        whichever titled group happens to be adjacent."""
        groups: dict[Optional[str], list[dict]] = {}
        for link in self.links_for_node(node_id):
            groups.setdefault(link.get("title"), []).append(link)
        return list(groups.items())

    def search(self, query: str) -> tuple[list[dict], list[dict]]:
        """Hierarchy-aware match over node names and link titles/urls ---
        the local equivalent of fn_search_tree, extended beyond a flat
        substring scan. Case-insensitive, matches anywhere in the string
        (mirroring Postgres ILIKE '%query%').

        Each node hit is tagged with `matched_level` (its node_type ---
        faculty/department/course_unit/etc, the levels named in
        Data_Model_and_retrieval_Complexity.docx) so callers can label
        *what kind* of thing matched, not just that something did. Each
        link hit is tagged with `matched_in` ("title" or "url") for the
        same reason on the resource side. Node hits and link hits are
        independent: a course-unit node matching by name (e.g.
        "Pathophysiology") does not suppress or fold in its own links
        also being listed as separate hits when the query happens to
        match one of THEIR titles too --- the caller decides how to
        present both, rather than this method silently dropping one on
        the other's behalf."""
        q = query.strip().lower()
        if not q:
            return [], []

        node_hits = []
        for n in self._nodes_by_id.values():
            if q in n["name"].lower():
                hit = dict(n)
                hit["matched_level"] = n.get("node_type", "node")
                node_hits.append(hit)

        link_hits = []
        for l in self._links_by_id.values():
            title_match = q in (l.get("title") or "").lower()
            url_match = q in l["url"].lower()
            if not title_match and not url_match:
                continue
            hit = dict(l)
            hit["matched_in"] = "title" if title_match else "url"
            link_hits.append(hit)

        return node_hits, link_hits

    # -- reshaping (mirrors supabase_client.py's _node_to_*/_link_to_*) --

    def node_to_course_shape(self, node: dict) -> dict:
        return {
            "id": node["id"],
            "code": node.get("node_type", "").upper()[:4] or "NODE",
            "name": node.get("name", "Untitled"),
            "resource_count": None,  # not tracked --- UI hides it when None
            "node_type": node.get("node_type", ""),
            "tile_image": tile_image_url(node.get("tile_url")),
        }

    def link_to_resource_shape(self, link: dict, node_name: str = "") -> dict:
        kind_to_filetype = {"youtube": "video", "drive_notes": "note", "drive_questions": "doc"}
        shape = {
            "id": link.get("id"),
            "title": link.get("title") or link.get("url", "Untitled link"),
            "course_code": node_name,
            "file_type": kind_to_filetype.get(link.get("link_kind"), "link"),
            "url": link.get("url"),
        }
        if link.get("link_kind") == "youtube":
            # Carried alongside url (not instead of it) so the Viewer can
            # embed without re-parsing, while Open-in-new-tab / Share
            # still have the original url to work with.
            shape["youtube_video_id"] = youtube_video_id(link.get("url", ""))
        elif link.get("link_kind") in ("drive_notes", "drive_questions"):
            # Round 3, same pattern as the youtube branch above: computed
            # once here rather than in the Viewer, and carried alongside
            # url (not instead of it) so a url that doesn't match a known
            # Google Docs/Drive shape still has its original url available
            # for a plain Open-link fallback instead of no link at all.
            shape["drive_embed_url"] = drive_embed_url(link.get("url", ""))
        return shape


@st.cache_resource
def get_store() -> TreeStore:
    if not DATA_PATH.exists():
        # Round 4: data/tree.json is intentionally gitignored (round 3's
        # .gitignore change) -- generated, not checked in. On a machine with
        # a terminal, tools/import_content.py's own docstring covers running
        # it by hand. Streamlit Community Cloud has no way to run a one-time
        # setup script before the app starts, and this project has no
        # terminal available for it either (see README) -- a fresh deploy
        # needs this to happen on its own. So: build it in-process from
        # repo_5.xlsx the first time this is called (cached after that by
        # @st.cache_resource for the running app's lifetime -- same
        # per-container lifetime data/tree.json itself would have had
        # either way, since Streamlit Cloud's filesystem doesn't persist
        # across reboots/redeploys regardless of how the file got there).
        repo_xlsx = Path(__file__).parent / "repo_5.xlsx"
        if not repo_xlsx.exists():
            raise FileNotFoundError(
                f"Couldn't find {DATA_PATH} or {repo_xlsx}. Add repo_5.xlsx "
                f"to the repo root -- GitHub's web upload or your Git GUI "
                f"both work, no terminal needed -- and reboot the app; "
                f"data/tree.json will be built from it automatically on "
                f"first load. (On a machine with a terminal, running "
                f"`python tools/import_content.py <repo_5.xlsx>` does the "
                f"same thing by hand.)"
            )
        from tools.import_content import build_tree
        tree = build_tree(repo_xlsx)
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        DATA_PATH.write_text(json.dumps(tree, indent=2))
    raw = json.loads(DATA_PATH.read_text())
    return TreeStore(raw["nodes"], raw["links"])
