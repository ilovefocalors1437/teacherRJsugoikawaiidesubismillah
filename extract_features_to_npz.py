"""
extract_features_to_npz.py — Pre-extract dataset images into 1,812-D feature vectors.

Reads images from:
    data set/<mode>/<ClassName>/*.jpg

Extracts HOG + HSV colour histogram feature vectors (via features.py) using the
exact active localizer crop geometry, and saves a compressed .npz archive:
    models/features_<mode>.npz (X: float32, y: str)

Benefits:
1. Massive compression: Converts hundreds of MBs of raw images into a ~15-20 MB matrix.
2. Lightning training: Scikit-learn can load the matrix and fit models in 1-2 seconds.
3. Git-friendly: Can be committed or versioned easily without uploading gigabytes of raw images.
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path
from collections import Counter
import cv2
import numpy as np

from features import extract_features, FEATURE_DESCRIPTION
from mentoscope_app import (
    MODES, MODELS_DIR, crop_box, LOCALIZER_MODE,
    localize_by_yolo_ear, localize_by_texture, _stub_box, localize_region
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data set"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _crop_box_for_training(img, mode):
    """Crop box matching the active LOCALIZER_MODE (must match inference)."""
    h, w = img.shape[:2]
    if LOCALIZER_MODE == "yolo":
        yb = localize_by_yolo_ear(img)
        if yb is not None:
            return yb
        tb = localize_by_texture(img)
        if tb is not None:
            return tb
        return _stub_box(h, w)
    elif LOCALIZER_MODE == "texture":
        tb = localize_by_texture(img)
        if tb is not None:
            return tb
        return _stub_box(h, w)
    else:
        box, _kind, _conf = localize_region(img, mode)
        return box


def extract_mode_features(mode: str):
    mode_dir = DATA_DIR / mode
    if not mode_dir.exists():
        print(f"[extract] Dataset folder not found: {mode_dir}")
        sys.exit(1)

    classes = list(MODES[mode]["classes"].keys())
    present = [c for c in classes if (mode_dir / c).is_dir()]
    if not present:
        print(f"[extract] No class subfolders found inside {mode_dir}")
        sys.exit(1)

    print(f"[extract] Processing mode='{mode}', localizer='{LOCALIZER_MODE}'...")
    print(f"[extract] Feature stack: {FEATURE_DESCRIPTION}")

    X, y = [], []
    counts = Counter()

    for cls in present:
        cdir = mode_dir / cls
        files = sorted(p for p in cdir.iterdir() if p.suffix.lower() in IMG_EXTS)
        print(f"[extract] Extracting '{cls}' ({len(files)} images)...")
        for i, p in enumerate(files):
            img = cv2.imread(str(p))
            if img is None:
                continue
            try:
                box = _crop_box_for_training(img, mode)
                feat = extract_features(crop_box(img, box))
                X.append(feat)
                y.append(cls)
                counts[cls] += 1
            except Exception as e:
                print(f"[extract] Skipping {p.name}: {e}")

    if not X:
        print("[extract] No features extracted.")
        sys.exit(1)

    X_arr = np.array(X, dtype=np.float32)
    y_arr = np.array(y)

    print(f"\n[extract] Summary for mode='{mode}':")
    for cls in present:
        print(f"    {cls:20s}: {counts.get(cls, 0)} samples")
    print(f"[extract] Feature matrix shape: {X_arr.shape}")

    MODELS_DIR.mkdir(exist_ok=True)
    out_npz = MODELS_DIR / f"features_{mode}.npz"
    np.savez_compressed(
        out_npz,
        X=X_arr,
        y=y_arr,
        classes=np.array(present),
        feature_description=FEATURE_DESCRIPTION,
        localizer=LOCALIZER_MODE,
    )
    print(f"[extract] Saved compressed feature vectors to: {out_npz}")
    print(f"[extract] File size: {out_npz.stat().st_size / (1024*1024):.2f} MB\n")
    return out_npz


def main():
    parser = argparse.ArgumentParser(description="Pre-extract features into .npz matrix")
    parser.add_argument("--mode", choices=sorted(MODES.keys()), default="ear", help="Exam mode (default: ear)")
    args = parser.parse_args()
    extract_mode_features(args.mode)


if __name__ == "__main__":
    main()
