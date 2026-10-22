"""The AI director: turns plain English into validated ops, checks its own work, and reports briefly.

Anthropic SDK with streaming, tool use, prompt caching, the `web_search` server tool and `pause_turn` handling.
The client is injectable (dependency injection only; there is no mock client in this repo - the director needs a real ANTHROPIC_API_KEY).

Safety rails
  * all ops of one request share an undo *group*: one `/undo` reverts the whole request;
  * `dry_run=True` computes everything in a discarded transaction and reports the plan;
  * the AI cannot touch locked or user-authored events (enforced in ops.py, errors come back to the model);
  * after building, touched scenes are linted; errors are fed back for up to 2 repair rounds.
"""
from __future__ import annotations

import base64
import os
import tempfile
import time
from pathlib import Path
from typing import Callable

from . import check as C
from . import ops as O
from . import render, summary
from . import vocab as V
from .session import Session
from .store import Store, StoreError

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_PLAN_MODEL = "claude-opus-5-5"
DEFAULT_EDIT_MODEL = "claude-haiku-5-5"
MAX_STEPS = 30
REPAIR_ROUNDS = 2

# approximate list prices, USD per million tokens (input, output). Override with INKREEL_PRICES="in,out" for the active model.
PRICES = {"opus": (15.0, 75.0), "sonnet": (3.0, 15.0), "haiku": (1.0, 5.0)}


class DirectorError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint

    def __str__(self):
        return f"{super().__str__()} Hint: {self.hint}" if self.hint else super().__str__()


SYSTEM = """You are the DIRECTOR inside Inkreel Studio, a terminal-driven 2D hand-drawn animation studio for whole series. The user talks to you in plain
English; you build and edit animation by calling tools. Every tool call is applied immediately and shown live in the studio, so work like a director
at an animator's desk: decide, build, check, then report briefly.

# How the studio works
- Hierarchy: Series > Episode > Scene. Characters, custom actions, the style and the bible belong to the SERIES, so a character looks and moves
  identically in every scene of every episode. Create a character once (create_character), reuse it everywhere.
- Look: hand-drawn, boiling ink lines, hatch shading, paper grain. Characters are jointed side-view cut-out puppets drawn procedurally (never AI images).
  Backgrounds: {backgrounds}. Time of day: {times}. Props: {props}. FX: {fx}.
- The frame is 1280x720 at zoom 1. World x runs 0..scene width. Ground line y = 570. A 300px character is a normal adult; two or three characters fit one wide frame.
  Put fighters about the attack's reach apart (punch ~130px, kick ~150, slash ~190, thrust ~230). Time is in seconds from the scene start.
- A character must be created and then placed in a scene (place) before it can move, act or speak.
- You are shown the series context at the top of every user message (<context>). It is authoritative: do not recreate what exists. Events have ids in
  [brackets]; a trailing * means the USER authored it, L means it is LOCKED. You must never edit, delete or rewrite those (the tools will refuse). Never change
  the user's dialogue unless they explicitly ask. Add new events around them instead.

# Library actions (each has a tested hand-keyed pose sequence)
{library}
Stances: {stances}. Emotions: {emotions}. Weapons: {weapons}. Hair: {hair}.
For anything the library lacks write joint keyframes with `keyframes` (one-off) or `define_action` (reusable signature move, usable as an attack in `strike`).
Joint angles are degrees from straight down; + = toward the facing direction.

# Craft rules
1. Anticipation, action, follow-through. Library actions have them; custom keys need a wind-up, a snap key (ease 'snap') and a settle key.
2. Sync everything to the contact frame. For fights use `strike`: it places the attack, the reaction on the exact contact frame, impact, shake and sound-text and returns when both
   fighters are free so you can chain the next exchange.
3. Rhythm: fights are conversations. Alternate attack/defend, mix results (dodge, block, light hits), escalate power (light, medium, heavy, knockdown), leave 0.3-0.8s of
   breathing room between exchanges and let the finisher have space. 6-12 seconds is a good fight.
4. Camera grammar: establish wide (zoom ~0.9), `frame` the fighters, push in (1.3-1.8) on emotional beats and big hits, shake on impacts, pull back for the aftermath. Letterbox 40-60 for cinematic scenes.
5. Staging: characters face each other, do not overlap, keep clear silhouettes. Keep idle characters alive (stance change, emote, gesture, nod while the other speaks).
6. Dialogue: one `say` per line, sequenced with the end time the tool returns (+0.2-0.4s gap). Give lines an emotion. Keep lines short.
7. Weight and pace: heavy characters get slower, bigger actions; light fast characters get snappier ones.
8. Sound-text and flashes sparingly. After a knockdown the character stays down; add getup if they should rise.
9. When a tool result shows a WARNING, fix it right away.

# Working method
- If the request is clear enough to start, START and build the whole scene in one go (characters, scene, props, placement, camera, choreography, fx, captions) with many tool
  calls in one response; they run in order. Make confident creative choices.
- If something important is genuinely ambiguous and would change the whole build, call `ask_user` with at most 3 short questions, each with your best-guess default, and
  make no other tool calls that turn. If the user replies "yes" or "defaults", use your defaults.
- After building or editing, call `check_scene` on the scene, fix every error and warning you caused, then (for new scenes) you may call `render_preview_frame` once at a key
  moment to look at your own work and fix staging problems. Then report.
- Research: when asked, or when authenticity matters (a real place, culture, costume, martial art, weapon, animation technique), use web_search first, call `note_research`
  with the distilled facts, and APPLY them to colours, props, costume, setting, motion and dialogue. Record lasting decisions with `set_bible`.
- Feedback ("faster", "more dramatic", "make him taller"): change only what is needed (update_event, remove_events, re-issue ops). Keep what works.
- If the engine cannot do something, say so in one sentence and offer the closest thing. Current limits: side-view 2D puppets (no turnarounds yet), no audio yet,
  creatures are built from the character system, movement is on a ground plane.

# Reply style
Plain text for a terminal: no markdown headings, tables or emoji. After building, reply in 2-5 short lines: what you made (scene id, duration), the one or two creative
choices worth knowing, and a concrete suggestion for next. Do not list every tool call."""


def build_system() -> str:
    lib = []
    for k, v in V.builtin_actions().items():
        lib.append(f"  {k} ({v['dur']}s{', contact@%.2f reach %s' % (v['hit'], v.get('reach')) if v.get('hit') else ''}"
                   f"{', ends ' + v['endStance'] if v.get('endStance') else ''}): {v['desc']}")
    return SYSTEM.format(backgrounds=", ".join(V.BACKGROUNDS), times=", ".join(V.TIMES), props=", ".join(V.PROPS), fx=", ".join(V.FX_KINDS),
                         library="\n".join(lib), stances=", ".join(V.stances()), emotions=", ".join(V.emotions()), weapons=", ".join(V.WEAPONS), hair=", ".join(V.HAIR))


EXTRA_TOOLS = [
    {"name": "ask_user",
     "description": "Ask the user up to 3 short clarifying questions when the request is genuinely ambiguous and the answer would change the whole build. "
                    "Give your best-guess default for each so the user can just say yes. Make no other tool calls in the same turn.",
     "input_schema": {"type": "object", "properties": {"questions": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
         "question": {"type": "string"}, "default": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}},
         "required": ["question", "default"]}}}, "required": ["questions"]}},
    {"name": "check_scene",
     "description": "Lint a scene: overlapping characters, out-of-reach hits, unreadable timing, dialogue overlap, off-stage action, missing assets/characters/weapons. "
                    "Returns findings with fixes. Call it after building or editing a scene and fix what it reports.",
     "input_schema": {"type": "object", "properties": {"scene": {"type": "string"}}, "required": ["scene"]}},
    {"name": "render_preview_frame",
     "description": "Render one frame of a scene and look at it (you receive the image) to critique staging, framing and readability. t is seconds from the scene start.",
     "input_schema": {"type": "object", "properties": {"scene": {"type": "string"}, "t": {"type": "number"}}, "required": ["scene", "t"]}},
    {"name": "search_bible",
     "description": "Search the series bible and research notes for more detail than the context excerpt shows.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]
INLINE = {"ask_user", "check_scene", "render_preview_frame", "search_bible"}


def tool_list(use_search: bool = True) -> list[dict]:
    tools = [dict(t) for t in O.TOOLS] + [dict(t) for t in EXTRA_TOOLS]
    if use_search:
        tools.append({"type": os.environ.get("INKREEL_SEARCH_TOOL", "web_search_20250305"), "name": "web_search", "max_uses": 6})
    return tools


def _price(model: str) -> tuple[float, float]:
    env = os.environ.get("INKREEL_PRICES")
    if env:
        try:
            a, b = env.split(",")
            return float(a), float(b)
        except ValueError:
            pass
    for k, v in PRICES.items():
        if k in model:
            return v
    return PRICES["sonnet"]


class Director:
    def __init__(self, store: Store, sid: str, client=None, model: str | None = None, think: bool = False, dry_run: bool = False,
                 on_text: Callable[[str], None] | None = None, on_op: Callable[[str, dict, bool, str], None] | None = None,
                 on_search: Callable[[str], None] | None = None, on_question: Callable[[list[dict]], None] | None = None,
                 backend=None):
        self.store, self.sid = store, sid
        self.fixed_model = model or os.environ.get("INKREEL_MODEL")
        self.think, self.dry_run = think, dry_run
        self.on_text = on_text or (lambda s: None)
        self.on_op = on_op or (lambda n, a, ok, m: None)
        self.on_search = on_search or (lambda q: None)
        self.on_question = on_question or (lambda q: None)
        self.use_search = os.environ.get("INKREEL_NO_SEARCH") != "1"
        self._client = client
        self.backend = backend or render.default_backend()
        self.focus_episode: str | None = None
        self.focus_scene: str | None = None
        self.usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "usd": 0.0, "requests": 0}
        self.last_plan: list[tuple[str, bool, str]] = []   # dry-run output
        self.last_model = ""

    # ------------------------------------------------------------------ plumbing
    @property
    def available(self) -> bool:
        return self._client is not None or bool(os.environ.get("ANTHROPIC_API_KEY"))

    @property
    def client(self):
        if self._client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise DirectorError("No ANTHROPIC_API_KEY set.", "export ANTHROPIC_API_KEY=sk-ant-... (or set it in your shell profile) and restart")
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def pick_model(self, text: str) -> str:
        if self.fixed_model:
            return self.fixed_model
        t = text.strip().lower()
        plan = os.environ.get("INKREEL_PLAN_MODEL", DEFAULT_PLAN_MODEL)
        edit = os.environ.get("INKREEL_EDIT_MODEL", DEFAULT_EDIT_MODEL)
        main = os.environ.get("INKREEL_MAIN_MODEL", DEFAULT_MODEL)
        builds = any(w in t for w in ("scene", "episode", "fight", "chase", "build", "create", "make a", "make an", "write", "research", "plan"))
        if t.startswith("/plan") or len(t) > 500:
            return plan
        if len(t) < 110 and self.focus_scene and not builds:
            return edit
        return main

    def cost_line(self) -> str:
        u = self.usage
        return (f"{u['requests']} requests, {u['input']:,} in ({u['cache_read']:,} cached) / {u['output']:,} out tokens, approx ${u['usd']:.3f} "
                f"(list prices; set INKREEL_PRICES=in,out to override)")

    def _account(self, resp, model: str):
        us = getattr(resp, "usage", None)
        if not us:
            return
        i, o = getattr(us, "input_tokens", 0) or 0, getattr(us, "output_tokens", 0) or 0
        cr, cw = getattr(us, "cache_read_input_tokens", 0) or 0, getattr(us, "cache_creation_input_tokens", 0) or 0
        pi, po = _price(model)
        self.usage["input"] += i + cr + cw
        self.usage["output"] += o
        self.usage["cache_read"] += cr
        self.usage["cache_write"] += cw
        self.usage["requests"] += 1
        self.usage["usd"] += (i * pi + cw * pi * 1.25 + cr * pi * 0.1 + o * po) / 1e6

    # ------------------------------------------------------------------ one API request
    def _request(self, model: str, system: list[dict], messages: list):
        kw = dict(model=model, max_tokens=16000, system=system, tools=tool_list(self.use_search), messages=messages)
        if self.think:
            kw.update(max_tokens=20000, thinking={"type": "enabled", "budget_tokens": 5000})
        try:
            import anthropic
        except ImportError:  # fake-only environments
            anthropic = None
        try:
            with self.client.messages.stream(**kw) as stream:
                for ev in stream:
                    t = getattr(ev, "type", "")
                    if t == "text":
                        self.on_text(ev.text)
                    elif t == "content_block_stop":
                        b = getattr(ev, "content_block", None)
                        if getattr(b, "type", "") == "server_tool_use":
                            q = (getattr(b, "input", None) or {}).get("query")
                            if q:
                                self.on_search(q)
                resp = stream.get_final_message()
            self._account(resp, model)
            return resp
        except Exception as e:
            if anthropic is None or not isinstance(e, anthropic.APIError):
                raise
            if isinstance(e, anthropic.AuthenticationError):
                raise DirectorError("The Anthropic API key was rejected.", "check ANTHROPIC_API_KEY")
            if isinstance(e, anthropic.NotFoundError):
                raise DirectorError(f"Model '{model}' was not found for this key.", "pick another with /model claude-sonnet-5-5 (or set INKREEL_MODEL)")
            if isinstance(e, anthropic.RateLimitError):
                raise DirectorError("Rate limited by the API.", "wait a few seconds and send again; edits so far are kept (/undo reverts them)")
            if isinstance(e, anthropic.BadRequestError):
                if self.use_search and "web_search" in str(e):
                    self.use_search = False
                    self.on_text("\n[web search is not available for this key/model; continuing without research]\n")
                    return self._request(model, system, messages)
                raise DirectorError(f"API request rejected: {e}", "if this repeats, run /clear to reset the chat memory")
            if isinstance(e, anthropic.APIConnectionError):
                raise DirectorError("Could not reach the Anthropic API.", "check your internet connection")
            raise DirectorError(f"API error {getattr(e, 'status_code', '?')}: {getattr(e, 'message', e)}")

    # ------------------------------------------------------------------ tools handled outside the op registry
    def _tool_check(self, a: dict) -> tuple[str, bool]:
        if self.dry_run:
            return "dry-run: lint skipped (nothing was written).", False
        try:
            return C.summarize(C.check_scene(self.store, self.sid, a.get("scene", ""))), False
        except StoreError as e:
            return str(e), True

    def _tool_preview(self, a: dict):
        if self.dry_run:
            return "dry-run: preview skipped.", True
        try:
            scn = a.get("scene", "")
            b = render.compile_bundle(self.store, self.sid, None, O.slug(scn))
            t = float(a.get("t", 0))
            out = Path(tempfile.mkdtemp(prefix="inkreel-preview-")) / "f.png"
            self.backend.still(b, render.locate(b, b["scenes"][0]["id"], max(0.0, t)), out, 0.6)
            data = base64.b64encode(out.read_bytes()).decode()
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                    {"type": "text", "text": f"frame of '{scn}' at t={t:.2f}s (1280x720 scaled). Critique staging/framing; fix real problems, ignore noise."}], False
        except (StoreError, render.RenderError, O.OpError, ValueError, IndexError) as e:
            return f"could not render preview: {e}", True

    def _tool_bible(self, a: dict) -> tuple[str, bool]:
        tx = self.store.reader()
        s = tx.read(f"series/{self.sid}/series.json")
        bible = tx.read(f"series/{self.sid}/bible.md", {"_text": ""})["_text"]
        return summary.retrieve(bible, s.get("notes", []), str(a.get("query", "")), budget_chars=6000) or "nothing found", False

    # ------------------------------------------------------------------ a full request
    def run(self, text: str, episode: str | None = None, scene: str | None = None) -> str:
        if not self.available:
            raise DirectorError("No ANTHROPIC_API_KEY set.", "export ANTHROPIC_API_KEY=sk-ant-... and restart")
        self.focus_episode = episode or self.focus_episode
        self.focus_scene = scene or self.focus_scene
        model = self.pick_model(text)
        self.last_model = model
        context = summary.series_context(self.store, self.sid, self.focus_episode, self.focus_scene, text)
        history = self.store.chat_load(self.sid, 12)
        user = f"<context>\n{context}\n</context>\n\n{text}"
        messages: list = [{"role": h["role"], "content": h["content"]} for h in history] + [{"role": "user", "content": user}]
        system = [{"type": "text", "text": build_system(), "cache_control": {"type": "ephemeral"}}]

        sess = Session(self.store, self.sid, self.focus_episode)
        group = f"d{int(time.time() * 1000)}"
        label = "director: " + text.strip().replace("\n", " ")[:60]
        self.last_plan = []
        touched: set[str] = set()
        n_ops = n_err = 0
        final_text = ""
        repairs = 0
        asked = False
        dry_cm = self.store.turn(self.sid, label, "ai", group=group, discard=True) if self.dry_run else None
        dry_tx = dry_cm.__enter__() if dry_cm else None
        dry_ctx = O.OpCtx(dry_tx, self.sid, self.focus_episode, "ai") if dry_tx else None
        called_check = False

        def flush(pending: list) -> list[tuple[str, bool, str]]:
            nonlocal n_ops, n_err
            if not pending:
                return []
            items = [(b.name, dict(b.input or {})) for b in pending]
            if dry_ctx is not None:
                res = []
                for name, args in items:
                    ok, msg = dry_tx.attempt(lambda: O.apply_op(dry_ctx, name, args))
                    res.append((name, ok, msg))
            else:
                res = sess.run(items, src="ai", label=label, group=group)
            for (name, args), (_, ok, msg) in zip(items, res):
                n_ops += 1
                n_err += 0 if ok else 1
                self.on_op(name, args, ok, msg)
                if ok and args.get("scene"):
                    touched.add(O.slug(args["scene"]))
                if ok and name == "create_scene":
                    touched.add(O.slug(args["id"]))
                    self.focus_scene = O.slug(args["id"])
            self.last_plan += res
            return res

        try:
            for _ in range(MAX_STEPS):
                resp = self._request(model, system, messages)
                messages.append({"role": "assistant", "content": resp.content})
                final_text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip() or final_text
                if resp.stop_reason == "pause_turn":
                    continue
                uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
                if not uses:
                    # self-check: lint what we touched, feed errors back for a bounded number of repairs
                    if touched and not self.dry_run and repairs < REPAIR_ROUNDS:
                        errs = []
                        for scn in sorted(touched):
                            try:
                                errs += [f"{scn}: {f['code']} @{f.get('t', '-')}: {f['message']} Fix: {f.get('hint', '')}" for f in C.check_scene(self.store, self.sid, scn) if f["severity"] == "error"]
                            except StoreError:
                                pass
                        if errs and not called_check:
                            repairs += 1
                            messages.append({"role": "user", "content": "check_scene found errors in your work. Fix them with tools, then reply briefly:\n" + "\n".join(errs[:12])})
                            continue
                    break
                results, pending = [], []
                by_id: dict[str, tuple[str, bool]] = {}

                def drain():
                    for b, (name, ok, msg) in zip(pending, flush(pending)):
                        by_id[b.id] = (msg, not ok)
                    pending.clear()

                order: list = []
                for b in uses:
                    if b.name in INLINE:
                        drain()
                        if b.name == "ask_user":
                            qs = list((b.input or {}).get("questions", []))[:3]
                            asked = True
                            self.on_question(qs)
                            by_id[b.id] = ("Questions shown to the user. Stop and wait for their answer; make no more tool calls.", False)
                        elif b.name == "check_scene":
                            called_check = True
                            by_id[b.id] = self._tool_check(dict(b.input or {}))
                        elif b.name == "render_preview_frame":
                            by_id[b.id] = self._tool_preview(dict(b.input or {}))
                        else:
                            by_id[b.id] = self._tool_bible(dict(b.input or {}))
                    else:
                        pending.append(b)
                drain()
                for b in uses:
                    content, is_err = by_id[b.id]
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": content, "is_error": is_err})
                messages.append({"role": "user", "content": results})
                if asked:
                    # let the model phrase the questions, then stop
                    resp = self._request(model, system, messages)
                    final_text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip() or final_text
                    break
            else:
                self.on_text("\n[stopped after 30 steps]\n")
        finally:
            if dry_cm:
                dry_cm.__exit__(None, None, None)

        note = f" [{n_ops} edits applied{', %d failed' % n_err if n_err else ''}{' (dry run, nothing written)' if self.dry_run else ''}]" if n_ops else ""
        self.store.chat_add(self.sid, "user", text)
        self.store.chat_add(self.sid, "assistant", (final_text or "(done)") + note)
        return final_text
