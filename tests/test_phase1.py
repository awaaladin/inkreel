import hashlib
import json
import shutil

import pytest

from inkreel import model as M
from inkreel import ops as O
from inkreel import render, sample
from inkreel.session import Session
from inkreel.store import Store, StoreError

SID = "ibeno_tides"


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "ws")


@pytest.fixture()
def built(store):
    sample.build(store)
    return store


def test_sample_structure(built):
    tx = built.reader()
    s = tx.read(f"series/{SID}/series.json")
    assert s["episodes"] == ["ep1", "ep2"]
    scenes = [x for e in s["episodes"] for x in tx.read(f"series/{SID}/episodes/{e}/episode.json")["scenes"]]
    assert len(scenes) == 6
    assert {"kabi", "ogun", "ima"} == {f[:-5] for f in tx.list(f"series/{SID}/libraries/characters")}
    for e in s["episodes"]:
        for scn in tx.read(f"series/{SID}/episodes/{e}/episode.json")["scenes"]:
            M.Scene.model_validate(tx.read(f"series/{SID}/episodes/{e}/scenes/{scn}.json"))


def test_events_have_ids_and_provenance(built):
    sc = built.reader().read(f"series/{SID}/episodes/ep1/scenes/duel_at_dusk.json")
    ids = []
    for a in sc["actors"].values():
        for tr in ("moves", "actions", "says"):
            ids += [(e["id"], e["src"], e["lock"]) for e in a[tr]]
    assert all(i and src == "import" and lock is False for i, src, lock in ids)
    assert len({i for i, _, _ in ids}) == len(ids)


@pytest.mark.parametrize("name,args,needle", [
    ("move", dict(scene="duel_at_dusk", char="kabi", to_x="abc", t=1), "must be a number"),
    ("move", dict(scene="nope", char="kabi", to_x=1, t=1), "no scene 'nope'"),
    ("create_character", dict(id="x", skin="blue-ish"), "hex colour"),
    ("act", dict(scene="duel_at_dusk", char="ima", action="slash_down", t=1), "not placed"),
    ("act", dict(scene="duel_at_dusk", char="kabi", action="flurble", t=1), "unknown action"),
    ("camera", dict(scene="duel_at_dusk", kind="zoom", t=1), "must be one of"),
    ("fx", dict(scene="duel_at_dusk", kind="sfx_text", t=1), "needs 'text'"),
    ("keyframes", dict(scene="duel_at_dusk", char="kabi", t=1, dur=1, keys=[{"t": 0, "pose": {"elbow": 3}}, {"t": 1}]), "unknown joint"),
    ("move", dict(scene="duel_at_dusk", char="kabi", to_x=float("nan"), t=1), "finite"),
])
def test_op_errors_explain_and_fix(built, name, args, needle):
    (n, ok, msg), = Session(built, SID).run([(name, args)])
    assert not ok and needle in msg
    # every error is addressed to the model with a way forward (hint) or a self-explanatory message
    assert len(msg) > 15


def test_failed_op_rolls_back_only_itself(built):
    s = Session(built, SID)
    before = built.reader().read(f"series/{SID}/episodes/ep1/scenes/duel_at_dusk.json")
    nmoves = len(before["actors"]["kabi"]["moves"])
    res = s.run([("move", dict(scene="duel_at_dusk", char="kabi", to_x=600, t=20)), ("move", dict(scene="duel_at_dusk", char="kabi", to_x="bad", t=21))])
    assert [ok for _, ok, _ in res] == [True, False]
    after = built.reader().read(f"series/{SID}/episodes/ep1/scenes/duel_at_dusk.json")
    assert len(after["actors"]["kabi"]["moves"]) == nmoves + 1


def test_strike_reach_warning(built):
    s = Session(built, SID)
    s.run([("create_scene", dict(id="far", episode="ep1")), ("place", dict(scene="far", char="kabi", x=100)), ("place", dict(scene="far", char="ogun", x=1000))], src="user")
    (_, ok, msg), = s.run([("strike", dict(scene="far", attacker="kabi", defender="ogun", attack="slash_down", t=1))])
    assert ok and "WARNING" in msg


def test_undo_redo_exact(built):
    rev0 = built.reader().read(f"series/{SID}/episodes/ep1/scenes/boatyard_dawn.json")
    s = Session(built, SID)
    s.run([("say", dict(scene="boatyard_dawn", char="kabi", text="Hello", t=12)), ("emote", dict(scene="boatyard_dawn", char="kabi", t=12, emotion="happy"))], label="two edits")
    assert built.reader().read(f"series/{SID}/episodes/ep1/scenes/boatyard_dawn.json") != rev0
    assert built.undo(SID)["label"] == "two edits"  # one turn = one undo step
    assert built.reader().read(f"series/{SID}/episodes/ep1/scenes/boatyard_dawn.json") == rev0
    assert built.redo(SID)["label"] == "two edits"
    assert any(e["text"] == "Hello" for e in built.reader().read(f"series/{SID}/episodes/ep1/scenes/boatyard_dawn.json")["actors"]["kabi"]["says"])
    built.undo(SID)
    s.run([("say", dict(scene="boatyard_dawn", char="kabi", text="New", t=13))])
    assert built.redo(SID) is None  # new work discards the redo stack


def test_undo_refuses_to_clobber_later_edit(built):
    s = Session(built, SID)
    s.run([("say", dict(scene="boatyard_dawn", char="kabi", text="A", t=12))], label="a")
    p = built.root / f"series/{SID}/episodes/ep1/scenes/boatyard_dawn.json"
    d = json.loads(p.read_text())
    d["name"] = "hand edited"
    p.write_text(json.dumps(d))  # user edits the file by hand
    with pytest.raises(StoreError, match="changed since"):
        built.undo(SID)
    assert json.loads(p.read_text())["name"] == "hand edited"


def test_snapshots_restore_diff(built):
    s = Session(built, SID)
    built.snapshot(SID, "before")
    s.run([("say", dict(scene="duel_at_dusk", char="ogun", text="New line", t=16)), ("delete", dict(kind="scene", id="rematch"))], src="user")
    d = built.diff_snapshots(SID, "before")
    assert "series/ibeno_tides/episodes/ep2/scenes/rematch.json" in d["removed"]
    assert len(d["scenes"]["duel_at_dusk"]["added"]) == 1
    built.restore(SID, "before")
    assert built.diff_snapshots(SID, "before") == {"added": [], "removed": [], "changed": [], "scenes": {}}
    built.undo(SID)  # restore itself is one undoable turn
    assert "series/ibeno_tides/episodes/ep2/scenes/rematch.json" in built.diff_snapshots(SID, "before")["removed"]


def test_locks_and_user_events_protected_from_ai(built):
    s = Session(built, SID)
    s.run([("say", dict(scene="duel_at_dusk", char="kabi", text="My own line", t=17))], src="user")
    sc = built.reader().read(f"series/{SID}/episodes/ep1/scenes/duel_at_dusk.json")
    mine = [e for e in sc["actors"]["kabi"]["says"] if e["text"] == "My own line"][0]
    assert mine["src"] == "user"
    # AI cannot delete or edit it
    (_, ok, msg), = s.run([("delete_event", dict(scene="duel_at_dusk", id=mine["id"]))], src="ai")
    assert not ok and "authored by the user" in msg
    (_, ok, msg), = s.run([("update_event", dict(scene="duel_at_dusk", id=mine["id"], fields={"text": "rewritten"}))], src="ai")
    assert not ok
    # remove_events skips it
    (_, ok, msg), = s.run([("remove_events", dict(scene="duel_at_dusk", what="says"))], src="ai")
    assert ok and "kept 1" in msg
    sc = built.reader().read(f"series/{SID}/episodes/ep1/scenes/duel_at_dusk.json")
    assert [e["text"] for e in sc["actors"]["kabi"]["says"]] == ["My own line"]
    # AI cannot lock/unlock; user can lock an AI/import event, then AI can't touch it
    (_, ok, _), = s.run([("set_lock", dict(scene="duel_at_dusk", ids=[mine["id"]], lock=False))], src="ai")
    assert not ok
    ogun_say = sc["actors"]["ogun"]["actions"][0]["id"]
    s.run([("set_lock", dict(scene="duel_at_dusk", ids=[ogun_say], lock=True))], src="user")
    (_, ok, msg), = s.run([("delete_event", dict(scene="duel_at_dusk", id=ogun_say))], src="ai")
    assert not ok and "locked" in msg
    # user editing marks provenance
    s.run([("update_event", dict(scene="duel_at_dusk", id=ogun_say, fields={"intensity": 1.3}))], src="user")
    sc = built.reader().read(f"series/{SID}/episodes/ep1/scenes/duel_at_dusk.json")
    e = [x for x in sc["actors"]["ogun"]["actions"] if x["id"] == ogun_say][0]
    assert e["intensity"] == 1.3 and e["src"] == "user" and e["lock"] is True


def test_series_level_character_and_action_reuse(built):
    s = Session(built, SID)
    res = s.run([("define_action", dict(name="tide_slam", dur=1.0, hit=0.5, reach=200, trail="weapon",
                                        keys=[{"t": 0, "pose": {}}, {"t": 0.5, "pose": {"aF": 120}, "ease": "snap"}, {"t": 1, "pose": {}}])),
                 ("act", dict(scene="duel_at_dusk", char="kabi", action="tide_slam", t=18)),
                 ("act", dict(scene="reef_storm", char="kabi", action="tide_slam", t=1))])
    assert all(ok for _, ok, _ in res), res
    assert "tide_slam" in render.compile_bundle(built, SID)["actions"]


def test_bundle_scopes(built):
    assert len(render.compile_bundle(built, SID)["scenes"]) == 6
    assert [x["id"] for x in render.compile_bundle(built, SID, "ep2")["scenes"]] == ["reef_storm", "rematch", "aftermath"]
    assert len(render.compile_bundle(built, SID, scene="shore_chase")["scenes"]) == 1
    with pytest.raises(StoreError):
        render.compile_bundle(built, SID, "ep9")


def test_corrupt_file_has_actionable_error(built):
    p = built.root / f"series/{SID}/episodes/ep1/scenes/boatyard_dawn.json"
    p.write_text("{ not json")
    (_, ok, msg), = Session(built, SID).run([("say", dict(scene="boatyard_dawn", char="kabi", text="x", t=1))])
    assert not ok and "corrupt" in msg and "snapshot" in msg


@pytest.mark.skipif(not render.find_node(), reason="node not installed")
def test_still_is_deterministic(built, tmp_path):
    b = render.compile_bundle(built, SID, scene="duel_at_dusk")
    be = render.default_backend()
    h = []
    for i in range(2):
        out = be.still(b, 6.5, tmp_path / f"s{i}.png")
        h.append(hashlib.sha256(out.read_bytes()).hexdigest())
    assert h[0] == h[1]


def test_api_roundtrip(built):
    from fastapi.testclient import TestClient
    from inkreel.api import create_app
    c = TestClient(create_app(built))
    j = c.get(f"/api/series/{SID}").json()
    assert [e["id"] for e in j["episodes"]] == ["ep1", "ep2"] and j["episodes"][0]["duration"] > 20
    r = c.post(f"/api/series/{SID}/ops", json={"ops": [{"name": "say", "args": {"scene": "boatyard_dawn", "char": "kabi", "text": "api", "t": 14}}], "src": "user"}).json()
    assert r["results"][0]["ok"]
    assert c.get(f"/api/series/{SID}/bundle", params={"scene": "boatyard_dawn"}).json()["bundle"]["scenes"][0]["id"] == "boatyard_dawn"
    assert c.post(f"/api/series/{SID}/undo").json()["undone"]["label"]
    assert c.get("/api/series/nope").status_code == 404
