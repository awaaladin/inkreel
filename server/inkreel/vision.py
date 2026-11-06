"""Computer vision for animators: measure a drawing against a reference picture.

`compare` lines a drawing up with the reference figure (same height, standing on the same line, best horizontal fit) and reports,
body part by body part, where the drawing differs: wider, narrower, shifted forward or back. It also writes an overlay picture
(red = only in the reference, blue = only in the drawing, dark = both) so the differences can be seen.

Nothing here generates art. It only measures, so a drawing can be corrected against the reference.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from . import trace

BAND_ORDER = ["head", "neck", "torso", "thigh", "shin", "foot"]


def figure_mask(path: str | Path, flip: bool = False) -> np.ndarray:
    """Boolean mask of the figure (white or plain background removed, white clothes kept)."""
    return trace._foreground(trace._load(path, flip))


def _bbox(m: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _crop(m: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = _bbox(m)
    return m[y0:y1, x0:x1]


def _bands(joints: dict, top: float, bottom: float) -> list[tuple[str, float, float]]:
    """Body-part bands as fractions (0..1) of the figure's height, from joint y positions in the reference picture."""
    H = max(1.0, bottom - top)
    f = lambda y: min(1.0, max(0.0, (y - top) / H))  # noqa: E731
    ys = {k: v[1] for k, v in joints.items()}
    return [("head", 0.0, f(ys["neck"])), ("neck", f(ys["neck"]), f(ys["shoulder"])), ("torso", f(ys["shoulder"]), f(ys["hip"])),
            ("thigh", f(ys["hip"]), f(ys["kneeF"])), ("shin", f(ys["kneeF"]), f(ys["ankleF"])), ("foot", f(ys["ankleF"]), 1.0)]


def _edges(m: np.ndarray, y0: int, y1: int) -> tuple[float, float, float]:
    """mean left edge, right edge and width (px) of the mask over rows y0..y1"""
    L, R = [], []
    for y in range(y0, max(y0 + 1, y1)):
        xs = np.nonzero(m[min(y, m.shape[0] - 1)])[0]
        if len(xs):
            L.append(xs.min())
            R.append(xs.max() + 1)
    if not L:
        return 0.0, 0.0, 0.0
    return float(np.mean(L)), float(np.mean(R)), float(np.mean(R) - np.mean(L))


def compare(ref_path: str | Path, mine_path: str | Path, out_dir: str | Path, joints: dict | None = None, flip_ref: bool = False) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ref_full = figure_mask(ref_path, flip_ref)
    mine_full = figure_mask(mine_path)
    rx0, ry0, rx1, ry1 = _bbox(ref_full)
    ref = ref_full[ry0:ry1, rx0:rx1]
    mine0 = _crop(mine_full)
    H = ref.shape[0]
    s = H / mine0.shape[0]
    mine = cv2.resize(mine0.astype(np.uint8) * 255, (max(1, int(round(mine0.shape[1] * s))), H), interpolation=cv2.INTER_AREA) > 127
    # best horizontal fit by IoU
    pad = max(ref.shape[1], mine.shape[1])
    Wc = ref.shape[1] + mine.shape[1] + 2 * pad
    best = (-1.0, 0)
    base = np.zeros((H, Wc), bool)
    base[:, pad:pad + ref.shape[1]] = ref
    for dx in range(-int(0.5 * ref.shape[1]), int(0.5 * ref.shape[1]) + 1, 2):
        c = np.zeros((H, Wc), bool)
        x = pad + dx
        c[:, x:x + mine.shape[1]] = mine
        iou = (base & c).sum() / max(1, (base | c).sum())
        if iou > best[0]:
            best = (iou, dx)
    iou, dx = best
    a = base
    b = np.zeros((H, Wc), bool)
    b[:, pad + dx:pad + dx + mine.shape[1]] = mine

    res: dict = {"iou": round(float(iou), 3), "height_scale": round(float(s), 3), "shift_px": int(dx),
                 "mine_aspect": round(mine0.shape[1] / mine0.shape[0], 3), "ref_aspect": round(ref.shape[1] / ref.shape[0], 3), "bands": {}}
    if joints:
        top_ref = ry0
        bot_ref = ry1
        for name, f0, f1 in _bands(joints, top_ref, bot_ref):
            y0, y1 = int(f0 * H), int(f1 * H)
            la, ra, wa = _edges(a, y0, y1)
            lb, rb, wb = _edges(b, y0, y1)
            res["bands"][name] = {
                "ref_width_pct": round(100 * wa / H, 1), "mine_width_pct": round(100 * wb / H, 1),
                "width_diff_pct": round(100 * (wb - wa) / max(1.0, wa), 1),
                "front_edge_shift_pct": round(100 * (rb - ra) / H, 1), "back_edge_shift_pct": round(100 * (lb - la) / H, 1),
                "band_iou": round(float((a[y0:y1] & b[y0:y1]).sum() / max(1, (a[y0:y1] | b[y0:y1]).sum())), 3),
                "from_pct": round(100 * f0, 1), "to_pct": round(100 * f1, 1)}

    # overlay picture
    canvas = np.full((H, Wc, 3), 255, np.uint8)
    canvas[a & ~b] = (80, 80, 230)       # BGR: only the reference = red
    canvas[b & ~a] = (230, 130, 60)      # only the drawing = blue
    canvas[a & b] = (70, 70, 70)         # both = dark grey
    ys, xs = np.nonzero(a | b)
    x0, x1 = max(0, xs.min() - 20), min(Wc, xs.max() + 20)
    canvas = canvas[:, x0:x1]
    if joints:
        for name, f0, f1 in _bands(joints, ry0, ry1):
            y = int(f0 * H)
            cv2.line(canvas, (0, y), (canvas.shape[1], y), (160, 160, 160), 1)
            cv2.putText(canvas, name, (4, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (90, 90, 90), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"IoU {iou:.2f}  red=reference only  blue=drawing only", (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2, cv2.LINE_AA)
    cv2.imwrite(str(out_dir / "overlay.png"), canvas)

    def _gray(m):
        g = np.full(m.shape, 255, np.uint8)
        g[m] = 60
        return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    side = np.hstack([_gray(a)[:, x0:x1], np.full((H, 10, 3), 255, np.uint8), _gray(b)[:, x0:x1], np.full((H, 10, 3), 255, np.uint8), canvas])
    cv2.imwrite(str(out_dir / "side_by_side.png"), side)
    (out_dir / "compare.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    res["overlay"] = str(out_dir / "overlay.png")
    res["side_by_side"] = str(out_dir / "side_by_side.png")
    return res


def advice(res: dict) -> list[str]:
    """Plain-language corrections from a compare() result."""
    out = []
    names = {"head": "head and hair", "neck": "neck and shoulders", "torso": "torso", "thigh": "hips and thighs", "shin": "knees and shins", "foot": "feet"}
    for n in BAND_ORDER:
        b = res["bands"].get(n)
        if not b:
            continue
        w = b["width_diff_pct"]
        if abs(w) >= 8:
            out.append(f"{names[n]}: {'too wide' if w > 0 else 'too narrow'} by {abs(w):.0f}% (reference {b['ref_width_pct']}% of height, mine {b['mine_width_pct']}%)")
        fs, bs = b["front_edge_shift_pct"], b["back_edge_shift_pct"]
        if abs(fs) >= 2.0:
            out.append(f"{names[n]}: front edge is {abs(fs):.1f}% of height too far {'forward' if fs > 0 else 'back'}")
        if abs(bs) >= 2.0:
            out.append(f"{names[n]}: back edge is {abs(bs):.1f}% of height too far {'forward' if bs > 0 else 'back'}")
    return out
