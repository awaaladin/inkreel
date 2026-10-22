"""Single source of truth for the data model.

`inkreel schema` exports these models to ../schemas/*.json; the studio's TypeScript types and (Phase 3) the Rust serde
structs are generated from that output. Never hand-duplicate a type.

Field names inside actor tracks (moves/actions/stances/emotes/says/faces) match the prototype engine's
format on purpose, so a scene compiles to engine input with almost no translation.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1

Src = Literal["ai", "user", "import"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _Loose(BaseModel):
    """For engine-facing records: unknown keys are kept (forward compatible with hand edits)."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# --------------------------------------------------------------------------- style
class Style(_M):
    """Per-series look. Read by the renderer; every field is tunable."""
    line_weight: float = Field(1.0, ge=0.3, le=3.0, description="multiplier on ink line width")
    boil_fps: int = Field(12, ge=4, le=24, description="how often line wobble re-seeds")
    wobble: float = Field(1.0, ge=0.0, le=3.0)
    animate_on: Literal["ones", "twos", "auto"] = "auto"
    twos_fps: int = 12
    fast_action_threshold: float = Field(0.6, description="joint speed (rad/s-ish) above which auto switches to ones")
    palette_set: str = "ibeno"
    grain: float = Field(0.05, ge=0.0, le=0.5)
    vignette: float = Field(0.16, ge=0.0, le=0.6)
    shading: Literal["flat", "hatch", "crosshatch"] = "hatch"
    handheld: float = Field(1.0, ge=0.0, le=4.0, description="camera drift amplitude")
    overlap: float = Field(1.0, ge=0.0, le=2.0, description="follow-through strength")
    hit_stop_frames: int = Field(3, ge=0, le=8)
    width: int = 1280
    height: int = 720
    fps: int = 24


# --------------------------------------------------------------------------- characters / actions
class Character(_Loose):
    id: str
    name: str
    rig_type: Literal["builtin_puppet", "imported_parts", "quadruped", "serpent", "winged"] = "builtin_puppet"
    height: float = Field(300, ge=120, le=560)
    skin: str = "#8a5a3b"
    hair: str = "#1b1210"
    hair_style: str = "short"
    top: str = "#c8553d"
    bottom: str = "#2f3a4f"
    accent: str = "#e2b04a"
    outfit: str = "tee"
    legs: str = "pants"
    build: str = "average"
    weapon: str = "none"
    weapon_color: str | None = None
    boots: str | None = None
    barefoot: bool = False
    headband: bool = False
    beard: bool = False
    glasses: bool = False
    scarf: bool = False
    scar: bool = False
    head_scale: float | None = None
    notes: str = ""
    voice_id: str | None = None
    default_stance: str = "idle"
    views: list[str] = Field(default_factory=lambda: ["side"], description="available turnaround views")


class Key(_M):
    t: float = Field(ge=0, le=1)
    pose: dict[str, float] | str = Field(default_factory=dict, description="joint angles, or a stance name")
    ease: str = "smooth"


class ActionDef(_Loose):
    desc: str = ""
    category: str = "custom"
    dur: float = Field(0.8, ge=0.1, le=60)
    mask: Literal["full", "upper"] = "full"
    keys: list[Key]
    trail: Literal["weapon", "hand", "foot"] | None = None
    face: str | None = None
    endStance: str | None = None
    dx: float | None = None
    dxSpan: float | None = None
    hit: float | None = Field(None, ge=0.1, le=0.95)
    reach: float | None = None
    tags: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- scene events (provenance + lock on each)
class _Event(_Loose):
    id: str = ""
    src: Src = "ai"
    lock: bool = False
    t: float = 0.0


class Move(_Event):
    x: float | None = None
    y: float | None = None
    dur: float = 1.0
    style: str = "walk"
    ease: str = "smooth"


class ActEvent(_Event):
    action: str = ""
    dur: float | None = None
    intensity: float | None = None
    dx: float | None = None
    target: str | None = None


class StanceEvent(_Event):
    stance: str = "idle"
    blend: float = 0.3


class Emote(_Event):
    emotion: str = "neutral"


class Say(_Event):
    text: str = ""
    dur: float = 2.0
    emotion: str | None = None
    style: str | None = None
    audio: str | None = Field(None, description="asset path of a recorded/TTS clip (Phase 6)")


class Face(_Event):
    dir: int | None = None
    target: str | None = None


class Actor(_M):
    x: float = 0
    y: float = 0
    facing: int = 1
    moves: list[Move] = Field(default_factory=list)
    actions: list[ActEvent] = Field(default_factory=list)
    stances: list[StanceEvent] = Field(default_factory=list)
    emotes: list[Emote] = Field(default_factory=list)
    says: list[Say] = Field(default_factory=list)
    faces: list[Face] = Field(default_factory=list)


class FxEvent(_Event):
    kind: str = "impact"
    dur: float = 0.6


class CamEvent(_Event):
    kind: str = "set"


class Caption(_Event):
    text: str = ""
    dur: float = 2.0
    style: str = "narration"


class AudioCue(_Event):
    kind: Literal["sfx", "music", "ambience", "dialogue"] = "sfx"
    asset: str = ""
    dur: float | None = None
    gain_db: float = 0.0


class Prop(_Loose):
    id: str = ""
    src: Src = "ai"
    lock: bool = False
    kind: str = "rock"
    x: float = 0


class Background(_Loose):
    preset: str = "beach"
    time: str = "day"
    weather: str | None = None
    palette: dict[str, str] | None = None
    image: str | None = Field(None, description="imported background asset (Phase 5)")


class Transition(_M):
    in_: str | None = Field(None, alias="in")
    out: str | None = None
    color: str | None = None
    dur: float | None = None


class Shot(_M):
    id: str
    name: str = ""
    t: float = 0
    dur: float = 0
    note: str = ""


class Scene(_Loose):
    schema_version: int = SCHEMA_VERSION
    id: str
    name: str = ""
    background: Background = Field(default_factory=Background)
    groundY: float = 570
    width: float = 1280
    duration: float | None = None
    letterbox: float | None = None
    transition: Transition | None = None
    props: list[Prop] = Field(default_factory=list)
    actors: dict[str, Actor] = Field(default_factory=dict)
    camera: list[CamEvent] = Field(default_factory=list)
    fx: list[FxEvent] = Field(default_factory=list)
    captions: list[Caption] = Field(default_factory=list)
    audio: list[AudioCue] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)
    local_actions: dict[str, ActionDef] = Field(default_factory=dict, description="one-off keyframed actions used only in this scene")
    next_event: int = 1


# --------------------------------------------------------------------------- hierarchy
class Episode(_M):
    id: str
    title: str
    number: int = 1
    scenes: list[str] = Field(default_factory=list, description="ordered scene ids")
    title_cards: list[dict[str, Any]] = Field(default_factory=list)
    music_beds: list[dict[str, Any]] = Field(default_factory=list)
    credits: list[str] = Field(default_factory=list)
    synopsis: str = ""


class Series(_M):
    schema_version: int = SCHEMA_VERSION
    id: str
    title: str
    logline: str = ""
    episodes: list[str] = Field(default_factory=list, description="ordered episode ids")
    notes: list[dict[str, Any]] = Field(default_factory=list, description="research notes")


class Workspace(_M):
    schema_version: int = SCHEMA_VERSION
    name: str
    series: list[str] = Field(default_factory=list)


class Snapshot(_M):
    id: int
    name: str
    created: str
    series: str


MODELS: dict[str, type[BaseModel]] = {
    "Workspace": Workspace, "Series": Series, "Style": Style, "Character": Character, "ActionDef": ActionDef,
    "Scene": Scene, "Episode": Episode,
}
