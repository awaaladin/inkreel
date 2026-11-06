"""MediaPipe helpers, ported from the user's own `mirror` (FaceLandmarker, SelfieSegmenter) and `vissionmirror` (ObjectDetector) Android code.

Same models, same settings, same idea (bitmap in, result out, fully offline), now in Python so the studio can use them:
  * person_mask    - cut a person out of a picture (mirror: SelfieSegmenterHelper)
  * face_landmarks - 478 points on a face, to measure face proportions (mirror: FaceLandmarkerHelper)
  * detect_objects - boxes for people/objects (vissionmirror: ObjectSensor)
Models live in <repo>/models (copied from the Android projects' assets).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

MODELS = Path(__file__).resolve().parents[2] / "models"


class ModelMissing(Exception):
    pass


def _model(name: str) -> bytes:
    """The model file's bytes (loaded from memory: more reliable than a path on Windows)."""
    p = MODELS / name
    if not p.exists():
        raise ModelMissing(f"model {name} not found in {MODELS}. Copy it from the mirror / vissionmirror Android assets.")
    return p.read_bytes()


def _mp_image(bgr: np.ndarray):
    import mediapipe as mp
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def face_landmarks(image_path: str | Path) -> np.ndarray | None:
    """(478, 3) normalised landmarks of the single face in the picture, or None if there is not exactly one."""
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_buffer=_model("face_landmarker.task")), running_mode=vision.RunningMode.IMAGE,
                                        num_faces=2, min_face_detection_confidence=0.3, min_face_presence_confidence=0.3, min_tracking_confidence=0.3)
    with vision.FaceLandmarker.create_from_options(opts) as lm:
        res = lm.detect(_mp_image(bgr))
    if len(res.face_landmarks) != 1:
        return None
    return np.array([[p.x, p.y, p.z] for p in res.face_landmarks[0]], np.float32)
