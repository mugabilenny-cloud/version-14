"""
One-time importer: repo_5.xlsx (flat path/link rows) -> data/tree.json.

Produces the same {nodes, links} shape the real Supabase schema exposes
(nodes: id/name/node_type/parent_id/sort_order, links: id/node_id/
link_kind/url/title), so local_client.py can serve it with the exact
function signatures supabase_client.py used to hit over HTTP.

Run once (or whenever repo_5.xlsx changes):
    python tools/import_content.py [path/to/repo_5.xlsx]

Cleaning rules (silent skip, no report file):
  - A row is usable only if it has both a url and a link_kind. Rows
    missing either (structural/blank spacer rows, path-only rows with
    no link) are dropped without comment.
  - link_kind is case- and separator-normalized: "drive_Notes" and
    "drive-Notes" both become "drive_notes"; "youtube" stays "youtube";
    anything else unrecognized is dropped.
  - Class Title is forward-filled *within* each path group before
    filtering, because the source data only carries the title on the
    first of each (youtube / drive_notes / drive_questions) triplet.
  - Node tree levels come from the path's own segment count (7 in this
    file: University/Faculty/Department/Year/Semester/CourseUnit/leaf-
    marker) rather than a hardcoded 8, so the importer doesn't silently
    mis-shape a future file with a different depth.

Round 7 addition (course tiles): the sheet now has a "course tile" column.
The image link sits on the FIRST row of each course unit and is attached
to that course unit's node as node["tile_url"]. It is read BEFORE the
usable-row filter above, because a course unit's first row can easily be
a row the filter drops (e.g. a youtube row with no url yet) -- the tile
must not disappear with it. Paths are also normalised (segments stripped,
re-joined) before the forward-fill/group-by, because the sheet has
"Class" vs "Class " and "BMS /Year 3" variants of the same path that
would otherwise be treated as different groups.

Round 3 addition: a url that's present (so the row isn't dropped by the
rule above) but doesn't start with http:// or https:// is still
imported as-is -- this importer has no way to know if a differently-
shaped value is a typo or intentional -- but is now also collected and
printed as a warning list after the import summary, so a url that's
obviously never going to open or embed doesn't have to be found by
clicking through the app first. This does NOT catch a url that's a
well-formed http(s) address but points somewhere dead, unshared, or
otherwise inaccessible -- that's a live-content problem no static check
on the spreadsheet can catch; see the Viewer's own fallback handling
for that case instead.
"""
import json
import sys
import uuid
from pathlib import Path

import pandas as pd

KIND_MAP = {
    "youtube": "youtube",
    "drive_notes": "drive_notes",
    "drive-notes": "drive_notes",
    "drive notes": "drive_notes",
    "drive_questions": "drive_questions",
    "drive-questions": "drive_questions",
    "drive questions": "drive_questions",
}

NODE_TYPE_BY_DEPTH = [
    "university",
    "faculty",
    "department",
    "year",
    "semester",
    "course_unit",
    "leaf",
]


COURSE_UNIT_DEPTH = NODE_TYPE_BY_DEPTH.index("course_unit")


def normalize_kind(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return KIND_MAP.get(key)


def stable_id(*parts: str) -> str:
    """Deterministic id from path parts, so re-running the import is idempotent
    (same input -> same node/link ids) instead of minting new uuids every run."""
    ns = uuid.uuid5(uuid.NAMESPACE_URL, "switch-app://tree")
    return str(uuid.uuid5(ns, "/".join(parts)))


def _normalise_path(raw):
    """Strip whitespace around every path segment, so 'BMS /Year 3' and
    'Class ' are the same segments everywhere else in this file."""
    if not isinstance(raw, str):
        return raw
    return "/".join(s.strip() for s in raw.split("/") if s.strip())


def _find_column(df: pd.DataFrame, wanted: str):
    """Case/space-insensitive column lookup ('course tile', 'Course Tile',
    'course_tile' all match). None if the sheet has no such column."""
    key = wanted.lower().replace("_", " ").strip()
    for c in df.columns:
        if str(c).lower().replace("_", " ").strip() == key:
            return c
    return None


def build_tree(xlsx_path: Path) -> dict:
    df = pd.read_excel(xlsx_path)
    df["path"] = df["path"].ffill()  # blank path cells belong to the row above
    df["path"] = df["path"].map(_normalise_path)
    df["Class Title"] = df.groupby("path")["Class Title"].ffill()
    tile_col = _find_column(df, "course tile")

    nodes: dict[str, dict] = {}
    links: list[dict] = []
    sort_counters: dict[str | None, int] = {}

    def get_or_create_node(segments: list[str], depth: int, parent_id: str | None) -> str:
        node_id = stable_id(*segments[: depth + 1])
        if node_id not in nodes:
            sort_counters.setdefault(parent_id, 0)
            nodes[node_id] = {
                "id": node_id,
                "name": segments[depth].strip(),
                "node_type": NODE_TYPE_BY_DEPTH[depth] if depth < len(NODE_TYPE_BY_DEPTH) else "node",
                "parent_id": parent_id,
                "sort_order": sort_counters[parent_id],
            }
            sort_counters[parent_id] += 1
        return node_id

    dropped = 0
    suspicious_urls = []  # present, but not http(s) -- likely to fail; flagged, not dropped
    for _, row in df.iterrows():
        path = row.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        segments = [s.strip() for s in path.split("/") if s.strip()]

        # Course tile: read before the usable-row filter (see docstring).
        if tile_col is not None:
            tile = row.get(tile_col)
            if isinstance(tile, str) and tile.strip() and len(segments) > COURSE_UNIT_DEPTH:
                unit_id = None
                parent_id = None
                for depth in range(COURSE_UNIT_DEPTH + 1):
                    parent_id = get_or_create_node(segments, depth, parent_id)
                unit_id = parent_id
                nodes[unit_id].setdefault("tile_url", tile.strip())

        kind = normalize_kind(row.get("link_kind"))
        url = row.get("url")
        if kind is None or not isinstance(url, str) or not url.strip():
            dropped += 1
            continue

        parent_id = None
        for depth in range(len(segments)):
            parent_id = get_or_create_node(segments, depth, parent_id)
        leaf_node_id = parent_id  # last segment created = the leaf this link hangs off

        title = row.get("Class Title")
        title = title.strip() if isinstance(title, str) and title.strip() else None

        clean_url = url.strip()
        if not clean_url.lower().startswith(("http://", "https://")):
            suspicious_urls.append((path, kind, clean_url))

        links.append(
            {
                "id": stable_id("link", path, kind, clean_url),
                "node_id": leaf_node_id,
                "link_kind": kind,
                "url": clean_url,
                "title": title,
            }
        )

    print(f"Imported {len(nodes)} nodes, {len(links)} links; skipped {dropped} unusable rows.",
          file=sys.stderr)
    if suspicious_urls:
        print(
            f"WARNING: {len(suspicious_urls)} link(s) have a url that doesn't start with "
            f"http:// or https:// -- imported as-is (not dropped), but very likely to fail "
            f"to open or embed. Check these rows in the source spreadsheet:",
            file=sys.stderr,
        )
        for path, kind, bad_url in suspicious_urls:
            print(f"  - [{kind}] {path!r}: {bad_url!r}", file=sys.stderr)
    return {"nodes": list(nodes.values()), "links": links}


def main():
    xlsx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "repo_5.xlsx"
    out_path = Path(__file__).parent.parent / "data" / "tree.json"
    tree = build_tree(xlsx_path)
    # Round 3 fix: a fresh clone of this repo has no data/ directory at all
    # yet (it's gitignored -- see .gitignore -- since it's generated, not
    # checked in). write_text() doesn't create missing parent directories,
    # so running this importer as the very first step on a new checkout
    # crashed with FileNotFoundError before this line was added.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(tree, indent=2))
    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
