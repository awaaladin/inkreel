"""Picture tracing, tested on a real image file drawn with OpenCV (a test fixture; the product traces the user's own pictures)."""
import math

import cv2
import numpy as np
import pytest

from inkreel import model as M
from inkreel import trace

# joint positions (x, y) in the fixture picture, standing in profile facing right
JOINTS = {
    "headTop": (200, 40), "neck": (200, 110), "shoulder": (200, 140), "hip": (200, 300),
    "elbowF": (215, 215), "handF": (225, 285), "elbowB": (185, 215), "handB": (178, 285),
    "kneeF": (215, 400), "ankleF": (215, 500), "toeF": (255, 505),
    "kneeB": (188, 400), "ankleB": (185, 500), "toeB": (225, 505),
}


@pytest.fixture()
def picture(tmp_path):
    img = np.full((560, 400, 3), 245, np.uint8)
    skin, shirt, pants = (90, 140, 200), (60, 90, 220), (90, 60, 40)   # BGR
    cv2.circle(img, (200, 75), 36, skin, -1)
    cv2.line(img, (200, 140), (200, 300), shirt, 56)
    for a, b, c, w in [("shoulder", "elbowB", shirt, 22), ("elbowB", "handB", skin, 18), ("shoulder", "elbowF", shirt, 22), ("elbowF", "handF", skin, 18),
                       ("hip", "kneeB", pants, 30), ("kneeB", "ankleB", pants, 24), ("hip", "kneeF", pants, 30), ("kneeF", "ankleF", pants, 24)]:
        cv2.line(img, JOINTS[a], JOINTS[b], c, w)
    cv2.line(img, JOINTS["ankleF"], JOINTS["toeF"], (30, 30, 30), 18)
    cv2.line(img, JOINTS["ankleB"], JOINTS["toeB"], (30, 30, 30), 18)
    cv2.circle(img, (215, 70), 5, (20, 20, 20), -1)   # an eye
    p = tmp_path / "fig.png"
    cv2.imwrite(str(p), img)
    return p


def layout(**kw):
    return {"name": "Fig", "height_px": 300, "facing": "right", "joints": {k: list(v) for k, v in JOINTS.items()},
            "face": {"anchor": [222, 90], "w": 22}, **kw}


def test_trace_builds_rigged_parts(picture):
    rec = trace.build(picture, layout())
    assert rec["rig_type"] == "traced" and rec["height"] == 300
    bones = {p["bone"] for p in rec["parts"]}
    assert {"head", "torso", "armF_up", "armF_lo", "legF_up", "legF_lo", "footF", "legB_up", "armB_up"} <= bones
    rings = sum(len(sh["rings"]) for p in rec["parts"] for sh in p["shapes"])
    assert rings > 12
    for p in rec["parts"]:
        for sh in p["shapes"]:
            assert sh["fill"].startswith("#") and len(sh["fill"]) == 7
            assert all(len(r) >= 3 for r in sh["rings"])
    rest = rec["rig"]["rest"]
    assert abs(rest["legF_up"]) < 12 and abs(rest["torso"]) < 3          # standing straight
    assert 75 < rest["footF"] < 105                                       # foot points forward
    assert rec["rig"]["torso"] == pytest.approx(160 * 300 / 465, rel=0.02)  # bone length in studio px, from the picture
    assert rec["rig"]["face"]["w"] > 0


def test_traced_record_is_a_valid_character(picture):
    rec = trace.build(picture, layout())
    ch = M.Character.model_validate({"id": "fig", "name": "Fig", **rec})
    assert ch.rig_type == "traced" and ch.parts


def test_parts_cover_the_character_without_gaps(picture):
    """Every foreground pixel belongs to exactly one bone, so nothing visible is lost when the character is cut into parts."""
    img = trace._load(picture, False)
    mask = trace._foreground(img)
    J = trace._joints(layout(), False, img.shape[1])
    bone_of = trace.assign_bones(mask, J)
    assert (bone_of[mask] >= 0).all() and (bone_of[~mask] == -1).all()
    # head pixels are the head, shin pixels are the shin
    assert bone_of[75, 200] == trace.DRAW_ORDER.index("head")
    assert bone_of[450, 215] in (trace.DRAW_ORDER.index("legF_lo"), trace.DRAW_ORDER.index("legB_lo"))


def test_left_facing_picture_is_mirrored(picture, tmp_path):
    flipped = cv2.flip(cv2.imread(str(picture)), 1)
    p = tmp_path / "left.png"
    cv2.imwrite(str(p), flipped)
    L = layout(facing="left")
    w = flipped.shape[1]
    L["joints"] = {k: [w - 1 - x, y] for k, (x, y) in JOINTS.items()}
    L["face"] = {"anchor": [w - 1 - 222, 90], "w": 22}
    a, b = trace.build(picture, layout()), trace.build(p, L)
    assert a["rig"]["rest"]["footF"] == pytest.approx(b["rig"]["rest"]["footF"], abs=3)
    assert math.isclose(a["rig"]["thigh"], b["rig"]["thigh"], rel_tol=0.03)


def test_missing_joint_explains_itself(picture):
    L = layout()
    del L["joints"]["kneeB"]
    with pytest.raises(trace.TraceError, match="kneeB"):
        trace.build(picture, L)


def test_unreadable_image_explains_itself(tmp_path):
    with pytest.raises(trace.TraceError, match="cannot read"):
        trace.build(tmp_path / "nope.png", layout())


def test_grid_and_preview_images_are_written(picture, tmp_path):
    g = trace.grid(picture, tmp_path / "g.png")
    p = trace.preview(picture, layout(), tmp_path / "p.png")
    for f in (g, p):
        im = cv2.imread(str(f))
        assert im is not None and im.shape[:2] == (560, 400)
