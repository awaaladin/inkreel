"""End-to-end tests in a real Chrome: the studio is served by the real server over a real workspace; nothing is mocked."""
import socket
import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")

from inkreel import render, sample  # noqa: E402
from inkreel.api import create_app  # noqa: E402
from inkreel.session import Session  # noqa: E402
from inkreel.store import Store  # noqa: E402

SID = "ibeno_tides"


def chrome_available():
    try:
        with pw.sync_playwright() as p:
            p.chromium.launch(channel="chrome", headless=True).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not chrome_available(), reason="Chrome not available to Playwright")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    import uvicorn
    store = Store(tmp_path_factory.mktemp("ws"))
    sample.build(store)
    Session(store, SID).run([("create_scene", dict(id="short", episode="ep1", name="Short test", duration=2.5, background="beach", time="day")),
                             ("place", dict(scene="short", char="kabi", x=500)), ("place", dict(scene="short", char="ima", x=800, facing="left")),
                             ("say", dict(scene="short", char="ima", text="Hello Kabi", t=0.3))], src="user")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(create_app(store), host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.1)
    yield store, f"http://127.0.0.1:{port}/?series={SID}"
    srv.should_exit = True


@pytest.fixture()
def page(server):
    store, url = server
    with pw.sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(viewport={"width": 1600, "height": 900}, accept_downloads=True)
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url)
        pg.wait_for_selector(".stage canvas", timeout=30000)
        pg.wait_for_function("() => !!window.Inkreel && !!window.Inkreel.renderOrbit && !document.querySelector('.stage-msg')", timeout=30000)
        pg.get_by_text("Short test").first.click()
        pg.wait_for_function("() => document.querySelector('.clock').textContent.includes('/ 0:02.5')", timeout=10000)
        pg.wait_for_timeout(800)
        pg.errors = errors
        yield pg, store
        b.close()
    assert not errors, errors


def canvas_hash(pg):
    return pg.evaluate("() => { const c = document.querySelector('.stage canvas'); const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data; let h = 0; for (let i = 0; i < d.length; i += 97) h = (h * 31 + d[i]) | 0; return h; }")


def canvas_variance(pg):
    return pg.evaluate("() => { const c = document.querySelector('.stage canvas'); const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data; const seen = new Set(); for (let i = 0; i < d.length; i += 4 * 53) seen.add((d[i] >> 4) * 256 + (d[i+1] >> 4) * 16 + (d[i+2] >> 4)); return seen.size; }")


def test_stage_draws_the_scene(page):
    pg, _ = page
    assert canvas_variance(pg) > 12      # a painted scene, not a blank canvas


SAVE_REF = "() => { const c = document.querySelector('.stage canvas'); window.__ref = new Uint8ClampedArray(c.getContext('2d').getImageData(0,0,c.width,c.height).data); }"
DIFF_REF = """() => { const c = document.querySelector('.stage canvas'); const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data, r = window.__ref;
  let n = 0; for (let i = 0; i < d.length; i += 4) if (Math.abs(d[i]-r[i]) + Math.abs(d[i+1]-r[i+1]) + Math.abs(d[i+2]-r[i+2]) > 40) n++; return n / (d.length / 4); }"""


def test_orbit_by_dragging_changes_the_picture_and_reset_restores_it(page):
    pg, _ = page
    pg.evaluate(SAVE_REF)
    st = pg.locator(".stage").bounding_box()
    cx, cy = st["x"] + st["width"] / 2, st["y"] + st["height"] / 2
    pg.mouse.move(cx, cy)
    pg.mouse.down()
    pg.mouse.move(cx + 140, cy + 30, steps=10)
    pg.mouse.up()
    pg.wait_for_timeout(800)
    assert pg.evaluate(DIFF_REF) > 0.05          # a clearly different view of the scene
    pg.get_by_role("button", name="Reset").click()
    ratio = 1.0
    for _ in range(40):                          # the camera glides home; wait until it has settled
        pg.wait_for_timeout(250)
        ratio = pg.evaluate(DIFF_REF)
        if ratio < 0.002:
            break
    assert ratio < 0.002                         # back to the original view (tiny anti-aliasing differences allowed)


def test_presets_move_the_camera(page):
    pg, store = page
    hashes = set()
    for name in ("Front", "Side", "Top", "3/4"):
        try:
            pg.get_by_role("button", name=name, exact=True).click(timeout=8000)
        except Exception:
            pg.screenshot(path=str(store.root / "preset_fail.png"))
            raise AssertionError(f"button {name} not clickable; page text: {pg.inner_text('body')[:300]!r}; shot {store.root / 'preset_fail.png'}")
        pg.wait_for_timeout(1300)
        hashes.add(canvas_hash(pg))
    assert len(hashes) == 4


def test_pose_slider_writes_a_real_key(page):
    pg, store = page
    s = pg.locator(".slider", has_text="Front arm").locator("input")
    s.focus()
    for _ in range(6):
        pg.keyboard.press("ArrowRight")
    pg.wait_for_timeout(1500)
    sc = store.reader().read(f"series/{SID}/episodes/ep1/scenes/short.json")
    keys = sc["actors"]["kabi"]["keys"]
    assert keys and keys[0]["src"] == "user" and "aF" in keys[0]["pose"]


def test_drawing_on_the_stage_saves_a_cel(page):
    pg, store = page
    pg.get_by_role("tab", name="Draw").click()
    pg.get_by_role("button", name="Start drawing").click()
    pg.wait_for_timeout(1000)
    st = pg.locator(".stage").bounding_box()
    x, y = st["x"] + st["width"] * 0.3, st["y"] + st["height"] * 0.3
    pg.mouse.move(x, y)
    pg.mouse.down()
    pg.mouse.move(x + 120, y + 60, steps=8)
    pg.mouse.move(x + 200, y, steps=8)
    pg.mouse.up()
    pg.wait_for_timeout(1500)
    d = store.reader().read(f"series/{SID}/episodes/ep1/scenes/short.json").get("drawings", [])
    assert len(d) == 1 and d[0]["strokes"][0]["pts"] and d[0]["src"] == "user"
    pg.screenshot(path=str(store.root / "drawn.png"))


def test_dialogue_line_is_listed_and_editable(page):
    pg, store = page
    pg.get_by_role("tab", name="Voice").click()
    ta = pg.get_by_label("Line by ima")
    assert ta.input_value() == "Hello Kabi"
    ta.fill("Hello again, Kabi")
    ta.blur()
    pg.wait_for_timeout(1200)
    sc = store.reader().read(f"series/{SID}/episodes/ep1/scenes/short.json")
    assert sc["actors"]["ima"]["says"][0]["text"] == "Hello again, Kabi"


@pytest.mark.skipif(not render.find_ffmpeg(), reason="ffmpeg not installed")
def test_record_saves_a_real_mp4(page):
    pg, store = page
    pg.get_by_role("button", name="Record").click()
    pg.wait_for_selector(".toast", timeout=90000)      # scene is 2.5s; stop-at-end finishes it, then the browser flushes and ffmpeg converts
    msg = pg.locator(".toast").first.inner_text()
    assert pg.locator(".toast.ok").count() == 1, f"recording did not save: {msg!r}"
    files = list((store.root / "exports").glob("*.mp4"))
    assert files and files[0].stat().st_size > 2000
    import subprocess
    probe = subprocess.run([render.find_ffmpeg(), "-i", str(files[0]), "-f", "null", "-"], capture_output=True, text=True)
    assert probe.returncode == 0 and "h264" in probe.stderr
