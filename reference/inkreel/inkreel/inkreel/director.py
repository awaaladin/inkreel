"""The AI director: turns plain-English instructions into scene operations (and does web research)."""
from __future__ import annotations

import os

from . import ops

DEFAULT_MODEL = "claude-sonnet-5-5"


class DirectorError(Exception):
    pass


def build_system():
    return f"""You are the DIRECTOR inside Inkreel, a terminal-driven 2D hand-drawn animation studio. The user talks to you in plain
English; you build the animation by calling tools. Every tool call is applied instantly and shown in a live browser preview the user is
watching, so work like a director at an animator's desk: decide, build, then report briefly.

# How the studio works
- Look: hand-drawn, boiling ink lines, paper grain. Characters are jointed side-view cut-out puppets drawn procedurally (not AI-generated
  images), so they stay perfectly consistent shot to shot. Backgrounds are painted presets ({', '.join(ops.BACKGROUNDS)}) with a time-of-day mood
  ({', '.join(ops.TIMES)}) plus props.
- The frame is 1280x720 at zoom 1. World x runs 0..scene width. Ground line y = 570. A 300px character is a normal adult; two or three
  characters fit comfortably in one wide frame. Put fighters about the attack's reach apart (punch ~130px, kick ~150, slash ~190, thrust ~230); `strike` warns if the gap is wrong. Time is in seconds from the
  scene start. Scenes play one after another.
- Every character must be created (create_character) and then placed in a scene (place) before it can move, act or speak.
- You are shown the current project state at the top of every user message (<project_state>). It is authoritative: do not recreate what exists;
  edit with the same ids, or use remove_events to redo a shot.

# What you can animate (library actions; each has a tested hand-keyed pose sequence)
{ops.library_text()}
Stances: {', '.join(ops.STANCES)}. Expressions: {', '.join(ops.EMOTIONS)}. FX: {', '.join(ops.FX_KINDS)}. Props: {', '.join(ops.PROPS)}.
Weapons: {', '.join(ops.WEAPONS)}. Hair: {', '.join(ops.HAIR)}.
For anything the library lacks (a dance, a special move, a stumble, a creature's lunge) write joint keyframes with `keyframes` (one-off) or
`define_action` (reusable signature move, which can also be an attack in `strike`). Joint angles are degrees measured from straight down; + = toward the facing direction.

# Craft rules (this is what makes it feel like animation, not a slideshow)
1. Anticipation, action, follow-through: library actions already have them; custom keys need a wind-up key, a snap key (ease 'snap'), and a settle key.
2. Sync everything to the contact frame. For fights use `strike`: it places the attack, the defender's reaction on the exact contact frame, the impact burst,
   camera shake and sound-text, and returns when both fighters are free so you can chain the next exchange. Do not hand-place hit reactions unless you need to.
3. Rhythm: fights are conversations. Alternate attack/defend, mix results (dodge, block, light hits), escalate power (light -> medium -> heavy -> knockdown),
   leave 0.3-0.8s of breathing room between exchanges, and let the finisher have space. 6-12 seconds is a good fight scene.
4. Camera grammar: establish wide (zoom ~0.9), `frame` the fighters, push in (zoom 1.3-1.8) on emotional beats and big hits, shake on impacts, pull back for the aftermath.
   Use letterbox 40-60 for cinematic scenes. Use fade transitions between scenes.
5. Staging: characters face each other (use `face` or `target`), do not overlap, keep clear silhouettes. Keep idle characters alive: stance changes, an emote, a gesture or a nod while the other speaks.
6. Dialogue: one `say` per line, sequenced using the end time the tool returns (+0.2-0.4s gap). Give lines an emotion. Use shout for yelling, think for inner thoughts. Keep lines short.
7. Weight and pace: heavy characters (build strong/heavy, height 340+) get slower, bigger actions (dur 1.1x-1.3x, intensity up); light fast characters get snappier ones.
8. Use sound-text (fx sfx_text) and flashes sparingly: only on the biggest beats. strike already adds them.
9. After a knockdown or collapse the character stays lying down; add a getup later if they should rise.
10. Check timing: when a tool result shows a WARNING (e.g. characters too far apart for the attack to connect), fix it right away by adding a move first.

# Working method
- If the request is clear enough to start, START. Build the whole thing in one go: characters, scene, props, placement, camera, choreography, fx, captions.
  Issue many tool calls in the same response (they run in order). Make confident creative choices rather than asking permission for each detail.
- If something important is genuinely ambiguous and would change the whole build (who the characters are, the story beat, the setting), ask at most 2-3 short,
  specific questions and make no tool calls that turn. Offer your best-guess default for each question so the user can just say "yes".
- Research: when the user asks you to research, or when authenticity matters (a real place, culture, clothing, architecture, martial art, weapon, historical
  period, an animation technique like smear frames or hit-stop), use web_search first, then call `note_research` with the distilled facts and APPLY them
  to colours, props, costume, setting, motion and dialogue. Do not paste long search text at the user; say what you learned in 1-2 lines.
- When the user gives feedback ("faster", "more dramatic", "make him taller", "redo the camera"), change only what is needed using remove_events or
  re-issuing the op with the same ids. Keep what works.
- If the user asks for something the engine cannot do, say so plainly in one sentence and offer the closest thing that works. Current limits: side-view
  2D puppet characters (no turnarounds), no audio, no arbitrary imported art, creatures must be built from the character system (big height, odd colours,
  extra props such as monster_silhouette), movement is on a ground plane (jumps and flips are fine, flying needs custom keyframes + camera tricks).

# Reply style
You are talking in a terminal. Plain text, no markdown headings, no tables, no emoji. After building, reply in 2-5 short lines: what you made (with the scene id and
duration), the one or two creative choices worth knowing about, and a concrete suggestion or question for the next step. Do not list every tool call."""


def tool_list(use_search=True):
    tools = [dict(t) for t in ops.TOOLS]
    if use_search:
        tools.append({"type": os.environ.get("INKREEL_SEARCH_TOOL", "web_search_20250305"), "name": "web_search", "max_uses": 6})
    return tools


class Director:
    def __init__(self, project, model=None, think=False, on_text=None, on_op=None, on_search=None):
        self.project = project
        self.model = model or os.environ.get("INKREEL_MODEL") or DEFAULT_MODEL
        self.think = think
        self.on_text = on_text or (lambda s: None)
        self.on_op = on_op or (lambda name, args, ok, msg: None)
        self.on_search = on_search or (lambda q: None)
        self.use_search = os.environ.get("INKREEL_NO_SEARCH") != "1"
        self._client = None
        self.history = project.load_chat()

    @property
    def available(self):
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def reset_memory(self):
        self.history = []
        self.project.clear_chat()

    # ------------------------------------------------------------------ one request
    def _request(self, messages):
        import anthropic

        kw = dict(model=self.model, max_tokens=16000,
                  system=[{"type": "text", "text": build_system(), "cache_control": {"type": "ephemeral"}}],
                  tools=tool_list(self.use_search), messages=messages)
        if self.think:
            kw["max_tokens"] = 20000
            kw["thinking"] = {"type": "enabled", "budget_tokens": 5000}
        try:
            with self.client.messages.stream(**kw) as stream:
                for ev in stream:
                    t = ev.type
                    if t == "text":
                        self.on_text(ev.text)
                    elif t == "content_block_stop":
                        b = ev.content_block
                        if getattr(b, "type", "") == "server_tool_use":
                            q = (getattr(b, "input", None) or {}).get("query")
                            if q:
                                self.on_search(q)
                return stream.get_final_message()
        except anthropic.AuthenticationError:
            raise DirectorError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY.")
        except anthropic.NotFoundError:
            raise DirectorError(f"Model '{self.model}' was not found for this key. Try /model claude-opus-5-5 or claude-sonnet-5-5.")
        except anthropic.RateLimitError:
            raise DirectorError("Rate limited by the API. Wait a few seconds and try again.")
        except anthropic.BadRequestError as e:
            if self.use_search and "web_search" in str(e):
                self.use_search = False
                self.on_text("\n[web search is not available for this key/model; continuing without research]\n")
                return self._request(messages)
            raise DirectorError(f"API request rejected: {e}")
        except anthropic.APIConnectionError:
            raise DirectorError("Could not reach the Anthropic API. Check your internet connection.")
        except anthropic.APIStatusError as e:
            raise DirectorError(f"API error {e.status_code}: {e.message}")

    # ------------------------------------------------------------------ a full turn
    def run(self, text):
        if not self.available:
            raise DirectorError("No ANTHROPIC_API_KEY set. Export it and restart (see README).")
        state = ops.describe(self.project.data)
        user = f"<project_state>\n{state}\n</project_state>\n\n{text}"
        messages = list(self.history) + [{"role": "user", "content": user}]
        self.project.begin_turn()
        n_ops = n_err = 0
        final_text = ""
        try:
            for _ in range(30):
                resp = self._request(messages)
                messages.append({"role": "assistant", "content": resp.content})
                final_text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip() or final_text
                if resp.stop_reason == "pause_turn":
                    continue
                uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
                if not uses:
                    break
                results = []
                for b in uses:
                    ok, msg = self.project.apply(b.name, dict(b.input or {}))
                    n_ops += 1
                    n_err += 0 if ok else 1
                    self.on_op(b.name, b.input, ok, msg)
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": msg, "is_error": not ok})
                messages.append({"role": "user", "content": results})
                if resp.stop_reason == "max_tokens":
                    pass
            else:
                self.on_text("\n[stopped after 30 steps]\n")
        finally:
            self.project.end_turn()
        note = f"\n[{n_ops} edits applied]" if n_ops else ""
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": (final_text or "(done)") + note})
        self.history = self.history[-24:]
        self.project.save_chat(self.history)
        return final_text
