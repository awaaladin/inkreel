"""Sample series "Ibeno Tides": 3 characters, 2 episodes, 7 scenes (duel, dialogue-only, chase, creature scare, rematch, ...)."""
from __future__ import annotations

from .session import Session
from .store import Store

SID = "ibeno_tides"

BIBLE = """# Ibeno Tides - series bible

## Premise
Ibeno, Akwa Ibom: a long Atlantic beach where fishing canoes, palms and brackish creeks meet the open sea. Something old stirs
beyond the surf line. Kabi, a young surfer, inherits his late father's board - a *transforming surfboard-sword* that locks into
a greatblade when the tide spirit answers.

## Cast
- **Kabi** (hero): 300px, dark brown skin, locs, orange tee, headband. Determined, quick, impulsive. Weapon: the surfboard-sword.
- **Ogun** (rival, once Kabi's mentor): 335px, strong build, bald, beard, plum tank. Calm, controlled, speaks slowly. Weapon: iron staff.
- **Ima** (village elder & boat-builder): 270px, braids, long wrapper in teal. Dry humour; knows the old stories.

## World rules
- The sea answers to blood-kin of the first canoe-builders. Creatures appear only at dusk, night and storm.
- No guns. Weapons are carved, forged or lashed from boat parts.
- Day is warm and gold; night is deep indigo with ochre firelight.

## Look
Hand-drawn, boiling ink lines, hatch shading, misregistered flat colour, paper grain. Camera is slightly handheld.
Locations: Ibeno shore (beach), the creek road (plains), Ima's boatyard (interior/hut), the reef edge (storm).

## Story so far
Ep1: Kabi meets Ima at dawn, chases Ogun along the shore, and they duel at dusk. Ep2: the sea answers; a creature rises at the reef.
"""


def build(store: Store, sid: str = SID) -> Session:
    if sid not in store.list_series():
        store.create_series(sid, "Ibeno Tides", "A surfer, a staff-fighter and a sea that remembers.")
    s = Session(store, sid)
    src = "import"
    r = s.run([
        ("set_bible", dict(text=BIBLE, mode="replace_all")),
        ("create_character", dict(id="kabi", name="Kabi", height=300, skin="#6b4228", hair="#120c0a", hair_style="locs", top="#d9822b", bottom="#2b3a55",
                                  accent="#2d8f85", outfit="tee", weapon="greatblade", headband=True, voice_id="young_male",
                                  notes="Hero. Quick, impulsive, loyal. Surfboard-sword.")),
        ("create_character", dict(id="ogun", name="Ogun", height=335, build="strong", skin="#4a2e1e", hair="#0c0808", hair_style="bald", top="#5a2f4a",
                                  bottom="#3b3b3b", accent="#c9a14a", outfit="tank", weapon="staff", beard=True, voice_id="deep_male",
                                  notes="Rival, former mentor. Calm and controlled.")),
        ("create_character", dict(id="ima", name="Ima", height=270, build="slim", skin="#7a4a30", hair="#d8d4cc", hair_style="braids", top="#2d8f85",
                                  bottom="#7a3b2a", accent="#e8c13a", outfit="long", scarf=True, voice_id="elder_female",
                                  notes="Village elder and boat-builder. Dry humour.")),
        ("create_episode", dict(id="ep1", title="Dusk on the Shore", synopsis="Kabi learns the board's secret, chases Ogun, and they fight at dusk.")),
        # ---------------------------------------------------------------- ep1 / s1 dialogue only
        ("create_scene", dict(id="boatyard_dawn", name="Ima's boatyard", background="interior", time="dawn", letterbox=0, transition_in="fade", transition_dur=0.6)),
        ("add_prop", dict(scene="boatyard_dawn", kind="lamp", x=220)),
        ("add_prop", dict(scene="boatyard_dawn", kind="crate", x=1020, scale=0.9)),
        ("add_prop", dict(scene="boatyard_dawn", kind="barrel", x=1130, scale=0.9)),
        ("place", dict(scene="boatyard_dawn", char="kabi", x=420, facing="right")),
        ("place", dict(scene="boatyard_dawn", char="ima", x=800, facing="left")),
        ("camera", dict(scene="boatyard_dawn", kind="set", t=0, x=640, y=370, zoom=1.05)),
        ("caption", dict(scene="boatyard_dawn", text="IMA'S BOATYARD - DAWN", t=0.4, dur=2.4, style="location")),
        ("say", dict(scene="boatyard_dawn", char="ima", text="Your father carved that board from the first canoe.", t=1.4, emotion="neutral")),
        ("emote", dict(scene="boatyard_dawn", char="kabi", t=3.2, emotion="shocked")),
        ("say", dict(scene="boatyard_dawn", char="kabi", text="It's just a board, Mama Ima.", t=3.6, emotion="sad")),
        ("act", dict(scene="boatyard_dawn", char="ima", action="shrug", t=5.6)),
        ("say", dict(scene="boatyard_dawn", char="ima", text="Then why does it hum when the tide turns?", t=6.2, emotion="smirk")),
        ("camera", dict(scene="boatyard_dawn", kind="move", t=6.2, dur=1.6, zoom=1.35, x=520, y=390)),
        ("act", dict(scene="boatyard_dawn", char="kabi", action="nod", t=8.3)),
        ("say", dict(scene="boatyard_dawn", char="kabi", text="Then I'll ask the tide myself.", t=8.8, emotion="determined")),
        # ---------------------------------------------------------------- ep1 / s2 chase
        ("create_scene", dict(id="shore_chase", name="The chase", background="beach", time="golden", width=3000, transition_in="cut")),
        ("add_prop", dict(scene="shore_chase", kind="palm", x=300)),
        ("add_prop", dict(scene="shore_chase", kind="palm", x=1100, scale=1.1)),
        ("add_prop", dict(scene="shore_chase", kind="boat", x=1700, y=-95, scale=0.7)),
        ("add_prop", dict(scene="shore_chase", kind="palm", x=2300)),
        ("add_prop", dict(scene="shore_chase", kind="rock", x=2700, y=-60, scale=0.8)),
        ("place", dict(scene="shore_chase", char="ogun", x=700, facing="right")),
        ("place", dict(scene="shore_chase", char="kabi", x=180, facing="right")),
        ("camera", dict(scene="shore_chase", kind="set", t=0, x=500, y=380, zoom=0.95)),
        ("move", dict(scene="shore_chase", char="ogun", to_x=2700, t=0.8, dur=5.5, style="run")),
        ("move", dict(scene="shore_chase", char="kabi", to_x=2400, t=1.2, dur=5.5, style="run")),
        ("camera", dict(scene="shore_chase", kind="follow", t=0.8, char="kabi", zoom=1.05, blend=0.8)),
        ("fx", dict(scene="shore_chase", kind="speedlines", t=1.2, dur=4.5, dir="left", intensity=0.5)),
        ("say", dict(scene="shore_chase", char="kabi", text="Ogun! Wait!", t=3.0, dur=1.4, style="shout", emotion="shout")),
        ("emote", dict(scene="shore_chase", char="ogun", t=3.0, emotion="smirk")),
        # ---------------------------------------------------------------- ep1 / s3 duel at dusk
        ("create_scene", dict(id="duel_at_dusk", name="Duel at the shore", background="beach", time="dusk", letterbox=46, transition_in="fade", transition_out="fade", transition_dur=0.6)),
        ("add_prop", dict(scene="duel_at_dusk", kind="palm", x=110, scale=1.15)),
        ("add_prop", dict(scene="duel_at_dusk", kind="palm", x=1190, scale=1.0, flip=True)),
        ("add_prop", dict(scene="duel_at_dusk", kind="boat", x=1010, y=-95, scale=0.7)),
        ("add_prop", dict(scene="duel_at_dusk", kind="rock", x=560, y=-70, scale=0.65)),
        ("add_prop", dict(scene="duel_at_dusk", kind="grass", x=250, y=120, scale=1.1, layer="front")),
        ("place", dict(scene="duel_at_dusk", char="kabi", x=300, facing="right")),
        ("place", dict(scene="duel_at_dusk", char="ogun", x=1000, facing="left")),
        ("camera", dict(scene="duel_at_dusk", kind="set", t=0, x=640, y=370, zoom=0.92)),
        ("caption", dict(scene="duel_at_dusk", text="IBENO SHORE - DUSK", t=0.6, dur=2.6, style="location")),
        ("say", dict(scene="duel_at_dusk", char="ogun", text="You came alone, boy.", t=1.2, emotion="smirk")),
        ("say", dict(scene="duel_at_dusk", char="kabi", text="I came to finish this.", t=3.2, emotion="determined")),
        ("stance", dict(scene="duel_at_dusk", char="kabi", stance="fight", t=4.5)),
        ("stance", dict(scene="duel_at_dusk", char="ogun", stance="fight", t=4.5)),
        ("move", dict(scene="duel_at_dusk", char="kabi", to_x=520, t=4.6, dur=1.3)),
        ("move", dict(scene="duel_at_dusk", char="ogun", to_x=720, t=4.6, dur=1.3)),
        ("camera", dict(scene="duel_at_dusk", kind="frame", t=4.4, blend=1.0, pad=260)),
        ("strike", dict(scene="duel_at_dusk", attacker="ogun", defender="kabi", attack="thrust", t=6.2, result="dodge")),
        ("move", dict(scene="duel_at_dusk", char="kabi", to_x=530, t=6.95, dur=0.4)),
        ("strike", dict(scene="duel_at_dusk", attacker="kabi", defender="ogun", attack="slash_up", t=7.4, result="block")),
        ("move", dict(scene="duel_at_dusk", char="ogun", to_x=655, t=8.2, dur=0.5, style="slide")),
        ("strike", dict(scene="duel_at_dusk", attacker="ogun", defender="kabi", attack="hook", t=8.85, result="hit", power="medium")),
        ("move", dict(scene="duel_at_dusk", char="kabi", to_x=505, t=10.15, dur=0.5)),
        ("strike", dict(scene="duel_at_dusk", attacker="kabi", defender="ogun", attack="kick", t=10.65, result="hit", power="light")),
        ("camera", dict(scene="duel_at_dusk", kind="move", t=11.5, dur=1.0, zoom=1.35, x=660, y=400)),
        ("strike", dict(scene="duel_at_dusk", attacker="kabi", defender="ogun", attack="slash_down", t=12.2, result="hit", power="knockdown")),
        ("camera", dict(scene="duel_at_dusk", kind="move", t=13.9, dur=1.2, zoom=1.0, x=640, y=380)),
        ("act", dict(scene="duel_at_dusk", char="kabi", action="victory", t=14.4)),
        ("say", dict(scene="duel_at_dusk", char="kabi", text="Stay down.", t=15.0, emotion="determined")),
        ("fx", dict(scene="duel_at_dusk", kind="vignette", t=12.2, dur=2.5, intensity=0.5)),
        # ---------------------------------------------------------------- ep2
        ("create_episode", dict(id="ep2", title="Tide of Teeth", synopsis="The sea answers. A creature rises at the reef and Kabi must hold the line - with Ogun.")),
        ("create_scene", dict(id="reef_storm", name="The reef", episode="ep2", background="beach", time="storm", weather="rain", letterbox=40, transition_in="fade")),
        ("add_prop", dict(scene="reef_storm", kind="monster_silhouette", x=900, y=-210, scale=2.2)),
        ("add_prop", dict(scene="reef_storm", kind="rock", x=240, y=-60)),
        ("place", dict(scene="reef_storm", char="kabi", x=330, facing="right")),
        ("place", dict(scene="reef_storm", char="ima", x=170, facing="right")),
        ("camera", dict(scene="reef_storm", kind="set", t=0, x=640, y=360, zoom=1.0)),
        ("fx", dict(scene="reef_storm", kind="rain", t=0, dur=9, intensity=0.8)),
        ("emote", dict(scene="reef_storm", char="kabi", t=1.0, emotion="scared")),
        ("act", dict(scene="reef_storm", char="ima", action="point", t=1.4)),
        ("say", dict(scene="reef_storm", char="ima", text="It has your father's eyes.", t=2.0, emotion="scared")),
        ("camera", dict(scene="reef_storm", kind="move", t=3.0, dur=2.0, zoom=1.4, x=800, y=300)),
        ("fx", dict(scene="reef_storm", kind="flash", t=3.4, dur=0.2, intensity=0.7)),
        ("camera", dict(scene="reef_storm", kind="shake", t=3.4, dur=1.2, amp=14)),
        ("act", dict(scene="reef_storm", char="kabi", action="power_up", t=5.2)),
        ("say", dict(scene="reef_storm", char="kabi", text="Then let it see me.", t=6.6, emotion="determined")),
        ("create_scene", dict(id="rematch", name="Two against the sea", episode="ep2", background="beach", time="night", letterbox=46, transition_in="cut")),
        ("add_prop", dict(scene="rematch", kind="campfire", x=640, scale=0.9)),
        ("add_prop", dict(scene="rematch", kind="palm", x=140)),
        ("place", dict(scene="rematch", char="kabi", x=380, facing="right")),
        ("place", dict(scene="rematch", char="ogun", x=900, facing="left")),
        ("camera", dict(scene="rematch", kind="set", t=0, x=640, y=370, zoom=0.95)),
        ("stance", dict(scene="rematch", char="kabi", stance="fight", t=0.6)),
        ("stance", dict(scene="rematch", char="ogun", stance="fight", t=0.6)),
        ("say", dict(scene="rematch", char="ogun", text="Not yet. Not while it's watching.", t=1.0, emotion="determined")),
        ("move", dict(scene="rematch", char="kabi", to_x=550, t=2.6, dur=1.0)),
        ("move", dict(scene="rematch", char="ogun", to_x=720, t=2.6, dur=1.0)),
        ("camera", dict(scene="rematch", kind="frame", t=2.6, blend=0.8, pad=240)),
        ("strike", dict(scene="rematch", attacker="ogun", defender="kabi", attack="thrust", t=4.0, result="block")),
        ("strike", dict(scene="rematch", attacker="kabi", defender="ogun", attack="slash_down", t=5.4, result="block")),
        ("strike", dict(scene="rematch", attacker="ogun", defender="kabi", attack="hook", t=6.8, result="hit", power="light")),
        ("strike", dict(scene="rematch", attacker="kabi", defender="ogun", attack="kick", t=8.2, result="hit", power="medium")),
        ("create_scene", dict(id="aftermath", name="Embers", episode="ep2", background="beach", time="night", transition_in="fade", transition_out="fade")),
        ("add_prop", dict(scene="aftermath", kind="campfire", x=640, scale=1.0)),
        ("place", dict(scene="aftermath", char="kabi", x=500, facing="right", stance="tired")),
        ("place", dict(scene="aftermath", char="ima", x=800, facing="left")),
        ("camera", dict(scene="aftermath", kind="set", t=0, x=650, y=390, zoom=1.15)),
        ("say", dict(scene="aftermath", char="ima", text="The tide heard you.", t=1.0, emotion="happy")),
        ("say", dict(scene="aftermath", char="kabi", text="Will it come back?", t=3.0, emotion="tired")),
        ("say", dict(scene="aftermath", char="ima", text="It always comes back. That's why we build boats.", t=5.0, emotion="smirk")),
    ], src=src, label="build sample series")
    bad = [(n, m) for n, ok, m in r if not ok]
    if bad:
        raise RuntimeError("sample failed: " + "; ".join(f"{n}: {m}" for n, m in bad[:5]))
    store.snapshot(sid, "sample built")
    return s
