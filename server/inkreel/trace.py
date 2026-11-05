"""Turn a character picture into a rigged, animatable vector character - by tracing, not generating.

Workflow (Claude Code does the looking, this does the cutting):
  1. `inkreel trace-grid picture.png`            -> picture_grid.png with labelled coordinates, so joint positions can be read off precisely
  2. write a layout JSON with the joint positions (pixels in the picture)
  3. `inkreel trace-preview picture.png layout.json` -> picture_preview.png: joints, bones and the body-part split drawn over the picture
  4. `inkreel trace <series> <char> picture.png layout.json` -> traced vector parts saved as a series character

How it works: background removal (alpha channel, or the border colour), colour quantisation (k-means in Lab), each foreground pixel is
assigned to the nearest bone (head, torso, upper/lower arm, thigh/shin/foot; front and back), then every colour region of every part is
traced to a polygon with OpenCV contours. Parts are stored in bone-local coordinates so the existing skeleton (walk cycles, actions,
pose keys, lip-sync) drives them, and each part sits at a depth for the orbit view.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError as e:  # pragma: no cover
    raise ImportError("tracing needs OpenCV: pip install opencv-python-headless") from e

# bone name -> (joint a, joint b). Angles use the solver's convention (degrees from straight down, + toward facing).
BONES = {
    "armB_up": ("shoulder", "elbowB"), "armB_lo": ("elbowB", "handB"),
    "legB_up": ("hip", "kneeB"), "legB_lo": ("kneeB", "ankleB"), "footB": ("ankleB", "toeB"),
    "torso": ("hip", "shoulder"),
    "legF_up": ("hip", "kneeF"), "legF_lo": ("kneeF", "ankleF"), "footF": ("ankleF", "toeF"),
    "head": ("neck", "headTop"),
    "armF_up": ("shoulder", "elbowF"), "armF_lo": ("elbowF", "handF"),
}
DRAW_ORDER = list(BONES)  # back limbs first, head and front arm last
# fraction of the character height by which each bone layer sits toward the viewer (matches the orbit view's depth layers)
DEPTH = {"armB_up": -0.09, "armB_lo": -0.09, "legB_up": -0.09, "legB_lo": -0.09, "footB": -0.09, "torso": 0.0,
         "legF_up": 0.05, "legF_lo": 0.05, "footF": 0.05, "head": 0.025, "armF_up": 0.09, "armF_lo": 0.09}
# which solver joint a bone hangs from, and which angle drives it
REQUIRED = ["headTop", "neck", "shoulder", "hip", "elbowF", "handF", "kneeF", "ankleF", "toeF", "elbowB", "handB", "kneeB", "ankleB", "toeB"]


class TraceError(Exception):
    def __init__(self, msg: str, hint: str = ""):
        super().__init__(msg)
        self.hint = hint

    def __str__(self):
        return f"{super().__str__()} Hint: {self.hint}" if self.hint else super().__str__()


def _load(path: str | Path, flip: bool) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise TraceError(f"cannot read image {path}", "use a PNG or JPG file")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    if flip:
        img = img[:, ::-1].copy()
    return img


def grid(path: str | Path, out: str | Path, step: int = 50) -> Path:
    """Copy of the picture with labelled coordinate lines, so joint positions can be read accurately."""
    img = _load(path, False)
    bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    h, w = bgr.shape[:2]
    for x in range(0, w, step):
        cv2.line(bgr, (x, 0), (x, h), (0, 0, 255) if x % (step * 2) == 0 else (120, 120, 255), 1)
        if x % (step * 2) == 0:
            cv2.putText(bgr, str(x), (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 200), 1, cv2.LINE_AA)
    for y in range(0, h, step):
        cv2.line(bgr, (0, y), (w, y), (255, 0, 0) if y % (step * 2) == 0 else (255, 140, 140), 1)
        if y % (step * 2) == 0:
            cv2.putText(bgr, str(y), (2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 0, 0), 1, cv2.LINE_AA)
    out = Path(out)
    cv2.imwrite(str(out), bgr)
    return out


def _foreground(img: np.ndarray) -> np.ndarray:
    """Boolean mask of the character: the alpha channel if the picture has one, otherwise everything unlike the border colour."""
    alpha = img[:, :, 3]
    if alpha.min() < 250:
        mask = alpha > 127
    else:
        bgr = img[:, :, :3].astype(np.float32)
        h, w = bgr.shape[:2]
        border = np.concatenate([bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]])
        bg = np.median(border, axis=0)
        dist = np.linalg.norm(bgr - bg, axis=2)
        t, _ = cv2.threshold(np.clip(dist, 0, 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        mask = dist > max(18.0, min(t * 0.6, 60.0))
    m = mask.astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros_like(m)
    big = stats[1:, cv2.CC_STAT_AREA].max() if n > 1 else 0
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= max(30, big * 0.02):
            keep[lab == i] = 1
    # anything not connected to the picture's edge is inside the character (a white shirt on a white page, eyes, enclosed gaps)
    inv = (1 - keep).astype(np.uint8)
    n2, lab2, st2, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    h, w = keep.shape
    edge_labels = set(np.unique(np.concatenate([lab2[0], lab2[-1], lab2[:, 0], lab2[:, w - 1]])).tolist())
    for i in range(1, n2):
        if i not in edge_labels:
            keep[lab2 == i] = 1
    return keep.astype(bool)


def _seg_dist(px: np.ndarray, py: np.ndarray, a: tuple[float, float], b: tuple[float, float]) -> np.ndarray:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy or 1e-9
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _joints(layout: dict, flip: bool, width: int) -> dict[str, tuple[float, float]]:
    j = {}
    for k in REQUIRED:
        if k not in layout.get("joints", {}):
            raise TraceError(f"layout is missing joint '{k}'", f"required joints: {REQUIRED}")
        x, y = layout["joints"][k]
        j[k] = (float(width - 1 - x) if flip else float(x), float(y))
    return j


def assign_bones(mask: np.ndarray, J: dict, weights: dict | None = None) -> np.ndarray:
    """Per-pixel bone index (into DRAW_ORDER); -1 outside the character. Nearest bone wins, scaled by a per-bone width so the torso and head
    are not swallowed by thin limbs."""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    px, py = xs.astype(np.float32), ys.astype(np.float32)
    height = max(1.0, max(J[k][1] for k in ("toeF", "toeB", "ankleF", "ankleB")) - J["headTop"][1])
    wt = {"torso": 0.115, "head": 0.1, "armF_up": 0.05, "armF_lo": 0.045, "armB_up": 0.05, "armB_lo": 0.045,
          "legF_up": 0.075, "legF_lo": 0.06, "legB_up": 0.075, "legB_lo": 0.06, "footF": 0.05, "footB": 0.05}
    if weights:
        wt.update(weights)
    best = np.full(px.shape, 1e9, np.float32)
    idx = np.full(px.shape, -1, np.int32)
    for i, name in enumerate(DRAW_ORDER):
        a, b = BONES[name]
        d = _seg_dist(px, py, J[a], J[b]) / (wt[name] * height)
        if name == "head":  # the head is a disc around its centre, not a thin segment
            cx, cy = (J["neck"][0] + J["headTop"][0]) / 2, (J["neck"][1] + J["headTop"][1]) / 2
            r = math.hypot(J["headTop"][0] - J["neck"][0], J["headTop"][1] - J["neck"][1]) / 2 * 1.15
            d = np.minimum(d, np.hypot(px - cx, py - cy) / max(r, 1.0) * 0.6)
        better = d < best
        best[better] = d[better]
        idx[better] = i
    out = np.full((h, w), -1, np.int32)
    out[ys, xs] = idx
    return out


def _angle_down(a: tuple[float, float], b: tuple[float, float]) -> float:
    """degrees from straight down, + toward +x (the solver's convention for limbs)."""
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))


def _angle_up(a: tuple[float, float], b: tuple[float, float]) -> float:
    """degrees from straight up, + toward +x (torso and head)."""
    return math.degrees(math.atan2(b[0] - a[0], -(b[1] - a[1])))


def _hex(bgr) -> str:
    return "#%02x%02x%02x" % (int(bgr[2]), int(bgr[1]), int(bgr[0]))


def _darker(hexcol: str, k: float) -> str:
    r, g, b = (int(hexcol[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))


def _rings(mask: np.ndarray, eps: float, min_area: float) -> list[list[list[float]]]:
    cs, hier = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    rings = []
    for c in cs:
        if abs(cv2.contourArea(c)) < min_area:
            continue
        ap = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
        if len(ap) >= 3:
            rings.append(ap.astype(float).tolist())
    return rings


def build(image: str | Path, layout: dict, colors: int = 10, detail: float = 1.0) -> dict:
    """-> the character record (without id/name) with traced vector parts."""
    flip = layout.get("facing", "right") == "left"
    img = _load(image, flip)
    h, w = img.shape[:2]
    J = _joints(layout, flip, w)
    mask = _foreground(img)
    if mask.sum() < 200:
        raise TraceError("could not find the character in the picture", "use a picture with a plain background or a transparent PNG")
    bone_of = assign_bones(mask, J, layout.get("weights"))

    # colour regions (k-means in Lab on the foreground only)
    bgr = cv2.medianBlur(img[:, :, :3], 5)          # flatten tiny speckle so colour regions come out as clean shapes
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    ys, xs = np.nonzero(mask)
    samples = lab[ys, xs]
    if len(samples) > 60000:
        samples = samples[np.random.default_rng(1).choice(len(samples), 60000, replace=False)]
    k = max(2, min(int(layout.get("colors", colors)), 24))
    cv2.setRNGSeed(7)
    _, _, centers = cv2.kmeans(samples, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3, cv2.KMEANS_PP_CENTERS)
    d = np.linalg.norm(lab[ys, xs][:, None, :] - centers[None, :, :], axis=2)
    label = np.full((h, w), -1, np.int32)
    label[ys, xs] = d.argmin(axis=1)
    centers_bgr = cv2.cvtColor(centers.reshape(1, -1, 3).astype(np.uint8), cv2.COLOR_LAB2BGR).reshape(-1, 3)

    height_px = float(layout.get("height_px", 300))
    foot_y = max(J[k][1] for k in ("toeF", "toeB", "ankleF", "ankleB"))
    px_h = max(1.0, foot_y - J["headTop"][1])
    s = height_px / px_h
    eps = max(0.6, 0.9 * detail / max(s, 0.2))        # simplification tolerance in picture pixels
    min_area = max(6.0, 10.0 / max(s * s, 0.04))

    head_c = ((J["neck"][0] + J["headTop"][0]) / 2, (J["neck"][1] + J["headTop"][1]) / 2)
    origins = {name: J[BONES[name][0]] for name in BONES}
    origins["head"] = head_c            # the solver hangs the head from its centre
    rest = {}
    for name, (a, b) in BONES.items():
        rest[name] = round(_angle_up(J[a], J[b]) if name in ("torso", "head") else _angle_down(J[a], J[b]), 2)
    parts = []
    for bi, name in enumerate(DRAW_ORDER):
        pm = bone_of == bi
        if pm.sum() < 8:
            continue
        ox, oy = origins[name]
        shapes = []
        ksz = max(1, int(round(1.6 / max(s, 0.05))))             # features thinner than ~1.6 studio px vanish (they would only be noise)
        kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksz, ksz))
        for ci in range(k):
            cm = pm & (label == ci)
            if cm.sum() < 6:
                continue
            cm = cv2.morphologyEx(cm.astype(np.uint8), cv2.MORPH_OPEN, kern).astype(bool)
            if cm.sum() < 6:
                continue
            rings = _rings(cm, eps, min_area)
            if not rings:
                continue
            shapes.append({"fill": _hex(centers_bgr[ci]), "area": int(cm.sum()),
                           "rings": [[[round((x - ox) * s, 1), round((y - oy) * s, 1)] for x, y in r] for r in rings]})
        # big regions first, small details (eyes, lines) on top
        shapes.sort(key=lambda sh: -sh["area"])
        for sh in shapes:
            del sh["area"]
        sil = cv2.morphologyEx(pm.astype(np.uint8), cv2.MORPH_CLOSE, kern)
        outline = [[[round((x - ox) * s, 1), round((y - oy) * s, 1)] for x, y in r] for r in _rings(sil.astype(bool), eps * 1.3, min_area * 2)]
        if shapes and outline:   # solid base in the part's main colour, so removing tiny details never leaves holes
            shapes.insert(0, {"fill": shapes[0]["fill"], "rings": outline})
        parts.append({"bone": name, "z": DEPTH[name], "shapes": shapes, "outline": outline})

    # A side view only shows the near arm and leg. With layout "mirror_back": true the hidden far limbs are copies of the visible ones,
    # a little darker, so the walk has two arms and two legs (the back-limb joints in the layout should equal the front ones).
    if layout.get("mirror_back"):
        have = {p["bone"]: p for p in parts}
        twin = {"armB_up": "armF_up", "armB_lo": "armF_lo", "legB_up": "legF_up", "legB_lo": "legF_lo", "footB": "footF"}
        for back, front in twin.items():
            if back not in have and front in have:
                src = have[front]
                parts.append({"bone": back, "z": DEPTH[back], "outline": src.get("outline", []),
                              "shapes": [{"fill": _darker(sh["fill"], 0.78), "rings": sh["rings"]} for sh in src["shapes"]]})
        parts.sort(key=lambda p: DRAW_ORDER.index(p["bone"]))

    # rig lengths in studio pixels, measured from the picture's own proportions (the solver uses these instead of its defaults)
    def L(a, b):
        return round(math.hypot(J[a][0] - J[b][0], J[a][1] - J[b][1]) * s, 2)
    head_r = L("neck", "headTop") / 2
    sh_to_head = math.hypot(J["shoulder"][0] - head_c[0], J["shoulder"][1] - head_c[1]) * s
    rig = {
        "torso": L("hip", "shoulder"), "neck": round(max(1.0, sh_to_head - 0.95 * head_r), 2),
        "headR": round(head_r, 2),
        "up": round((L("shoulder", "elbowF") + L("shoulder", "elbowB")) / 2, 2), "fore": round((L("elbowF", "handF") + L("elbowB", "handB")) / 2, 2),
        "thigh": round((L("hip", "kneeF") + L("hip", "kneeB")) / 2, 2), "shin": round((L("kneeF", "ankleF") + L("kneeB", "ankleB")) / 2, 2),
        "foot": round((L("ankleF", "toeF") + L("ankleB", "toeB")) / 2, 2),
        "rest": rest,
    }
    face = layout.get("face")
    if face:
        fx = float(width_flip(face["anchor"][0], w, flip))
        rig["face"] = {"x": round((fx - head_c[0]) * s, 1), "y": round((face["anchor"][1] - head_c[1]) * s, 1), "w": round(float(face.get("w", 30)) * s, 1)}
    return {"rig_type": "traced", "height": round(height_px, 1), "rig": rig, "parts": parts, "views": ["side"]}


def width_flip(x: float, w: int, flip: bool) -> float:
    return (w - 1 - x) if flip else x


def preview(image: str | Path, layout: dict, out: str | Path) -> Path:
    """The picture with the foreground tinted by bone and the joints/bones drawn on top, to check the layout before tracing."""
    flip = layout.get("facing", "right") == "left"
    img = _load(image, flip)
    h, w = img.shape[:2]
    J = _joints(layout, flip, w)
    mask = _foreground(img)
    bone_of = assign_bones(mask, J, layout.get("weights"))
    bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    rng = np.random.default_rng(3)
    pal = {n: tuple(int(v) for v in rng.integers(60, 255, 3)) for n in DRAW_ORDER}
    tint = bgr.copy()
    for i, n in enumerate(DRAW_ORDER):
        tint[bone_of == i] = pal[n]
    bgr = cv2.addWeighted(bgr, 0.45, tint, 0.55, 0)
    for n, (a, b) in BONES.items():
        cv2.line(bgr, tuple(int(v) for v in J[a]), tuple(int(v) for v in J[b]), (0, 0, 0), 3)
    for k, (x, y) in J.items():
        cv2.circle(bgr, (int(x), int(y)), 5, (0, 0, 255), -1)
        cv2.putText(bgr, k, (int(x) + 6, int(y) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(bgr, k, (int(x) + 6, int(y) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)
    out = Path(out)
    cv2.imwrite(str(out), bgr)
    return out


# --------------------------------------------------------------------------- textured parts: the picture's own pixels, cut at the joints
DEFAULT_WEIGHTS = {"torso": 0.115, "head": 0.1, "armF_up": 0.05, "armF_lo": 0.045, "armB_up": 0.05, "armB_lo": 0.045,
                   "legF_up": 0.075, "legF_lo": 0.06, "legB_up": 0.075, "legB_lo": 0.06, "footF": 0.05, "footB": 0.05}
ARM_BONES = ("armF_up", "armF_lo", "armB_up", "armB_lo")


def sprites(image: str | Path, layout: dict, out_dir: str | Path, url_prefix: str, scale: float = 0.45) -> list[dict]:
    """Cut every body part out of the picture as a transparent PNG. Returns `parts` records with a `sprite` instead of vector shapes.

    * each part = the pixels of its bone, plus a round cap at its joint (so a bent knee or elbow shows no wedge-shaped gap);
    * the near arm hangs in front of the body in a side view, so it is painted out of the torso/leg pictures (inpainting) and the body is whole when the arm swings away;
    * with layout "mirror_back" the hidden far arm and leg are darker copies of the near ones.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    flip = layout.get("facing", "right") == "left"
    img = _load(image, flip)
    h, w = img.shape[:2]
    J = _joints(layout, flip, w)
    fg = _foreground(img)
    if fg.sum() < 200:
        raise TraceError("could not find the character in the picture", "use a picture with a plain background or a transparent PNG")
    fg = cv2.erode(fg.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))).astype(bool)   # drop the light keyline around the figure
    wt = dict(DEFAULT_WEIGHTS)
    wt.update(layout.get("weights") or {})
    bone_of = assign_bones(fg, J, {k: v for k, v in wt.items()})
    height = max(1.0, max(J[k][1] for k in ("toeF", "toeB", "ankleF", "ankleB")) - J["headTop"][1])
    head_c = ((J["neck"][0] + J["headTop"][0]) / 2, (J["neck"][1] + J["headTop"][1]) / 2)
    origin = {n: J[BONES[n][0]] for n in BONES}
    origin["head"] = head_c
    idx = {n: i for i, n in enumerate(DRAW_ORDER)}
    bgr = img[:, :, :3].copy()

    # the near arm out of the picture: inpaint where it lay over the body
    arm_px = np.zeros((h, w), bool)
    for n in ("armF_up", "armF_lo"):
        arm_px |= bone_of == idx[n]
    plate = bgr.copy()
    if arm_px.any():
        grown = cv2.dilate(arm_px.astype(np.uint8), np.ones((5, 5), np.uint8))
        plate = cv2.inpaint(bgr, grown, 9, cv2.INPAINT_TELEA)

    def row_span_fill(pm: np.ndarray) -> np.ndarray:
        """arm pixels that lie between this part's own left and right edge on the same row (the arm was in front of it)."""
        out = np.zeros_like(pm)
        ys = np.nonzero(pm.any(axis=1))[0]
        for y in ys:
            xs = np.nonzero(pm[y])[0]
            out[y, xs.min():xs.max() + 1] = True
        return out & arm_px

    f = scale
    kk = float(layout.get("height_px", 300)) / height / f      # studio px per sprite px
    parts = []
    for name in DRAW_ORDER:
        pm = bone_of == idx[name]
        if pm.sum() < 8 and not (layout.get("mirror_back") and name.endswith("B")):
            continue
        if name.endswith("B") and layout.get("mirror_back") and pm.sum() < 50:
            continue                                   # made later from the near twin
        a_name = BONES[name][0]
        ox0, oy0 = origin[name]
        rad = wt[name] * height * (1.1 if name != "head" else 0.0)
        cap = np.zeros((h, w), np.uint8)
        if rad > 0:
            cv2.circle(cap, (int(ox0), int(oy0)), int(rad), 1, -1)
        grow = cv2.dilate(pm.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))).astype(bool)
        m = (pm | grow | cap.astype(bool)) & fg
        src = bgr
        if name not in ARM_BONES:
            m |= row_span_fill(pm) & fg
            src = plate
        if m.sum() < 8:
            continue
        parts.append(_cut(name, m, src, f, J, origin, out_dir, url_prefix, kk))

    if layout.get("mirror_back"):
        have = {p["bone"]: p for p in parts}
        twin = {"armB_up": "armF_up", "armB_lo": "armF_lo", "legB_up": "legF_up", "legB_lo": "legF_lo", "footB": "footF"}
        for back, front in twin.items():
            if front in have and back not in have:
                s0 = have[front]["sprite"]
                src_png = cv2.imread(str(out_dir / f"{front}.png"), cv2.IMREAD_UNCHANGED)
                dark = src_png.copy()
                dark[:, :, :3] = (dark[:, :, :3].astype(np.float32) * 0.74).astype(np.uint8)
                cv2.imwrite(str(out_dir / f"{back}.png"), dark)
                parts.append({"bone": back, "z": DEPTH[back], "sprite": dict(s0, url=f"{url_prefix}/{back}.png")})
    parts.sort(key=lambda p: DRAW_ORDER.index(p["bone"]))
    # a drawing order that puts the far limbs first is already DRAW_ORDER; the sprite scale (studio px per sprite px) is filled in by the caller
    return parts


def _cut(name, m, src_bgr, f, J, origin, out_dir, url_prefix, shade):
    ys, xs = np.nonzero(m)
    x0, x1, y0, y1 = xs.min() - 2, xs.max() + 3, ys.min() - 2, ys.max() + 3
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(m.shape[1], x1), min(m.shape[0], y1)
    alpha = (m[y0:y1, x0:x1].astype(np.uint8) * 255)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.6)
    rgb = src_bgr[y0:y1, x0:x1]
    # bleed colour into the transparent edge so scaling does not pull in the light page colour
    inv = (alpha < 200).astype(np.uint8)
    rgb = cv2.inpaint(rgb, inv, 3, cv2.INPAINT_TELEA) if inv.any() and (~inv.astype(bool)).any() else rgb
    rgba = np.dstack([rgb, alpha])
    nw, nh = max(1, int(round(rgba.shape[1] * f))), max(1, int(round(rgba.shape[0] * f)))
    small = cv2.resize(rgba, (nw, nh), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(Path(out_dir) / f"{name}.png"), small)
    ox, oy = origin[name]
    return {"bone": name, "z": DEPTH[name], "sprite": {"url": f"{url_prefix}/{name}.png", "ox": round((ox - x0) * f, 1), "oy": round((oy - y0) * f, 1), "w": nw, "h": nh, "k": round(shade, 5)}}
