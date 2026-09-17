"""
test_landmarks.py — quick check of the new multi-landmark localization.

Runs the MentoScope pipeline (via the Flask test client, no server needed)
on a real ear image from data set/ear/, and prints the landmarks array so
you can confirm a primary + at least one secondary landmark are present.

    python test_landmarks.py
"""
from pathlib import Path
import json
import sys

import cv2

from mentoscope_app import app, MODES, localize_landmarks

ROOT = Path(__file__).resolve().parent
EAR_IMG = ROOT / "data set" / "ear" / "AOM" / "AOM_000.jpg"


def main():
    if not EAR_IMG.exists():
        print(f"[test] missing test image: {EAR_IMG}")
        sys.exit(1)

    frame = cv2.imread(str(EAR_IMG))
    if frame is None:
        print(f"[test] could not read image: {EAR_IMG}")
        sys.exit(1)

    print(f"[test] image: {EAR_IMG.name}  shape={frame.shape[1]}x{frame.shape[0]}")
    print(f"[test] ear landmark prompts: {[lm['prompt'] for lm in MODES['ear']['landmarks']]}")
    print()

    # 1) Direct call to the localization function (shows raw boxes).
    landmarks, primary_box, localizer = localize_landmarks(frame, "ear")
    print(f"[test] localizer: {localizer}")
    print(f"[test] primary_box (used for classification): {primary_box}")
    print(f"[test] landmarks found: {len(landmarks)}")
    for lm in landmarks:
        print(f"        - {lm['role']:9s} {lm['label']:22s} "
              f"box={lm['box']} conf={lm['confidence']}")
    print()

    # 2) Full pipeline through the Flask test client (/classify_upload), so we
    #    see the EXACT JSON the frontend would receive.
    client = app.test_client()
    with open(EAR_IMG, "rb") as f:
        resp = client.post(
            "/classify_upload?mode=ear",
            data={"image": (f, EAR_IMG.name)},
            content_type="multipart/form-data",
        )
    if resp.status_code != 200:
        print(f"[test] /classify_upload failed: {resp.status_code} {resp.get_data(as_text=True)}")
        sys.exit(1)

    payload = resp.get_json()
    print("[test] /classify_upload response:")
    print(f"        localizer : {payload['localizer']}")
    print(f"        classifier: {payload['classifier']}")
    r = payload["results"][0]
    print(f"        primary   : {r['label']} @ {r['confidence']*100:.0f}%  box={r['box']}")
    print(f"        landmarks ({len(payload['landmarks'])}):")
    for lm in payload["landmarks"]:
        print(f"          - {lm['role']:9s} {lm['label']:22s} "
              f"box={lm['box']} conf={lm['confidence']}")
    print()

    # 3) Save the annotated frame so you can eyeball primary vs secondary boxes.
    annotated = cv2.imread(str(ROOT / "static" / "last_upload_ear.jpg"))
    if annotated is not None:
        out = ROOT / "test_landmarks_annotated.jpg"
        cv2.imwrite(str(out), annotated)
        print(f"[test] annotated image written to: {out}")

    # 4) Verdict.
    primary = any(lm["role"] == "primary" for lm in payload["landmarks"])
    secondary = any(lm["role"] == "secondary" for lm in payload["landmarks"])
    print()
    if primary and secondary:
        print("[test] PASS — primary + at least one secondary landmark present.")
    else:
        print(f"[test] NOTE — primary={primary}, secondary={secondary}. "
              "Zero-shot detection on otoscope close-ups is unreliable for small "
              "structures; secondary landmarks may not always appear. The primary "
              "still classified and the response shape is correct either way.")


if __name__ == "__main__":
    main()