# To Do website

A small task list built with plain HTML, CSS and JavaScript (no framework, no backend, no build step). Requirements come from `To_Do_Website_PRD.docx` (v1.0).

## Project structure

```
public/           <- the website; this is the folder Vercel serves
  index.html      structure: heading, form, filters, list, warning areas
  style.css       presentation: responsive layout, focus styles, colours
  script.js       behaviour: state, validation, storage, rendering, events
tests/
  e2e_test.py     browser tests (Playwright + Chromium)
README.md
```

## Run locally

Any static server works (opening `index.html` by double-click also works, but a server matches the deployed behaviour):

```
python3 -m http.server 8000 -d public
```

Then open http://localhost:8000. (Or: `npx serve public`.)

## Run the tests (optional)

```
pip install playwright
playwright install chromium
python3 tests/e2e_test.py
```

## How it works

- `script.js` keeps the tasks in one array, `[{ id, title, completed, createdAt }]`, and re-draws the list from it after every change.
- Every task has a unique ID (`crypto.randomUUID`, with a fallback). Buttons and checkboxes act on that ID, never on a list position, so actions hit the right task under any filter (even with duplicate titles).
- Titles are trimmed and must be 1–200 characters (counted as Unicode characters). They are put on the page with `textContent`, so text like `<b>hi</b>` shows literally.
- Tasks are saved as JSON in `localStorage` under the key `todo-app.tasks.v1` after each successful change.

### Decisions where the PRD was silent

| Question | Decision |
| --- | --- |
| Task no longer matches the filter after completing/reactivating | It leaves the view; this is announced and focus moves to a neighbouring task. |
| What counts as malformed saved data | Invalid JSON, a non-array, or any item that is not a valid task (missing field, wrong type, bad title, duplicate ID). |
| Duplicate titles | Allowed. |
| Invisible-only titles (e.g. zero-width spaces) | Treated as blank. |
| Delete confirmation | Inline in the task row (Cancel is focused first; Escape cancels). |

## Storage failures

| Situation | Behaviour |
| --- | --- |
| Storage blocked (e.g. some private modes) | Warning banner; list works temporarily; status says "Not saved". |
| A save fails (e.g. quota full) | Warning banner; the change stays on the page but is **not** reported as saved; the next successful save clears the warning. |
| Saved data is unreadable | Nothing is loaded, **saving is switched off** so the original is never overwritten. You can download the raw text, or discard it (a backup copy is kept under `todo-app.tasks.v1.unreadable-backup` first). |
| Leaving with unsaved changes | The browser shows its "leave page?" prompt. |

Tasks live only in this browser on this device: no backup, no syncing.

## Multiple tabs

Other tabs' changes arrive through the `storage` event, and the list updates. Before each change the page re-reads storage, so an edit made in one tab is applied to the latest data rather than a stale copy. An in-progress edit draft is kept, and acting on a task deleted elsewhere shows a message.

**Remaining limitations:** the read-then-write is not atomic, so two tabs saving within the same instant can still lose one update (last write wins). A tab holding unsaved changes (after a failed save) does not merge in other tabs' changes. Storage events are not delivered in the same tab, and an edit box in another tab is not locked.

## Deploy to Vercel (static site)

Checked against Vercel's docs (Configuring a Build / Builds pages): for a static site set **Framework Preset = Other**, leave **Build Command** empty, and Vercel serves the `public` folder if it exists (otherwise the project root). No `vercel.json` is needed.

1. Put this project in a Git repository and push it to GitHub/GitLab/Bitbucket.
2. In Vercel: **Add New → Project**, import the repository.
3. Framework Preset: **Other**. Build Command: leave blank. Install Command: leave default/blank. Output Directory: leave blank (auto-uses `public`) or set it to `public`.
4. Click **Deploy**.

Or with the CLI, from the project folder: `npm i -g vercel`, then `vercel` (preview) and `vercel --prod` (production). Vercel settings can change; if the dashboard differs, check https://vercel.com/docs/builds/configure-a-build.
