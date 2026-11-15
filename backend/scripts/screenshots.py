"""Take documentation screenshots of the NexusPulse dashboard with Playwright.

Usage (from backend/):
    .\\.venv\\Scripts\\python.exe scripts\\screenshots.py --start-server
    .\\.venv\\Scripts\\python.exe scripts\\screenshots.py --base http://127.0.0.1:8020

Needs: pip install playwright && python -m playwright install chromium.
With --start-server the script launches `python -m nexuspulse serve --port <port>`,
waits for /api/health, takes all shots and stops that server again.
Besides saving PNGs it checks the interactive features (hover tooltip, inflection
card zoom + SHAP panel, player selection) and prints PASS/FAIL per check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "img"
MAIN_MATCH = "EUN1_4025052100"
MAIN_CHAMPION = "Viktor"
COMEBACK_MATCH = "EUW1_8040176757"
WIDTH, HEIGHT, SCALE = 1600, 1800, 1.5  # tall viewport: no scrolling, so clips use page coords

# Grid geometry of the timeline chart (must match TimelineChart.tsx).
GRID_LEFT, GRID_RIGHT, G0_TOP, G0_H = 128, 40, 40, 250

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}".rstrip(), flush=True)


def wait_health(base: str, timeout: float = 90) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"backend at {base} did not answer /api/health within {timeout}s")


def get_json(base: str, path: str):
    with urllib.request.urlopen(f"{base}{path}", timeout=60) as r:
        return json.load(r)


def open_match(page: Page, base: str, match: str, lang: str) -> None:
    page.goto(f"{base}/?match={match}&lang={lang}", wait_until="networkidle")
    page.wait_for_selector("#timeline-title", timeout=60_000)
    page.wait_for_selector("section[aria-labelledby='timeline-title'] canvas", timeout=30_000)
    page.wait_for_timeout(2000)  # ECharts animation


def full_shot(page: Page, name: str) -> None:
    # Shrink the viewport so the full-page capture ends where the content ends.
    page.set_viewport_size({"width": WIDTH, "height": 800})
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / name), full_page=True)
    page.set_viewport_size({"width": WIDTH, "height": HEIGHT})


def chart_box(page: Page):
    box = page.locator("section[aria-labelledby='timeline-title'] div[role='img']").bounding_box()
    assert box, "timeline chart not found"
    return box


def chart_hash(page: Page) -> str:
    png = page.locator("section[aria-labelledby='timeline-title'] div[role='img']").screenshot()
    return hashlib.md5(png).hexdigest()


def minute_x(page: Page, minutes: list[float], minute: float) -> tuple[float, float]:
    box = chart_box(page)
    idx = min(range(len(minutes)), key=lambda i: abs(minutes[i] - minute))
    w = box["width"] - GRID_LEFT - GRID_RIGHT
    x = box["x"] + GRID_LEFT + (idx + 0.5) * w / len(minutes)
    y = box["y"] + G0_TOP + G0_H * 0.5
    return x, y


def tooltip_text(page: Page) -> str:
    # ECharts renders the tooltip as an absolutely positioned div inside the chart container.
    return page.evaluate(
        """() => {
          const root = document.querySelector("section[aria-labelledby='timeline-title'] div[role='img']");
          const tips = [...root.querySelectorAll('div')].filter(d => d.style.position === 'absolute'
              && getComputedStyle(d).display !== 'none' && getComputedStyle(d).opacity !== '0' && d.innerText.trim());
          return tips.map(t => t.innerText).join('\\n');
        }"""
    )


def run(base: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dyn = get_json(base, f"/api/analysis/{MAIN_MATCH}/timeline-dynamics")
    ov = get_json(base, f"/api/analysis/{MAIN_MATCH}/overview")
    minutes = [p["minute"] for p in dyn["timeline"]]
    infl = dyn["inflection_points"]
    target = next((i for i in infl if i["minute"] == 26), None) or max(infl, key=lambda i: abs(i["delta"]))
    viktor = next((p for p in ov["participants"] if p["champion"] == MAIN_CHAMPION), None)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=SCALE)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        # 1 + 2: full dashboards
        open_match(page, base, MAIN_MATCH, "hu")
        full_shot(page, "01_dashboard_hu.png")
        open_match(page, base, MAIN_MATCH, "en")
        full_shot(page, "02_dashboard_en.png")
        check("english UI", "Win probability" in page.inner_text("body") or "win probability" in page.inner_text("body").lower())

        # 8: match summary panel (HU)
        open_match(page, base, MAIN_MATCH, "hu")
        summary = page.locator("section[aria-labelledby='summary-title']")
        summary.wait_for(timeout=30_000)
        text = summary.inner_text().lower()
        check("summary panel rendered", "meccs-összefoglaló" in text and "mvp" in text, repr(text[:120]))
        check("summary has should-have-performed-better callout", "többet kellett volna hoznia" in text)
        summary.screenshot(path=str(OUT / "08_summary_hu.png"))
        page.mouse.move(5, 5)
        before = chart_hash(page)
        summary.locator("button[aria-label]").first.click()
        page.wait_for_timeout(1200)
        page.mouse.move(5, 5)
        page.wait_for_timeout(300)
        check("summary minute click zooms chart", chart_hash(page) != before)

        # 3: hover tooltip around minute 26
        open_match(page, base, MAIN_MATCH, "hu")
        section = page.locator("section[aria-labelledby='timeline-title']")
        section.scroll_into_view_if_needed()
        x, y = minute_x(page, minutes, 26)
        page.mouse.move(x - 40, y)
        page.mouse.move(x, y, steps=8)
        page.wait_for_timeout(700)
        tip = tooltip_text(page)
        check("hover tooltip visible", bool(tip), repr(tip[:120]))
        check("tooltip has SHAP breakdown", "%" in tip and len(tip.splitlines()) > 6)
        sb = section.bounding_box()
        page.screenshot(path=str(OUT / "03_tooltip_hover.png"),
                        clip={"x": 0, "y": sb["y"] - 8, "width": WIDTH, "height": sb["height"] + 16})

        # 4: inflection card click -> zoom + SHAP panel
        open_match(page, base, MAIN_MATCH, "hu")
        page.mouse.move(5, 5)
        before = chart_hash(page)
        card = page.locator("ul[aria-label] button", has_text=f"{target['minute']}:00").first
        card.click()
        page.wait_for_timeout(1500)
        check("inflection card pressed", card.get_attribute("aria-pressed") == "true")
        shap_title = page.inner_text("#shap-title")
        check("SHAP panel opened", str(target["minute"]) in shap_title, repr(shap_title))
        check("SHAP bars rendered", page.locator("[aria-labelledby='shap-title'] p").count() >= 1)
        page.mouse.move(5, 5)
        page.wait_for_timeout(300)
        after = chart_hash(page)
        check("chart zoomed after card click", before != after)
        grid = page.locator("main > div.grid").first  # chart + inflection panel row
        gb = grid.bounding_box()
        page.screenshot(path=str(OUT / "04_inflection_click.png"),
                        clip={"x": 0, "y": gb["y"] - 8, "width": WIDTH, "height": gb["height"] + 16})

        # 5: select Viktor via scoreboard row
        open_match(page, base, MAIN_MATCH, "hu")
        if viktor:
            row = page.locator("tbody tr", has_text=MAIN_CHAMPION).first
            row.click()
            page.wait_for_timeout(1200)
            check("player row selected", row.get_attribute("aria-selected") == "true")
            title = page.inner_text("#player-title")
            check("player panel shows Viktor", MAIN_CHAMPION in title, repr(title))
            # Also try selecting a player by clicking its stability ribbon (heatmap lane).
            box = chart_box(page)
            lanes = sorted(dyn["player_stability"], key=lambda p: (p["team"] != "blue",
                           ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"].index(p["role"]) if p["role"] in
                           ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"] else 9))
            other = next((i, l) for i, l in enumerate(lanes) if l["champion"] != MAIN_CHAMPION)
            g1_top = G0_TOP + G0_H + 44
            lx = box["x"] + GRID_LEFT + (box["width"] - GRID_LEFT - GRID_RIGHT) * 0.5
            ly = box["y"] + g1_top + 24 * other[0] + 12
            page.mouse.click(lx, ly)
            page.wait_for_timeout(800)
            title2 = page.inner_text("#player-title")
            check("ribbon click selects player", other[1]["champion"] in title2, repr(title2))
            page.locator("tbody tr", has_text=MAIN_CHAMPION).first.click()
            page.mouse.move(5, 5)
            page.wait_for_timeout(1200)
        else:
            check("player row selected", False, "Viktor not in match")
        pp = page.locator("section[aria-labelledby='player-title']").bounding_box()
        top = chart_box(page)["y"] + G0_TOP + G0_H + 20
        page.screenshot(path=str(OUT / "05_player_tilt.png"),
                        clip={"x": 0, "y": top, "width": WIDTH, "height": pp["y"] + pp["height"] - top + 8})

        # 6: comeback match
        open_match(page, base, COMEBACK_MATCH, "hu")
        full_shot(page, "06_comeback_euw.png")

        # 7: Swagger UI
        page.goto(f"{base}/docs", wait_until="networkidle")
        page.wait_for_timeout(1500)
        ok = page.locator(".swagger-ui").count() > 0
        check("swagger /docs available", ok)
        if ok:
            full_shot(page, "07_api_swagger.png")

        check("no JS errors", not errors, "; ".join(errors[:5]))
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8020")
    ap.add_argument("--start-server", action="store_true")
    args = ap.parse_args()
    proc = None
    if args.start_server:
        port = args.base.rsplit(":", 1)[-1]
        backend = Path(__file__).resolve().parents[1]
        proc = subprocess.Popen([sys.executable, "-m", "nexuspulse", "serve", "--port", port], cwd=backend,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_health(args.base)
        run(args.base)
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=20)
    failed = [r for r in results if not r[1]]
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
