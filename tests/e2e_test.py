"""End-to-end checks for the To Do site, run in real Chromium.

Setup:  pip install playwright && playwright install chromium
Run:    python3 tests/e2e_test.py
"""
import json, os, subprocess, sys, time
from playwright.sync_api import sync_playwright

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public")
PORT = 8765
URL = f"http://localhost:{PORT}/index.html"
KEY = "todo-app.tasks.v1"
results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition)))
    print(("PASS  " if condition else "FAIL  ") + name + (f"  [{detail}]" if not condition and detail else ""))


def titles(page):
    return page.locator("#task-list li .task-main label").all_inner_texts()


def stored(page):
    return page.evaluate(f"JSON.parse(localStorage.getItem('{KEY}'))")


def add(page, text):
    page.fill("#new-title", text)
    page.press("#new-title", "Enter")


def row(page, title, nth=0):
    return page.locator("#task-list li", has=page.locator(".task-main label", has_text=title)).nth(nth)


def fresh(browser, init=None, width=1000):
    ctx = browser.new_context(viewport={"width": width, "height": 800})
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.goto(URL)
    return ctx, page


def wait_live(page, text):
    page.wait_for_function("t => document.getElementById('live').textContent.includes(t)", arg=text, timeout=2000)


def run(p):
    browser = p.chromium.launch()

    # ---------- empty state, add, validation ----------
    ctx, page = fresh(browser)
    check("Empty state says 'No tasks yet'", "No tasks yet" in page.inner_text("#empty"))
    check("Input has a visible label", page.get_by_label("New task").count() == 1)
    check("Storage limitation is explained", "not backed up or synced" in page.inner_text("main"))

    add(page, "  Buy milk  ")
    check("Add trims and creates task", titles(page) == ["Buy milk"])
    check("Input cleared after add", page.input_value("#new-title") == "")
    t = stored(page)[0]
    check("Task has id/title/completed/createdAt", set(t) == {"id", "title", "completed", "createdAt"} and t["completed"] is False and t["createdAt"].endswith("Z"))

    for label, value in [("empty", ""), ("spaces", "     "), ("tabs/newlines", " \t \n "), ("zero-width", "\u200b\u200b")]:
        add(page, value)
        check(f"Rejects {label} title", len(titles(page)) == 1 and page.inner_text("#add-error") != "")
    check("Error is announced (role=alert) and input flagged", page.get_attribute("#add-error", "role") == "alert" and page.get_attribute("#new-title", "aria-invalid") == "true")
    add(page, "x" * 201)
    check("Rejects 201-character title", len(titles(page)) == 1 and "200" in page.inner_text("#add-error"))
    add(page, "y" * 200)
    check("Accepts exactly 200 characters", len(titles(page)) == 2 and page.inner_text("#add-error") == "")

    payload = "<img src=x onerror=\"window.__xss=1\"><b>bold</b> & <script>window.__xss=2</script>"
    add(page, payload)
    check("HTML-like text shown literally", payload in titles(page))
    check("HTML-like text not executed or parsed", page.evaluate("window.__xss") is None and page.locator("#task-list img, #task-list b, #task-list script").count() == 0)
    page.reload()
    check("HTML-like text still literal after reload", payload in titles(page))
    check("No JS errors so far", not page.errors, page.errors)
    ctx.close()

    # ---------- actions under every filter (duplicate titles to prove correct-task targeting) ----------
    ctx, page = fresh(browser)
    for name in ["Same", "Same", "Other"]:
        add(page, name)
    ids = [t["id"] for t in stored(page)]
    check("IDs are unique", len(set(ids)) == 3)

    row(page, "Same", 1).get_by_role("checkbox").check()
    s = stored(page)
    check("Completing second duplicate affects only that task", [x["completed"] for x in s] == [False, True, False])
    check("Completed state has non-colour cue (badge + checkbox)", row(page, "Same", 1).locator(".badge").count() == 1)

    page.click("[data-filter=active]")
    check("Active filter shows only unfinished", titles(page) == ["Same", "Other"])
    row(page, "Other").get_by_role("checkbox").click()   # row leaves the view, so check() cannot re-read it
    check("Completing in Active view removes it from view", titles(page) == ["Same"])
    check("...and the correct task changed", [x["completed"] for x in stored(page)] == [False, True, True])

    page.click("[data-filter=completed]")
    check("Completed filter shows only finished", titles(page) == ["Same", "Other"])
    row(page, "Other").get_by_role("checkbox").click()
    check("Reactivating in Completed view works", titles(page) == ["Same"] and [x["completed"] for x in stored(page)] == [False, True, False])

    # edit while filtered
    row(page, "Same").get_by_role("button", name="Edit task: Same").click()
    page.fill("#task-list input[type=text]", "Same (edited)")
    page.click("#task-list button:text('Save')")
    check("Edit under Completed filter changes the right task", [x["title"] for x in stored(page)] == ["Same", "Same (edited)", "Other"])
    check("Edit preserves id, completed and createdAt", stored(page)[1]["id"] == ids[1] and stored(page)[1]["completed"] is True)

    # delete while filtered, cancel first
    row(page, "Same (edited)").get_by_role("button", name="Delete task").click()
    page.click("#task-list button:text('Cancel')")
    check("Cancel delete preserves task", len(stored(page)) == 3 and titles(page) == ["Same (edited)"])
    row(page, "Same (edited)").get_by_role("button", name="Delete task").click()
    check("Delete asks for confirmation", "Delete this task" in page.inner_text("#task-list"))
    page.click("#task-list button:text('Yes, delete')")
    check("Confirmed delete removes only that task", [x["id"] for x in stored(page)] == [ids[0], ids[2]])
    check("Filtered empty state shown", "No completed tasks yet" in page.inner_text("#empty"))
    page.click("[data-filter=active]")
    row(page, "Same").get_by_role("button", name="Delete task").click()
    page.keyboard.press("Escape")
    check("Escape cancels delete", len(stored(page)) == 2)
    page.click("[data-filter=all]")
    check("All filter shows everything", titles(page) == ["Same", "Other"])

    # edit cancel + validation
    row(page, "Other").get_by_role("button", name="Edit task").click()
    page.fill("#task-list input[type=text]", "changed")
    page.click("#task-list button:text('Cancel')")
    check("Cancel edit keeps original title", "Other" in titles(page) and stored(page)[1]["title"] == "Other")
    row(page, "Other").get_by_role("button", name="Edit task").click()
    page.fill("#task-list input[type=text]", "   ")
    page.keyboard.press("Enter")
    check("Edit rejects blank title and stays editing", page.locator("#task-list .error").inner_text() != "" and stored(page)[1]["title"] == "Other")
    page.fill("#task-list input[type=text]", "z" * 201)
    page.keyboard.press("Enter")
    check("Edit rejects oversized title", "200" in page.locator("#task-list .error").inner_text() and stored(page)[1]["title"] == "Other")
    page.keyboard.press("Escape")
    check("Escape cancels edit", page.locator("#task-list input[type=text]").count() == 0)

    # persistence
    row(page, "Other").get_by_role("checkbox").check()
    page.reload()
    check("Titles and completion persist after reload", titles(page) == ["Same", "Other"] and row(page, "Other").locator(".badge").count() == 1)
    check("Save status reports success", "saved" in page.inner_text("#save-status").lower() and "Not saved" not in page.inner_text("#save-status"))
    p2 = ctx.new_page(); p2.goto(URL)
    check("Persist when reopened in a new tab", titles(p2) == ["Same", "Other"])
    p2.close(); ctx.close()

    # ---------- keyboard + focus ----------
    ctx, page = fresh(browser)
    page.focus("#new-title"); page.keyboard.type("Keyboard task"); page.keyboard.press("Enter")
    page.keyboard.press("Tab"); page.keyboard.press("Tab")  # to filters? verify by walking below
    page.focus("#task-list input[type=checkbox]"); page.keyboard.press("Space")
    check("Space toggles checkbox", stored(page)[0]["completed"] is True)
    page.focus("[data-action=edit]"); page.keyboard.press("Enter")
    check("Edit reachable by keyboard; input focused", page.evaluate("document.activeElement.type") == "text")
    page.keyboard.press("Escape")
    check("Focus returns to Edit button after cancel", page.evaluate("document.activeElement.dataset.action") == "edit")
    outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle + '|' + getComputedStyle(document.activeElement).outlineWidth")
    check("Focused control has a visible outline", outline.startswith("solid") and not outline.endswith("|0px"), outline)
    unnamed = page.evaluate("""[...document.querySelectorAll('button,input')].filter(e =>
        !(e.getAttribute('aria-label') || e.textContent.trim() || (e.labels && e.labels.length))).length""")
    check("All buttons/inputs have accessible names", unnamed == 0)
    ctx.close()

    # ---------- malformed / invalid saved data ----------
    bad_values = {
        "invalid JSON": "{not json",
        "not an array": '{"a":1}',
        "item missing field": json.dumps([{"id": "1", "title": "x", "completed": False}]),
        "title too long": json.dumps([{"id": "1", "title": "q" * 201, "completed": False, "createdAt": "2026-01-01T00:00:00Z"}]),
        "duplicate ids": json.dumps([{"id": "1", "title": "a", "completed": False, "createdAt": "z"}] * 2),
    }
    for label, raw in bad_values.items():
        ctx, page = fresh(browser)
        page.evaluate(f"localStorage.setItem('{KEY}', {json.dumps(raw)})")
        page.reload()
        ok = not page.errors and not page.locator("#storage-banner").is_hidden() and page.locator("#storage-actions").is_visible()
        add(page, "temp")
        check(f"Malformed data ({label}): warns, no crash, still usable", ok and titles(page) == ["temp"], page.errors)
        check(f"Malformed data ({label}): original NOT overwritten", page.evaluate(f"localStorage.getItem('{KEY}')") == raw)
        ctx.close()

    ctx, page = fresh(browser)
    page.evaluate(f"localStorage.setItem('{KEY}', '{{broken')")
    page.reload(); add(page, "keep me")
    with page.expect_download() as dl:
        page.click("#download-raw")
    check("Unreadable data can be downloaded", open(dl.value.path()).read() == "{broken")
    page.once("dialog", lambda d: d.accept())
    page.click("#start-fresh")
    page.wait_for_timeout(200)
    check("Start fresh: backup kept, list saved, banner gone", page.evaluate(f"localStorage.getItem('{KEY}.unreadable-backup')") == "{broken" and stored(page)[0]["title"] == "keep me" and page.locator("#storage-banner").is_hidden())
    ctx.close()

    ctx, page = fresh(browser)
    page.evaluate(f"localStorage.setItem('{KEY}', '{{broken')")
    page.reload()
    page.once("dialog", lambda d: d.dismiss())
    page.click("#start-fresh")
    check("Declining discard leaves data untouched", page.evaluate(f"localStorage.getItem('{KEY}')") == "{broken")
    ctx.close()

    # ---------- storage unavailable ----------
    ctx, page = fresh(browser, "Object.defineProperty(window,'localStorage',{get(){throw new DOMException('blocked','SecurityError')}})")
    check("Storage blocked: page still loads, warning shown", not page.errors and "blocking storage" in page.inner_text("#storage-banner"), page.errors)
    add(page, "temporary")
    check("Storage blocked: temporary use works", titles(page) == ["temporary"])
    check("Storage blocked: never claims saved", "Not saved" in page.inner_text("#save-status") and "All changes are saved" not in page.inner_text("main"))
    wait_live(page, "not saved")
    check("Storage blocked: announcement says not saved", True)
    ctx.close()

    # ---------- write failure (quota) then recovery ----------
    ctx, page = fresh(browser, "window.__fail=false; const s=Storage.prototype.setItem; Storage.prototype.setItem=function(k,v){ if(window.__fail) throw new DOMException('full','QuotaExceededError'); return s.call(this,k,v); }")
    add(page, "saved one")
    page.evaluate("window.__fail=true")
    add(page, "unsaved two")
    check("Write failure: alert banner, task kept in page", "could not be saved" in page.inner_text("#storage-banner") and titles(page) == ["saved one", "unsaved two"])
    check("Write failure: status says Not saved", "Not saved" in page.inner_text("#save-status"))
    check("Write failure: storage holds only the saved one", [x["title"] for x in stored(page)] == ["saved one"])
    page.evaluate("window.__fail=false")
    add(page, "three")
    check("Recovery: next successful write saves everything and clears warning", [x["title"] for x in stored(page)] == ["saved one", "unsaved two", "three"] and page.locator("#storage-banner").is_hidden())
    ctx.close()

    # ---------- other tabs ----------
    ctx = browser.new_context()
    a = ctx.new_page(); b = ctx.new_page(); a.goto(URL); b.goto(URL)
    add(a, "from A")
    b.wait_for_function("document.querySelectorAll('#task-list li').length === 1", timeout=3000)
    check("Tab B updates when tab A adds a task", titles(b) == ["from A"])
    row(b, "from A").get_by_role("button", name="Edit task").click()
    b.fill("#task-list input[type=text]", "B draft")
    row(a, "from A").get_by_role("checkbox").check()
    b.wait_for_function("document.querySelector('#task-list input[type=text]') !== null", timeout=3000)
    check("Tab B keeps in-progress edit draft when A changes data", b.input_value("#task-list input[type=text]") == "B draft")
    b.press("#task-list input[type=text]", "Enter")
    s = stored(b)
    check("Edit in B merges with A's completion (no lost update)", s[0]["title"] == "B draft" and s[0]["completed"] is True)
    a.wait_for_function("(document.querySelector('#task-list label') || {}).textContent === 'B draft'", timeout=3000)
    # delete in A, then act on stale row in B
    row(a, "B draft").get_by_role("button", name="Delete task").click(); a.click("#task-list button:text('Yes, delete')")
    b.wait_for_function("document.querySelectorAll('#task-list li').length === 0", timeout=3000)
    check("Tab B reflects deletion made in tab A", titles(b) == [] and "No tasks yet" in b.inner_text("#empty"))
    ctx.close()

    # ---------- layout: 320px, long unbroken text, all row modes ----------
    ctx, page = fresh(browser, width=320)
    add(page, "W" * 200); add(page, "short")
    page.click("[data-filter=all]")
    def no_hscroll():
        return page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    check("320px: no horizontal scroll (list)", no_hscroll())
    row(page, "WWWW").get_by_role("button", name="Edit task").click()
    check("320px: no horizontal scroll (editing)", no_hscroll())
    page.keyboard.press("Escape")
    row(page, "WWWW").get_by_role("button", name="Delete task").click()
    check("320px: no horizontal scroll (confirm)", no_hscroll())
    page.keyboard.press("Escape")
    small = page.evaluate("[...document.querySelectorAll('button')].filter(b => b.offsetParent !== null && b.offsetHeight < 40).length")
    check("320px: touch targets >= 40px tall", small == 0)
    page.screenshot(path=os.path.join(os.path.dirname(__file__), "screenshot-320.png"), full_page=True)
    ctx.close()
    ctx, page = fresh(browser, width=1280)
    page.evaluate("document.documentElement.style.zoom='2'")   # rough 200% zoom emulation
    add(page, "zoom check")
    check("200% zoom emulation: no horizontal scroll, controls present", page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth * 1.01") and titles(page) == ["zoom check"])
    ctx.close()

    browser.close()


def contrast_checks():
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    def ratio(a, b):
        la, lb = sorted([lum(a), lum(b)], reverse=True)
        return (la + 0.05) / (lb + 0.05)
    pairs = {"text/card": ("#1f2937", "#ffffff"), "muted/card": ("#4b5563", "#ffffff"), "muted/bg": ("#4b5563", "#f3f4f6"),
             "white/accent": ("#ffffff", "#1d4ed8"), "accent/card": ("#1d4ed8", "#ffffff"), "danger/card": ("#b91c1c", "#ffffff"),
             "white/danger": ("#ffffff", "#b91c1c"), "warn text/bg": ("#78350f", "#fef3c7")}
    for name, (fg, bg) in pairs.items():
        r = ratio(fg, bg)
        check(f"Contrast {name} >= 4.5:1 ({r:.1f})", r >= 4.5)
    check(f"Input border vs card >= 3:1 ({ratio('#6b7280', '#ffffff'):.1f})", ratio("#6b7280", "#ffffff") >= 3)


if __name__ == "__main__":
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "-d", ROOT], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        with sync_playwright() as p:
            run(p)
        contrast_checks()
    finally:
        server.terminate()
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)
