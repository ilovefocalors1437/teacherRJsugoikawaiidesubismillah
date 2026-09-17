"""
MentoScope — ENT otoscopy trainer (Flask backend)
==================================================
Two-stage detection pipeline, run once per exam **mode** (ear / nose /
throat — see MODES below). Each mode is fully independent: its own
YOLO-World prompt, its own class list, its own trained model file.
Nothing is shared between modes except the pipeline shape and the
feature extractor.

  1. OpenCV     capture one frame from the endoscope (grab_single_frame)
  2. YOLO-World LOCALIZE the mode's landmarks -> primary box + secondary
                 boxes (never judges health — only answers WHERE)
  3. crop       take only the pixels inside that box
  4. sklearn    CLASSIFY the crop using that mode's own model
                (the only step that decides normal vs. abnormal)
  5. OpenCV     draw the box + classification label onto the frame

Explanations are a fixed text lookup keyed by class (no LLM).

Both AI stages are switchable stubs so the app runs end-to-end with no
camera, no model file, and no GPU — then upgrades in place, per mode:
  * USE_REAL_MODEL        -> real ultralytics YOLO-World vs. a fixed centre box
  * models/classifier_<mode>.joblib -> real trained classifier vs. a
    "Normal @ 0%" stub (produced by `train_classifier.py --mode <mode>`)
"""
from __future__ import annotations

import time
import json
import base64
import threading
from pathlib import Path

import cv2
import numpy as np
import joblib
from flask import Flask, render_template, jsonify, Response, request, send_from_directory
from flask_cors import CORS

from features import extract_features

app = Flask(__name__)
# The heavy stuff (this backend, models, YOLO) is meant to run on one machine
# while the frontend can be served from anywhere else on the LAN (another
# device's browser, or a static build served off a Pi) — CORS is needed
# because that frontend origin differs from this backend's origin.
CORS(app)

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "models"
SAMPLES_DIR = ROOT / "static" / "samples"
FRONTEND_DIST = ROOT / "frontend" / "dist"   # React build (npm run build)
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# ---------------------------------------------------------------- config
# Startup default for the camera source. Overridable at runtime from the
# Practice page's camera picker (POST /camera_source) — see _camera_state
# below; this constant only matters for the very first request.
#   int -> local webcam index (0 = default webcam).
#   str -> MJPEG stream URL, e.g. the phone's ScreenCropStreamer feed
#          ("http://<phone-ip>:8080/stream", shown on-screen in that app once
#          streaming starts). Same pipeline either way — only the frame
#          SOURCE changes; localize/classify/draw don't know the difference.
CAMERA_INDEX: int | str = 0
WEBCAM_PROBE_RANGE = 5   # /camera_options checks indices 0..this-1 for local webcams
USE_REAL_MODEL = False          # True -> real YOLO-World localization (first run
                                # auto-downloads weights); False -> centre-box stub.
                                #
                                # Kept False on purpose. YOLO-World is COCO-pretrained
                                # open-vocabulary: measured 0 detections across all 5
                                # ear classes even at conf=0.05, because it has never
                                # seen ear anatomy and cannot zero-shot "tympanic
                                # membrane". Turning it on only costs a ~9s model load
                                # and makes the classifier's crop disagree with what it
                                # was trained on. To really use it you'd have to
                                # fine-tune YOLO on annotated otoscopy images, then
                                # retrain the classifier with USE_REAL_MODEL=True so
                                # train/inference crops match again.
SAVE_ANNOTATED = True           # write static/last_activation_<mode>.jpg each /activate
YOLO_WEIGHTS = "yolov8s-world.pt"
YOLO_CONF_THRESHOLD = 0.05      # detection confidence cutoff passed to YOLO-World.
                                # Zero-shot CLIP detection on specialized medical
                                # close-ups is unreliable; set low so real detections
                                # aren't filtered, and the primary-not-found fallback
                                # kicks in cleanly when nothing fires.
DEFAULT_MODE = "ear"

# --------------------------------------------------------------------
# LOCALIZER MODE — which method draws the detection box (and so the crop
# the sklearn classifier sees). Options:
#   "yolo"    -> trained YOLOv8 detector (models/yolo_ear.pt). Highest-
#                confidence box per frame; if zero detections, falls back
#                to the texture localizer for THAT frame only.
#   "texture" -> median-local-std content finder (localize_by_texture).
#   "stub"    -> fixed centre-60% box.
# HONEST mAP50 CAVEAT: yolo_ear.pt was trained on SYNTHETIC images (real
# ear photos pasted onto solid-colour/gradient/noise backgrounds at random
# positions). Training mAP50 was 0.995, but that validation set was
# generated the SAME synthetic way — it proves the synthetic-label
# technique works, NOT that the model is 99.5% accurate on real endoscope
# camera frames. Treat real-frame performance as unvalidated.
# Auto-resolved at startup: "yolo" if the .pt exists, else "texture".
LOCALIZER_MODE = "yolo" if (Path(__file__).resolve().parent / "models" / "yolo_ear.pt").exists() else "texture"
YOLO_EAR_WEIGHTS = "models/yolo_ear.pt"

# Texture-based content localizer. When ON, /activate / /stream_detect /
# /classify_upload locate the real-content region (dense local texture) instead
# of the fixed centre-box stub. This finds "real tissue vs. flat/non-content
# areas (colour blocks, black borders, blanks)" — it does NOT yet find a small
# anomaly WITHIN all-tissue (that still needs the planned trained detector).
# Falls back to the centre-box stub if no textured region is found.
USE_TEXTURE_LOCALIZER = True
# Tile size (px) + median-local-std threshold for a tile to count as "textured".
# Note: report MS-CV-001 verified tile=60 / thresh=1.5 on a SYNTHETIC 900x900
# test image (3x3 colour blocks with an otoscopy photo in one cell — the sharp
# block boundaries produce very high local-std values). Real otoscopy tissue
# texture is far subtler: measured median-local-std on real ear samples peaks
# around 0.3–0.6. A threshold of 0.3 cleanly separates real tissue (0.3+) from
# flat black borders / blank areas (0.0–0.2), so that's the production default.
TEXTURE_TILE = 60
TEXTURE_TILE_THRESH = 0.3

# Adaptive grid — how many grid cells the anomaly's own box should span per
# side. The grid resolution is derived so this footprint is CONSISTENT
# regardless of frame size: unit_size = min(box_w, box_h) / this value, then
# the whole frame is tiled with cells of that unit_size (so a 60%-of-frame
# box and a 7%-of-frame box each land on a grid where they span ~N×N cells).
# Increase for a finer grid, decrease for coarser — only this needs tuning.
GRID_CELLS_PER_ANOMALY_SIDE = 3

# Sane bounds on the computed grid so a wildly small/large box can't produce
# a near-1×1 or an absurdly dense grid. The upper bound is sized to preserve
# the ~NxN footprint for typical small boxes; only genuinely extreme boxes
# (tiny relative to the frame) hit the clamp and trigger a one-line warning.
GRID_MIN_CELLS = 2
GRID_MAX_CELLS = 50

# Near-full-frame edge case: if the detection box covers at least this
# fraction of BOTH frame axes (e.g. a membrane-filling finding, or the
# centre-60% stub on a close-up), the NxN subdivision would fragment an
# anomaly that really "fills the view" into many tiny cells. Instead the
# whole finding is represented as a SINGLE highlighted cell. Tunable.
NEAR_FULL_FRAME_THRESHOLD = 0.7

# Live continuous-detection stream tuning
STREAM_INFER_INTERVAL = 0.12    # seconds between inferences (~8 fps); video still
                                # streams at full camera fps, only inference is throttled
_stream_lock = threading.Lock()
_latest_result: dict[str, dict] = {}   # mode -> last structured payload, for /last_result

# ================================================================
# MODES — one entry per exam type. Everything downstream (localize,
# classify, draw, explain) reads from the active mode's config only.
# Datasets never mix: train_classifier.py trains one mode's model from
# "data set/<mode>/*" and writes only that mode's model_path/scaler_path.
# ================================================================
MODES = {
    "ear": {
        # One PRIMARY landmark (cropped + classified) + SECONDARY landmarks
        # (drawn as name-only annotation, never classified). All of a mode's
        # prompts are passed to YOLO-World in a SINGLE set_classes/predict call.
        "landmarks": [
            {"prompt": "tympanic membrane", "label": "Tympanic Membrane", "role": "primary"},
            {"prompt": "cone of light",     "label": "Cone of Light",     "role": "secondary"},
            {"prompt": "malleus handle",    "label": "Malleus Handle",    "role": "secondary"},
        ],
        # Keys MUST match the folder names under "data set/ear/":
        #   Normal / AOM / Cerumen / CSOM / Myringosclerosis
        "classes": {
            "Normal": {
                "label": "Normal",
                "status": "normal",
                "explanation": "The tympanic membrane looks healthy — translucent and pearly-grey, with a clear cone of light and no bulging or fluid.",
            },
            "AOM": {
                "label": "Acute Otitis Media",
                "status": "attention",
                "explanation": "The drum looks red and bulging, a sign of acute middle-ear infection with pus building up behind it.",
            },
            "Cerumen": {
                "label": "Cerumen Impaction",
                "status": "caution",
                "explanation": "Ear wax is obscuring part of the drum and may need clearing before the membrane can be fully assessed.",
            },
            "CSOM": {
                "label": "Chronic Otitis Media",
                "status": "attention",
                "explanation": "A persistent, non-healing perforation of the eardrum with ongoing discharge — a long-standing problem, distinct from an acute infection.",
            },
            "Myringosclerosis": {
                "label": "Myringosclerosis",
                "status": "caution",
                "explanation": "Chalky white calcified patches on the eardrum, left behind by old healed infections or trauma — usually not urgent in itself, but worth noting.",
            },
        },
        "model_path": MODELS_DIR / "classifier_ear.joblib",
        "scaler_path": MODELS_DIR / "scaler_ear.joblib",
        "meta_path": MODELS_DIR / "meta_ear.json",
    },
    # NOSE — starting-point classes only; refine once a real nose dataset
    # is organised. Keys MUST match folder names under "data set/nose/".
    "nose": {
        "landmarks": [
            {"prompt": "nasal turbinate",    "label": "Nasal Turbinate",    "role": "primary"},
            {"prompt": "nasal septum",       "label": "Nasal Septum",       "role": "secondary"},
            {"prompt": "inferior turbinate", "label": "Inferior Turbinate", "role": "secondary"},
        ],
        "classes": {
            "Normal": {
                "label": "Normal",
                "status": "normal",
                "explanation": "The nasal turbinates and septum look healthy — pink mucosa, clear airway, no visible swelling or discharge.",
            },
            "Allergic_Rhinitis": {
                "label": "Allergic Rhinitis",
                "status": "attention",
                "explanation": "The turbinates look swollen and pale or bluish, consistent with allergic inflammation rather than infection.",
            },
            "Nasal_Polyp": {
                "label": "Nasal Polyp",
                "status": "attention",
                "explanation": "A smooth, pale, grape-like growth is visible in the nasal cavity, which can block airflow and needs specialist follow-up.",
            },
            "Deviated_Septum": {
                "label": "Deviated Septum",
                "status": "attention",
                "explanation": "The nasal septum is shifted to one side, narrowing one nasal passage relative to the other.",
            },
        },
        "model_path": MODELS_DIR / "classifier_nose.joblib",
        "scaler_path": MODELS_DIR / "scaler_nose.joblib",
        "meta_path": MODELS_DIR / "meta_nose.json",
    },
    # THROAT — starting-point classes only; refine once a real throat
    # dataset is organised. Keys MUST match folder names under
    # "data set/throat/".
    "throat": {
        "landmarks": [
            {"prompt": "tonsil",                    "label": "Tonsil",                    "role": "primary"},
            {"prompt": "posterior pharyngeal wall", "label": "Posterior Pharyngeal Wall", "role": "secondary"},
            {"prompt": "uvula",                     "label": "Uvula",                     "role": "secondary"},
        ],
        "classes": {
            "Normal": {
                "label": "Normal",
                "status": "normal",
                "explanation": "The tonsils and posterior pharynx look healthy — pink, symmetric, with no swelling, redness or exudate.",
            },
            "Pharyngitis": {
                "label": "Pharyngitis",
                "status": "attention",
                "explanation": "The posterior pharynx looks red and inflamed, consistent with a sore throat from infection or irritation.",
            },
            "Tonsillitis": {
                "label": "Tonsillitis",
                "status": "attention",
                "explanation": "The tonsils look enlarged and red, sometimes with white patches, suggesting an active infection.",
            },
        },
        "model_path": MODELS_DIR / "classifier_throat.joblib",
        "scaler_path": MODELS_DIR / "scaler_throat.joblib",
        "meta_path": MODELS_DIR / "meta_throat.json",
    },
}


def resolve_mode(raw: str | None) -> str:
    """Validate an incoming mode string, falling back to DEFAULT_MODE."""
    if raw in MODES:
        return raw
    if raw is not None:
        print(f"[app][warn] unknown mode '{raw}', falling back to '{DEFAULT_MODE}'")
    return DEFAULT_MODE


def class_order(mode: str) -> list[str]:
    return list(MODES[mode]["classes"].keys())


def meta_for(mode: str, cls: str) -> dict:
    """Metadata for a class name, with a safe default for unexpected labels."""
    return MODES[mode]["classes"].get(cls, {"label": cls, "status": "attention",
                                              "explanation": "No explanation available for this class yet."})


# ================================================================
# STEP 1 & 2 (streaming) — camera handling + no-camera fallback
# (mode-agnostic: it's the same physical camera regardless of what
# the operator is examining)
# ================================================================
# Runtime-switchable camera source (Practice page's camera picker). Holding
# both fields lets the frontend flip back and forth without losing whichever
# webcam index / phone URL was last typed in. A bare read/write of a single
# variable is already atomic under the GIL; the lock exists because picking
# a source touches two fields (type + value) that must be read/written together.
_camera_lock = threading.Lock()
_camera_state = {
    "type": "phone" if isinstance(CAMERA_INDEX, str) else "webcam",
    "webcam_index": CAMERA_INDEX if isinstance(CAMERA_INDEX, int) else 0,
    "phone_url": CAMERA_INDEX if isinstance(CAMERA_INDEX, str) else "",
}


def get_camera_state() -> dict:
    with _camera_lock:
        return dict(_camera_state)


def _active_camera_source() -> int | str:
    state = get_camera_state()
    return state["phone_url"] if state["type"] == "phone" else state["webcam_index"]


def open_camera(index: int | str | None = None):
    """Return an opened VideoCapture, or None if no camera is available.
    Defaults to the active camera source (see _camera_state) so every
    caller picks up a camera switch made from the Practice page.

    Bounds open/read timeouts for network sources (e.g. a phone MJPEG
    stream) so a wrong IP or an unstreaming phone fails fast into the
    sample/synthetic fallback instead of hanging the request thread."""
    if index is None:
        index = _active_camera_source()
    if isinstance(index, str):
        cap = cv2.VideoCapture(
            index, cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000],
        )
    else:
        cap = cv2.VideoCapture(index)
    if cap is not None and cap.isOpened():
        return cap
    if cap is not None:
        cap.release()
    return None


def probe_webcams(max_index: int = WEBCAM_PROBE_RANGE) -> list[int]:
    """Which local webcam indices actually open, 0..max_index-1. Used by
    /camera_options so the picker only lists webcams that exist."""
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap is not None and cap.isOpened():
            found.append(i)
        if cap is not None:
            cap.release()
    return found


def _load_sample_frame():
    """First image in static/samples/, used as a stand-in captured frame."""
    if SAMPLES_DIR.is_dir():
        for p in sorted(SAMPLES_DIR.iterdir()):
            if p.suffix.lower() in IMG_EXTS:
                img = cv2.imread(str(p))
                if img is not None:
                    return img
    return None


def _synthetic_frame(size: int = 720):
    """Last-resort placeholder frame so the pipeline always has pixels."""
    frame = np.full((size, size, 3), 40, dtype=np.uint8)
    cv2.circle(frame, (size // 2, size // 2), size // 2 - 20, (70, 70, 70), 2)
    cv2.putText(frame, "NO CAMERA - synthetic frame", (size // 2 - 210, size // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1, cv2.LINE_AA)
    return frame


def _fallback_frame():
    sample = _load_sample_frame()
    return sample if sample is not None else _synthetic_frame()


def generate_frames():
    """MJPEG stream for the live preview. Falls back to a static sample /
    synthetic frame (streamed slowly) when no camera is connected."""
    cap = open_camera()
    if cap is None:
        jpg = cv2.imencode(".jpg", _fallback_frame())[1].tobytes()
        while True:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
            time.sleep(0.2)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
    finally:
        cap.release()


def grab_single_frame():
    """Capture ONE frame. Returns (frame_bgr, source) where source is
    'camera' | 'sample' | 'synthetic'. Always succeeds so /activate works
    with or without an endoscope plugged in."""
    cap = open_camera()
    if cap is not None:
        ok, frame = cap.read()
        cap.release()
        if ok and frame is not None:
            return frame, "camera"
    sample = _load_sample_frame()
    if sample is not None:
        return sample, "sample"
    return _synthetic_frame(), "synthetic"


# ================================================================
# STEP 2 — LOCALIZE (YOLO-World)  |  stub = fixed centre box
# One lazily-loaded model instance is reused across modes. Each mode
# declares a list of landmark prompts (one PRIMARY + any number of
# SECONDARY). All of a mode's prompts are passed to YOLO-World in a
# SINGLE set_classes / predict call — open-vocab models accept multiple
# class prompts at once, so we never call the model once per prompt.
# ================================================================
# ================================================================
# YOLO-World (landmark prompts) — legacy multi-prompt localizer.
# Kept for USE_REAL_MODEL; the new yolo_ear.pt detector is a separate
# single-weight model loaded by _get_yolo_ear() below.
# ================================================================
_yolo_model = "unloaded"
_yolo_last_prompts: tuple | None = None   # cache key: prompt list last set on the model


def _get_yolo():
    """Lazy-load ultralytics YOLO-World the first time it's needed.
    The first load auto-downloads the weights — log that clearly so it
    isn't mistaken for a hang."""
    global _yolo_model
    if _yolo_model == "unloaded":
        try:
            from ultralytics import YOLOWorld
            if not (ROOT / YOLO_WEIGHTS).exists():
                print("[app] Downloading YOLO-World weights, this happens once...")
            _yolo_model = YOLOWorld(YOLO_WEIGHTS)
            print(f"[app] loaded YOLO-World ({YOLO_WEIGHTS})")
        except Exception as exc:
            print(f"[app][warn] could not load YOLO-World ({exc}); using centre-box stub")
            _yolo_model = None
    return _yolo_model


# ================================================================
# YOLO EAR DETECTOR — the trained yolo_ear.pt model.
# IMPORTANT: this model predicts AOM/CSOM/Cerumen/etc directly (it's a
# multi-class detector), but for now we ONLY use its BOUNDING BOX for
# localization. YOLO's own class output is intentionally unused; the
# sklearn classifier remains the single source of truth for classification
# to avoid conflicting predictions between two models. The box is fed into
# the same downstream pipeline (adaptive_grid -> overlapping_cells ->
# crop -> sklearn classify).
# ================================================================
_yolo_ear_model = "unloaded"   # "unloaded" | YOLO | None


def _get_yolo_ear():
    """Lazy-load the trained YOLOv8 ear detector (models/yolo_ear.pt) once.
    Returns the model, or None if it couldn't load (caller falls back)."""
    global _yolo_ear_model
    if _yolo_ear_model == "unloaded":
        path = ROOT / YOLO_EAR_WEIGHTS
        if not path.exists():
            _yolo_ear_model = None
            return None
        try:
            from ultralytics import YOLO
            _yolo_ear_model = YOLO(str(path))
            print(f"[localizer] YOLO model loaded from {YOLO_EAR_WEIGHTS}")
        except Exception as exc:
            print(f"[localizer][warn] could not load {YOLO_EAR_WEIGHTS} ({exc})")
            _yolo_ear_model = None
    return _yolo_ear_model


def localize_by_yolo_ear(frame):
    """Highest-confidence YOLO box for THIS frame, or None (zero detections).

    ONLY the box is returned — YOLO's class prediction is intentionally
    discarded (sklearn is the single classifier). Returns [x1,y1,x2,y2]."""
    model = _get_yolo_ear()
    if model is None:
        return None
    res = model.predict(frame, verbose=False)
    boxes = res[0].boxes
    if boxes is None or len(boxes) == 0:
        return None
    # Highest-confidence detection (ignore its class).
    conf = boxes.conf.cpu().numpy()
    best = int(np.argmax(conf))
    x1, y1, x2, y2 = boxes.xyxy.cpu().numpy()[best].astype(int)
    return [int(x1), int(y1), int(x2), int(y2)]


def _mode_prompts(mode: str) -> list[str]:
    """Ordered prompt list for a mode (primary first, then secondaries).
    Order matters: it's how we map YOLO class indices back to landmark roles."""
    return [lm["prompt"] for lm in MODES[mode]["landmarks"]]


def _stub_box(h, w):
    """Centre-60% box used when real localization is off or the primary
    landmark isn't found in a given frame."""
    bw, bh = int(w * 0.6), int(h * 0.6)
    x1, y1 = (w - bw) // 2, (h - bh) // 2
    return [x1, y1, x1 + bw, y1 + bh]


def localize_landmarks(frame, mode: str):
    """Run YOLO-World ONCE with ALL of the mode's landmark prompts.

    Returns (landmarks, primary_box, localizer_kind) where:
      * landmarks     — list of {label, box, role, confidence} for every
                        detected landmark (primary + secondaries), in the
                        order they appear in MODES[mode]["landmarks"].
      * primary_box   — the PRIMARY landmark's box, cropped for classification.
                        Falls back to the centre-60% stub box if the primary
                        landmark isn't found in THIS frame (classification
                        still runs on something reasonable).
      * localizer_kind — "yolo" if the primary box came from real detection,
                        otherwise "stub".
    """
    global _yolo_last_prompts
    h, w = frame.shape[:2]
    lms = MODES[mode]["landmarks"]
    prompts = _mode_prompts(mode)

    detected: dict[int, dict] = {}   # landmark index -> best detection
    used_real = False

    if USE_REAL_MODEL:
        model = _get_yolo()
        if model is not None:
            try:
                if _yolo_last_prompts != tuple(prompts):
                    model.set_classes(prompts)
                    _yolo_last_prompts = tuple(prompts)
                res = model.predict(frame, conf=YOLO_CONF_THRESHOLD, verbose=False)
                boxes = res[0].boxes
                if boxes is not None and len(boxes):
                    xyxy = boxes.xyxy.cpu().numpy()
                    conf = boxes.conf.cpu().numpy()
                    cls = boxes.cls.cpu().numpy().astype(int)
                    for i in range(len(cls)):
                        ci = int(cls[i])
                        if ci < 0 or ci >= len(lms):
                            continue
                        c = float(conf[i])
                        prev = detected.get(ci)
                        if prev is None or c > prev["confidence"]:
                            x1, y1, x2, y2 = xyxy[i].astype(int)
                            detected[ci] = {
                                "label": lms[ci]["label"],
                                "role": lms[ci]["role"],
                                "box": [int(x1), int(y1), int(x2), int(y2)],
                                "confidence": round(c, 4),
                            }
                    used_real = True
            except Exception as exc:
                print(f"[app][warn] YOLO inference failed ({exc}); using centre-box stub")

    # Build the ordered landmarks list; remember the primary box.
    landmarks = []
    primary_box = None
    primary_from_real = False
    for idx, lm in enumerate(lms):
        d = detected.get(idx)
        if d is None:
            continue
        landmarks.append(d)
        if lm["role"] == "primary" and primary_box is None:
            primary_box = d["box"]
            primary_from_real = True

    # Primary not found -> stub centre-box fallback for THIS frame only.
    if primary_box is None:
        primary_box = _stub_box(h, w)
        if used_real:
            primary_label = next((lm["label"] for lm in lms if lm["role"] == "primary"), "primary")
            print(f"[app][notice] '{primary_label}' not detected in this frame; "
                  f"using centre-box stub for classification (mode={mode}).")

    localizer_kind = "yolo" if primary_from_real else "stub"
    return landmarks, primary_box, localizer_kind


def localize_region(frame, mode: str):
    """Backward-compatible single-box localize, used by train_classifier.py.
    Returns the PRIMARY landmark's box (or the centre-box stub fallback), so
    training crops come from the same primary box the served pipeline classifies."""
    landmarks, primary_box, localizer_kind = localize_landmarks(frame, mode)
    primary = next((lm for lm in landmarks if lm["role"] == "primary"), None)
    loc_conf = primary["confidence"] if primary else None
    return primary_box, localizer_kind, loc_conf


def crop_box(frame, box):
    """Clamp box to the frame and return the crop (or the whole frame if
    the box is degenerate)."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    x1, x2 = sorted((max(0, min(int(x1), w - 1)), max(0, min(int(x2), w))))
    y1, y2 = sorted((max(0, min(int(y1), h - 1)), max(0, min(int(y2), h))))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return frame
    return frame[y1:y2, x1:x2]


# ================================================================
# STEP 4 — CLASSIFY (scikit-learn)  |  stub = "Normal" @ 0%
#
# _get_classifier() is THE single loader for every mode's model. It is
# reached only via classify_crop(), which is reached only via _detect() —
# and _detect() is what /activate, /stream_detect and /classify_upload all
# call. So all three endpoints resolve the model path identically; there is
# no second loading code path that could drift.
#
# Each mode caches independently (a missing nose model never affects ear),
# and the cache is keyed on the model file's mtime, so training a model
# while the server is running is picked up automatically — no restart.
# ================================================================
class _Classifier:
    def __init__(self, clf, scaler, meta):
        self.clf = clf
        self.scaler = scaler
        self.meta = meta or {}


_UNSET = object()
_classifier_lock = threading.Lock()
_classifiers: dict[str, "_Classifier | None"] = {}
_classifier_key: dict[str, object] = {}   # mode -> mtime signature the cache was built from


def _model_signature(mode: str):
    """(model_mtime, scaler_mtime) or None if either file is missing.
    Changing this signature invalidates the cached model → hot reload."""
    cfg = MODES[mode]
    try:
        return (cfg["model_path"].stat().st_mtime, cfg["scaler_path"].stat().st_mtime)
    except OSError:
        return None


def _read_meta(mode: str) -> dict:
    try:
        return json.loads(MODES[mode]["meta_path"].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def classifier_status_line(mode: str) -> str:
    """One-line human status for a mode, used at startup and on (re)load."""
    cfg = MODES[mode]
    model = _classifiers.get(mode)
    if model is None:
        return (f"[{mode}] classifier: STUB — {cfg['model_path']} not found "
                f"(run: python train_classifier.py --mode {mode})")
    n = model.meta.get("n_samples")
    classes = model.meta.get("classes") or list(model.clf.classes_)
    trained = f"trained on {n} samples, {len(classes)} classes" if n else f"{len(classes)} classes"
    return f"[{mode}] classifier: LOADED — {cfg['model_path']} ({trained})"


def _get_classifier(mode: str):
    """THE single lazy-loader for one mode's classifier + scaler.

    Returns a _Classifier, or None to mean "use the stub". Re-checks the
    model file's mtime every call, so a newly-trained model is picked up
    without restarting the server (and a deleted model falls back to stub).
    """
    sig = _model_signature(mode)
    with _classifier_lock:
        cached = _classifiers.get(mode, _UNSET)
        if cached is not _UNSET and _classifier_key.get(mode) == sig:
            return cached  # cache is current (whether a model or the stub)

        cfg = MODES[mode]
        if sig is None:
            _classifiers[mode] = None
            _classifier_key[mode] = None
            print(classifier_status_line(mode))
            return None

        try:
            clf = joblib.load(cfg["model_path"])
            scaler = joblib.load(cfg["scaler_path"])
        except Exception as exc:
            _classifiers[mode] = None
            _classifier_key[mode] = sig
            print(f"[{mode}] classifier: STUB — failed to load {cfg['model_path']} ({exc})")
            return None

        _classifiers[mode] = _Classifier(clf, scaler, _read_meta(mode))
        _classifier_key[mode] = sig
        print(classifier_status_line(mode))

        # The classifier only sees the localizer's crop. If the model was
        # trained against a different localizer, the crop geometry — and so the
        # features — no longer match what it learned. Say so loudly.
        trained_with = _classifiers[mode].meta.get("use_real_model")
        if trained_with is not None and bool(trained_with) != bool(USE_REAL_MODEL):
            print(f"[{mode}] classifier: WARNING — model was trained with "
                  f"USE_REAL_MODEL={trained_with}, but the app is running with "
                  f"USE_REAL_MODEL={USE_REAL_MODEL}. Crops won't match; retrain "
                  f"(python train_classifier.py --mode {mode}) or flip the flag back.")
        return _classifiers[mode]


def classify_crop(mode: str, crop):
    """Return (class_name, confidence, scores) where scores is a list of
    (class_name, probability) covering every class the model knows."""
    model = _get_classifier(mode)
    if model is None:  # stub
        return "Normal", 0.0, [(c, 0.0) for c in class_order(mode)]
    feat = extract_features(crop).reshape(1, -1)
    feat = model.scaler.transform(feat)
    proba = model.clf.predict_proba(feat)[0]
    classes = list(model.clf.classes_)
    top = int(np.argmax(proba))
    scores = [(c, float(p)) for c, p in zip(classes, proba)]
    return classes[top], float(proba[top]), scores


# ================================================================
# STEP 5 — DRAW overlay (OpenCV)
# ================================================================
def draw_overlay(frame, box, label_text, landmarks=None):
    """Draw the PRIMARY localization box + classification label (accent colour),
    plus any SECONDARY landmark boxes (muted colour, name only) onto a copy of
    the frame. Secondary boxes are purely visual/educational annotation and
    carry NO classification. Returns the annotated frame."""
    out = frame.copy()

    # Secondary landmarks first (muted), so the primary box draws on top.
    muted = (150, 150, 160)  # BGR — soft slate, visually distinct from the accent
    for lm in (landmarks or []):
        if lm.get("role") != "secondary":
            continue
        sx1, sy1, sx2, sy2 = [int(v) for v in lm["box"]]
        cv2.rectangle(out, (sx1, sy1), (sx2, sy2), muted, 1)
        tag = lm.get("label", "")
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (sx1, max(0, sy1 - th - 8)), (sx1 + tw + 10, sy1), muted, -1)
        cv2.putText(out, tag, (sx1 + 5, max(11, sy1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (245, 245, 245), 1, cv2.LINE_AA)

    # Primary box — accent colour, with the classification label + confidence.
    teal = (150, 120, 20)  # BGR
    x1, y1, x2, y2 = [int(v) for v in box]
    cv2.rectangle(out, (x1, y1), (x2, y2), teal, 2)
    (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
    cv2.rectangle(out, (x1, max(0, y1 - th - 10)), (x1 + tw + 12, y1), teal, -1)
    cv2.putText(out, label_text, (x1 + 6, max(12, y1 - 7)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    return out


# ---------------------------------------------------------------- helpers
def _b64_jpeg(frame):
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")


def _norm(box, w, h):
    x1, y1, x2, y2 = box
    return [round(x1 / w, 5), round(y1 / h, 5), round(x2 / w, 5), round(y2 / h, 5)]


# ================================================================
# TEXTURE-BASED CONTENT LOCALIZER
# Finds the real-content region (dense local texture = tissue) vs.
# flat/non-content areas (colour blocks, black borders, blanks). The KEY
# trick: score small tiles by the MEDIAN local standard deviation. Median
# ignores thin high-contrast boundary lines (a minority of pixels in a
# tile) while still responding to genuine tissue detail (which fills the
# tile) — so block boundaries that fool naive variance/edge approaches are
# ignored.
#
# HONEST SCOPE: this solves "find real-content vs non-content". It does NOT
# yet find a small anomaly WITHIN all-tissue (on a real otoscope frame
# that's tissue edge-to-edge, it localizes the whole tissue area). Finding
# a specific lesion within that still needs the planned trained detector.
# ================================================================
def texture_map(img, win=9):
    """Per-pixel local standard deviation over a (win x win) neighbourhood."""
    from scipy import ndimage
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float64)
    mean = ndimage.uniform_filter(gray, win)
    sq = ndimage.uniform_filter(gray ** 2, win)
    return np.sqrt(np.maximum(sq - mean ** 2, 0))


def localize_by_texture(img, tile=TEXTURE_TILE, tile_thresh=TEXTURE_TILE_THRESH):
    """Return content box [x1,y1,x2,y2], or None if no textured region.

    Divides the local-std map into (tile x tile) blocks and flags a block
    as "textured" when its MEDIAN local-std exceeds tile_thresh. Returns the
    bounding box of all textured blocks. Median (not mean) is what makes it
    robust to the minority-of-pixels boundary lines between flat regions."""
    ls = texture_map(img)
    h, w = ls.shape
    ny, nx = h // tile, w // tile
    if ny == 0 or nx == 0:
        return None
    hot = np.zeros((ny, nx), dtype=bool)
    for ty in range(ny):
        for tx in range(nx):
            block = ls[ty * tile:(ty + 1) * tile, tx * tile:(tx + 1) * tile]
            if block.size and np.median(block) > tile_thresh:
                hot[ty, tx] = True
    if not hot.any():
        return None
    ys, xs = np.where(hot)
    return [int(xs.min() * tile), int(ys.min() * tile),
            int((xs.max() + 1) * tile), int((ys.max() + 1) * tile)]


def compute_adaptive_grid(box, frame_width, frame_height,
                          cells_per_side=GRID_CELLS_PER_ANOMALY_SIDE,
                          min_cells=GRID_MIN_CELLS, max_cells=GRID_MAX_CELLS):
    """Derive a grid whose cell size makes the anomaly span ~N cells per axis.

    Uses SEPARATE unit sizes per axis so the box spans ~N cells in BOTH
    dimensions regardless of its aspect ratio:
        col_unit = box_width  / cells_per_side   -> cols = round(frame_width  / col_unit)
        row_unit = box_height / cells_per_side   -> rows = round(frame_height / row_unit)
    (The earlier min(bw,bh)/N used a single unit for both axes, which made the
    larger box dimension span more than N cells — producing wide bands on
    non-square boxes/frames.) Both axes are clamped to [min_cells, max_cells];
    if clamping fires a one-line warning is logged. Returns (rows, cols)."""
    x1, y1, x2, y2 = box
    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    col_unit = max(1.0, box_w / max(1, cells_per_side))
    row_unit = max(1.0, box_h / max(1, cells_per_side))
    raw_cols = max(1, int(round(frame_width / col_unit)))
    raw_rows = max(1, int(round(frame_height / row_unit)))
    cols = min(max_cells, max(min_cells, raw_cols))
    rows = min(max_cells, max(min_cells, raw_rows))
    if rows != raw_rows or cols != raw_cols:
        kind = "small" if (raw_rows > max_cells or raw_cols > max_cells) else "large"
        print(f"[app][notice] adaptive grid clamped: box={box} "
              f"col_unit={col_unit:.1f}px row_unit={row_unit:.1f}px "
              f"raw={raw_rows}x{raw_cols} -> {rows}x{cols} (box seems unusually {kind} "
              f"relative to {frame_width}x{frame_height} frame).")
    return rows, cols


def cells_overlapping_box(box, frame_width, frame_height, rows, cols,
                          overlap_threshold=0.15):
    """Every grid cell the detection box meaningfully overlaps.

    For each cell we compute (cell ∩ box area) / cell_area — i.e. what
    fraction of THAT CELL is covered by the anomaly — and include the cell
    when that fraction exceeds overlap_threshold. The reference area is the
    CELL (not the box) so the metric is stable across grid densities: with
    the unit-size tiling the anomaly's box spans ~N×N cells, and every cell
    it passes through is flagged regardless of how fine the grid is. An
    anomaly straddling a boundary therefore highlights ALL the cells it
    spills into, not just one. Returns a list of {"row","col","cell_box"}."""
    bx1, by1, bx2, by2 = box
    cell_w = frame_width / cols
    cell_h = frame_height / rows
    cell_area = max(1.0, cell_w * cell_h)
    out = []
    for r in range(rows):
        for c in range(cols):
            cx1 = c * cell_w
            cy1 = r * cell_h
            cx2 = (c + 1) * cell_w
            cy2 = (r + 1) * cell_h
            ix1 = max(bx1, cx1)
            iy1 = max(by1, cy1)
            ix2 = min(bx2, cx2)
            iy2 = min(by2, cy2)
            if ix2 <= ix1 or iy2 <= iy1:
                continue
            overlap = ((ix2 - ix1) * (iy2 - iy1)) / cell_area
            if overlap >= overlap_threshold:
                out.append({
                    "row": r,
                    "col": c,
                    "cell_box": [int(round(cx1)), int(round(cy1)),
                                 int(round(cx2)), int(round(cy2))],
                })
    return out


def _detect(mode, frame):
    """Run the pipeline (localize -> crop -> classify) on one frame for
    `mode`. Returns a dict with the structured result plus the pieces
    needed to draw the overlay. Shared by /activate (single-shot) and
    /stream_detect (live) so both stay in perfect step."""
    h, w = frame.shape[:2]

    # --- LOCALIZE ---
    # LOCALIZER_MODE selects which method draws the box (and so the crop the
    # sklearn classifier sees). The box feeds the SAME downstream pipeline
    # (adaptive_grid -> overlapping_cells -> crop -> sklearn) regardless of
    # which localizer produced it, so the three are interchangeable.
    #   yolo:    trained detector; per-frame fallback to texture on 0 boxes
    #   texture: median-local-std content finder
    #   stub:    fixed centre-60% box
    # YOLO landmarks (USE_REAL_MODEL path) are still collected for the
    # secondary annotation drawing; they don't affect classification.
    raw_landmarks, yolo_box, yolo_kind = localize_landmarks(frame, mode)

    if LOCALIZER_MODE == "yolo":
        yb = None
        try:
            yb = localize_by_yolo_ear(frame)
        except Exception as exc:
            print(f"[localizer][warn] YOLO inference failed ({exc}); trying texture")
        if yb is not None:
            box = yb
            localizer = "yolo"
        else:
            # Zero detections this frame -> texture fallback (NOT a crash).
            tb = localize_by_texture(frame)
            if tb is not None:
                box = tb
                localizer = "texture"
            else:
                box = _stub_box(h, w)
                localizer = "stub"
    elif LOCALIZER_MODE == "texture":
        tb = None
        try:
            tb = localize_by_texture(frame)
        except Exception as exc:
            print(f"[app][warn] texture localizer failed ({exc}); using {yolo_kind} box")
        if tb is not None:
            box = tb
            localizer = "texture"
        else:
            box = _stub_box(h, w)
            localizer = "stub"
    else:  # "stub" or anything else
        box = yolo_box
        localizer = yolo_kind

    # --- CROP + CLASSIFY ---
    # Classification ALWAYS sees the localized region (texture box when on),
    # not the whole frame — this is what makes /classify_upload on a frame
    # full of colour blocks classify just the real ear in the corner.
    crop = crop_box(frame, box)
    cls, conf, scores = classify_crop(mode, crop)
    meta = meta_for(mode, cls)
    scores_sorted = sorted(scores, key=lambda kv: kv[1], reverse=True)

    # Normalise landmark boxes (0-1) for the response + overlay drawing.
    landmarks = [
        {
            "label": lm["label"],
            "box": lm["box"],
            "box_norm": _norm(lm["box"], w, h),
            "role": lm["role"],
            "confidence": lm["confidence"],
        }
        for lm in raw_landmarks
    ]
    primary = next((lm for lm in landmarks if lm["role"] == "primary"), None)
    loc_conf = primary["confidence"] if primary else None

    result = {
        "class": cls,
        "label": meta["label"],
        "status": meta["status"],
        "box": box,
        "box_norm": _norm(box, w, h),
        "confidence": round(conf, 4),
        "explanation": meta["explanation"],
        "scores": [
            {"class": c, "label": meta_for(mode, c)["label"], "p": round(p, 4)}
            for c, p in scores_sorted
        ],
    }
    # Adaptive grid: resolution is derived from THIS box's size. The grid
    # tiles the ENTIRE frame (cell (0,0) starts at frame origin), and only
    # the cells the box overlaps are highlighted. A short class abbreviation
    # is attached to each highlighted cell for the on-image label.
    box_w = max(1, box[2] - box[0])
    box_h = max(1, box[3] - box[1])
    near_full = (box_w >= NEAR_FULL_FRAME_THRESHOLD * w and
                 box_h >= NEAR_FULL_FRAME_THRESHOLD * h)

    if near_full:
        # The finding fills most of the visible area — don't fragment it
        # into NxN cells. Use a coarse 2×2 grid and highlight just the one
        # cell containing the box's centre, representing "fills the view".
        grid_rows, grid_cols = 2, 2
        cx = (box[0] + box[2]) / 2.0
        cy = (box[1] + box[3]) / 2.0
        cc = min(grid_cols - 1, max(0, int(cx // (w / grid_cols))))
        cr = min(grid_rows - 1, max(0, int(cy // (h / grid_rows))))
        cw = w / grid_cols
        ch = h / grid_rows
        cells = [{
            "row": cr, "col": cc,
            "cell_box": [int(round(cc * cw)), int(round(cr * ch)),
                         int(round((cc + 1) * cw)), int(round((cr + 1) * ch))],
            "label": cls,
        }]
    else:
        grid_rows, grid_cols = compute_adaptive_grid(box, w, h)
        cells = cells_overlapping_box(box, w, h, grid_rows, grid_cols)
        for c in cells:
            c["label"] = cls

    grid = {
        "rows": grid_rows,
        "cols": grid_cols,
        "highlighted_cells": cells,
    }
    return {
        "box": box,
        "landmarks": landmarks,
        "overlay_text": f"{meta['label']} {conf * 100:.0f}%",
        "localizer": localizer,
        "classifier": "trained" if _get_classifier(mode) is not None else "stub",
        "frame_size": [w, h],
        "localization": {"box": box, "box_norm": _norm(box, w, h), "confidence": loc_conf},
        "result": result,
        "grid": grid,
    }


# ================================================================
# Routes
# ================================================================
@app.route("/")
def index():
    """Serve the built React app (frontend/dist) when present; fall back to
    the legacy single-file template otherwise."""
    if (FRONTEND_DIST / "index.html").exists():
        return send_from_directory(FRONTEND_DIST, "index.html")
    return render_template("index.html")


@app.route("/assets/<path:filename>")
def frontend_assets(filename):
    return send_from_directory(FRONTEND_DIST / "assets", filename)


@app.route("/<path:filename>")
def frontend_public(filename):
    """Files copied from frontend/public (card images, favicons...). Explicit
    routes above (/video_feed, /activate, /camera_status, /static, /assets)
    take precedence."""
    target = FRONTEND_DIST / filename
    if FRONTEND_DIST.exists() and target.is_file():
        return send_from_directory(FRONTEND_DIST, filename)
    return jsonify({"error": "not found"}), 404


@app.route("/video_feed")
def video_feed():
    """Self-Check Mode: raw live feed (or fallback frame), no AI overlay."""
    return Response(generate_frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/camera_status")
def camera_status():
    """Whether the active camera source is currently reachable, so the
    frontend can show an 'awaiting endoscope' state instead of guessing
    from a failed <img> load. Includes the source itself so the Practice
    page's camera picker can show what's active on load/refresh."""
    cap = open_camera()
    connected = cap is not None
    if cap is not None:
        cap.release()
    return jsonify({"connected": connected, "source": get_camera_state()})


@app.route("/camera_options")
def camera_options():
    """Local webcam indices that actually open, plus the active source —
    populates the Practice page's camera picker."""
    return jsonify({"webcams": probe_webcams(), "source": get_camera_state()})


@app.route("/camera_source", methods=["POST"])
def set_camera_source():
    """Switch the active camera source (Practice page's camera picker).
    Body: {"type": "webcam", "index": 0} or {"type": "phone", "url": "http://..."}.
    Existing MJPEG connections (video_feed/stream_detect) keep the OLD
    source until the frontend remounts them — this only flips what the
    NEXT open_camera() call picks up."""
    body = request.get_json(silent=True) or {}
    kind = body.get("type")
    if kind == "webcam":
        try:
            idx = int(body.get("index", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "index must be an integer"}), 400
        with _camera_lock:
            _camera_state["type"] = "webcam"
            _camera_state["webcam_index"] = idx
    elif kind == "phone":
        url = (body.get("url") or "").strip()
        if not url:
            return jsonify({"error": "url is required for a phone source"}), 400
        with _camera_lock:
            _camera_state["type"] = "phone"
            _camera_state["phone_url"] = url
    else:
        return jsonify({"error": "type must be 'webcam' or 'phone'"}), 400

    cap = open_camera()
    connected = cap is not None
    if cap is not None:
        cap.release()
    return jsonify({"connected": connected, "source": get_camera_state()})


def stream_detect_frames(mode):
    """Continuous-detection MJPEG: the SAME pipeline as /activate, run on a
    throttled subset of live frames with the overlay burned into every
    frame. Video streams at full camera fps; inference runs ~every
    STREAM_INFER_INTERVAL and the last box/label is reused on skipped
    frames so the overlay never flickers blank. Same no-camera fallback as
    generate_frames (sample -> synthetic)."""
    cap = open_camera()
    use_camera = cap is not None
    if use_camera:
        static_frame, source = None, "camera"
    else:
        sample = _load_sample_frame()
        static_frame = sample if sample is not None else _synthetic_frame()
        source = "sample" if sample is not None else "synthetic"

    last_infer = 0.0
    last_box = None
    last_text = ""
    last_landmarks = None
    consecutive_read_failures = 0
    try:
        while True:
            if use_camera:
                ok, frame = cap.read()
                if not ok:
                    consecutive_read_failures += 1
                    print(f"[stream][warn] cap.read() failed (mode={mode}, "
                          f"{consecutive_read_failures}x) — source stalled or dropped.")
                    # Network sources (e.g. a phone MJPEG stream) can drop a frame
                    # without the connection itself dying; only give up after a
                    # real run of failures, not one blip.
                    if consecutive_read_failures >= 10:
                        break
                    continue
                consecutive_read_failures = 0
            else:
                frame = static_frame.copy()

            now = time.time()
            if now - last_infer >= STREAM_INFER_INTERVAL:
                last_infer = now
                try:
                    d = _detect(mode, frame)
                except Exception as exc:
                    # A single bad frame (e.g. a torn/corrupt JPEG from a lossy
                    # network relay) must not kill the whole stream — log it and
                    # keep showing the last good overlay instead.
                    print(f"[stream][warn] _detect failed on one frame (mode={mode}): {exc}")
                else:
                    last_box = d["box"]
                    last_text = d["overlay_text"]
                    last_landmarks = d["landmarks"]
                    with _stream_lock:
                        _latest_result[mode] = {
                            "timestamp": now, "mode": mode, "source": source,
                            "localizer": d["localizer"], "classifier": d["classifier"],
                            "frame_size": d["frame_size"], "localization": d["localization"],
                            "results": [d["result"]],
                            "landmarks": d["landmarks"],
                            "grid": d["grid"],
                        }

            annotated = (draw_overlay(frame, last_box, last_text, last_landmarks)
                         if last_box is not None else frame)
            ok, buffer = cv2.imencode(".jpg", annotated)
            if not ok:
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
            if not use_camera:
                time.sleep(0.2)  # don't busy-spin on a static fallback frame
    finally:
        if cap is not None:
            cap.release()


@app.route("/stream_detect")
def stream_detect():
    """Live continuous detection stream (annotated MJPEG) for one mode.
    Companion to /last_result, which serves the matching text/result."""
    mode = resolve_mode(request.args.get("mode"))
    return Response(stream_detect_frames(mode),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/last_result")
def last_result():
    """Latest structured detection from the live stream, for the findings
    panel to poll while in Live mode. Empty until the stream has produced
    its first inference for that mode."""
    mode = resolve_mode(request.args.get("mode"))
    with _stream_lock:
        payload = _latest_result.get(mode)
    if payload is None:
        return jsonify({"mode": mode, "pending": True, "results": []})
    return jsonify(payload)


@app.route("/activate", methods=["POST"])
def activate():
    """Run the full pipeline on one frame for the requested mode (ear /
    nose / throat, default ear) and return JSON the frontend uses to
    freeze the frame and draw the overlay + result panel."""
    body = request.get_json(silent=True) or {}
    mode = resolve_mode(request.args.get("mode") or body.get("mode"))
    try:
        frame, source = grab_single_frame()          # 1. capture one frame
        d = _detect(mode, frame)                     # 2-4. localize -> crop -> classify
        annotated = draw_overlay(frame, d["box"], d["overlay_text"], d["landmarks"])  # 5. draw
        if SAVE_ANNOTATED:
            (ROOT / "static").mkdir(exist_ok=True)
            cv2.imwrite(str(ROOT / "static" / f"last_activation_{mode}.jpg"), annotated)

        return jsonify({
            "timestamp": time.time(),
            "mode": mode,
            "source": source,
            "localizer": d["localizer"],
            "classifier": d["classifier"],
            "frame": _b64_jpeg(frame),
            "frame_size": d["frame_size"],
            "localization": d["localization"],
            "results": [d["result"]],
            "landmarks": d["landmarks"],
            "grid": d["grid"],
        })
    except Exception as exc:
        print(f"[app][error] /activate failed (mode={mode}): {exc}")
        return jsonify({"error": str(exc)}), 500


UPLOAD_EXTS = {".png", ".jpg", ".jpeg"}


@app.route("/classify_upload", methods=["POST"])
def classify_upload():
    """Clarify mode: classify an UPLOADED image instead of a camera frame.
    Same pipeline and same response shape as /activate, so the frontend can
    reuse its result rendering. Accepts multipart/form-data with an 'image'
    field (PNG/JPG only)."""
    mode = resolve_mode(request.args.get("mode") or request.form.get("mode"))

    file = request.files.get("image")
    if file is None or not file.filename:
        return jsonify({"error": "No image uploaded."}), 400

    ext = Path(file.filename).suffix.lower()
    if ext not in UPLOAD_EXTS:
        return jsonify({"error": f"Unsupported file type '{ext or '?'}'. Please upload a PNG or JPG image."}), 400

    try:
        raw = np.frombuffer(file.read(), dtype=np.uint8)
        frame = cv2.imdecode(raw, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Could not read that image — it may be corrupt or not a real PNG/JPG."}), 400

        d = _detect(mode, frame)                                     # localize -> crop -> classify
        annotated = draw_overlay(frame, d["box"], d["overlay_text"], d["landmarks"])  # draw
        if SAVE_ANNOTATED:
            (ROOT / "static").mkdir(exist_ok=True)
            cv2.imwrite(str(ROOT / "static" / f"last_upload_{mode}.jpg"), annotated)

        return jsonify({
            "timestamp": time.time(),
            "mode": mode,
            "source": "upload",
            "localizer": d["localizer"],
            "classifier": d["classifier"],
            "frame": _b64_jpeg(frame),
            "frame_size": d["frame_size"],
            "localization": d["localization"],
            "results": [d["result"]],
            "landmarks": d["landmarks"],
            "grid": d["grid"],
        })
    except Exception as exc:
        print(f"[app][error] /classify_upload failed (mode={mode}): {exc}")
        return jsonify({"error": str(exc)}), 500


def _local_lan_ip() -> str:
    """Best-effort LAN-facing IP for the startup log (doesn't actually send
    anything — just asks the OS which interface would be used to reach the
    internet, which is normally the WiFi/ethernet adapter other devices see)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "?.?.?.?"
    finally:
        s.close()


def log_classifier_startup():
    """Loud, unambiguous per-mode classifier + localizer status in the
    terminal. Eagerly resolves each mode through the same _get_classifier()
    the request handlers use, so what you see here IS what they will use."""
    print("[app] MentoScope starting on http://127.0.0.1:5000 "
          f"(LAN: http://{_local_lan_ip()}:5000 — reachable from other devices, "
          "e.g. a frontend build served from a Pi)")
    print(f"[app] USE_REAL_MODEL={USE_REAL_MODEL} (YOLO-World landmark prompts)")
    print(f"[app] USE_TEXTURE_LOCALIZER={USE_TEXTURE_LOCALIZER} "
          f"(tile={TEXTURE_TILE}px, thresh={TEXTURE_TILE_THRESH})")
    # Resolve the localizer and print clearly which one is active + why.
    if LOCALIZER_MODE == "yolo":
        if (ROOT / YOLO_EAR_WEIGHTS).exists():
            _get_yolo_ear()  # logs "[localizer] YOLO model loaded from ..."
            print(f"[localizer] LOCALIZER_MODE=yolo (weights: {YOLO_EAR_WEIGHTS})")
        else:
            print(f"[localizer] yolo_ear.pt not found, falling back to texture localizer")
    elif LOCALIZER_MODE == "texture":
        print(f"[localizer] LOCALIZER_MODE=texture "
              f"(tile={TEXTURE_TILE}px, thresh={TEXTURE_TILE_THRESH})")
    else:
        print(f"[localizer] LOCALIZER_MODE={LOCALIZER_MODE} (centre-box)")
    print(f"[app] models dir: {MODELS_DIR}")
    for _mode in MODES:
        _get_classifier(_mode)  # prints "[mode] classifier: LOADED|STUB — <path> ..."
    print("[app] models are hot-reloaded on file change — after training you do NOT")
    print("[app] need to restart this server; the next request picks the new model up.")


if __name__ == "__main__":
    log_classifier_startup()
    # host="0.0.0.0": bind every interface, not just loopback, so a frontend
    # running elsewhere on the LAN (another PC, a Pi) can actually reach this
    # backend. Windows will prompt for a Firewall exception the first time —
    # allow it on Private networks.
    app.run(host="0.0.0.0", debug=True, port=5000, threaded=True)