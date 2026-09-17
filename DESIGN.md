# Design

Visual system for MentoScope. Follows the spirit of the DESIGN.md spec: theme → color → type → components → motion → layout. Register is **product** (design serves the task).

## Theme

Light, warm-clinical. A calm paper surface under bright skills-lab lighting, with the otoscope view as the single dark, saturated focal object. It reads as one **instrument panel**, not a scrolling page — everything fits one screen, everything is visible by default, motion only enhances.

## Color (OKLCH)

Strategy: **restrained** — warm-neutral surfaces + one reserved accent, plus a minimal semantic status set.

- `--paper` warm off-white body; `--surface` panels; `--line` hairlines.
- `--ink` / `--ink-soft` / `--ink-faint` warm near-black text ramp (all meeting AA at their sizes).
- **`--accent` clinical teal** — reserved for two things only: primary actions (Activate) and the **localization box** (its meaning is constant: "membrane here").
- **Status vocabulary** (classification only, never decorative):
  - `normal` → teal-green (healthy drum)
  - `attention` → amber/clay (AOM / OME / Otitis Externa)
  - `caution` → sand-amber (Cerumen / view obscured)
  - Always paired with an icon + text label. Never colour alone.

Tissue tones for the illustrated-eardrum fallback live in their own token group (pinkish membrane, cone-of-light highlight, canal vignette).

## Typography

Three families on clear contrast axes:

- **Source Serif 4** — headings and the classification label (editorial, medical-journal authority).
- **IBM Plex Sans** — UI, controls, body, explanations (clinical clarity; deliberately not Inter).
- **IBM Plex Mono** — instrument readouts only: confidence %, coordinates, status ticker, class scores.

Fixed rem scale (product register), ~1.2 ratio. Body measure 60–75ch. `text-wrap: balance` on headings, `pretty` on prose.

## Components

- **Scope instrument** — circular clipped viewport, bezel + canal vignette, degree/orientation ticks, corner brackets that lock during analysis, circular progress ring.
- **Activate control** — primary teal button; becomes a ghost "Reset" after activation; disabled+spinner while analysing.
- **Diagnosis card** — serif class label + status chip (icon+text+colour) + mono confidence + one-sentence explanation.
- **Probability breakdown** — per-class horizontal meters from `predict_proba`, top class emphasised, rest muted (honest uncertainty).
- **States** — Self-Check guidance (empty), Analyzing (scan sequence + skeletons), Activated (result), and Error (capture/model failure) all designed.

## Motion

Instrument-grade, purposeful. 150–420ms, `ease-out-expo`/`quart` (no bounce). Analyzing: vertical scan sweep + reticle + progress ring + mono status ticker. Reveal: one decisive box draw + card rise. Every animation has a `prefers-reduced-motion` crossfade/instant fallback; content is never gated behind a reveal.

## Layout

Two-pane workbench — scope left, findings right — collapsing to a single stacked column below ~940px. Max width ~1140px, centered. Structural responsiveness (reflow, collapse), not fluid type.
