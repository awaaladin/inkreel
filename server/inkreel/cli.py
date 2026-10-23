"""inkreel CLI. Claude Code is the director: it runs these commands (or imports inkreel.ops) to build and edit the animation;
the studio shows the result live. Everything here is real; nothing calls an AI API."""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import check, sample, timing
from .session import Session
from .store import Store, StoreError

REPO = Path(__file__).resolve().parents[2]
console = Console(highlight=False)


def default_workspace() -> Path:
    return Path(os.environ.get("INKREEL_WORKSPACE") or (REPO / "workspaces" / "default"))


def open_store(a) -> Store:
    return Store(Path(a.workspace) if a.workspace else default_workspace())


def cmd_new(a):
    s = open_store(a)
    sid = s.create_series(a.series, a.title)
    console.print(f"[green]created series[/] {sid} in {s.root}")


def cmd_build_sample(a):
    s = open_store(a)
    sample.build(s)
    console.print(f"[green]sample series built[/] ibeno_tides in {s.root}")


def cmd_op(a):
    """inkreel op <series> <name> '<json args>'  - run one op as the user would."""
    s = open_store(a)
    sess = Session(s, a.series, a.episode)
    args = json.loads(a.args or "{}")
    for n, ok, m in sess.run([(a.name, args)], src=a.src, label=f"op {a.name}"):
        console.print(f"[{'green' if ok else 'red'}]{'+' if ok else 'x'}[/] {escape(n)} {escape(m)}")
        return 0 if ok else 1


def cmd_run(a):
    """Batch: a JSON file {"ops": [{"name":..., "args":{...}}, ...]} applied as one undoable turn."""
    s = open_store(a)
    spec = json.loads(Path(a.script).read_text(encoding="utf-8"))
    sess = Session(s, a.series, spec.get("episode"))
    res = sess.run([(o["name"], o.get("args", {})) for o in spec["ops"]], src=a.src, label=spec.get("label", f"run {Path(a.script).name}"))
    bad = 0
    for n, ok, m in res:
        bad += 0 if ok else 1
        console.print(f"[{'green' if ok else 'red'}]{'+' if ok else 'x'}[/] {escape(n)} {escape(m)}")
    return 1 if bad else 0


def cmd_status(a):
    s = open_store(a)
    tx = s.reader()
    sr = tx.read(f"series/{a.series}/series.json")
    t = Table(show_header=True, header_style="bold")
    for h in ("episode", "scene", "look", "cast", "length"):
        t.add_column(h)
    for e in sr["episodes"]:
        for x in tx.read(f"series/{a.series}/episodes/{e}/episode.json")["scenes"]:
            sc = tx.read(f"series/{a.series}/episodes/{e}/scenes/{x}.json")
            t.add_row(e, x, f"{sc['background']['preset']}/{sc['background'].get('time', 'day')}", ",".join(sc["actors"]), f"{timing.scene_duration(sc):.1f}s")
    console.print(t)


def cmd_lint(a):
    s = open_store(a)
    tx = s.reader()
    scenes = [a.scene] if a.scene else [x for e in tx.read(f"series/{a.series}/series.json")["episodes"] for x in tx.read(f"series/{a.series}/episodes/{e}/episode.json")["scenes"]]
    errs = 0
    for scn in scenes:
        for f in check.check_scene(s, a.series, scn):
            errs += f["severity"] == "error"
            console.print(f"{f['severity']:<7} {scn} t={f.get('t', '-')}: {escape(f['message'])} {escape(f.get('hint', ''))}")
    return 1 if errs else 0


def cmd_undo(a):
    s = open_store(a)
    r = s.undo(a.series)
    console.print(f"undone: {escape(r['label'])}" if r else "nothing to undo")


def cmd_snapshot(a):
    s = open_store(a)
    console.print(f"snapshot {s.snapshot(a.series, a.name)} saved")


def _traced_layout(a):
    return json.loads(Path(a.layout).read_text(encoding="utf-8"))


def cmd_trace_grid(a):
    from . import trace
    out = Path(a.out) if a.out else Path(a.image).with_name(Path(a.image).stem + "_grid.png")
    console.print(f"[green]wrote[/] {trace.grid(a.image, out, a.step)}")


def cmd_trace_preview(a):
    from . import trace
    out = Path(a.out) if a.out else Path(a.image).with_name(Path(a.image).stem + "_preview.png")
    console.print(f"[green]wrote[/] {trace.preview(a.image, _traced_layout(a), out)}")


def cmd_trace(a):
    """Trace a picture into a rigged vector character and save it in the series library."""
    from . import trace
    s = open_store(a)
    layout = _traced_layout(a)
    try:
        rec = trace.build(a.image, layout, colors=a.colors, detail=a.detail)
    except trace.TraceError as e:
        console.print(f"[red]{escape(str(e))}[/]")
        return 1
    cid = a.character
    rec = {"id": cid, "name": layout.get("name", cid.title()), "notes": layout.get("notes", ""), **rec}
    if a.skin or layout.get("skin"):
        rec["skin"] = a.skin or layout["skin"]
    with s.turn(a.series, f"trace character {cid}", "user") as tx:
        tx.write(f"series/{a.series}/libraries/characters/{cid}.json", rec)
    n = sum(len(sh["rings"]) for p in rec["parts"] for sh in p["shapes"])
    console.print(f"[green]traced[/] {cid}: {len(rec['parts'])} parts, {n} shapes, height {rec['height']}px")


def cmd_schema(a):
    from . import model as M
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, m in M.MODELS.items():
        (out / f"{name}.schema.json").write_text(json.dumps(m.model_json_schema(by_alias=True), indent=1), encoding="utf-8")
    console.print(f"wrote {len(M.MODELS)} schemas to {out}")


def cmd_serve(a):
    import uvicorn

    from .api import create_app
    s = open_store(a)
    url = f"http://127.0.0.1:{a.port}/" + (f"?series={a.series}" if a.series else "")
    console.print(f"[bold]Inkreel studio[/] {url}  (workspace {s.root})")
    if a.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(s), host=a.host, port=a.port, log_level="warning")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="inkreel", description="2D animation studio with a 3D-style orbit view")
    ap.add_argument("--workspace", "-w", default=None, help="workspace folder (default: $INKREEL_WORKSPACE or ./workspaces/default)")
    sp = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        p = sp.add_parser(name, help=help_)
        p.set_defaults(fn=fn)
        return p
    p = add("new", cmd_new, "create a series"); p.add_argument("series"); p.add_argument("--title")
    add("build-sample", cmd_build_sample, "build the Ibeno Tides sample series")
    p = add("serve", cmd_serve, "start the studio"); p.add_argument("series", nargs="?"); p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8790); p.add_argument("--open", action="store_true")
    p = add("op", cmd_op, "run one op"); p.add_argument("series"); p.add_argument("name"); p.add_argument("args", nargs="?")
    p.add_argument("--episode"); p.add_argument("--src", default="user")
    p = add("run", cmd_run, "run a JSON file of ops as one undoable turn"); p.add_argument("series"); p.add_argument("script"); p.add_argument("--src", default="user")
    p = add("status", cmd_status, "list scenes"); p.add_argument("series")
    p = add("lint", cmd_lint, "check scenes for problems"); p.add_argument("series"); p.add_argument("scene", nargs="?")
    p = add("undo", cmd_undo, "undo the last change"); p.add_argument("series")
    p = add("snapshot", cmd_snapshot, "save a named snapshot"); p.add_argument("series"); p.add_argument("name")
    p = add("trace-grid", cmd_trace_grid, "picture with coordinate grid, to read joint positions"); p.add_argument("image"); p.add_argument("--out"); p.add_argument("--step", type=int, default=50)
    p = add("trace-preview", cmd_trace_preview, "preview the joint/part layout on the picture"); p.add_argument("image"); p.add_argument("layout"); p.add_argument("--out")
    p = add("trace", cmd_trace, "trace a picture into a rigged vector character"); p.add_argument("series"); p.add_argument("character"); p.add_argument("image"); p.add_argument("layout")
    p.add_argument("--colors", type=int, default=10); p.add_argument("--detail", type=float, default=1.0); p.add_argument("--skin")
    p = add("schema", cmd_schema, "export JSON Schemas from the models"); p.add_argument("--out", default=str(REPO / "schemas"))
    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except StoreError as e:
        console.print(f"[red]{escape(str(e))}[/]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
