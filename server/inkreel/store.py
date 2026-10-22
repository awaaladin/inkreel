"""Workspace store: plain JSON files on disk + SQLite index for the op log, undo/redo and snapshots.

Files are the source of truth. Every change happens inside a *turn* (`with store.turn(...) as tx`):
reads are cached, writes are buffered, and `commit` writes all dirty files atomically (temp + rename)
while recording before/after blobs so the turn can be undone/redone exactly, without ever clobbering a
later edit (undo refuses with a conflict if the file changed since).
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from . import model as M


class StoreError(Exception):
    """Problem the caller can fix; `hint` says how."""

    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint

    def __str__(self):
        base = super().__str__()
        return f"{base} Hint: {self.hint}" if self.hint else base


def slug(s: Any) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")
    if not out:
        raise StoreError("id must contain letters or digits", "use something like 'duel_at_shore'")
    return out


def _sha(b: bytes | None) -> str:
    return hashlib.sha256(b).hexdigest() if b is not None else ""


def _dump(data: Any) -> bytes:
    return (json.dumps(data, indent=1, ensure_ascii=False, sort_keys=False) + "\n").encode("utf-8")


SCHEMA = """
CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, series TEXT, src TEXT, label TEXT, state INTEGER DEFAULT 0, grp TEXT);
CREATE TABLE IF NOT EXISTS turn_files(turn_id INTEGER, path TEXT, before BLOB, after BLOB);
CREATE TABLE IF NOT EXISTS ops(turn_id INTEGER, seq INTEGER, name TEXT, args TEXT, ok INTEGER, msg TEXT);
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT, series TEXT, name TEXT, ts REAL, blob BLOB);
CREATE TABLE IF NOT EXISTS rev(series TEXT PRIMARY KEY, n INTEGER);
CREATE TABLE IF NOT EXISTS chat(id INTEGER PRIMARY KEY AUTOINCREMENT, series TEXT, ts REAL, role TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY AUTOINCREMENT, series TEXT, kind TEXT, spec TEXT, state TEXT, progress REAL DEFAULT 0, out TEXT, error TEXT, ts REAL);
"""
# turn.state: 0 = applied, 1 = undone (redo-able), 2 = dead (undone then superseded)


class Tx:
    def __init__(self, store: "Store", series: str | None, label: str, src: str, group: str | None = None):
        self.store, self.series, self.label, self.src, self.group = store, series, label, src, group
        self.discard = False                 # dry run: compute everything, write nothing
        self.cache: dict[str, Any] = {}      # rel path -> parsed json (deep) or None if deleted
        self.dirty: set[str] = set()
        self.ops: list[tuple[str, dict, bool, str]] = []
        self.touched_scenes: list[str] = []

    # ---- raw io
    def exists(self, rel: str) -> bool:
        if rel in self.cache:
            return self.cache[rel] is not None
        return (self.store.root / rel).exists()

    def read(self, rel: str, default: Any = ...) -> Any:
        if rel not in self.cache:
            p = self.store.root / rel
            if not p.exists():
                if default is ...:
                    raise StoreError(f"missing file {rel}", "check the id or create it first")
                return copy.deepcopy(default)
            try:
                txt = p.read_text(encoding="utf-8")
                self.cache[rel] = {"_text": txt} if rel.endswith(".md") else json.loads(txt)
            except json.JSONDecodeError as e:
                raise StoreError(f"{rel} is corrupt JSON ({e})", "restore from a snapshot: inkreel snapshots / restore")
        v = self.cache[rel]
        if v is None:
            if default is ...:
                raise StoreError(f"{rel} was deleted in this turn")
            return copy.deepcopy(default)
        return v

    def write(self, rel: str, data: Any) -> None:
        self.cache[rel] = data
        self.dirty.add(rel)

    def touch(self, rel: str) -> None:
        """Mark an object obtained from read() as modified in place."""
        self.dirty.add(rel)

    def mut(self, rel: str, default: Any = ...) -> Any:
        """read() for in-place editing: marks the file dirty (an unchanged result is dropped at commit)."""
        v = self.read(rel, default)
        self.dirty.add(rel)
        return v

    def delete(self, rel: str) -> None:
        self.cache[rel] = None
        self.dirty.add(rel)

    def list(self, rel_dir: str, suffix: str = ".json") -> list[str]:
        base = self.store.root / rel_dir
        names = set(p.name for p in base.glob(f"*{suffix}")) if base.exists() else set()
        for k, v in self.cache.items():
            if k.startswith(rel_dir + "/") and "/" not in k[len(rel_dir) + 1:] and k.endswith(suffix):
                (names.add if v is not None else names.discard)(k.rsplit("/", 1)[1])
        return sorted(names)

    # ---- op-level atomicity: if fn raises, undo its in-memory changes
    def attempt(self, fn: Callable[[], str]) -> tuple[bool, str]:
        cache_bak = copy.deepcopy(self.cache)
        dirty_bak = set(self.dirty)
        try:
            return True, fn()
        except Exception as e:  # OpError / StoreError / malformed model input
            self.cache, self.dirty = cache_bak, dirty_bak
            return False, str(e) if str(e) else f"{type(e).__name__}"

    def record(self, name: str, args: dict, ok: bool, msg: str) -> None:
        self.ops.append((name, args, ok, msg))


class Store:
    def __init__(self, root: str | Path, create: bool = True, name: str | None = None):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.listeners: list[Callable[[dict], None]] = []
        if not (self.root / "workspace.json").exists():
            if not create:
                raise StoreError(f"{self.root} is not an Inkreel workspace", "run: inkreel new <series> --workspace <dir>")
            self.root.mkdir(parents=True, exist_ok=True)
            self._atomic_write(self.root / "workspace.json", _dump(M.Workspace(name=name or self.root.name).model_dump()))
        (self.root / ".inkreel").mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / ".inkreel" / "index.sqlite", check_same_thread=False)
        self.db.executescript(SCHEMA)
        try:
            self.db.execute("ALTER TABLE turns ADD COLUMN grp TEXT")
        except sqlite3.OperationalError:
            pass  # column already there
        self.db.commit()

    # ------------------------------------------------------------------ series scaffolding
    def reader(self) -> Tx:
        """Read-only view (a Tx that is never committed)."""
        return Tx(self, None, "read", "system")

    def list_series(self) -> list[str]:
        ws = json.loads((self.root / "workspace.json").read_text(encoding="utf-8"))
        return ws.get("series", [])

    def create_series(self, sid: str, title: str | None = None, logline: str = "") -> str:
        sid = slug(sid)
        if sid in self.list_series():
            raise StoreError(f"series '{sid}' already exists", "pick another id or open it")
        title = title or sid.replace("_", " ").title()
        with self.turn(sid, f"create series {sid}", "user") as tx:
            tx.write(f"series/{sid}/series.json", M.Series(id=sid, title=title, logline=logline).model_dump())
            tx.write(f"series/{sid}/style.json", M.Style().model_dump())
            tx.write(f"series/{sid}/bible.md", {"_text": f"# {title} - series bible\n\n## Look\nHand-drawn, boiling ink lines, paper grain.\n"})
            ws = tx.read("workspace.json")
            ws["series"].append(sid)
            tx.touch("workspace.json")
        return sid

    # ------------------------------------------------------------------ paths
    @staticmethod
    def series_dir(sid: str) -> str:
        return f"series/{sid}"

    @staticmethod
    def episode_dir(sid: str, eid: str) -> str:
        return f"series/{sid}/episodes/{eid}"

    @staticmethod
    def scene_path(sid: str, eid: str, scn: str) -> str:
        return f"series/{sid}/episodes/{eid}/scenes/{scn}.json"

    # ------------------------------------------------------------------ io
    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def emit(self, ev: dict) -> None:
        for fn in list(self.listeners):
            try:
                fn(ev)
            except Exception:
                pass

    def rev(self, series: str) -> int:
        r = self.db.execute("SELECT n FROM rev WHERE series=?", (series,)).fetchone()
        return r[0] if r else 0

    # ------------------------------------------------------------------ turns
    @contextmanager
    def turn(self, series: str | None, label: str = "edit", src: str = "user", group: str | None = None, discard: bool = False):
        """All-or-nothing group of changes = one undo step. Exceptions inside discard everything.
        Turns sharing a `group` (one director request = several tool batches) are undone together."""
        with self.lock:
            tx = Tx(self, series, label, src, group)
            tx.discard = discard
            yield tx
            self._commit(tx)

    def _commit(self, tx: Tx) -> int | None:
        if tx.discard:
            return None
        changed: list[tuple[str, bytes | None, bytes | None]] = []
        for rel in sorted(tx.dirty):
            p = self.root / rel
            before = p.read_bytes() if p.exists() else None
            val = tx.cache.get(rel)
            after = _dump(val) if val is not None else None
            if rel.endswith(".md") and isinstance(val, dict) and "_text" in val:  # markdown stored as {"_text": ...}
                after = val["_text"].encode("utf-8")
            if before is not None and after is not None and rel.endswith(".json"):
                try:
                    if json.loads(before) == val:  # same content, different formatting: not a change
                        continue
                except json.JSONDecodeError:
                    pass
            if before != after:
                changed.append((rel, before, after))
        if not changed and not tx.ops:
            return None
        cur = self.db.cursor()
        tid = None
        if changed:
            cur.execute("UPDATE turns SET state=2 WHERE state=1 AND series IS ?", (tx.series,))  # new work kills redo
            cur.execute("INSERT INTO turns(ts,series,src,label,grp) VALUES(?,?,?,?,?)", (time.time(), tx.series, tx.src, tx.label, tx.group))
            tid = cur.lastrowid
            for rel, before, after in changed:
                cur.execute("INSERT INTO turn_files VALUES(?,?,?,?)", (tid, rel, gzip.compress(before) if before is not None else None,
                                                                         gzip.compress(after) if after is not None else None))
        for i, (name, args, ok, msg) in enumerate(tx.ops):
            cur.execute("INSERT INTO ops VALUES(?,?,?,?,?,?)", (tid or 0, i, name, json.dumps(args, default=str), int(ok), msg))
        for rel, before, after in changed:
            p = self.root / rel
            if after is None:
                p.unlink(missing_ok=True)
            else:
                self._atomic_write(p, after)
        if changed and tx.series:
            cur.execute("INSERT INTO rev(series,n) VALUES(?,1) ON CONFLICT(series) DO UPDATE SET n=n+1", (tx.series,))
        self.db.commit()
        if changed:
            scenes = sorted({r for r, _, _ in changed if "/scenes/" in r})
            self.emit({"type": "changed", "series": tx.series, "rev": self.rev(tx.series) if tx.series else 0, "turn": tid,
                       "files": [r for r, _, _ in changed], "scenes": [Path(s).stem for s in scenes], "src": tx.src, "label": tx.label})
        return tid

    # ------------------------------------------------------------------ undo / redo
    def _turn_files(self, tid: int):
        rows = self.db.execute("SELECT path,before,after FROM turn_files WHERE turn_id=?", (tid,)).fetchall()
        return [(p, gzip.decompress(b) if b is not None else None, gzip.decompress(a) if a is not None else None) for p, b, a in rows]

    def _flip(self, tid: int, series: str | None, to_before: bool) -> dict:
        files = self._turn_files(tid)
        conflicts = []
        for rel, before, after in files:
            expect = after if to_before else before
            p = self.root / rel
            cur = p.read_bytes() if p.exists() else None
            if cur != expect:
                conflicts.append(rel)
        if conflicts:
            raise StoreError(f"cannot {'undo' if to_before else 'redo'}: {', '.join(conflicts)} changed since",
                             "a later edit touched the same file; undo that first or restore a snapshot")
        for rel, before, after in files:
            target = before if to_before else after
            p = self.root / rel
            if target is None:
                p.unlink(missing_ok=True)
            else:
                self._atomic_write(p, target)
        self.db.execute("UPDATE turns SET state=? WHERE id=?", (1 if to_before else 0, tid))
        if series:
            self.db.execute("INSERT INTO rev(series,n) VALUES(?,1) ON CONFLICT(series) DO UPDATE SET n=n+1", (series,))
        self.db.commit()
        self.emit({"type": "changed", "series": series, "rev": self.rev(series) if series else 0, "turn": tid,
                   "files": [r for r, _, _ in files], "scenes": [Path(r).stem for r, _, _ in files if "/scenes/" in r],
                   "src": "history", "label": "undo" if to_before else "redo"})
        return {"turn": tid, "files": [r for r, _, _ in files]}

    def undo(self, series: str | None) -> dict | None:
        with self.lock:
            r = self.db.execute("SELECT id,label,grp FROM turns WHERE state=0 AND series IS ? ORDER BY id DESC LIMIT 1", (series,)).fetchone()
            if not r:
                return None
            ids = [r[0]]
            if r[2]:
                ids = [x[0] for x in self.db.execute("SELECT id FROM turns WHERE state=0 AND series IS ? AND grp=? ORDER BY id DESC", (series, r[2])).fetchall()]
            files: list[str] = []
            for i in ids:
                files += self._flip(i, series, True)["files"]
            return {"turn": ids[0], "turns": len(ids), "files": files, "label": r[1]}

    def redo(self, series: str | None) -> dict | None:
        with self.lock:
            r = self.db.execute("SELECT id,label,grp FROM turns WHERE state=1 AND series IS ? ORDER BY id DESC LIMIT 1", (series,)).fetchone()
            if not r:
                return None
            ids = [r[0]]
            if r[2]:
                ids = [x[0] for x in self.db.execute("SELECT id FROM turns WHERE state=1 AND series IS ? AND grp=? ORDER BY id ASC", (series, r[2])).fetchall()]
            files: list[str] = []
            for i in ids:
                files += self._flip(i, series, False)["files"]
            return {"turn": ids[-1], "turns": len(ids), "files": files, "label": r[1]}

    def history(self, series: str | None, limit: int = 30) -> list[dict]:
        rows = self.db.execute("SELECT id,ts,src,label,state FROM turns WHERE series IS ? ORDER BY id DESC LIMIT ?", (series, limit)).fetchall()
        out = []
        for tid, ts, src, label, state in rows:
            ops = self.db.execute("SELECT name,ok FROM ops WHERE turn_id=? ORDER BY seq", (tid,)).fetchall()
            out.append({"id": tid, "ts": ts, "src": src, "label": label, "state": ["applied", "undone", "dead"][state],
                        "ops": len(ops), "failed": sum(1 for _, ok in ops if not ok)})
        return out

    # ------------------------------------------------------------------ chat memory (director)
    def chat_add(self, series: str, role: str, content: str) -> None:
        with self.lock:
            self.db.execute("INSERT INTO chat(series,ts,role,content) VALUES(?,?,?,?)", (series, time.time(), role, content))
            self.db.commit()

    def chat_load(self, series: str, n: int = 12) -> list[dict]:
        rows = self.db.execute("SELECT role,content FROM chat WHERE series=? ORDER BY id DESC LIMIT ?", (series, n)).fetchall()
        msgs = [{"role": r, "content": c} for r, c in reversed(rows)]
        while msgs and msgs[0]["role"] != "user":   # API wants a user turn first
            msgs.pop(0)
        return msgs

    def chat_clear(self, series: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM chat WHERE series=?", (series,))
            self.db.commit()

    # ------------------------------------------------------------------ snapshots
    def _series_files(self, sid: str) -> dict[str, bytes]:
        base = self.root / self.series_dir(sid)
        out = {}
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix in (".json", ".md", ".srt"):
                out[p.relative_to(self.root).as_posix()] = p.read_bytes()
        return out

    def snapshot(self, sid: str, name: str) -> int:
        with self.lock:
            files = {k: v.decode("utf-8") for k, v in self._series_files(sid).items()}
            blob = gzip.compress(json.dumps(files).encode("utf-8"))
            cur = self.db.execute("INSERT INTO snapshots(series,name,ts,blob) VALUES(?,?,?,?)", (sid, name, time.time(), blob))
            self.db.commit()
            return cur.lastrowid

    def snapshots(self, sid: str) -> list[dict]:
        rows = self.db.execute("SELECT id,name,ts FROM snapshots WHERE series=? ORDER BY id", (sid,)).fetchall()
        return [{"id": i, "name": n, "ts": t} for i, n, t in rows]

    def _snap_files(self, snap_id: int) -> dict[str, str]:
        r = self.db.execute("SELECT blob FROM snapshots WHERE id=?", (snap_id,)).fetchone()
        if not r:
            raise StoreError(f"no snapshot {snap_id}", "list them with: inkreel snapshots")
        return json.loads(gzip.decompress(r[0]))

    def find_snapshot(self, sid: str, ref: str | int) -> int:
        snaps = self.snapshots(sid)
        for s in snaps:
            if str(s["id"]) == str(ref) or s["name"] == ref:
                return s["id"]
        raise StoreError(f"no snapshot '{ref}' for series {sid}", f"have: {[s['name'] for s in snaps] or 'none'}")

    def restore(self, sid: str, ref: str | int) -> int | None:
        """Restore a snapshot as one undoable turn."""
        snap = self._snap_files(self.find_snapshot(sid, ref))
        with self.turn(sid, f"restore snapshot {ref}", "user") as tx:
            current = {k for k in self._series_files(sid)}
            for rel in current - set(snap):
                tx.delete(rel)
            for rel, text in snap.items():
                if rel.endswith(".json"):
                    tx.write(rel, json.loads(text))
                else:
                    tx.write(rel, {"_text": text})
        return self.rev(sid)

    def diff_snapshots(self, sid: str, a: str | int, b: str | int | None = None) -> dict:
        """Structural diff a -> b (b=None means the working tree). Scenes are compared event-by-event by id."""
        fa = self._snap_files(self.find_snapshot(sid, a))
        fb = self._snap_files(self.find_snapshot(sid, b)) if b is not None else {k: v.decode("utf-8") for k, v in self._series_files(sid).items()}
        out: dict[str, Any] = {"added": [], "removed": [], "changed": [], "scenes": {}}
        for rel in sorted(set(fa) | set(fb)):
            if rel not in fa:
                out["added"].append(rel)
            elif rel not in fb:
                out["removed"].append(rel)
            elif fa[rel] != fb[rel]:
                out["changed"].append(rel)
                if "/scenes/" in rel and rel.endswith(".json"):
                    out["scenes"][Path(rel).stem] = diff_scene(json.loads(fa[rel]), json.loads(fb[rel]))
        return out


def _events(scene: dict) -> dict[str, dict]:
    ev = {}
    for cid, a in (scene.get("actors") or {}).items():
        for track in ("moves", "actions", "stances", "emotes", "says", "faces"):
            for e in a.get(track, []):
                ev[f"{cid}.{track}.{e.get('id') or json.dumps(e, sort_keys=True)}"] = e
    for track in ("camera", "fx", "captions", "audio", "props"):
        for e in scene.get(track, []):
            ev[f"{track}.{e.get('id') or json.dumps(e, sort_keys=True)}"] = e
    return ev


def diff_scene(a: dict, b: dict) -> dict:
    ea, eb = _events(a), _events(b)
    return {
        "added": sorted(k for k in eb if k not in ea),
        "removed": sorted(k for k in ea if k not in eb),
        "changed": sorted(k for k in ea if k in eb and ea[k] != eb[k]),
        "meta": {k: [a.get(k), b.get(k)] for k in ("name", "background", "duration", "width", "groundY", "letterbox") if a.get(k) != b.get(k)},
    }
