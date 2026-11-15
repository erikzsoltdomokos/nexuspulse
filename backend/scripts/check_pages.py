"""Verify the live GitHub Pages demo renders data and save docs/img/09_github_pages.png.

Usage (from backend/): .\\.venv\\Scripts\\python.exe scripts\\check_pages.py [--url URL]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[2] / "docs" / "img" / "09_github_pages.png"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://erikzsoltdomokos.github.io/nexuspulse/")
    args = ap.parse_args()
    ok = True
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 800}, device_scale_factor=1.5)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(f"{args.url}?lang=hu", wait_until="networkidle")
        page.wait_for_selector("section[aria-labelledby='timeline-title'] canvas", timeout=60_000)
        page.wait_for_selector("section[aria-labelledby='summary-title']", timeout=30_000)
        page.wait_for_timeout(2500)
        body = page.inner_text("body")
        checks = {
            "default match EUN1_4025052100 selected": page.locator("select").first.input_value() == "EUN1_4025052100",
            "scoreboard shows Viktor": "Viktor" in body,
            "summary panel": "többet kellett volna hoznia" in body.lower(),
            "static note": "Statikus bemutató" in body,
            "match list has 40+ entries": page.locator("select option").count() > 40,
            "no JS errors": not errors,
        }
        for name, passed in checks.items():
            print(f"[{'PASS' if passed else 'FAIL'}] {name}")
            ok &= passed
        if errors:
            print("errors:", errors[:5])
        page.screenshot(path=str(OUT), full_page=True)
        browser.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
