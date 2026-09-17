"""
features.py — shared image feature extraction for MentoScope.

Both `train_classifier.py` (training) and `mentoscope_app.py` (inference)
import `extract_features()` from here, so the two paths use *identical*
parameters by construction. If these ever drifted apart, the saved model
would silently misbehave at inference time — so this file is the single
source of truth for how a cropped tympanic-membrane region becomes a
feature vector.

Feature vector = HOG (grayscale shape/texture) ++ HSV colour histogram.
CPU-only, no deep learning — runs fine on this ARM64 laptop.
"""
from __future__ import annotations

import cv2
import numpy as np
from skimage.feature import hog

# --- Fixed parameters — MUST be identical for training and inference. ---
IMG_SIZE = (128, 128)              # (w, h) every crop is resized to this
HOG_ORIENTATIONS = 9
HOG_PIXELS_PER_CELL = (16, 16)
HOG_CELLS_PER_BLOCK = (2, 2)
HIST_BINS = 16                     # bins per HSV channel

# Human-readable description of the feature stack (used in README / logs).
FEATURE_DESCRIPTION = (
    "HOG (9 orientations, 16px cells, 2x2 blocks, L2-Hys) "
    "++ HSV colour histogram (16 bins per channel)"
)


def _color_histogram(bgr: np.ndarray) -> np.ndarray:
    """Normalised per-channel HSV histogram: 3 channels x HIST_BINS."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    channel_ranges = [(0, 180), (0, 256), (0, 256)]  # H, S, V
    parts = []
    for channel, (lo, hi) in enumerate(channel_ranges):
        hist = cv2.calcHist([hsv], [channel], None, [HIST_BINS], [lo, hi])
        hist = cv2.normalize(hist, hist).flatten()
        parts.append(hist)
    return np.concatenate(parts).astype(np.float32)


def extract_features(bgr: np.ndarray) -> np.ndarray:
    """Turn one BGR crop (OpenCV image) into a 1-D float32 feature vector.

    Raises ValueError on an empty/None image so callers can skip it rather
    than feed garbage into the model.
    """
    if bgr is None or getattr(bgr, "size", 0) == 0:
        raise ValueError("extract_features received an empty image")
    if bgr.ndim == 2:  # grayscale in -> promote to 3-channel
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)

    img = cv2.resize(bgr, IMG_SIZE, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    hog_feat = hog(
        gray,
        orientations=HOG_ORIENTATIONS,
        pixels_per_cell=HOG_PIXELS_PER_CELL,
        cells_per_block=HOG_CELLS_PER_BLOCK,
        block_norm="L2-Hys",
        feature_vector=True,
    ).astype(np.float32)

    color_feat = _color_histogram(img)
    return np.concatenate([hog_feat, color_feat])
