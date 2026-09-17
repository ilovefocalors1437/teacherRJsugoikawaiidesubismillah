"""
train_classifier.py — train a MentoScope exam-mode classifier.

Supports two fast training workflows:
1. Feature Vector Mode (Default): Loads pre-extracted features from
   models/features_<mode>.npz and trains in ~1-2 seconds!
2. Full Pipeline Extraction: If .npz does not exist or --extract is passed,
   reads images from "data set/<mode>/<ClassName>/*.jpg", extracts HOG+HSV
   features, saves the .npz, and trains the RandomForestClassifier.

Usage:
    python train_classifier.py                # trains "ear" from features_<mode>.npz
    python train_classifier.py --mode ear
    python train_classifier.py --mode ear --extract   # forces re-extraction from images
"""
from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter

import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

from features import FEATURE_DESCRIPTION
from mentoscope_app import MODES, MODELS_DIR, USE_REAL_MODEL, LOCALIZER_MODE
from extract_features_to_npz import extract_mode_features

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data set"

RANDOM_STATE = 42
TEST_SIZE = 0.2
MIN_PER_CLASS = 2


def load_dataset_matrix(mode: str, force_extract: bool = False):
    """Load (X, y) feature matrices from .npz or extract if needed."""
    npz_path = MODELS_DIR / f"features_{mode}.npz"

    if force_extract or not npz_path.exists():
        print(f"[train] Pre-extracted features not found at {npz_path}. Extracting from images...")
        extract_mode_features(mode)

    print(f"[train] Loading feature matrix from: {npz_path}")
    data = np.load(npz_path)
    X = data["X"]
    y = data["y"]
    classes = list(data["classes"])

    counts = Counter(y)
    print(f"[train] Feature matrix loaded: {X.shape[0]} samples x {X.shape[1]} features")
    print(f"[train] Samples per class (mode='{mode}'):")
    for cls in classes:
        print(f"    {cls:20s}: {counts.get(cls, 0)}")

    return X, y, classes


def parse_args():
    parser = argparse.ArgumentParser(description="Train MentoScope classifier using Feature Vectors.")
    parser.add_argument(
        "--mode", choices=sorted(MODES.keys()), default="ear",
        help="Which exam mode to train (default: ear)"
    )
    parser.add_argument(
        "--extract", action="store_true",
        help="Force re-extraction of feature vectors from raw images before training"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    mode = args.mode
    cfg = MODES[mode]

    print("==================================================")
    print(f" MentoScope Classifier Training (Mode: '{mode}')")
    print("==================================================")
    print(f"[train] Feature Stack: {FEATURE_DESCRIPTION}")
    print(f"[train] Active Localizer: {LOCALIZER_MODE}")

    X, y, classes = load_dataset_matrix(mode, force_extract=args.extract)

    print("\n[train] Fitting StandardScaler and splitting dataset (80% Train / 20% Test)...")
    scaler = StandardScaler().fit(X)
    X_scaled = scaler.transform(X)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X_scaled, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )

    print("[train] Training RandomForestClassifier (n_estimators=300, class_weight='balanced')...")
    clf = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    clf.fit(X_tr, y_tr)

    print(f"\n[train] Evaluation on Held-Out Test Set (mode='{mode}'):\n")
    print(classification_report(y_te, clf.predict(X_te), zero_division=0))

    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(clf, cfg["model_path"])
    joblib.dump(scaler, cfg["scaler_path"])

    meta = {
        "mode": mode,
        "classes": list(clf.classes_),
        "n_samples": int(X.shape[0]),
        "n_features": int(X.shape[1]),
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "feature_stack": FEATURE_DESCRIPTION,
        "use_real_model": bool(USE_REAL_MODEL),
        "localizer": LOCALIZER_MODE,
    }
    cfg["meta_path"].write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\n[train] SAVE PATHS:")
    print(f"  Model  -> {cfg['model_path']}")
    print(f"  Scaler -> {cfg['scaler_path']}")
    print(f"  Meta   -> {cfg['meta_path']}")
    print(f"\n[train] SUCCESS: mode='{mode}' trained on {meta['n_samples']} samples across {len(meta['classes'])} classes.")


if __name__ == "__main__":
    main()
