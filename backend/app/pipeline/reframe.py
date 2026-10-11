"""Decide how to turn a horizontal video into a 9:16 vertical one.

- "crop": a face is on screen most of the time, so crop a 9:16 window centred on the speaker.
- "blur": no steady face (gameplay, slides, wide shots): show the full frame over a blurred copy.
- "fill": the source is already (nearly) vertical, so just scale it to fill.
"""

from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .ffmpeg import MediaInfo

log = logging.getLogger("clippy.reframe")

YUNET_URLS = (
    "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
)
TARGET_ASPECT = 9 / 16


@dataclass
class Layout:
    mode: str  # "crop" | "blur" | "fill"
    crop_x: int = 0
    crop_w: int = 0
    crop_h: int = 0


class FaceFinder:
    """Face detector: OpenCV YuNet (downloaded once, ~230 KB), else a Haar cascade, else none."""

    def __init__(self, models_dir: Path, allow_download: bool = True):
        import cv2

        self.cv2 = cv2
        self.yunet = None
        self.haar = None
        model = models_dir / "face_detection_yunet_2023mar.onnx"
        if not model.exists() and allow_download:
            models_dir.mkdir(parents=True, exist_ok=True)
            for url in YUNET_URLS:
                try:
                    urllib.request.urlretrieve(url, model)
                    break
                except Exception as e:  # offline is fine, we fall back
                    log.warning("Could not download face model from %s: %s", url, e)
                    model.unlink(missing_ok=True)
        if model.exists() and hasattr(cv2, "FaceDetectorYN"):
            try:
                self.yunet = cv2.FaceDetectorYN.create(str(model), "", (320, 320), 0.7)
            except Exception as e:
                log.warning("Could not load face model: %s", e)
        if self.yunet is None:
            cascade = Path(getattr(getattr(cv2, "data", None), "haarcascades", "")) / "haarcascade_frontalface_default.xml"
            if cascade.exists():
                self.haar = cv2.CascadeClassifier(str(cascade))

    @property
    def available(self) -> bool:
        return self.yunet is not None or self.haar is not None

    def largest_face_x(self, frame) -> float | None:
        """Horizontal centre of the biggest face, 0..1 of frame width, or None."""
        cv2 = self.cv2
        h, w = frame.shape[:2]
        scale = 640 / w if w > 640 else 1.0
        small = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale != 1.0 else frame
        sh, sw = small.shape[:2]
        boxes: list[tuple[float, float, float, float]] = []
        if self.yunet is not None:
            self.yunet.setInputSize((sw, sh))
            _, faces = self.yunet.detect(small)
            if faces is not None:
                boxes = [(f[0], f[1], f[2], f[3]) for f in faces]
        elif self.haar is not None:
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            boxes = [tuple(b) for b in self.haar.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))]
        if not boxes:
            return None
        x, _, bw, _ = max(boxes, key=lambda b: b[2] * b[3])
        return float((x + bw / 2) / sw)


def _dominant_position(xs: list[float]) -> float:
    """Where the speaker usually is. A histogram beats a median when two people alternate."""
    hist, edges = np.histogram(xs, bins=12, range=(0, 1))
    best = int(np.argmax(hist))
    in_bin = [x for x in xs if edges[best] <= x <= edges[best + 1]]
    return float(np.mean(in_bin)) if in_bin else float(np.median(xs))


def _even(n: float) -> int:
    return int(n) // 2 * 2


def plan_layout(video: Path, info: MediaInfo, start: float, end: float, finder: FaceFinder | None,
                samples: int = 12) -> Layout:
    if info.aspect <= TARGET_ASPECT + 0.08:
        return Layout(mode="fill")
    if finder is None or not finder.available:
        return Layout(mode="blur")
    import cv2

    cap = cv2.VideoCapture(str(video))
    xs: list[float] = []
    try:
        for t in np.linspace(start + 0.3, max(start + 0.3, end - 0.3), samples):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            x = finder.largest_face_x(frame)
            if x is not None:
                xs.append(x)
    finally:
        cap.release()
    if len(xs) < max(2, int(samples * 0.4)):
        return Layout(mode="blur")
    crop_h = _even(info.height)
    crop_w = _even(crop_h * TARGET_ASPECT)
    if crop_w > info.width:
        return Layout(mode="fill")
    centre = _dominant_position(xs) * info.width
    crop_x = _even(min(max(0, centre - crop_w / 2), info.width - crop_w))
    return Layout(mode="crop", crop_x=crop_x, crop_w=crop_w, crop_h=crop_h)
