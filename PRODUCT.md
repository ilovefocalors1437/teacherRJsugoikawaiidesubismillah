# Product

## Register

product

## Users

Nursing and medical students learning **otoscopy** — how to look into the ear and read the tympanic membrane (eardrum). Their context is a skills lab, supervised practice, or a poster/demo station: focused, a little anxious about getting it right, building confidence before they examine real patients. The job to be done on any given screen: *"Am I looking at the drum, and does it look normal or like a common pathology?"*

## Product Purpose

MentoScope is an AI-assisted ENT otoscopy trainer. A student views a live circular endoscope feed, tries to read the drum themselves (**Self-Check**), then presses **Activate** to run a two-stage AI:

1. **Localize** — YOLO-World finds the tympanic membrane and draws one box. This step never judges health; it only answers *"where is the drum?"*
2. **Classify** — a separately-trained scikit-learn model classifies the cropped region as **Normal, AOM (Acute Otitis Media), OME (Otitis Media with Effusion), Otitis Externa,** or **Earwax/Cerumen**, with a confidence and a plain-language explanation.

Success = students recognise the membrane and its state faster and more confidently, with the tool behaving like an instructor pointing over their shoulder.

## Brand Personality

Calm, clinical, trustworthy. Voice is an experienced instructor: precise, factual, reassuring, never alarmist or gamified. Three words: **clinical, assured, teacherly.** It should feel like calibrated equipment, not a consumer app.

## Anti-references

- Consumer health apps: gradients, cartoon mascots, gamified streaks, emoji.
- Marketing / landing-page treatment (this is a tool, not a pitch).
- Alarm-red medical "alert" dashboards that spike anxiety.
- Generic AI-SaaS slop: Inter + purple→blue gradient, decorative glassmorphism, cards nested in cards, a rounded-square icon tile above every heading, uppercase eyebrow on every section.

## Design Principles

- **Instrument, not app.** The interface behaves like calibrated clinical equipment — steady, legible, unshowy.
- **The image is the subject.** The drum leads; the UI defers to it and never competes for attention.
- **Localize and classify are different claims.** The box says *"here"* (constant); the label says *"what"* (variable). Never let the UI conflate the two.
- **Honest uncertainty.** Show the confidence and the runner-up classes. Don't dramatise a guess into a diagnosis.
- **Teach, don't just tell.** Every result carries the one thing a student should notice and why.

## Accessibility & Inclusion

WCAG 2.1 AA: body text ≥4.5:1, large text ≥3:1, visible keyboard focus, a complete keyboard path, and a `prefers-reduced-motion` alternative for every animation. Classification status is conveyed by **icon + text label + colour together**, never colour alone (protects colour-blind users and the "is this normal?" read). Legible at poster/demo distance.
