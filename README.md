# MentoScope

An AI-assisted **ENT trainer** for nursing and medical students, covering
three exam **modes** — **Ear**, **Nose**, **Throat** — selected in the UI.
A student looks at a live circular endoscope feed, tries to read the target
region themselves (**Self-Check**), then presses **Activate** — the app
localizes that mode's anatomical region and classifies its condition, the
way an instructor would point over their shoulder.

---

## Two-stage detection pipeline, per mode

MentoScope deliberately separates *where* from *what* — two different models
making two different claims — and runs the whole pipeline **once per mode**,
with no shared state between modes:

| Stage | Tool | Job | Output |
|------|------|-----|--------|
| **1. Localize** | YOLO-World | Find the mode's target region (e.g. tympanic membrane for ear). **Never judges health** — it draws the box in the same place whether the region is normal or diseased. | one box `[x1,y1,x2,y2]` |
| **2. Classify** | scikit-learn (RandomForest on HOG + colour-histogram features) | Look at **only the cropped box** and decide the condition, using that mode's own trained model. This is the *only* step that says normal vs. abnormal. | class label + confidence |

Full flow inside `/activate`:

```
OpenCV grab frame → YOLO-World localize (mode's prompt) → crop box → sklearn classify (mode's model) → OpenCV draw box + label
```

Mode is a first-class parameter — see `MODES` at the top of
`mentoscope_app.py`. Each mode defines its own YOLO-World prompt, its own
class list, and its own model file:

| Mode | YOLO-World prompt | Classes | Model files |
|------|---|---|---|
| `ear` | "tympanic membrane" | `Normal`, `AOM`, `OME`, `Otitis_Externa`, `Cerumen` | `classifier_ear.joblib` / `scaler_ear.joblib` |
| `nose` | "nasal turbinate" | `Normal`, `Allergic_Rhinitis`, `Nasal_Polyp`, `Deviated_Septum` *(starting-point placeholders — refine once real data exists)* | `classifier_nose.joblib` / `scaler_nose.joblib` |
| `throat` | "tonsil" | `Normal`, `Pharyngitis`, `Tonsillitis` *(starting-point placeholders — refine once real data exists)* | `classifier_throat.joblib` / `scaler_throat.joblib` |

Explanations are a fixed, factual text lookup per class (no LLM), defined
alongside each mode's classes in `MODES`.

---

## It runs in STUB mode until you train it — per mode, independently

The app **always runs**, even with no camera, no model, and no GPU. Each
mode's classifier loads lazily and independently, so a missing `nose` model
never affects `ear` (or vice versa):

- **No camera?** `grab_single_frame()` falls back to the first image in
  `static/samples/`, or a synthetic frame. Mode-agnostic — it's the same
  physical camera regardless of what's being examined.
- **No trained model for a mode?** that mode's classifier returns
  `Normal @ 0%` and logs a warning. The pipeline shape, routes, and UI all
  work — you just get real accuracy *after* training that specific mode.
- **YOLO-World** is behind `USE_REAL_MODEL` (default `False` → a fixed
  centre-60% box, regardless of mode). Flip it to `True` to use real
  `ultralytics` detection; the active mode's prompt is applied automatically.

So the demo works today for all three modes; the intelligence drops in one
mode at a time without touching the frontend or the routes.

---

## Train a classifier (turn stub → real, one mode at a time)

### 1. Organise the dataset — one subfolder per mode, never mixed

```
data set/
    ear/
        Normal/            *.jpg …
        AOM/               *.jpg …
        OME/               *.jpg …
        Otitis_Externa/    *.jpg …
        Cerumen/           *.jpg …
    nose/
        Normal/            *.jpg …
        Allergic_Rhinitis/ *.jpg …
        Nasal_Polyp/       *.jpg …
        Deviated_Septum/   *.jpg …
    throat/
        Normal/            *.jpg …
        Pharyngitis/       *.jpg …
        Tonsillitis/       *.jpg …
```

For `ear`, the Kaggle **"eardrum dataset otitis media"** (by *erdalbasaran*)
sorted into the class folders above works well. Nose/throat classes are
starting points — adjust `MODES` in `mentoscope_app.py` and the folder names
here together if you change them.

Each mode's classifier trains **only** on its own `data set/<mode>/` folder
and writes **only** its own model file — there's no path where one mode's
images or model can affect another's. If a mode's folder is missing or
empty, `train_classifier.py` prints exactly what's expected for that mode
instead of crashing.

### 2. Train

```bash
python train_classifier.py                # trains "ear" (default)
python train_classifier.py --mode nose
python train_classifier.py --mode throat
```

Each run extracts HOG + HSV-colour-histogram features (see `features.py`),
scales them, fits a `RandomForestClassifier` on a stratified train/test
split, prints a per-class classification report, and saves that mode's:

```
models/classifier_<mode>.joblib
models/scaler_<mode>.joblib
models/meta_<mode>.json          # classes, n_samples, localizer used, trained_at
```

### No restart needed

The app **hot-reloads models**. `_get_classifier()` re-checks the model file's
mtime on every request, so:

- train while the server is running → the **next request** uses the new model
- delete a model → that mode falls straight back to its stub

You should never be debugging a "stuck stub" that's really a stale process. The
terminal running `mentoscope_app.py` prints one loud line per mode at startup
**and** whenever a model is (re)loaded or falls back:

```
[ear] classifier: LOADED — …\models\classifier_ear.joblib (trained on 3014 samples, 5 classes)
[nose] classifier: STUB — …\models\classifier_nose.joblib not found (run: python train_classifier.py --mode nose)
```

### Training preprocessing must match inference

The classifier only ever sees **the localizer's crop**, never the whole frame.
So `train_classifier.py` runs every training image through the app's own
`localize_region()` → `crop_box()` before extracting features — the identical
two steps `/activate`, `/stream_detect` and `/classify_upload` apply.

> Training on full images while serving centre-crops silently wrecks accuracy
> (a real AOM image scored `AOM 98%` on the full image but `Cerumen 31%` on the
> served crop). The crop the model learns on **must** be the crop it is given.

Because of this, a model is tied to the localizer it was trained with. The
metadata records `use_real_model`, and the app prints a loud `WARNING` if you
flip `USE_REAL_MODEL` without retraining.

> `features.py` is imported by **both** the trainer and the app for
> **every mode**, so training and inference use identical features by
> construction — they can't drift. `train_classifier.py` also imports
> `MODES` directly from `mentoscope_app.py`, so a mode's class list and
> model paths are defined in exactly one place.

---

## Run the app

```bash
pip install flask opencv-python numpy scikit-image scikit-learn joblib
# for real localization only (optional): pip install ultralytics
python mentoscope_app.py       # → http://127.0.0.1:5000
```

### Frontend (React + Vite, 3 pages)

The UI lives in `frontend/` — a dark-clinical React app with hash routing:

- `#/` **Landing** — choose Practice Mode or Theory (image cards)
- `#/practice` **Practice** — the scope + activate + findings workbench, with a
  **Live / Freeze** toggle:
  - **Freeze** — press **Activate** to grab one frame and inspect the static
    annotated result + findings in detail (single-shot `/activate`).
  - **Live** — the scope points at `/stream_detect?mode=<mode>` for continuous
    real-time detection, and the findings panel polls `/last_result?mode=<mode>`
    so the label/confidence/explanation update live as you move the scope.
    Switching back to Freeze (or leaving the page) unmounts the stream `<img>`
    and clears the poll, so no connection is left hanging.
- `#/clarify` **Clarify** — *Detect with Image*. Upload a PNG/JPG (drag-and-drop
  onto the scope or click to browse; other file types are rejected inline) and it
  runs the **same** pipeline as Practice for the selected region, showing the
  annotated result + findings with the same result view. Backed by
  `POST /classify_upload`.
- `#/theory` **Theory** — tutorial (placeholder for now)

```bash
cd frontend
npm install
npm run build    # → frontend/dist, served automatically by Flask at /
npm run dev      # dev server on :5173, proxies API calls to Flask (run Flask alongside)
```

Flask serves `frontend/dist` when it exists and falls back to the legacy
`templates/index.html` otherwise.

> **Adding a backend route?** Also add it to `API_ROUTES` in
> `frontend/vite.config.js`. If you don't, `npm run dev` serves `index.html`
> for that path instead of proxying it, `res.json()` throws, and the UI reports
> a misleading *"Upload failed — is the server running?"* even though Flask is
> running perfectly. (This is exactly what broke Clarify: `/classify_upload`
> was missing from the proxy list.)

### Routes
- `GET /` — the trainer UI (React build if present, else `templates/index.html`)
- `GET /video_feed` — MJPEG live preview (falls back to a sample/synthetic frame; mode-agnostic, same camera regardless of mode)
- `GET /camera_status` — `{"connected": bool}`, whether `open_camera()` currently succeeds. Lets the frontend show an "awaiting endoscope" state instead of waiting for a broken `<img>`.
- `GET /stream_detect?mode=<mode>` — **live continuous detection.** Runs the same pipeline as `/activate` on live frames and streams annotated JPEGs (`multipart/x-mixed-replace`, same as `/video_feed`) with the detection box + label **burned into every frame**. Inference is throttled to ~8 fps (`STREAM_INFER_INTERVAL`) while video streams at full camera fps; the last box/label is reused on skipped frames so the overlay never flickers. Same no-camera fallback (sample → synthetic) and same per-mode config as everything else.
- `GET /last_result?mode=<mode>` — companion to `/stream_detect`: the latest structured detection (label, confidence, explanation, scores…) for that mode, so the findings panel can poll it while Live. Returns `{"pending": true, "results": []}` until the stream has produced its first inference.
- `POST /classify_upload?mode=<mode>` — **Clarify mode.** `multipart/form-data` with an `image` field (PNG/JPG only; other types or corrupt files get a clear 400 JSON error). Runs the identical pipeline as `/activate` on the uploaded image and returns the **same response shape**, so the frontend reuses the exact result view.
- `POST /activate` — **single-shot** ("Freeze"): runs the pipeline **for one mode** on one frame, returns JSON. Mode comes from a query param (`/activate?mode=nose`) or a JSON body (`{"mode": "nose"}`); defaults to `"ear"` if omitted or unrecognised:

```jsonc
{
  "mode": "nose",                        // which mode answered
  "source": "camera|sample|synthetic",
  "localizer": "yolo|stub",
  "classifier": "trained|stub",
  "frame": "data:image/jpeg;base64,…",   // captured frame, for the UI to freeze
  "frame_size": [w, h],
  "results": [{
    "class": "Allergic_Rhinitis",
    "label": "Allergic Rhinitis",
    "status": "attention",               // normal | attention | caution
    "box": [x1, y1, x2, y2],
    "box_norm": [fx1, fy1, fx2, fy2],     // 0–1, for overlay positioning
    "confidence": 0.88,
    "explanation": "…",
    "scores": [{ "class": "Allergic_Rhinitis", "label": "…", "p": 0.88 }, …]
  }]
}
```

The core `results` contract is a list of `{label, box, confidence, explanation}`
— the extra keys (`class`, `status`, `scores`, `box_norm`, and the top-level
`mode`) are additive so the UI can show which mode answered, a status chip,
and an honest per-class probability breakdown.

The Flask dev server runs with `threaded=True` so the MJPEG `/video_feed`
stream can't block a concurrent `/activate` call.

---

## Localization (`LOCALIZER_MODE`)

The box-drawing stage is selectable via `LOCALIZER_MODE` at the top of
`mentoscope_app.py`. It auto-resolves at startup:

| Mode | What draws the box | When to use |
|------|--------------------|-------------|
| **`"yolo"`** *(default if `models/yolo_ear.pt` exists)* | Trained **YOLOv8** detector — highest-confidence box per frame. On **zero detections** for a given frame, falls back to the texture localizer for that frame only (never crashes). | Real endoscope frames. |
| **`"texture"`** *(default otherwise)* | Classical CV: median local-standard-deviation per tile (`localize_by_texture`). Finds "real tissue vs. flat/non-content" — robust to colour-block boundaries via the median trick. | No trained detector available, or non-tissue backgrounds. |
| **`"stub"`** | Fixed centre-60% box. | Legacy fallback / debugging. |

> **Honest mAP50 caveat:** `models/yolo_ear.pt` was trained on **synthetic**
> images (real ear photos pasted onto solid-colour/gradient/noise backgrounds
> at random positions). Training mAP50 was **0.995**, but that validation set
> was generated the **same synthetic way** — it proves the synthetic-label
> generation technique works, **not** that the model is 99.5% accurate on real
> endoscope camera frames. Treat real-frame localization performance as
> unvalidated until tested on real otoscopy footage.

### YOLO's class output is intentionally unused

`yolo_ear.pt` predicts AOM/CSOM/Cerumen/etc. **directly** (it's a multi-class
detector). For now we **only use its bounding box** for localization — its
class prediction is discarded. The **scikit-learn classifier remains the
single source of truth** for the class label, to avoid two models producing
conflicting predictions. The box feeds the same downstream pipeline
(`adaptive_grid → overlapping_cells → crop → sklearn classify`) regardless of
which localizer produced it.

### Startup logging

The terminal prints clearly which localizer is active and why:

```
[localizer] YOLO model loaded from models/yolo_ear.pt
[localizer] LOCALIZER_MODE=yolo (weights: models/yolo_ear.pt)
```
or
```
[localizer] yolo_ear.pt not found, falling back to texture localizer
```

---

## Switches

| Where | Flag | Effect |
|-------|------|--------|
| `mentoscope_app.py` | `MODES` | per-mode config: YOLO-World prompt, class list + explanations, model/scaler paths |
| `mentoscope_app.py` | `LOCALIZER_MODE` | `"yolo"` / `"texture"` / `"stub"` — which method draws the detection box (auto-resolved; see above) |
| `mentoscope_app.py` | `USE_REAL_MODEL` | legacy: `True` = real YOLO-World (mode's prompt applied automatically), `False` = centre-box stub |
| `mentoscope_app.py` | `USE_TEXTURE_LOCALIZER` | enables the texture localizer as a fallback target |
| `mentoscope_app.py` | `CAMERA_INDEX` | which UVC device to open |
| `mentoscope_app.py` | `SAVE_ANNOTATED` | write `static/last_activation_<mode>.jpg` each activate |
| — | presence of `models/classifier_<mode>.joblib` | that mode's trained classifier vs. `Normal @ 0%` stub, independently per mode |
| — | presence of `models/yolo_ear.pt` | enables `LOCALIZER_MODE=yolo`; absence auto-falls-back to `"texture"` |

## Files

```
mentoscope_app.py     Flask app + the 5-step pipeline, per mode (MODES config, stub/real switches)
features.py           shared HOG + colour-hist extractor (train == infer, every mode)
train_classifier.py   trains one mode's sklearn classifier (--mode ear|nose|throat)
frontend/              React (Vite) UI — Landing / Practice / Theory
templates/index.html  legacy single-file UI, served only if frontend/dist is absent
static/samples/       drop one photo per class here (currently ear only — see the note file)
data set/              your labelled training images, one subfolder per mode
    ear/, nose/, throat/    each holding one subfolder per class
models/                created by training: classifier_<mode>.joblib, scaler_<mode>.joblib, meta_<mode>.json
```

> Note: this is a training aid, not a medical device — it supports supervised
> learning and is not a substitute for clinical examination or diagnosis.
