"""Vocabulary and built-in library loading. Built-ins live in ../libraries; a series can add/override in its own libraries/."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIB_DIR = REPO / "libraries"

BACKGROUNDS = ["beach", "forest", "plains", "fortress", "street", "interior", "void"]
TIMES = ["day", "dawn", "golden", "dusk", "night", "storm"]
PROPS = ["palm", "tree", "bush", "rock", "crate", "barrel", "torch", "campfire", "hut", "boat", "lamp", "pillar",
         "banner", "fence", "sign", "grass", "monster_silhouette"]
FX_KINDS = ["impact", "slash", "dust", "ring", "sparks", "sfx_text", "flash", "vignette", "tint", "speedlines", "rain"]
PARTS = ["head", "chest", "hip", "hand_front", "hand_back", "foot_front", "foot_back", "weapon_tip", "feet", "center"]
WEAPONS = ["none", "sword", "katana", "dagger", "staff", "spear", "club", "greatblade"]
HAIR = ["short", "afro", "locs", "braids", "bun", "mohawk", "bald"]
OUTFITS = ["tee", "tank", "long", "bare"]
LEGS = ["pants", "shorts"]
BUILDS = ["slim", "average", "strong", "heavy", "child"]
EASES = ["linear", "in", "out", "inOut", "smooth", "snap", "back", "hold", "elastic"]
JOINTS = ["torso", "head", "aF", "eF", "aB", "eB", "tF", "kF", "tB", "kB", "wpn", "rx", "ry", "rot"]
MOVE_STYLES = ["walk", "run", "sneak", "slide", "backstep"]
MOVE_SPEED = {"walk": 150, "run": 380, "sneak": 80, "slide": 300, "backstep": 110}
CAM_KINDS = ["set", "move", "follow", "frame", "shake"]
BUBBLE_STYLES = ["say", "shout", "whisper", "think"]
CAPTION_STYLES = ["narration", "title", "location"]

POWER = {
    "light": dict(react="hit_light", amp=5, size=70, sfx=["POW!", "TAP!", "THWIP!"], flash=0.0, dust=False),
    "medium": dict(react="hit_heavy", amp=11, size=105, sfx=["WHAM!", "BAM!", "SMACK!"], flash=0.0, dust=False),
    "heavy": dict(react="hit_heavy", amp=18, size=140, sfx=["KRAKK!", "WHAMM!", "CRUNCH!"], flash=0.45, dust=True),
    "knockdown": dict(react="hit_knockdown", amp=26, size=170, sfx=["BOOOM!", "KA-BOOM!", "SLAMM!"], flash=0.6, dust=True),
}

NAMED_COLORS = {
    "black": "#111111", "white": "#f5f5f0", "red": "#c83a2e", "blue": "#2f5fb5", "green": "#3a8a4a", "yellow": "#e8c13a",
    "orange": "#e07a2a", "purple": "#6a3f8f", "pink": "#e58aa8", "brown": "#7a5030", "grey": "#808080", "gray": "#808080",
    "gold": "#d6a93a", "teal": "#2d8f85", "navy": "#1f2f5a", "cream": "#f2e8cf", "silver": "#c7ced4", "crimson": "#a3202e",
}
HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


@lru_cache(maxsize=1)
def builtin() -> dict:
    """{'stances':{}, 'emotions':{}, 'actions':{name:def}} loaded from libraries/."""
    actions = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((LIB_DIR / "actions").glob("*.json"))}
    return {
        "stances": json.loads((LIB_DIR / "stances.json").read_text(encoding="utf-8")),
        "emotions": json.loads((LIB_DIR / "emotions.json").read_text(encoding="utf-8")),
        "actions": actions,
    }


def stances() -> list[str]:
    return list(builtin()["stances"])


def emotions() -> list[str]:
    return list(builtin()["emotions"])


def builtin_actions() -> dict:
    return builtin()["actions"]
