# Switch — local-data build with auth, hierarchy search, embedded video, and the KIU Resource Hub

> **Round 8 — KIU Hub entries from a spreadsheet, WhatsApp contact:**
> The Hub can now be fed the same way as the course content: one sheet, `hub_repo.xlsx` at the repo root, columns `path` | `title` | `url` | `details` (details optional; `category`/`link`/`notes` also accepted as column names). The first `path` segment is the category (one tab each, in order of appearance); an optional second segment (`Hostels/Kansanga`) becomes the filter dropdown; a blank `path` cell belongs to the row above, as in `repo_5.xlsx`. If `hub_repo.xlsx` is missing or has no usable rows, the Hub shows the original `data/listings.xlsx` tabs unchanged. Every entry in both modes has a "Contact on WhatsApp" button that opens a chat with 0778612930 (`WHATSAPP_NUMBER` in `pages/7_KIU_Hub.py`, written as 256778612930) with a message naming the entry.

> **Earlier fix (round 7 — image course tiles, topic accordions, Sign out moved):**
> (1) `repo_5.xlsx` now has a **course tile** column (an image link on the first row of each course unit). `tools/import_content.py` stores it on the course-unit node as `tile_url` (read *before* the usable-row filter, so a first row with no video url yet doesn't lose its tile); `tree_store.tile_image_url()` turns a Google Drive share link into Drive's thumbnail address. The Drive file must be shared **"Anyone with the link"**, same as the notes/doc embeds; if the image can't load, the tile falls back to a solid colour.
> (2) Home tiles are now the image itself, and the tile *is* the button (no "Open" label); they fade in one after another and stay two-across on a phone (`ui_components.course_tile_grid`).
> (3) Course Detail opens straight onto the unit's topics (the extra "Class" step is skipped), each topic a collapsed accordion with Video / Notes / Questions (`ui_components.topic_section`).
> (4) Sign out moved from Home's header to the bottom of the KIU Hub page.


This is the six-original-screen "Switch" UX prototype (Home / My Courses /
Course Detail / Upload / Saved / Viewer), wired to the course-content
spreadsheet instead of a live Supabase project, with local file-backed auth
added on top. No external database, no network calls at runtime except the
YouTube and Google Docs/Drive iframe embeds themselves — everything else
reads from JSON files bundled in the repo.

**This round merges in the KIU Resource Hub** (previously its own separate
app/repo — hostel, job and scholarship listings read from a spreadsheet) as
an eighth screen, reachable from Home's banner and the page list in
Streamlit's own sidebar, plus a colorful, swipeable brand-photo carousel on
the sign-up screen. See "The KIU Resource Hub" and "What changed this round"
below for the details.

**Earlier fix (round 6): no more bottom nav bar, and "My Active Courses" never shows
the university tile.** The custom fixed bottom tab bar (Home / My Courses /
Hub / Upload / Saved, one row of buttons pinned to the bottom of every
screen) is gone. Navigation is Streamlit's own page list now — tap the
collapsed-sidebar arrow at the top left of any screen (it was always there,
just easy to miss under the custom bar) to get to Upload, Saved, My
Courses, the Hub, or Home from anywhere. On Home, "My Active Courses" no
longer ever falls back to a "KIU" tile with a "UNIV" badge, and no longer
trims down to one orphaned tile either — it always shows one full
semester's worth of course-unit tiles — the student's own semester when
it resolves, or, when it doesn't, a different real semester in the exact
same shape (multiple tiles, same grid), with a notice explaining the
substitution. `local_client.resolve_active_courses()` no longer calls
`store.roots()` at all — see "Local auth" below for what's still true
from the earlier session fix (accounts still don't survive a Community
Cloud restart; see "What's intentionally NOT here").

**Earlier fix: the "KIU / UNIV tile instead of my course units" bug.**
Signing up or logging in puts a session token in the URL, and every bare
`st.switch_page()` call then silently dropped it — so Home and My Courses
saw nobody signed in and fell back to the tree root. All navigation goes
through `local_auth.switch_page()`, and Home and My Courses send a
signed-out visitor to the sign-in page instead of quietly rendering a guest
view.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

First run needs `data/tree.json` to exist. It's gitignored (generated, not
checked in), so on a fresh checkout — including a fresh Streamlit Community
Cloud deploy — it doesn't exist yet. As long as `repo_5.xlsx` is present at
the repo root, `tree_store.get_store()` builds `data/tree.json` from it
automatically the first time the app runs (see "The data" below) — no
terminal or manual step required, which matters since this project doesn't
have a terminal available for deployment (only a Git GUI / GitHub's web
upload). On a machine that does have a terminal, running
`python tools/import_content.py repo_5.xlsx` by hand does the same thing,
and is the only way to regenerate `data/tree.json` after the spreadsheet
changes without just deleting the file and letting the app rebuild it fresh
on next load.

Once data's in place, you'll land on the sign-up/login screen
(`pages/0_Auth.py`) — now with a swiping strip of brand photos at the top.
Sign up, pick your current semester from the real list the data has, and
you're in for up to 3 days without needing to log in again. From Home, the
KIU Resource Hub is one tap away (banner card on Home, or "KIU Hub" in
Streamlit's own sidebar page list) and needs nothing signed in — it reads
`data/listings.xlsx` independently of everything above.

## The KIU Resource Hub

Was its own standalone app/repo (see `kiu-resource-hub-documentation.docx`
from that round); now lives at `pages/7_KIU_Hub.py` inside this one. What it
does is unchanged: reads hostel, job and scholarship listings from a single
workbook, `data/listings.xlsx`, and shows them as three searchable/
filterable tabs (🏠 Hostels, 💼 Jobs Board, 🎓 Scholarships). Editing that
workbook and pushing it to GitHub is still the entire "content management"
system — no separate admin app, no database, same as the original spec.

**`data/listings.xlsx` in this repo has sample rows only** (one shaded
example per sheet) — no real KIU listings were supplied when this round was
built. Open the `Instructions` sheet inside the workbook for the exact
editing rules (don't rename sheet tabs or headers, one listing per row,
leave blanks empty rather than "N/A"); replace the shaded sample row on
each of Hostels/Jobs/Scholarships with real data and push the file back to
`data/listings.xlsx` — no code changes needed for new listings, same
publishing model as before.

Two deliberate adaptations from the standalone version, both because this
is now a page inside a phone-first app rather than its own desktop site:

- **`layout="wide"` → `layout="centered"`.** Every other Switch page uses
  `layout="centered"` (this app is headed for a native mobile wrapper — see
  the project's own history); keeping the Hub's original "wide" layout
  would mean the page violently changes width on every navigation in or
  out of it. The trade-off is that the 3-column field rows (Area/Price/
  Room Type, etc.) run narrower than they did standalone — kept as-is
  rather than redesigned sight unseen; worth an eyeball once deployed (see
  "Testing" in the handoff doc).
- **`DATA_PATH` gained a `.parent`.** The original `app.py` sat at the repo
  root; this file sits one level deeper, in `pages/`, so finding
  `data/listings.xlsx` needs the extra step back up. Everything else about
  how the workbook is found, cached (5-minute TTL, `Refresh` button to
  bypass it), and read is unchanged from the original.

## What's here

**Local data layer (no external database).** `supabase_client.py`'s live
HTTP/RPC calls are replaced by `tree_store.py` (loads `data/tree.json`,
provides tree/search/grouping) and `local_client.py` (same function names
and shapes `supabase_client.py` had, so every page's import line was the
only required change versus the original prototype).

**Local auth (no external database, no plaintext passwords).** `local_auth.py`
— PBKDF2-HMAC-SHA256 with a random per-user salt; the raw password is never
written to disk. Session tokens (not passwords) persist across reloads via
`st.query_params`, file-backed in `data/sessions.json` with a 3-day expiry.
A valid session skips straight to Home with no re-prompt; an expired or
missing one routes to `pages/0_Auth.py`. Home and My Courses check this
themselves (`local_auth.require_user()`), not just `app.py`, so a bookmark or a
browser reload on either page can't fall through to a guest view.
**Always navigate with `local_auth.switch_page()`, never `st.switch_page()`** —
Streamlit clears the URL's query params on a page switch unless told what to
keep, which is exactly what used to drop the token. (That is also why
`requirements.txt` asks for Streamlit 1.52 or newer, the first version that
lets `st.switch_page()` carry query params.)

**Hierarchy-aware search.** `TreeStore.search()` tags node hits with which
tree level matched (faculty/department/course_unit/etc.) and link hits with
whether the query matched a title or a url, instead of one flat undifferentiated
list. `local_client.search_courses()` surfaces both to the search box.

**Per-topic grouping in Course Detail.** Every row in `repo_5.xlsx` ends its
path in the literal segment `"Class"`, so a course unit's 14+ links (for
Pathophysiology, for example) all share one tree node — see the caveat
below. `TreeStore.links_for_node_grouped()` splits them back into their real
topics (Epilepsy 2, Meningitis, Stroke, etc.) using each link's own `title`
field, and Course Detail renders a labeled section per topic instead of one
flat pile of cards.

**Red-coded inline YouTube embeds.** `tree_store.youtube_video_id()` extracts
the video id from a youtube url; `ui_components.youtube_embed()` renders an
actual playable iframe; `video_resource_card()` wraps that in a styled card
with a red (`#DC2626`) type chip. Reachable from Course Detail, Saved, Home's
search results, and the Viewer page.

**Embedded Google Docs/Drive viewing.** `tree_store.drive_embed_url()`
recognizes a docs.google.com or drive.google.com url (Docs, Sheets, Slides,
or a generic Drive file link) and builds Google's own iframe-embeddable
`/preview` (`/embed` for Slides) address; `ui_components.drive_doc_embed()`
renders it, the note/doc (`drive_notes`/`drive_questions`) equivalent of the
YouTube embed above. The Viewer always shows a direct "Open in Google Docs"
link alongside the embed — a document that isn't shared "Anyone with the
link" will show Google's own access-denied page inside the iframe rather
than failing visibly, so the direct link is there regardless of whether the
embed itself looks like it worked. A url that doesn't match a recognized
Google Docs/Drive shape falls back to a plain link instead of an embed
attempt; a resource with no url at all gets a plain "link unavailable"
message instead of either.

**Per-user history and saved items.** `local_history.py` and `local_saved.py`
— file-backed, so a save or a "recently opened" entry survives a closed tab
within your 3-day session, not just the current browser tab.

**Colorful, swipeable brand-photo carousel at sign-up.** `ui_components.
onboarding_carousel()` — five brand photos, auto-advancing every 3.2s,
genuinely swipeable by touch (CSS scroll-snap, not a JS reimplementation of
the gesture), with a dot-indicator strip. Lives on `pages/0_Auth.py`, above
the wordmark — the first thing anyone new to the app sees.

**KIU Resource Hub entry point on Home.** `ui_components.hub_banner()` — a
photo-backed card + button, placed after the search block and before "My
Active Courses" so it's visible on every Home load regardless of whether a
search is active.

## The data

`data/tree.json` is generated from `repo_5.xlsx` — either automatically (see
"Run it" above: `tree_store.get_store()` builds it in-process the first time
`data/tree.json` doesn't exist but `repo_5.xlsx` does) or by hand, if
`repo_5.xlsx` has changed and you have a terminal available:

```bash
python tools/import_content.py path/to/repo_5.xlsx
```

Either path produces the same file — the in-process version calls the exact
same `build_tree()` function this command does, it's just triggered by the
app itself instead of by you. Delete `data/tree.json` and reload the app to
force a rebuild from the current `repo_5.xlsx` without a terminal.

Current import: **24 nodes, 157 links** (30 of them YouTube videos with
real, working urls).

`data/listings.xlsx` (KIU Resource Hub) is separate from all of the above —
no importer, no generated JSON, just read directly. See "The KIU Resource
Hub" above.

### Two things worth knowing about the source data — not bugs, don't "fix" these

1. Every path in `repo_5.xlsx` ends in the literal segment `"Class"` rather
   than a per-topic name — this is why the title-based grouping above exists
   at all. The fix is at the link-grouping level (already built), not by
   trying to split `"Class"` into separate tree nodes.
2. The source file has two slightly different department-name spellings
   under Health Sciences (`"BMS   0000"` with extra internal spaces, and
   plain `"BMS"`) that produce two separate tree nodes rather than merging.
   This may reflect a real distinction in the source data — don't silently
   merge these.

### A note on dead/inaccessible drive_notes / drive_questions links

Unlike the YouTube urls above, the `drive_notes`/`drive_questions` urls in
the source spreadsheet have not been individually verified as reachable —
some have been reported dead or inaccessible. That's a property of the
spreadsheet data (and, for a url that does resolve, of that Google Doc's
own sharing setting — it needs to be shared "Anyone with the link" for
Google's `/preview` embed to render for someone who isn't signed into the
owner's account), not something `tools/import_content.py` or the Viewer can
repair on their own. Two things do help track it down:

- The importer now warns (to stderr, at the end of the import) about any
  url that doesn't start with `http://`/`https://` — a cheap, mechanical
  check that catches an obviously-broken cell, not a dead-but-well-formed
  one.
- A resource that has no url at all, or a url that isn't a recognized
  Google Docs/Drive address, gets a distinct "unavailable" or "can't
  preview inline" message in the Viewer instead of either a blank iframe or
  the fully-generic placeholder — see "Embedded Google Docs/Drive viewing"
  above.

Actually confirming which specific rows are dead means opening each url and
checking its sharing setting directly.

## Push notifications (FCM) for ads

The app can send rich push ads — small app icon, title, message, and a
large image, exactly the format in the design reference — to every device
that opts in. Students get an "Enable notifications" card on Home; staff
sign in with Firebase Authentication and send ads from a dashboard that
only allowlisted staff emails can open.

Everything here is free: Firebase Cloud Messaging is free on Firebase's
Spark plan, the sender calls FCM's HTTP v1 REST API directly from Python
with a service-account key, and there are no Cloud Functions, no paid
databases and no third-party push services.

### One-time Firebase setup

1. Create a Firebase project at <https://console.firebase.google.com>
   (the free Spark plan is enough).
2. **Project settings → General → Your apps → Add app → Web.** Copy the
   config values (`apiKey`, `authDomain`, `projectId`,
   `messagingSenderId`, `appId`).
3. **Cloud Messaging → Web Push certificates → Generate key pair.** Copy
   the VAPID key.
4. **Project settings → Service accounts → Generate new private key.**
   Download the JSON file.
5. **Authentication → Sign-in method → Email/Password → Enable.** Then add
   each staff member under **Authentication → Users → Add user**. On their
   first sign-in at `/Ads_Admin`, Firebase sends a verification email;
   they must open it before the dashboard unlocks.
6. Put everything in `.streamlit/secrets.toml` (local) or the app's
   **Secrets** settings (Streamlit Community Cloud). Start from
   `.streamlit/secrets.toml.example`, which lists every key:

   ```toml
   [fcm]
   api_key = "..."
   auth_domain = "your-project.firebaseapp.com"
   project_id = "your-project"
   messaging_sender_id = "..."
   app_id = "..."
   vapid_key = "B..."
   service_account_json = '''{ ...entire private-key JSON file... }'''

   [ads_admin]
   emails = ["staff@example.com"]
   ```

   `.streamlit/secrets.toml` is gitignored. The service-account JSON is a
   **real secret** — it can send notifications to the project; never commit
   it or paste it into chat/issue trackers. The web config and VAPID key are
   public by design (they are sent to the browser).

7. `pip install -r requirements.txt` (adds `google-auth`, used to mint the
   OAuth2 token for FCM; `requests` was already a Streamlit dependency but
   is now listed explicitly).

If any of the FCM values are missing, the student-facing opt-in card
simply does not render and the admin dashboard shows a setup checklist —
nothing else in the app changes.

### Opting in (student side)

Home shows a "Campus notifications" card. Clicking **Enable
notifications** prompts for browser permission, registers
`static/firebase-messaging-sw.js`, gets an FCM device token, and reloads
Home once with the token in the URL. `pages/1_Home.py` saves it to
`data/push_tokens.json` against the signed-in user and immediately
strips the parameter. `inject_base_css()` also mounts a hidden copy of
`static/fcm.html` on every page so foreground messages keep working
outside Home.

The card is only the permission request. Browsers require a user gesture
before they will show the notification prompt, so the request cannot be
fully automatic; what is automatic is everything after that. Once the
permission is granted or denied the card removes itself, and if the
permission is granted while the server has no token for the user (a
restart or redeploy wiped `data/push_tokens.json`), a hidden Home-only
copy of `static/fcm.html` re-fetches the token and hands it back through
the same one-time reload — no card, no click. Users who never decide
keep seeing the small card until they do.

### Sending an ad (staff side)

Open `/Ads_Admin` directly (the sidebar link is hidden so students don't
land on the sign-in gate by accident). Sign in with one of the staff
emails listed in `[ads_admin] emails`; the first sign-in also requires
opening the verification link Firebase emails you. Then compose the
notification, check the live preview, and press **Send**. Delivery goes
to every token in `data/push_tokens.json`; permanently rejected tokens
are pruned automatically, transient errors are not. Sent ads and their
delivery counts are kept in `data/ads.json` (newest first, capped at 50).

Sign-in is handled by Firebase Authentication in a small same-origin
iframe (`static/admin_auth.html`). It hands back a Firebase ID token
once, through the URL; `admin_auth.py` verifies Google's signature,
audience and expiry and then checks that the token's email is verified
and in the allowlist. The token is stripped from the URL immediately,
and **Lock** signs the Firebase user out. Students can create Firebase
accounts of their own, but without an allowlisted, verified email they
are rejected before the dashboard renders.

The large-image URL must be a **public http(s) URL** — the phone fetches
it directly when the notification is shown; Firebase does not host or
upload it. The click-through URL can be `/` (open Switch), any
root-relative path, or a full `https://` address.

### Limits worth knowing

- **Registrations don't survive a Community Cloud restart/redeploy.** Like
  accounts and sessions, `data/push_tokens.json` and `data/ads.json` live
  on the container disk, which is wiped on every reboot and redeploy.
  Students have to opt in again afterwards. Durable subscriptions need
  storage outside the container — the same open decision accounts have.
- **Push requires a secure context:** HTTPS (Community Cloud) or
  `http://localhost` for local testing. Plain `http://<LAN-IP>` will not
  work.
- **If you restrict the Firebase web API key**, allow the deployed app's
  domain (and `localhost` for local testing) in the key's HTTP-referrer
  restrictions; otherwise `getToken()` is rejected.
- **iOS** only delivers web push to a site added to the Home Screen
  (iOS 16.4+). Android Chrome and desktop browsers work directly.
- **No scheduling.** Ads send immediately; a timed queue would need a
  always-on worker, which is outside the "free, no Cloud Functions" scope.
- **Click-through sign-in:** a tap opens the app at `/`, not with the
  student's `?session=` token, so on a device where the session has
  expired they may need to log in again.
- Ads are only sent to devices that explicitly opted in; there is no
  silent/bulk notification path.

## What's intentionally NOT here

- **Ads / "What's New on Campus" feed** — no ads table exists locally, so
  `fetch_feed()` returns empty and that section stays hidden.
- **Student uploads / crowdsourcing** — the Upload screen is still a
  placeholder form; content is added by re-running the importer.
- **PDF/slide inline preview** — still shows a placeholder box in the
  Viewer rather than a real renderer. In practice this only matters if the
  data grows a `pdf`/`ppt` file type later: the current importer only ever
  produces `video`/`note`/`doc` from the source spreadsheet's `youtube` /
  `drive_notes` / `drive_questions` link kinds, and video and note/doc both
  get a real embed now (see "Embedded Google Docs/Drive viewing" above).
- **Accounts, sessions, history and saved items that survive a restart.**
  `data/users.json`, `sessions.json`, `history.json` and `saved.json` live on
  the app container's own disk. On Streamlit Community Cloud that disk is
  wiped on every reboot and redeploy, and nothing written at runtime is ever
  committed back to GitHub, so after a restart everyone has to sign up again
  (a signed-in browser is simply sent to the sign-in page). This is not a
  `.gitignore` problem: taking `data/*.json` out of `.gitignore` would not
  help, and would risk committing password hashes to a public repo.
  `tree.json` is the one exception, and only because it can be rebuilt from
  `repo_5.xlsx`. A real fix needs storage outside the container (a hosted
  database, for example) — a decision that hasn't been made yet.
- **A password-change or account-settings screen** — sign-out exists (bottom
  of the KIU Hub page); nothing else account-related does yet.
- **Real KIU Resource Hub listings** — `data/listings.xlsx` ships with one
  sample row per sheet only; see "The KIU Resource Hub" above.

## Project layout

```
app.py                  entry point — auth gate, routes to Home or sign-in
local_auth.py           local hash+salt auth, 3-day sessions (data/users.json,
                         data/sessions.json); switch_page() (the only way to
                         navigate), require_user(), start_session(), sign_out()
local_history.py        per-user "recently opened" (data/history.json)
local_saved.py          per-user saved/bookmarked items (data/saved.json)
fcm_client.py           FCM HTTP v1 sender + device-token store + ad history
                         (data/push_tokens.json, data/ads.json); free/no-Cloud-
                         Functions sender, see "Push notifications" above
admin_auth.py           verifies Firebase ID tokens and the [ads_admin] email
                         allowlist for the staff dashboard
ui_components.py        shared widgets — cards, tiles, youtube embeds,
                         onboarding carousel, KIU Hub banner, notification
                         opt-in card + hidden app-wide notification runtime
local_client.py         drop-in for supabase_client.py — same functions,
                         backed by tree_store.py instead of HTTP
tree_store.py           loads data/tree.json, tree-walk + search + grouping
pages/
  0_Auth.py             sign-up / login — brand-photo carousel at the top
  1_Home.py             search, KIU Hub banner, active-semester tiles,
                         recent history, feed (signed-in only)
  2_My_Courses.py       (signed-in only)
  3_Course_Detail.py    topic-grouped resources, video embeds
  4_Upload.py
  5_Saved.py
  6_Viewer.py           full-resource view, video/doc embeds, history recording
  7_KIU_Hub.py           KIU Resource Hub — hostels / jobs / scholarships,
                         reads data/listings.xlsx directly, no auth needed
  8_Ads_Admin.py          staff-only push-ad composer/dashboard, gated by
                         Firebase email auth + the [ads_admin] email
                         allowlist (not local_auth)
tools/
  import_content.py     xlsx -> data/tree.json converter (Switch content only;
                         the KIU Hub has no importer, see above)
data/
  tree.json             generated — do not hand-edit; delete + reload, or re-run the importer
  listings.xlsx          KIU Resource Hub source data — hand-edited directly,
                         sample rows only, see "The KIU Resource Hub" above
  users.json, sessions.json, history.json, saved.json
                         generated at runtime as people sign up and use the
                         app — not checked in with real data, and wiped by a
                         Community Cloud restart (see "What's intentionally
                         NOT here")
  push_tokens.json, ads.json
                         generated when devices opt in / an ad is sent —
                         same Community Cloud wipe caveat as above
static/
  fcm.html               notification opt-in card + hidden runtime handler
  firebase-messaging-sw.js
                         FCM service worker (shows the rich notification)
  admin_auth.html        staff Firebase email/password sign-in
  icons/                 Switch notification icons (192/512, plus 96 badge)
assets/
  manifest.json
  onboarding/            5 brand photos used by the sign-up carousel, the
                         Home banner, and the KIU Hub header
.streamlit/config.toml
.streamlit/secrets.toml.example
                         template for FCM + admin-password secrets
```
