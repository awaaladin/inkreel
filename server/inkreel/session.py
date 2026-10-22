"""Apply ops as one atomic, undoable turn. Shared by the director, CLI, API and tests."""
from __future__ import annotations

from typing import Iterable

from . import ops as O
from .store import Store, StoreError


class Session:
    def __init__(self, store: Store, sid: str, eid: str | None = None):
        if sid not in store.list_series():
            raise StoreError(f"no series '{sid}'", f"have: {store.list_series() or 'none'}; create one with: inkreel new {sid}")
        self.store, self.sid, self.eid = store, sid, eid

    def run(self, items: Iterable[tuple[str, dict]], src: str = "ai", label: str = "edit", group: str | None = None,
            dry_run: bool = False) -> list[tuple[str, bool, str]]:
        """Run ops in order inside one turn. A failing op rolls back only itself; the turn keeps the rest."""
        results = []
        with self.store.turn(self.sid, label, src, group=group, discard=dry_run) as tx:
            ctx = O.OpCtx(tx, self.sid, self.eid, src)
            for name, args in items:
                ok, msg = tx.attempt(lambda: O.apply_op(ctx, name, args))
                tx.record(name, args, ok, msg)
                results.append((name, ok, msg))
            self.eid = ctx.eid or self.eid
        return results

    def one(self, name: str, args: dict, src: str = "user") -> str:
        (n, ok, msg), = self.run([(name, args)], src=src, label=name)
        if not ok:
            raise O.OpError(msg)
        return msg
