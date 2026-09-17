/* Shared result-rendering for any page that shows a MentoScope detection
   (Practice's frozen frame + live poll, and Clarify's uploaded image).
   One implementation so the result view never diverges between pages. */

// Ear class metadata — fallback labels/explanations for the offline ear demo
// mock. Live/upload results from the backend already carry their own
// label/status/explanation, so this is only a safety net for those fields.
// Must stay in sync with MODES["ear"]["classes"] in mentoscope_app.py.
export const CLASS_META = {
  Normal:           { label: "Normal",                tier: "fine",    explanation: "The tympanic membrane looks healthy — translucent and pearly-grey, with a clear cone of light and no bulging or fluid." },
  AOM:              { label: "Acute Otitis Media",    tier: "flagged", explanation: "The drum looks red and bulging, a sign of acute middle-ear infection with pus building up behind it." },
  Cerumen:          { label: "Cerumen Impaction",     tier: "flagged", explanation: "Ear wax is obscuring part of the drum and may need clearing before the membrane can be fully assessed." },
  CSOM:             { label: "Chronic Otitis Media",  tier: "flagged", explanation: "A persistent, non-healing perforation of the eardrum with ongoing discharge — a long-standing problem, distinct from an acute infection." },
  Myringosclerosis: { label: "Myringosclerosis",      tier: "flagged", explanation: "Chalky white calcified patches on the eardrum, left behind by old healed infections or trauma — usually not urgent in itself, but worth noting." },
};
export const CLASS_ORDER = ["Normal", "AOM", "Cerumen", "CSOM", "Myringosclerosis"];
export const MOCK_BOX = [0.2, 0.2, 0.8, 0.8]; // matches the backend centre-60% stub

// Adaptive grid — mirrors the backend compute_adaptive_grid() so the offline
// ear demo's mock responses carry the same grid shape as the real backend.
// Uses SEPARATE per-axis unit sizes so the box spans ~N cells in BOTH
// dimensions regardless of its aspect ratio.
export const GRID_CELLS_PER_ANOMALY_SIDE = 3;
export function adaptiveGridFromBoxNorm(boxNorm, frameW = 1, frameH = 1,
  cellsPerSide = GRID_CELLS_PER_ANOMALY_SIDE, minCells = 2, maxCells = 50) {
  const [x1, y1, x2, y2] = boxNorm;
  const boxW = Math.max(1e-6, x2 - x1) * frameW;
  const boxH = Math.max(1e-6, y2 - y1) * frameH;
  const colUnit = Math.max(1e-6, boxW / Math.max(1, cellsPerSide));
  const rowUnit = Math.max(1e-6, boxH / Math.max(1, cellsPerSide));
  const rawCols = Math.max(1, Math.round(frameW / colUnit));
  const rawRows = Math.max(1, Math.round(frameH / rowUnit));
  const clamp = (n) => Math.min(maxCells, Math.max(minCells, n));
  return { rows: clamp(rawRows), cols: clamp(rawCols) };
}

// Every grid cell the normalized box meaningfully overlaps (intersection /
// CELL area >= threshold), mirroring cells_overlapping_box(). Reference area
// is the CELL (not the box) so the metric is stable across grid densities.
// Used by the offline demo mock so multi-cell highlight works without a backend.
export function cellsOverlappingBoxNorm(boxNorm, rows, cols, overlapThreshold = 0.15) {
  const [bx1, by1, bx2, by2] = boxNorm;
  const cellW = 1 / cols, cellH = 1 / rows;
  const cellArea = Math.max(1e-9, cellW * cellH);
  const out = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const cx1 = c * cellW, cy1 = r * cellH, cx2 = (c + 1) * cellW, cy2 = (r + 1) * cellH;
      const ix1 = Math.max(bx1, cx1), iy1 = Math.max(by1, cy1);
      const ix2 = Math.min(bx2, cx2), iy2 = Math.min(by2, cy2);
      if (ix2 <= ix1 || iy2 <= iy1) continue;
      if (((ix2 - ix1) * (iy2 - iy1)) / cellArea >= overlapThreshold) {
        out.push({ row: r, col: c });
      }
    }
  }
  return out;
}

// Two-tier severity for colour: backend `status` (normal/attention/caution)
// wins; CLASS_META.tier is only a fallback for the offline ear mock.
const STATUS_TIER = { normal: "fine", attention: "flagged", caution: "flagged" };
export const tierOf = (r) => STATUS_TIER[r.status] || (CLASS_META[r.class] ? CLASS_META[r.class].tier : "flagged");

export const labelOf = (r) => (CLASS_META[r.class] ? CLASS_META[r.class].label : r.label);
export const explanationOf = (r) => (CLASS_META[r.class] ? CLASS_META[r.class].explanation : r.explanation);

export const ChipIcon = ({ tier }) =>
  tier === "fine" ? (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><circle cx="8" cy="8" r="6.4" stroke="currentColor" strokeWidth="1.4" /><path d="M5.4 8.2 7.1 9.9 10.6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
  ) : (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 2.2 14.5 13.4H1.5L8 2.2Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" /><path d="M8 6.4v3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /><circle cx="8" cy="11.2" r="0.8" fill="currentColor" /></svg>
  );

/* The localization box drawn over a frozen/uploaded frame (Practice freeze +
   Clarify). Live mode burns its own box into the stream, so it doesn't use this. */
export function ScopeBox({ result }) {
  const box = result.box_norm || MOCK_BOX;
  const [x1, y1, x2, y2] = box;
  return (
    <div
      className="fbox"
      style={{ left: `${x1 * 100}%`, top: `${y1 * 100}%`, width: `${(x2 - x1) * 100}%`, height: `${(y2 - y1) * 100}%` }}
    >
      <span className="fbox__tag" data-tier={tierOf(result)}>{labelOf(result)}</span>
    </div>
  );
}

/* Adaptive grid-cell localization overlay: thin grid lines across the
   ENTIRE circular scope view (edge to edge), with EVERY cell the detection
   overlaps drawn with a highlight border + a small abbreviation pill. Grid
   resolution + highlighted cells come from the API response (grid.rows /
   grid.cols / highlighted_cells), so the overlay always matches whatever
   was computed for THIS detection — never cached or fixed. */
export function ScopeGrid({ grid, result }) {
  if (!grid) return null;
  const { rows = 0, cols = 0, highlighted_cells = [] } = grid;
  const tier = result ? tierOf(result) : "flagged";

  // Faint reference lines across the WHOLE frame (all internal divisions).
  const vLines = Array.from({ length: Math.max(0, cols - 1) }, (_, i) => i);
  const hLines = Array.from({ length: Math.max(0, rows - 1) }, (_, i) => i);
  const hl = highlighted_cells.filter((c) => c && c.row >= 0 && c.col >= 0);
  const labelText = result ? (CLASS_META[result.class] ? CLASS_META[result.class].label : result.label) : "";

  // ONE label for the entire highlighted region: compute the bounding box of
  // all highlighted cells, place the pill just above the topmost row (or below
  // if it would clip off the top of the frame). This avoids drawing the label
  // once per row/cell.
  let labelEl = null;
  if (labelText && hl.length > 0 && cols > 0 && rows > 0) {
    const minRow = Math.min(...hl.map((c) => c.row));
    const minCol = Math.min(...hl.map((c) => c.col));
    const maxCol = Math.max(...hl.map((c) => c.col));
    const spansTop = minRow === 0; // first row → label would clip above; place below
    const tagTop = spansTop ? `${((minRow + 1) / rows) * 100}%` : `${(minRow / rows) * 100}%`;
    const tagLeft = `${(((minCol + maxCol + 1) / 2) / cols) * 100}%`;
    labelEl = (
      <span
        className={`sgrid__tag sgrid__tag--${tier}${spansTop ? " sgrid__tag--below" : ""}`}
        style={{ left: tagLeft, top: tagTop }}
      >
        {labelText}
      </span>
    );
  }

  return (
    <div className="sgrid" aria-hidden="true">
      {vLines.map((i) => (
        <div key={`v${i}`} className="sgrid__line sgrid__line--v" style={{ left: `${((i + 1) / cols) * 100}%` }} />
      ))}
      {hLines.map((i) => (
        <div key={`h${i}`} className="sgrid__line sgrid__line--h" style={{ top: `${((i + 1) / rows) * 100}%` }} />
      ))}
      {hl.map((c, i) => (
        <div
          key={`c${i}-${c.row}-${c.col}`}
          className={`sgrid__cell sgrid__cell--${tier}`}
          style={{
            left: `${(c.col / cols) * 100}%`,
            top: `${(c.row / rows) * 100}%`,
            width: `${(1 / cols) * 100}%`,
            height: `${(1 / rows) * 100}%`,
          }}
        />
      ))}
      {labelEl}
    </div>
  );
}

/* The findings diagnosis card: status chip, class, confidence, explanation,
   and the per-class probability breakdown. */
export function DiagnosisPanel({ result }) {
  const tier = tierOf(result);
  const pct = Math.round((result.confidence || 0) * 100);
  const scores = (result.scores || []).slice().sort((a, b) => b.p - a.p);
  return (
    <div className="dx">
      <span className="chip" data-tier={tier}><ChipIcon tier={tier} />{tier === "fine" ? "Normal" : "Flagged"}</span>
      <div className="dx__label">{labelOf(result)}</div>
      <div className="dx__conf"><b>{pct}%</b><span>confidence</span></div>
      <p className="dx__desc">{explanationOf(result)}</p>
      {scores.length > 0 && (
        <div className="scores">
          <div className="scores__title">Class probabilities</div>
          {scores.map((s, i) => (
            <div key={s.class} className={`score${i === 0 ? " is-top" : ""}`}>
              <span className="score__name">{CLASS_META[s.class] ? CLASS_META[s.class].label : s.label}</span>
              <span className="score__pct">{Math.round(s.p * 100)}%</span>
              <div className="score__track"><div className="score__fill" style={{ "--v": s.p.toFixed(3) }}></div></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
