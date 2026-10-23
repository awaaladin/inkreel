"""Open the studio in the installed Chrome, optionally orbit/click, and save screenshots. Used to verify the UI for real.

    python tools/shot.py http://127.0.0.1:8790/?series=ibeno_tides out_dir [--scene SCENE_NAME] [--yaw 40 --pitch 15] [--t 5] [--tab draw]
"""
import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--scene", help="scene name to click in the left rail")
    ap.add_argument("--yaw", type=float, default=0)
    ap.add_argument("--pitch", type=float, default=0)
    ap.add_argument("--t", type=float, help="seek to seconds (scrub position) in the scope")
    ap.add_argument("--tab", help="inspector tab label")
    ap.add_argument("--w", type=int, default=1700)
    ap.add_argument("--h", type=int, default=950)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    logs = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        pg = b.new_page(viewport={"width": a.w, "height": a.h})
        pg.on("console", lambda m: logs.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        pg.goto(a.url)
        pg.wait_for_selector(".stage canvas", timeout=30000)
        pg.wait_for_timeout(2500)
        if a.scene:
            pg.get_by_text(a.scene, exact=False).first.click()
            pg.wait_for_timeout(1200)
        if a.t is not None:
            box = pg.locator(".scrub").bounding_box()
            total = pg.locator(".clock").inner_text().split("/")[1].strip()
            m, s = total.split(":")
            tot = int(m) * 60 + float(s)
            pg.mouse.click(box["x"] + box["width"] * min(0.999, a.t / max(tot, 0.1)), box["y"] + box["height"] / 2)
            pg.wait_for_timeout(600)
        if a.tab:
            pg.get_by_role("tab", name=a.tab).click()
            pg.wait_for_timeout(400)
        pg.screenshot(path=str(out / "1_flat.png"))
        if a.yaw or a.pitch:
            st = pg.locator(".stage").bounding_box()
            cx, cy = st["x"] + st["width"] / 2, st["y"] + st["height"] / 2
            pg.mouse.move(cx, cy)
            pg.mouse.down()
            pg.mouse.move(cx + a.yaw / 0.4, cy + a.pitch / 0.3, steps=12)
            pg.mouse.up()
            pg.wait_for_timeout(700)
            pg.screenshot(path=str(out / "2_orbit.png"))
        b.close()
    print("\n".join(logs[:15]) or "no console errors")


if __name__ == "__main__":
    sys.exit(main())
