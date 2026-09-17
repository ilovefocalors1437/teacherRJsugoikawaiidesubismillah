from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ------------------------------------------------------------ styling helpers
TITLE_FILL = PatternFill("solid", fgColor="0F766E")   # clinical teal
HEAD_FILL = PatternFill("solid", fgColor="134E4A")
SUBHEAD_FILL = PatternFill("solid", fgColor="CCFBF1")
ZEBRA_FILL = PatternFill("solid", fgColor="F0FDFA")
WARN_FILL = PatternFill("solid", fgColor="FEF3C7")
OK_FILL = PatternFill("solid", fgColor="DCFCE7")

TITLE_FONT = Font(name="Calibri", size=18, bold=True, color="FFFFFF")
HEAD_FONT = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
SUBHEAD_FONT = Font(name="Calibri", size=11, bold=True, color="134E4A")
BODY_FONT = Font(name="Calibri", size=11, color="1F2937")
MONO_FONT = Font(name="Consolas", size=10, color="111827")

THIN = Side(style="thin", color="CBD5E1")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER_WRAP = Alignment(wrap_text=True, vertical="center", horizontal="center")


def set_widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def title_row(ws, text, span):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=span)
    c = ws.cell(row=1, column=1, value=text)
    c.font = TITLE_FONT
    c.fill = TITLE_FILL
    c.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[1].height = 34


def header_row(ws, row, headers, fill=HEAD_FILL, font=HEAD_FONT):
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = font
        c.fill = fill
        c.alignment = CENTER_WRAP
        c.border = BORDER
    ws.row_dimensions[row].height = 22


def data_rows(ws, start_row, rows, zebra=True, mono_cols=None):
    mono_cols = mono_cols or set()
    for r_off, row in enumerate(rows):
        r = start_row + r_off
        for c_off, val in enumerate(row, start=1):
            c = ws.cell(row=r, column=c_off, value=val)
            c.font = MONO_FONT if c_off in mono_cols else BODY_FONT
            c.alignment = WRAP
            c.border = BORDER
            if zebra and r_off % 2 == 1:
                c.fill = ZEBRA_FILL


def section_title(ws, row, text, span):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=span)
    c = ws.cell(row=row, column=1, value=text)
    c.font = SUBHEAD_FONT
    c.fill = SUBHEAD_FILL
    c.alignment = Alignment(vertical="center", horizontal="left", indent=1)
    ws.row_dimensions[row].height = 24


# ================================================================ workbook
wb = Workbook()

# ------------------------------------------------ 1. OVERVIEW
ws = wb.active
ws.title = "1. Overview"
set_widths(ws, [26, 95])
title_row(ws, "MentoScope — Project Overview", 2)

section_title(ws, 3, "What it is", 2)
overview = [
    ("Name", "MentoScope"),
    ("Type", "AI-assisted ENT (Ear / Nose / Throat) otoscopy TRAINING app — a teaching aid, explicitly NOT a medical device."),
    ("Audience", "Nursing and medical students learning otoscopy / rhinoscopy / pharyngoscopy in a skills lab or at a demo station."),
    ("Job to be done", "“Am I looking at the drum, and does it look normal or like a common pathology?”"),
    ("Metaphor", "Behaves like an experienced instructor pointing over the student's shoulder — localizes the right region, then classifies it."),
    ("Register", "Product (clinical, assured, teacherly) — calibrated equipment, not a consumer app."),
    ("Backend", "Python / Flask (single file: mentoscope_app.py). Threaded dev server on port 5000."),
    ("Frontend", "React 18 + Vite (frontend/), hash-routed (works from Flask or file://). 4 pages: Landing / Practice / Clarify / Theory."),
    ("ML stack", "CPU-only. scikit-learn RandomForest on HOG + HSV features (features.py). Optional YOLO-World for localization."),
    ("Runs today?", "YES — end-to-end in STUB mode with no camera, no model, no GPU. Intelligence drops in per-mode independently."),
    ("Currently trained", "EAR classifier only (3014 samples, 5 classes). Nose & Throat are placeholders → return “Normal @ 0%” stubs."),
    ("Repo root", "C:\\Users\\LENOVO\\Desktop\\Basic Python\\MentoScope"),
]
header_row(ws, 4, ["Field", "Detail"])
data_rows(ws, 5, overview)

# ------------------------------------------------ 2. CORE IDEA (pipeline)
ws = wb.create_sheet("2. Core Pipeline")
set_widths(ws, [6, 18, 26, 38, 34])
title_row(ws, "Two-Stage Detection Pipeline — “WHERE vs. WHAT”", 5)
note = (
    "The central design insight: SEPARATE localization from classification. "
    "The box always means the same thing (‘target region here’); only the label says "
    "what the condition is. Runs once per exam mode, no shared state between modes."
)
ws.merge_cells("A3:E3")
c = ws.cell(row=3, column=1, value=note)
c.font = Font(italic=True, color="0F766E"); c.alignment = WRAP
ws.row_dimensions[3].height = 42

header_row(ws, 5, ["#", "Stage", "Tool", "Job", "Output"])
pipe = [
    (1, "Capture", "OpenCV (cv2.VideoCapture)",
     "Grab one BGR frame from the endoscope / webcam. Falls back to sample image → synthetic frame.",
     "frame (HxWx3 BGR)"),
    (2, "Localize", "YOLO-World (gated by USE_REAL_MODEL)",
     "Find the mode's target region (e.g. tympanic membrane). NEVER judges health — draws the same box whether healthy or diseased. Only answers WHERE.",
     "one box [x1,y1,x2,y2] + confidence"),
    (3, "Crop", "crop_box()",
     "Take only the pixels inside the box (clamped to frame). Degenerate box → returns whole frame.",
     "cropped image"),
    (4, "Classify", "scikit-learn RandomForest (per-mode .joblib)",
     "Decide the condition using THAT MODE'S OWN model, trained on the same kind of crop. The ONLY step that says normal vs. abnormal.",
     "class label + confidence + per-class scores"),
    (5, "Draw", "OpenCV draw_overlay()",
     "Burn the localization box (teal) + classification label into a copy of the frame.",
     "annotated frame"),
]
data_rows(ws, 6, pipe)

section_title(ws, 13, "Why this matters (anti-conflation)", 5)
why = [
    ("Design principle", "The box says HERE (constant meaning). The label says WHAT (variable). The UI must NEVER conflate the two."),
    ("Training implication", "The classifier only ever sees the localizer's CROP, never the full frame. So training images must go through the SAME localize→crop before feature extraction — or accuracy silently breaks. (A real AOM image scored AOM 98% on full image but Cerumen 31% on the served crop.)"),
    ("Stub-safe", "Each AI stage degrades to a stub independently, so the full 5-step pipeline shape always runs end-to-end."),
]
header_row(ws, 14, ["", "Topic", "", "Why", ""])
data_rows(ws, 15, [("", a, "", b, "") for a, b in why])

# ------------------------------------------------ 3. MODES & CLASSES
ws = wb.create_sheet("3. Modes & Classes")
set_widths(ws, [10, 22, 18, 30, 14, 52])
title_row(ws, "Exam Modes — each fully independent (own prompt, classes, model)", 6)
header_row(ws, 3, ["Mode", "Class key", "Label", "Status tier", "Folder name", "Explanation (plain language)"])

modes = [
    # ear
    ("ear", "Normal", "Normal", "normal", "Normal", "The tympanic membrane looks healthy — translucent and pearly-grey, with a clear cone of light and no bulging or fluid."),
    ("ear", "AOM", "Acute Otitis Media", "attention", "AOM", "The drum looks red and bulging, a sign of acute middle-ear infection with pus building up behind it."),
    ("ear", "Cerumen", "Cerumen Impaction", "caution", "Cerumen", "Ear wax is obscuring part of the drum and may need clearing before the membrane can be fully assessed."),
    ("ear", "CSOM", "Chronic Otitis Media", "attention", "CSOM", "A persistent, non-healing perforation of the eardrum with ongoing discharge — a long-standing problem, distinct from an acute infection."),
    ("ear", "Myringosclerosis", "Myringosclerosis", "caution", "Myringosclerosis", "Chalky white calcified patches on the eardrum, left behind by old healed infections or trauma — usually not urgent in itself, but worth noting."),
    # nose
    ("nose", "Normal", "Normal", "normal", "Normal", "The nasal turbinates and septum look healthy — pink mucosa, clear airway, no visible swelling or discharge."),
    ("nose", "Allergic_Rhinitis", "Allergic Rhinitis", "attention", "Allergic_Rhinitis", "The turbinates look swollen and pale or bluish, consistent with allergic inflammation rather than infection."),
    ("nose", "Nasal_Polyp", "Nasal Polyp", "attention", "Nasal_Polyp", "A smooth, pale, grape-like growth is visible in the nasal cavity, which can block airflow and needs specialist follow-up."),
    ("nose", "Deviated_Septum", "Deviated Septum", "attention", "Deviated_Septum", "The nasal septum is shifted to one side, narrowing one nasal passage relative to the other."),
    # throat
    ("throat", "Normal", "Normal", "normal", "Normal", "The tonsils and posterior pharynx look healthy — pink, symmetric, with no swelling, redness or exudate."),
    ("throat", "Pharyngitis", "Pharyngitis", "attention", "Pharyngitis", "The posterior pharynx looks red and inflamed, consistent with a sore throat from infection or irritation."),
    ("throat", "Tonsillitis", "Tonsillitis", "attention", "Tonsillitis", "The tonsils look enlarged and red, sometimes with white patches, suggesting an active infection."),
]
data_rows(ws, 4, modes)

section_title(ws, 17, "Per-mode technical config (from MODES in mentoscope_app.py)", 6)
header_row(ws, 18, ["Mode", "YOLO-World prompt", "Model file", "Scaler file", "Meta file", "Status"])
cfg_rows = [
    ("ear", "tympanic membrane", "models/classifier_ear.joblib", "models/scaler_ear.joblib", "models/meta_ear.json", "TRAINED — 3014 samples, 5 classes"),
    ("nose", "nasal turbinate", "models/classifier_nose.joblib", "models/scaler_nose.joblib", "models/meta_nose.json", "STUB — no dataset/model yet"),
    ("throat", "tonsil", "models/classifier_throat.joblib", "models/scaler_throat.joblib", "models/meta_throat.json", "STUB — no dataset/model yet"),
]
data_rows(ws, 19, cfg_rows)

# ------------------------------------------------ 4. BACKEND ROUTES & FUNCS
ws = wb.create_sheet("4. Backend (Flask)")
set_widths(ws, [22, 12, 34, 60])
title_row(ws, "Backend — mentoscope_app.py (Flask)", 4)
header_row(ws, 3, ["Route / Function", "Method", "Purpose", "Notes"])
routes = [
    ("GET /", "GET", "Serve the trainer UI", "React build (frontend/dist) if present, else legacy templates/index.html."),
    ("GET /video_feed", "GET", "Raw live MJPEG preview (no AI)", "Falls back to sample → synthetic frame. Mode-agnostic (same camera for all modes)."),
    ("GET /camera_status", "GET", "Is a real camera reachable?", "Returns {\"connected\": bool} so UI can show ‘awaiting endoscope’ instead of a broken <img>."),
    ("GET /stream_detect?mode=", "GET", "LIVE continuous detection MJPEG", "Same pipeline as /activate on throttled ~8 fps frames; box+label burned into every frame; reuses last box on skipped frames so overlay never flickers."),
    ("GET /last_result?mode=", "GET", "Latest structured detection for a mode", "Companion to /stream_detect for the findings panel to poll while Live. {\"pending\":true,\"results\":[]} until first inference."),
    ("POST /activate?mode=", "POST", "Single-shot ‘Freeze’ analysis on one frame", "Returns full JSON: frame (base64), results[], localizer kind, classifier kind. Default mode ‘ear’."),
    ("POST /classify_upload?mode=", "POST", "‘Clarify’ — classify an uploaded image", "multipart/form-data ‘image’ field, PNG/JPG only; corrupt/other → 400 JSON. Same response shape as /activate."),
    ("GET /assets/<path>", "GET", "Serve Vite-built JS/CSS assets", "From frontend/dist/assets."),
    ("GET /<path>", "GET", "Serve frontend/public files", "Falls through to 404 JSON if missing; explicit routes above take precedence."),
]
data_rows(ws, 4, routes, zebra=True)

section_title(ws, 14, "Key internal functions", 4)
header_row(ws, 15, ["Function", "Module", "Purpose", "Notes"])
funcs = [
    ("resolve_mode(raw)", "app", "Validate incoming mode string", "Falls back to DEFAULT_MODE (‘ear’) on unknown/None; prints a warning."),
    ("open_camera(index)", "app", "Open a cv2.VideoCapture or return None", "Uses CAMERA_INDEX."),
    ("_load_sample_frame()", "app", "First image in static/samples/", "Fallback when no camera."),
    ("_synthetic_frame(size)", "app", "Last-resort grey placeholder frame", "Always succeeds so pipeline never crashes."),
    ("grab_single_frame()", "app", "Capture ONE frame → (frame, source)", "source = ‘camera’ | ‘sample’ | ‘synthetic’."),
    ("generate_frames()", "app", "MJPEG generator for /video_feed", "Slow loop on fallback frames."),
    ("localize_region(frame, mode)", "app", "Stage 2 — find target region box", "Uses YOLO-World if USE_REAL_MODEL else centre-60% stub. Caches last prompt."),
    ("crop_box(frame, box)", "app", "Stage 3 — clamp + slice pixels", "Whole frame if degenerate (<4px)."),
    ("_get_classifier(mode)", "app", "Stage 4 — THE single lazy model loader", "mtime-based hot reload; per-mode cache; warns if trained localizer ≠ current."),
    ("classify_crop(mode, crop)", "app", "Run classifier on a crop", "Stub → (‘Normal’, 0.0, zeros). Else scaler.transform + predict_proba."),
    ("draw_overlay(frame, box, text)", "app", "Stage 5 — burn box + label", "Teal rectangle + filled label background."),
    ("_detect(mode, frame)", "app", "Full pipeline localize→crop→classify", "Shared by /activate and /stream_detect so they stay in sync."),
    ("log_classifier_startup()", "app", "Loud per-mode status at boot", "Prints LOADED/STUB line per mode + hot-reload reminder."),
    ("extract_features(bgr)", "features", "HOG + HSV histogram → 1-D vector", "Shared by trainer AND app so features can’t drift."),
    ("load_dataset(mode)", "train_classifier", "Load one mode's labelled images", "Exits with a clear ‘expected layout’ message if missing/empty/mismatched."),
    ("main()", "train_classifier", "Train + save one mode's model", "StandardScaler + stratified 80/20 + RandomForest(300, balanced); prints classification report."),
]
data_rows(ws, 16, funcs, mono_cols={1})

# ------------------------------------------------ 5. CONFIG / SWITCHES
ws = wb.create_sheet("5. Config & Switches")
set_widths(ws, [24, 16, 30, 56])
title_row(ws, "Configuration Switches & Constants", 4)
header_row(ws, 3, ["Name", "Default", "Where", "Effect"])
switches = [
    ("MODES", "(dict)", "mentoscope_app.py", "Per-mode config: YOLO prompt, class list + explanations, model/scaler/meta paths. THE single source of truth (imported by train_classifier.py too)."),
    ("DEFAULT_MODE", "‘ear’", "mentoscope_app.py", "Fallback mode when an endpoint gets an unknown/missing mode."),
    ("CAMERA_INDEX", "0", "mentoscope_app.py", "Which UVC device cv2.VideoCapture opens."),
    ("USE_REAL_MODEL", "False", "mentoscope_app.py", "True = real ultralytics YOLO-World localizer; False = fixed centre-60% stub box. Flipping without retraining prints a loud WARNING."),
    ("SAVE_ANNOTATED", "True", "mentoscope_app.py", "Write static/last_activation_<mode>.jpg (and last_upload_<mode>.jpg) each analysis."),
    ("YOLO_WEIGHTS", "‘yolov8s-world.pt’", "mentoscope_app.py", "Weights file for YOLO-World (only loaded if USE_REAL_MODEL=True)."),
    ("STREAM_INFER_INTERVAL", "0.12 s", "mentoscope_app.py", "~8 fps inference throttle for /stream_detect (video still streams at full camera fps)."),
    ("IMG_EXTS", "{jpg,jpeg,png,bmp,webp}", "app + trainer", "Recognised image extensions for samples/training."),
    ("UPLOAD_EXTS", "{png,jpg,jpeg}", "mentoscope_app.py", "Allowed types for /classify_upload."),
    ("IMG_SIZE", "(128,128)", "features.py", "Every crop resized to this before HOG. MUST match train vs infer (guaranteed by shared module)."),
    ("HOG_ORIENTATIONS", "9", "features.py", "HOG orientation bins."),
    ("HOG_PIXELS_PER_CELL", "(16,16)", "features.py", "HOG cell size."),
    ("HOG_CELLS_PER_BLOCK", "(2,2)", "features.py", "HOG block size."),
    ("HIST_BINS", "16", "features.py", "HSV histogram bins per channel (×3 = 48 colour features)."),
    ("RANDOM_STATE", "42", "train_classifier.py", "Reproducible train/test split + RandomForest."),
    ("TEST_SIZE", "0.2", "train_classifier.py", "20% held-out test set, stratified."),
    ("MIN_PER_CLASS", "2", "train_classifier.py", "Minimum images per class (stratified split needs ≥2)."),
    ("RF n_estimators", "300", "train_classifier.py", "RandomForest tree count; class_weight=‘balanced’, n_jobs=−1."),
    ("file presence", "(on disk)", "models/classifier_<mode>.joblib", "A mode is TRAINED vs STUB independently — just by whether its model file exists."),
]
data_rows(ws, 4, switches)

# ------------------------------------------------ 6. FILE INVENTORY
ws = wb.create_sheet("6. File Inventory")
set_widths(ws, [34, 14, 70])
title_row(ws, "File / Folder Inventory", 3)
header_row(ws, 3, ["Path", "Type", "Purpose"])
files = [
    ("mentoscope_app.py", "Python", "Flask app + the 5-step per-mode pipeline. MODES config, stub/real switches, all routes, hot-reload logic."),
    ("features.py", "Python", "Shared HOG + HSV feature extractor. Imported by BOTH trainer and app → train==infer guaranteed."),
    ("train_classifier.py", "Python", "Trains ONE mode's sklearn classifier (--mode ear|nose|throat). Reads data set/<mode>/, writes models/classifier_<mode>.*"),
    ("models/classifier_ear.joblib", "model", "Trained RandomForest for EAR (exists)."),
    ("models/scaler_ear.joblib", "model", "Fitted StandardScaler for EAR (exists)."),
    ("models/meta_ear.json", "json", "Ear model metadata: 3014 samples, 5 classes, 1812 features, trained 2026-07-10, localizer=stub."),
    ("models/classifier_nose.joblib", "model", "NOSE model — NOT present (stub mode)."),
    ("models/classifier_throat.joblib", "model", "THROAT model — NOT present (stub mode)."),
    ("frontend/index.html", "html", "Vite entry HTML."),
    ("frontend/package.json", "json", "React 18 + Vite 5 build config (dev/build/preview scripts)."),
    ("frontend/vite.config.js", "js", "Vite config (proxy to Flask on dev)."),
    ("frontend/src/main.jsx", "jsx", "React DOM root."),
    ("frontend/src/App.jsx", "jsx", "Tiny hash router (#/, #/practice, #/clarify, #/theory). Renders AmbientGlow + routed page."),
    ("frontend/src/styles.css", "css", "Full dark/clinical-clinical design system."),
    ("frontend/src/components/AmbientGlow.jsx", "jsx", "Persistent ambient-light backdrop behind all routes."),
    ("frontend/src/lib/diagnosis.jsx", "jsx", "Shared result rendering: CLASS_META, DiagnosisPanel, ScopeBox, ChipIcon, tierOf/labelOf/explanationOf."),
    ("frontend/src/pages/Landing.jsx", "jsx", "3D orbiting-card hero (drag + momentum + parallax tilt). 3 destinations × 2."),
    ("frontend/src/pages/Practice.jsx", "jsx", "Scope + Activate + findings workbench. Live/Freeze toggle, region switch (ear/nose/throat), live poll."),
    ("frontend/src/pages/Clarify.jsx", "jsx", "Upload PNG/JPG (drag-drop or browse) → classify with same result view."),
    ("frontend/src/pages/Theory.jsx", "jsx", "Placeholder tutorial page."),
    ("frontend/public/*.png", "image", "practice-card / clarify-card / theory-card images for the landing ring."),
    ("data set/ear/{AOM,Cerumen,CSOM,Myringosclerosis,Normal}/", "dataset", "Labelled ear training images (5 class folders present)."),
    ("data set/nose/ (empty)", "dataset", "NOSE dataset folders — expected but not yet populated."),
    ("data set/throat/ (empty)", "dataset", "THROAT dataset folders — expected but not yet populated."),
    ("static/samples/", "image", "Sample images used as no-camera fallback + ear demo mock (normal/aom/cerumen/csom/myringosclerosis.jpg)."),
    ("static/last_activation_*.jpg", "image", "Saved annotated frame from last /activate per mode."),
    ("static/last_upload_*.jpg", "image", "Saved annotated frame from last /classify_upload per mode."),
    ("README.md", "doc", "Comprehensive project documentation (architecture, training, routes, switches)."),
    ("DESIGN.md", "doc", "Visual design system: theme, colour, type, components, motion, layout."),
    ("PRODUCT.md", "doc", "Product definition: users, purpose, brand personality, design principles, accessibility."),
    ("Research Paper.txt", "doc", "Deep clinical+ML background: ENT pathologies, grading scales, endoscope optics, ML architectures, simulators."),
]
data_rows(ws, 4, files)

# ------------------------------------------------ 7. TRAINING
ws = wb.create_sheet("7. Training")
set_widths(ws, [28, 80])
title_row(ws, "Training a Classifier — turn STUB into real accuracy, one mode at a time", 2)
section_title(ws, 3, "Dataset layout (one subfolder per class, per mode)", 2)
layout = [
    ("data set/ear/", "Normal/ AOM/ Cerumen/ CSOM/ Myringosclerosis/  ← *.jpg / *.png in each"),
    ("data set/nose/", "Normal/ Allergic_Rhinitis/ Nasal_Polyp/ Deviated_Septum/"),
    ("data set/throat/", "Normal/ Pharyngitis/ Tonsillitis/"),
    ("Rule", "Folder names MUST match MODES[mode]['classes'] keys EXACTLY (case-sensitive). Trainer refuses to run otherwise and prints what to rename."),
    ("Isolation", "Each mode trains ONLY from its own folder and writes ONLY its own model. No path where one mode's data/model can leak into another."),
]
header_row(ws, 4, ["Item", "Detail"])
data_rows(ws, 5, layout)

section_title(ws, 12, "Commands", 2)
cmds = [
    ("Train ear (default)", "python train_classifier.py"),
    ("Train nose", "python train_classifier.py --mode nose"),
    ("Train throat", "python train_classifier.py --mode throat"),
    ("Run the app", "python mentoscope_app.py    → http://127.0.0.1:5000"),
    ("Install deps", "pip install flask opencv-python numpy scikit-image scikit-learn joblib"),
    ("Optional (real YOLO)", "pip install ultralytics   (only if you will set USE_REAL_MODEL=True)"),
    ("Frontend build", "cd frontend && npm install && npm run build    → frontend/dist (served by Flask)"),
    ("Frontend dev", "cd frontend && npm run dev   (run Flask alongside; Vite proxies API)"),
]
data_rows(ws, 13, cmds, mono_cols={2})

section_title(ws, 22, "What train_classifier.py does (per mode)", 2)
steps = [
    ("1", "Imports MODES, localize_region, crop_box, USE_REAL_MODEL directly from mentoscope_app.py → class list & paths defined once."),
    ("2", "Validates dataset folder exists, all expected class folders present (no missing/extra) — else exits with a clear ‘expected layout’ message."),
    ("3", "For every image: localize_region(img, mode) → crop_box → extract_features (IDENTICAL preprocessing the served pipeline applies)."),
    ("4", "StandardScaler.fit on the feature matrix."),
    ("5", "Stratified 80/20 train/test split (random_state=42)."),
    ("6", "RandomForestClassifier(n_estimators=300, class_weight=‘balanced’, n_jobs=−1)."),
    ("7", "Prints sklearn classification_report on held-out test set."),
    ("8", "Saves classifier_<mode>.joblib + scaler_<mode>.joblib + meta_<mode>.json (classes, n_samples, n_features, trained_at, use_real_model)."),
    ("9", "Reminds that the Flask app hot-reloads — NO restart needed; next request uses the new model."),
]
header_row(ws, 23, ["Step", "Action"])
data_rows(ws, 24, steps)

section_title(ws, 34, "Critical correctness rule (train==infer)", 2)
ws.merge_cells("A35:B35")
c = ws.cell(row=35, column=1, value=(
    "The classifier only ever sees the localizer's CROP, never the whole frame. Training on full images "
    "while serving centre-crops silently wrecks accuracy. Therefore train_classifier.py runs every image "
    "through the app's own localize_region()→crop_box() before extracting features. A model is tied to the "
    "localizer it was trained with — meta records use_real_model, and the app prints a loud WARNING if you "
    "flip USE_REAL_MODEL without retraining."))
c.alignment = WRAP; c.font = Font(bold=True, color="92400E"); c.fill = WARN_FILL
ws.row_dimensions[35].height = 80

# ------------------------------------------------ 8. ML FEATURES
ws = wb.create_sheet("8. ML Features")
set_widths(ws, [26, 20, 54])
title_row(ws, "Feature Engineering (features.py) — CPU-only, no deep learning", 3)
header_row(ws, 3, ["Component", "Value", "Detail"])
feats = [
    ("Resize", "128×128", "Every crop resized with INTER_AREA before anything else."),
    ("HOG orientations", "9", "Gradient orientation bins."),
    ("HOG pixels per cell", "16×16", "On the grayscale version of the resized crop."),
    ("HOG cells per block", "2×2", "Block normalization."),
    ("HOG block norm", "L2-Hys", "Transforms.R2006-style with clipping."),
    ("HSV histogram", "16 bins × 3 channels", "H ∈ [0,180], S ∈ [0,256], V ∈ [0,256]; each channel L2-normalised, then concatenated."),
    ("Total feature length", "1812", "= HOG (1764) + colour (48) per meta_ear.json."),
    ("Output dtype", "float32", "1-D vector."),
    ("Edge cases", "—", "Raises ValueError on None/empty image; promotes grayscale → 3-channel automatically."),
    ("Why HOG + HSV", "—", "Shape/texture (HOG) + tissue colour cues (HSV) — robust on small CPU-only datasets; no GPU needed."),
    ("Why a single module", "—", "features.py is imported by BOTH train_classifier.py and mentoscope_app.py, so the two paths CANNOT drift apart."),
]
data_rows(ws, 4, feats)

# ------------------------------------------------ 9. FRONTEND
ws = wb.create_sheet("9. Frontend (React)")
set_widths(ws, [16, 24, 80])
title_row(ws, "Frontend — React 18 + Vite (frontend/)", 3)
header_row(ws, 3, ["Page", "Hash route", "What it does"])
pages = [
    ("Landing", "#/", "3D orbiting-card hero. 6 panels (2× each destination) on a ring: drag + momentum + wheel + mouse parallax tilt, with auto-drift. Click a card → route. Respects prefers-reduced-motion."),
    ("Practice", "#/practice", "The scope + Activate + findings workbench. Region switch (Ear/Nose/Throat), Live/Freeze toggle, camera-status banner, scan animation, diagnosis card + per-class probability meters. Freeze→/activate; Live→/stream_detect + polls /last_result."),
    ("Clarify", "#/clarify", "‘Detect with Image’ — drag-and-drop or browse a PNG/JPG → POST /classify_upload. Reuses the exact same result view as Practice. Non-image types rejected inline."),
    ("Theory", "#/theory", "Placeholder tutorial page (‘Usage guideline — in progress.’)."),
]
data_rows(ws, 4, pages)

section_title(ws, 9, "Frontend modules", 3)
header_row(ws, 10, ["File", "Exports / Role", "Detail"])
mods = [
    ("App.jsx", "Router + shell", "Hash router; renders <AmbientGlow/> once (persists across routes) + the routed page; scrolls to top on route change."),
    ("main.jsx", "Entry", "ReactDOM root mounting <App/>."),
    ("AmbientGlow.jsx", "Backdrop", "Persistent ambient light behind all content."),
    ("lib/diagnosis.jsx", "Shared result rendering", "CLASS_META (ear fallback), CLASS_ORDER, MOCK_BOX; tierOf/labelOf/explanationOf; ChipIcon; ScopeBox (CSS box overlay for freeze/upload); DiagnosisPanel (chip + label + confidence + explanation + per-class meters)."),
    ("styles.css", "Design system", "Full warm-clinical dark-instrument theme: tokens, scope disc, brackets, scan animation, probability meters, skeletons, error box, orbit hero."),
    ("vite.config.js", "Build config", "Vite setup + dev proxy to Flask."),
]
data_rows(ws, 11, mods)

section_title(ws, 18, "Frontend behaviour notes", 3)
beh = [
    ("Live vs Freeze", "Freeze = single-shot /activate on a frozen frame with a crisp CSS overlay box. Live = continuous /stream_detect (box burned into frames) + /last_result polling at 600 ms."),
    ("No-backend demo", "If /activate is unreachable (e.g. opened from file://), Practice falls back to a built-in ear MOCK with plausible predict_proba distributions. Nose/Throat → honest 0% stub."),
    ("Cleanup", "Switching Live off, changing region, or unmounting clears the poll interval and unmounts the stream <img> so no connection hangs."),
    ("Offline mock only ear", "MOCK_SCORES / CLASS_META in diagnosis.jsx cover ear classes only; must stay in sync with MODES[‘ear’][‘classes’] in the backend."),
]
header_row(ws, 19, ["Topic", "", "Detail"])
data_rows(ws, 20, [(a, "", b) for a, b in beh])

# ------------------------------------------------ 10. DESIGN SYSTEM
ws = wb.create_sheet("10. Design System")
set_widths(ws, [18, 34, 64])
title_row(ws, "Visual System (DESIGN.md)", 3)
header_row(ws, 3, ["Aspect", "Decision", "Detail"])
design = [
    ("Theme", "Light, warm-clinical", "Calm paper surface under bright skills-lab lighting; the otoscope view is the single dark, saturated focal object. Reads as ONE instrument panel — everything fits one screen."),
    ("Colour", "Restrained", "Warm neutrals (--paper/--surface/--line) + warm ink ramp. One reserved accent (clinical teal) for primary actions + the localization box ONLY. Minimal semantic status set (normal/attention/caution), always with icon+text, never colour alone."),
    ("Tissue tones", "Separate token group", "Pinkish membrane, cone-of-light highlight, canal vignette — for the illustrated-eardrum fallback."),
    ("Typography", "Three families", "Source Serif 4 (headings + class label, medical-journal authority); IBM Plex Sans (UI/body/explanations — not Inter); IBM Plex Mono (instrument readouts: confidence %, coordinates, ticker, scores). Fixed ~1.2 rem scale; 60–75ch body measure; text-wrap balance/pretty."),
    ("Components", "Scope / Activate / Diagnosis", "Circular scope viewport w/ bezel + ticks + brackets + progress ring; primary teal Activate (→ ghost Reset); diagnosis card = serif label + status chip + mono confidence + 1-sentence explanation; per-class probability meters (top emphasised, rest muted)."),
    ("States", "4 designed", "Self-Check (empty), Analyzing (scan sweep + reticle + ring + ticker), Activated (result), Error (capture/model failure)."),
    ("Motion", "Instrument-grade", "150–420 ms, ease-out-expo/quart (no bounce). Analyzing = vertical scan + reticle + progress ring + ticker. Reveal = one decisive box draw + card rise. Every animation has prefers-reduced-motion fallback; content never gated behind a reveal."),
    ("Layout", "Two-pane workbench", "Scope left, findings right; collapses to single stacked column < ~940 px. Max ~1140 px centered. Structural responsiveness, not fluid type."),
]
data_rows(ws, 4, design)

# ------------------------------------------------ 11. PRODUCT
ws = wb.create_sheet("11. Product")
set_widths(ws, [22, 90])
title_row(ws, "Product Definition (PRODUCT.md)", 2)
section_title(ws, 3, "Identity", 2)
prod = [
    ("Register", "product"),
    ("Users", "Nursing & medical students learning otoscopy in a skills lab / supervised practice / demo station. Focused, a little anxious, building confidence before real patients."),
    ("Purpose", "AI-assisted ENT otoscopy trainer. Student views live endoscope, attempts Self-Check, then Activate runs 2-stage AI: localize (where) → classify (what)."),
    ("Success metric", "Students recognise the membrane and its state faster and more confidently — like an instructor over their shoulder."),
    ("Brand personality", "Calm · clinical · trustworthy. Voice = experienced instructor: precise, factual, reassuring, never alarmist or gamified. Clinical · assured · teacherly."),
    ("Anti-references", "Consumer health apps (gradients, mascots, streaks, emoji); marketing landing-page treatment; alarm-red ‘alert’ dashboards; generic AI-SaaS slop (Inter + purple-blue gradient, glassmorphism, cards-in-cards, icon tile + uppercase eyebrow everywhere)."),
]
header_row(ws, 4, ["Field", "Detail"])
data_rows(ws, 5, prod)

section_title(ws, 12, "Design Principles", 2)
principles = [
    ("Instrument, not app", "Behaves like calibrated clinical equipment — steady, legible, unshowy."),
    ("The image is the subject", "The drum leads; the UI defers and never competes for attention."),
    ("Localize ≠ classify", "Box says HERE (constant); label says WHAT (variable). Never conflate."),
    ("Honest uncertainty", "Show confidence and runner-up classes; don’t dramatise a guess into a diagnosis."),
    ("Teach, don’t just tell", "Every result carries the one thing a student should notice and why."),
]
header_row(ws, 13, ["Principle", "Meaning"])
data_rows(ws, 14, principles)

section_title(ws, 20, "Accessibility & Inclusion", 2)
a11y = [
    ("WCAG 2.1 AA", "Body text ≥4.5:1, large text ≥3:1, visible keyboard focus, complete keyboard path, prefers-reduced-motion fallback for every animation."),
    ("Never colour alone", "Status always shown as icon + text label + colour together (protects colour-blind users + the ‘is this normal?’ read)."),
    ("Poster legible", "Legible at poster/demo distance."),
]
header_row(ws, 21, ["Requirement", "Detail"])
data_rows(ws, 22, a11y)

# ------------------------------------------------ 12. RESEARCH (clinical)
ws = wb.create_sheet("12. Clinical Background")
set_widths(ws, [20, 22, 26, 26, 50])
title_row(ws, "Clinical Background (from Research Paper.txt)", 5)
ws.merge_cells("A3:E3")
c = ws.cell(row=3, column=1, value=(
    "Why MentoScope exists: GPs identify middle-ear conditions ~64% of the time, pediatricians ~50%, "
    "ENT specialists ~73%. A self-guided training aid that interprets close-up endoscopic frames helps "
    "students transition from novice observers to competent diagnosticians. Below is the pathology "
    "knowledge the project is grounded in."))
c.alignment = WRAP; c.font = Font(italic=True, color="0F766E"); ws.row_dimensions[3].height = 56

section_title(ws, 5, "EAR conditions (otologic)", 5)
header_row(ws, 6, ["Condition", "Colour / Translucency", "Contour", "Landmarks", "Pathophysiology"])
ear_clin = [
    ("Normal TM", "Pearly grey, translucent", "Slightly concave in", "Malleus handle, lateral process, umbo, cone of light visible", "Healthy middle ear; normal eustachian ventilation."),
    ("Erythematous (red) ear", "Pink→bright red, translucent", "Normal concave", "All landmarks preserved; prominent malleus vessels", "Vascular injection without effusion (crying, coughing, fever, strain)."),
    ("AOM", "Bright red, opaque", "Marked outward bulging", "Landmarks lost", "Acute bacterial/viral infection; purulent fluid + pressure behind drum."),
    ("OME", "Amber/yellow/grey, dull", "Flat or retracted", "Shortened malleus; prominent lateral process", "Non-purulent middle-ear fluid; eustachian dysfunction."),
    ("CSOM", "Variable; exposed mucosa red", "Non-continuous membrane", "Perforated pars tensa; middle-ear structures visible", "Persistent perforation + chronic mucosal inflammation + discharge."),
    ("Myringosclerosis", "Semi-translucent + opaque white zones", "Normal", "Chalky white calcified plaques in membrane", "Calcification of fibrous layer after trauma/infection."),
    ("Attic retraction / Cholesteatoma", "Whitish greasy mass", "Invaginated pocket (pars flaccida)", "Pars flaccida collapsed; structures eroded", "Squamous debris in deep retraction pocket → bone destruction."),
    ("Cerumen impaction", "Yellow/orange/brown/black, opaque", "Solid amorphous mass", "Canal + drum obscured", "Endogenous ceruminous/sebaceous secretions in outer canal."),
    ("Otitis externa / otomycosis", "Red canal; fungal spores black/white/yellow", "Swollen narrowed lumen", "Canal distorted; drum often obscured", "Acute bacterial or fungal infection of canal skin (water exposure)."),
    ("Glomus tumour", "Deep red/blue mass behind drum", "Unilateral bulging", "Distorts posterior/inferior quadrants", "Vascular paraganglioma of middle ear / skull base."),
    ("Tympanostomy tube (grommet)", "Synthetic blue/green/white/metallic", "Patent circular collar", "In anterior/posterior-inferior quadrant", "Surgically inserted ventilation tube."),
]
data_rows(ws, 7, ear_clin)

section_title(ws, 19, "NOSE conditions (rhinologic)", 5)
header_row(ws, 20, ["Condition", "Colour / Translucency", "Contour", "Origin", "Key criteria"])
nose_clin = [
    ("Deviated septum (DNS)", "Smooth pink mucosa", "Rigid asymmetric midline protrusion", "Osteocartilaginous septum", "7 Mladina types; graded 0–3 (Salihoglu). 86% show contralateral inferior turbinate hypertrophy."),
    ("Inferior turbinate hypertrophy", "Deep pink→red, opaque", "Large firm rounded swelling", "Anterior-inferior lateral wall", "Firm, non-translucent, sensitive; graded 1–4 (25% increments)."),
    ("Nasal polyps", "Pale grey/yellow/greenish, translucent", "Smooth gelatinous teardrop", "Middle meatus / ethmoid / sinus ostia", "Mobile, insensitive, bilateral, don’t bleed easily."),
    ("Inverted papilloma", "Pinkish-grey, opaque", "Lobulated cauliflower, firm", "Unilateral middle meatus / lateral wall", "Unilateral fleshy textured mass; malignant potential."),
    ("Malignant tumour", "Red/grey/purple, opaque", "Irregular asymmetric nodular ulcerated", "Unilateral cavity / sinuses", "Rapid growth, necrotic bleeding surface, destruction."),
    ("Concha bullosa", "Normal pink mucosa", "Enlarged rounded middle turbinate", "Middle turbinate", "Pneumatized middle turbinate; predisposes to sinusitis."),
    ("Allergic rhinitis", "Pale/bluish/purple; clear secretions", "Smooth boggy diffuse swelling", "Generalized mucosa (esp. inferior turbinates)", "Pale edematous turbinates + watery secretions; ↑green/blue RGB."),
    ("Purulent sinusitis", "Opaque yellow/white/green mucopus", "Thick viscous fluid tracks", "Middle meatus / sphenoethmoid recess", "Active mucopurulent discharge from sinus ostia."),
    ("Atrophic rhinitis", "Dry pale mucosa + green-black crusts", "Widened cavity; eroded tissue", "Generalized lining + septum", "Crusting, foul odor (ozena), atrophy, septal perforation."),
    ("Nasal synechia", "Pink fibrous bands", "Bridge-like connections", "Septum ↔ lateral wall", "Post-surgery/trauma adhesions causing airflow turbulence."),
]
data_rows(ws, 21, nose_clin)

section_title(ws, 32, "THROAT conditions (pharyngeal/laryngeal)", 5)
header_row(ws, 33, ["Condition", "Symmetry", "Location", "Vascular pattern", "Key criteria"])
throat_clin = [
    ("Pharyngitis", "Symmetrical/diffuse", "Posterior pharyngeal wall; tonsillar pillars", "Diffuse hyperemic erythema", "Diffuse redness, congestion, prominent lymphoid follicles."),
    ("Acute tonsillitis", "Typically bilateral", "Palatine tonsils (lateral oropharynx)", "Hyperemic bright red", "Swollen tonsils ± white/yellow exudate in crypts."),
    ("Peritonsillar abscess (Quinsy)", "Asymmetric unilateral", "Soft palate + anterior tonsillar pillar", "Severe localized hyperemia", "Uvula deviation, medial tonsil displacement."),
    ("Epiglottitis", "Symmetrical bulbous", "Supraglottic larynx (base of tongue)", "‘Cherry red’ or pale edematous", "Sausage-like epiglottis; airway narrowed — emergency."),
    ("Vocal fold nodules", "Strictly bilateral", "Anterior 1/3–middle 1/3 of membranous folds", "Translucent→white; minimal vessels", "Symmetrical callous-like thickenings; hourglass closure."),
    ("Vocal fold polyp", "Unilateral", "Mid membranous free edge", "Gelatinous/hemorrhagic; prominent vessel", "Larger pedunculated/sessile; impairs mucosal wave."),
    ("Vocal fold cyst", "Unilateral", "Superficial lamina propria", "Normal→minimally hyperemic", "Smooth yellowish-white sphere within the fold."),
    ("Vocal fold papilloma", "Uni- or bilateral", "True folds / ventricles / supraglottis", "Hypervascular pinkish-white rough", "Grape/cauliflower-like HPV-driven growths."),
    ("Reinke’s edema", "Diffuse bilateral", "Reinke’s space along whole fold", "Pale water-bag-like", "Large floppy translucent fluid pouches; smokers."),
    ("Vocal process granuloma", "Uni- or bilateral", "Posterior glottis over arytenoid vocal process", "Pink→dark red lobulated", "Nodular ulcerated posterior mass; intubation/reflux."),
    ("Leukoplakia", "Uni- or bilateral", "Mucosa of true vocal folds", "White keratinized plaque limits vessels", "Needs biopsy to rule out dysplasia/malignancy."),
    ("Reflux laryngitis (LPR)", "Symmetrical", "Posterior commissure / interarytenoid", "Erythema + congestion", "Cobblestone appearance; posterior redness/swelling."),
    ("Candidiasis (thrush)", "Patchy/multifocal", "Oral cavity / oropharynx / laryngopharynx", "Normal underlying mucosa", "Thick white plaque-like patches."),
]
data_rows(ws, 34, throat_clin)

section_title(ws, 48, "Grading scales & optics referenced", 5)
header_row(ws, 49, ["Topic", "Scale / Spec", "Detail", "", ""])
scales = [
    ("Tonsil size", "Brodsky 0–4", "0=in fossa → 4=>75% (‘kissing’). Volumes: G1≈2.58mL, G2≈4.33mL, G3≈6.58mL, G4≈9.33mL."),
    ("Airway risk", "Mallampati I–IV", "Visibility of pillars/uvula/soft palate. Class III–IV + Brodsky 3–4 → ↑ sleep-disordered breathing risk."),
    ("Septal deviation", "Mladina types 1–7", "Types 1–4 vertical (axial); 5–6 horizontal (coronal); 7 = complex combo."),
    ("Deviation severity", "Salihoglu 0–3", "0=centered → 3=>66.7% obstruction."),
    ("Turbinate hypertrophy", "Grade 1–4", "1=<25% → 4=>75% of nasal cavity."),
    ("Endoscope optics", "Rigid Hopkins rod-lens", "0°/30°/45°/70° directions of view; superior contrast/resolution."),
    ("Flexible scopes", "Fiber-optic vs Chip-on-Tip", "Fiber = honeycomb/dead pixels; CoT = HD digital, zero fiber artifacts."),
    ("Frame selection", "SSIM ≥ 0.90", "Drop redundant/blurry video frames while preserving key structural changes."),
    ("Segmentation", "U-Net", "Pixel acc 96.76%, Dice 71.68% for TM ring / malleus / light reflex."),
    ("CNN backbones", "VGG19 / ResNet50 / MobileNetV2", "VGG19: 94.51% acc / 98.10% spec / 93.86% prec on 4-class otitis media."),
    ("Transformers", "DeiT", "F1 0.96–1.00 across acute/chronic/normal."),
    ("Ensembles", "Voting (InceptionV3+ResNet101)", "~93.67% 5-fold on 6-class otoendoscopic."),
    ("Data scarcity", "Supervised contrastive / LDM+ControlNet", "Contrastive lifts small-data acc 82.27%→85.82%; LDM generates synthetic laryngeal frames."),
    ("Summaries", "Sumotosima (multimodal BART)", "98.03% classification; outperforms GPT-4o/LLaVA by 88.53% ROUGE."),
    ("Simulators", "Earsi / Kyoto Kagaku EAR II / VOXEL-MAN / OtoSim", "Physical + VR training platforms (haptics, depth alarms, surface-coverage tracking)."),
]
data_rows(ws, 50, [(a, b, c, "", "") for a, b, c in scales])

# ------------------------------------------------ 13. STATUS & GAPS
ws = wb.create_sheet("13. Status & Gaps")
set_widths(ws, [22, 14, 70])
title_row(ws, "Current Status, Gaps & Ideas", 3)
header_row(ws, 3, ["Area", "Status", "Detail"])
status = [
    ("Ear classifier", "DONE", "Trained: 3014 samples, 5 classes, 1812 features, RandomForest. classifier_ear.joblib + scaler_ear.joblib + meta_ear.json present."),
    ("Nose classifier", "STUB", "Dataset folders expected but empty; no model. Returns Normal @ 0%. Needs a real rhinoscopy dataset organised into the 4 class folders."),
    ("Throat classifier", "STUB", "Dataset folders expected but empty; no model. Returns Normal @ 0%. Needs a real pharyngoscopy dataset organised into the 3 class folders."),
    ("Localizer", "STUB", "USE_REAL_MODEL=False → fixed centre-60% box. Real YOLO-World coded & lazy-loaded behind the flag, just not enabled by default."),
    ("Camera", "OPTIONAL", "App runs without camera (sample→synthetic fallback). /camera_status exposes connectivity to the UI."),
    ("Live detection", "DONE", "/stream_detect + /last_result continuous mode with ~8 fps throttled inference + 600 ms polling."),
    ("Upload (Clarify)", "DONE", "/classify_upload with PNG/JPG validation, same result view as Practice."),
    ("Frontend", "DONE", "4 pages, full design system, Live/Freeze, region switch, drag-drop upload, 3D landing, reduced-motion support."),
    ("Theory page", "PLACEHOLDER", "Theory.jsx is a stub (‘Usage guideline — in progress.’)."),
    ("Legacy UI", "FALLBACK", "templates/index.html referenced as fallback if frontend/dist absent (file not present in current listing)."),
    ("Explanations", "STATIC", "Fixed text lookup per class (no LLM). Research paper describes multimodal summary (Sumotosima/BART) as a future direction."),
    ("Segmentation", "NOT IMPLEMENTED", "Paper recommends U-Net ROI segmentation; project uses YOLO-World localization instead."),
    ("Video keyframing", "NOT IMPLEMENTED", "Paper recommends SSIM keyframe extraction; project processes single frames / throttled stream."),
    ("Depth/safety tracking", "NOT IMPLEMENTED", "Paper describes canal-depth + surface-coverage + trauma alerts (simulator integration)."),
    ("Accessibility", "DESIGNED", "WCAG AA intent documented; status never colour-alone (icon+text+colour)."),
]
data_rows(ws, 4, status)
# colour the status cell
for r in range(4, 4 + len(status)):
    val = ws.cell(row=r, column=2).value
    fill = OK_FILL if val == "DONE" else WARN_FILL
    ws.cell(row=r, column=2).fill = fill

# ------------------------------------------------------------ save
out = r"C:\Users\LENOVO\Desktop\Basic Python\MentoScope\MentoScope_Overview.xlsx"
wb.save(out)
print("Saved:", out)
print("Sheets:", wb.sheetnames)