"""Project persistence: project.json, undo history, change notifications."""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path

from . import ops


class Project:
    def __init__(self, root, title=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "project.json"
        self.meta_dir = self.root / ".inkreel"
        self.meta_dir.mkdir(exist_ok=True)
        (self.root / "exports").mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.version = 0
        self.listeners = []
        self.undo_stack: list[str] = []
        self.redo_stack: list[str] = []
        self.touched: list[str] = []
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            self._upgrade()
        else:
            self.data = ops.new_project(title or self.root.name.replace("-", " ").replace("_", " ").title())
            self._write()
        self.chat_path = self.meta_dir / "chat.json"

    # ------------------------------------------------------------------ io
    def _upgrade(self):
        base = ops.new_project()
        for k, v in base.items():
            self.data.setdefault(k, v)
        for k, v in base["meta"].items():
            self.data["meta"].setdefault(k, v)

    def _write(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        os.replace(tmp, self.path)

    def snapshot_json(self):
        return json.dumps(self.data)

    # ------------------------------------------------------------------ notify
    def emit(self, event):
        for fn in list(self.listeners):
            try:
                fn(event)
            except Exception:
                pass

    def _changed(self):
        self.version += 1
        self._write()
        self.emit({"type": "project", "version": self.version})

    # ------------------------------------------------------------------ ops
    def begin_turn(self):
        with self.lock:
            self._turn_start = self.snapshot_json()
            self.touched = []

    def end_turn(self):
        """Commit the turn to the undo stack if anything changed."""
        with self.lock:
            now = self.snapshot_json()
            start = getattr(self, "_turn_start", None)
            if start is not None and start != now:
                self.undo_stack.append(start)
                self.undo_stack = self.undo_stack[-40:]
                self.redo_stack.clear()
                if self.touched:
                    self.emit({"type": "touched", "scene": self.touched[-1]})
            self._turn_start = None

    def apply(self, name, args):
        """Apply one op atomically. Returns (ok, message)."""
        with self.lock:
            work = copy.deepcopy(self.data)
            try:
                msg = ops.apply(work, name, args)
            except ops.OpError as e:
                return False, str(e)
            except Exception as e:  # malformed model input
                return False, f"{type(e).__name__}: {e}"
            self.data = work
            sc = (args or {}).get("scene") or ((args or {}).get("id") if name == "create_scene" else None)
            if sc:
                self.touched.append(ops.slug(sc))
            self._changed()
            return True, msg

    def run_ops(self, items):
        """Convenience for scripts: items = [(name, args), ...]. Prints failures."""
        out = []
        self.begin_turn()
        for name, args in items:
            ok, msg = self.apply(name, args)
            out.append((ok, msg))
        self.end_turn()
        return out

    def undo(self):
        with self.lock:
            if not self.undo_stack:
                return False
            self.redo_stack.append(self.snapshot_json())
            self.data = json.loads(self.undo_stack.pop())
            self._changed()
            return True

    def redo(self):
        with self.lock:
            if not self.redo_stack:
                return False
            self.undo_stack.append(self.snapshot_json())
            self.data = json.loads(self.redo_stack.pop())
            self._changed()
            return True

    # ------------------------------------------------------------------ chat memory
    def load_chat(self):
        try:
            return json.loads(self.chat_path.read_text())
        except Exception:
            return []

    def save_chat(self, msgs):
        self.chat_path.write_text(json.dumps(msgs[-30:], indent=1))

    def clear_chat(self):
        if self.chat_path.exists():
            self.chat_path.unlink()
