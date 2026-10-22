"""A built-in demo (no API key needed): a short beach duel that exercises characters, dialogue, camera, fights and fx."""
from __future__ import annotations


def demo_ops(prefix="demo_"):
    h, r, sc = prefix + "hero", prefix + "rival", prefix + "duel"
    ops = [
        ("create_character", dict(id=h, name="Kabi", height=300, skin="#6b4228", hair="#120c0a", hair_style="locs", top="#d9822b",
                                   bottom="#2b3a55", accent="#2d8f85", outfit="tee", weapon="greatblade", headband=True)),
        ("create_character", dict(id=r, name="Ogun", height=335, build="strong", skin="#4a2e1e", hair="#0c0808", hair_style="bald",
                                   top="#5a2f4a", bottom="#3b3b3b", accent="#c9a14a", outfit="tank", weapon="staff", beard=True)),
        ("create_scene", dict(id=sc, name="Duel at the shore", background="beach", time="dusk", letterbox=46, transition_in="fade",
                              transition_out="fade", transition_dur=0.6)),
        ("add_prop", dict(scene=sc, kind="palm", x=110, scale=1.15)),
        ("add_prop", dict(scene=sc, kind="palm", x=1190, scale=1.0, flip=True)),
        ("add_prop", dict(scene=sc, kind="boat", x=1010, y=-95, scale=0.7)),
        ("add_prop", dict(scene=sc, kind="rock", x=560, y=-70, scale=0.65)),
        ("add_prop", dict(scene=sc, kind="grass", x=250, y=120, scale=1.1, layer="front")),
        ("place", dict(scene=sc, char=h, x=300, facing="right")),
        ("place", dict(scene=sc, char=r, x=1000, facing="left")),
        ("camera", dict(scene=sc, kind="set", t=0, x=640, y=370, zoom=0.92)),
        ("caption", dict(scene=sc, text="IBENO SHORE - DUSK", t=0.6, dur=2.6, style="location")),
        ("say", dict(scene=sc, char=r, text="You came alone, boy.", t=1.2, emotion="smirk")),
        ("say", dict(scene=sc, char=h, text="I came to finish this.", t=3.2, emotion="determined")),
        ("stance", dict(scene=sc, char=h, stance="fight", t=4.5)),
        ("stance", dict(scene=sc, char=r, stance="fight", t=4.5)),
        ("move", dict(scene=sc, char=h, to_x=520, t=4.6, dur=1.3)),
        ("move", dict(scene=sc, char=r, to_x=720, t=4.6, dur=1.3)),
        ("camera", dict(scene=sc, kind="frame", t=4.4, blend=1.0, pad=260)),
        ("strike", dict(scene=sc, attacker=r, defender=h, attack="thrust", t=6.2, result="dodge")),
        ("move", dict(scene=sc, char=h, to_x=530, t=6.95, dur=0.4)),
        ("strike", dict(scene=sc, attacker=h, defender=r, attack="slash_up", t=7.4, result="block")),
        ("move", dict(scene=sc, char=r, to_x=655, t=8.2, dur=0.5, style="slide")),
        ("strike", dict(scene=sc, attacker=r, defender=h, attack="hook", t=8.85, result="hit", power="medium")),
        ("move", dict(scene=sc, char=h, to_x=505, t=10.15, dur=0.5)),
        ("strike", dict(scene=sc, attacker=h, defender=r, attack="kick", t=10.65, result="hit", power="light")),
        ("camera", dict(scene=sc, kind="move", t=11.5, dur=1.0, zoom=1.35, x=660, y=400)),
        ("strike", dict(scene=sc, attacker=h, defender=r, attack="slash_down", t=12.2, result="hit", power="knockdown")),
        ("camera", dict(scene=sc, kind="move", t=13.9, dur=1.2, zoom=1.0, x=640, y=380)),
        ("act", dict(scene=sc, char=h, action="victory", t=14.4)),
        ("say", dict(scene=sc, char=h, text="Stay down.", t=15.0, emotion="determined")),
        ("fx", dict(scene=sc, kind="vignette", t=12.2, dur=2.5, intensity=0.5)),
    ]
    return ops
