import { useEffect, useRef, useState } from "react";
import { CLASS_META, CLASS_ORDER, MOCK_BOX, DiagnosisPanel, ScopeGrid, adaptiveGridFromBoxNorm, cellsOverlappingBoxNorm } from "../lib/diagnosis.jsx";
import { apiUrl } from "../lib/api.js";

const SAMPLE_FILE = { Normal: "normal", AOM: "aom", Cerumen: "cerumen", CSOM: "csom", Myringosclerosis: "myringosclerosis" };
const CASES = CLASS_ORDER.map((cls, i) => ({
  id: String(i + 1).padStart(2, "0"),
  cls,
  img: apiUrl(`/static/samples/${SAMPLE_FILE[cls]}.jpg`),
}));

const REGIONS = [
  { id: "ear", label: "Ear" },
  { id: "nose", label: "Nose" },
  { id: "throat", label: "Throat" },
];

/* Plausible predict_proba distributions for the no-backend ear demo. */
const MOCK_SCORES = {
  Normal:           { Normal: 0.92, Myringosclerosis: 0.04, Cerumen: 0.02, AOM: 0.01, CSOM: 0.01 },
  AOM:              { AOM: 0.88, CSOM: 0.07, Cerumen: 0.03, Normal: 0.01, Myringosclerosis: 0.01 },
  Cerumen:          { Cerumen: 0.90, CSOM: 0.05, Normal: 0.03, AOM: 0.01, Myringosclerosis: 0.01 },
  CSOM:             { CSOM: 0.85, AOM: 0.07, Cerumen: 0.05, Myringosclerosis: 0.02, Normal: 0.01 },
  Myringosclerosis: { Myringosclerosis: 0.86, Normal: 0.08, CSOM: 0.03, Cerumen: 0.02, AOM: 0.01 },
};

const REDUCED = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const SCAN_MS = REDUCED ? 320 : 2100;
const LIVE_POLL_MS = 600;
const MODE_LABEL = { idle: "Self-Check", analyzing: "Analyzing", active: "Active", error: "Error", live: "Live" };
const READOUT = { idle: "SELF-CHECK", analyzing: "SCANNING", active: "AI OVERLAY", error: "ERROR", live: "LIVE DETECT" };

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

function adaptiveGridFor(boxNorm, cls) {
  const [x1, y1, x2, y2] = boxNorm;
  const boxW = x2 - x1, boxH = y2 - y1;
  // Mirror the backend NEAR_FULL_FRAME_THRESHOLD edge case: a membrane-filling
  // finding is represented as a single highlighted cell, not NxN fragments.
  if (boxW >= 0.7 && boxH >= 0.7) {
    const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
    const col = Math.min(1, Math.max(0, Math.floor(cx * 2)));
    const row = Math.min(1, Math.max(0, Math.floor(cy * 2)));
    return { rows: 2, cols: 2, highlighted_cells: [{ row, col, label: cls }] };
  }
  const { rows, cols } = adaptiveGridFromBoxNorm(boxNorm);
  const cells = cellsOverlappingBoxNorm(boxNorm, rows, cols).map((c) => ({ ...c, label: cls }));
  return { rows, cols, highlighted_cells: cells };
}

function buildMockResponse(c) {
  const dist = MOCK_SCORES[c.cls];
  const meta = CLASS_META[c.cls];
  return {
    mode: "ear", localizer: "stub", classifier: "demo", frame: null,
    grid: adaptiveGridFor(MOCK_BOX, c.cls),
    results: [{
      class: c.cls, label: meta.label, status: meta.status, box_norm: MOCK_BOX,
      confidence: dist[c.cls], explanation: meta.explanation,
      scores: CLASS_ORDER.map((k) => ({ class: k, label: CLASS_META[k].label, p: dist[k] || 0 })),
    }],
  };
}

// No-backend fallback for Nose/Throat: honestly stubbed (0% confidence).
function buildStubResponse(mode) {
  return {
    mode, localizer: "stub", classifier: "stub", frame: null,
    grid: adaptiveGridFor(MOCK_BOX, "Normal"),
    results: [{
      class: "Normal", label: "Normal", status: "normal", box_norm: MOCK_BOX,
      confidence: 0, explanation: "Model not trained yet for this mode.", scores: [],
    }],
  };
}

async function fetchActivation(mode) {
  try {
    const r = await fetch(apiUrl(`/activate?mode=${mode}`), { method: "POST" });
    const data = await r.json();
    if (!r.ok || data.error) return { __error: (data && data.error) || `HTTP ${r.status}` };
    return data;
  } catch {
    return { __mock: true }; // no backend reachable → demo mode
  }
}

const CheckIcon = () => (
  <svg className="pill-check" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <path d="M2.2 6.3 4.8 8.8 9.8 3.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function Practice() {
  const [phase, setPhase] = useState("idle");   // freeze-mode flow: idle | analyzing | active | error
  const [live, setLive] = useState(false);      // Live continuous detection vs. Freeze single-shot
  const [region, setRegion] = useState("ear");
  const [resp, setResp] = useState(null);       // result being shown (freeze result OR latest live poll)
  const [errMsg, setErrMsg] = useState("");
  const [imgSrc, setImgSrc] = useState(apiUrl("/video_feed"));
  const [imgKind, setImgKind] = useState("feed"); // feed | case | frozen | none  (freeze mode only)
  const [liveErr, setLiveErr] = useState(false);  // /stream_detect unreachable (e.g. static preview)
  const [cameraConnected, setCameraConnected] = useState(null);
  const [camType, setCamType] = useState("webcam");     // webcam | phone — active camera source
  const [webcamOptions, setWebcamOptions] = useState([]); // local webcam indices found by the backend
  const [webcamIndex, setWebcamIndex] = useState(0);
  const [phoneUrlInput, setPhoneUrlInput] = useState(""); // phone MJPEG URL, e.g. http://<ip>:8080/stream
  const [camVersion, setCamVersion] = useState(0);        // bumped on every source switch to remount the feed <img>
  const [camBusy, setCamBusy] = useState(false);
  const [camStatusMsg, setCamStatusMsg] = useState("");
  const feedOk = useRef(true);
  const busy = useRef(false);
  const currentCase = CASES[0];
  const isEar = region === "ear";
  const regionLabel = REGIONS.find((rg) => rg.id === region).label;

  const showCaseOrDrum = (c) => { setImgSrc(c.img); setImgKind("case"); };

  const onImgError = () => {
    if (imgKind !== "feed") { setImgKind("none"); return; }
    feedOk.current = false;
    if (isEar) showCaseOrDrum(currentCase);
    else setImgKind("none");
  };

  const toIdle = (c = currentCase) => {
    setPhase("idle"); setResp(null); setErrMsg("");
    if (feedOk.current) { setImgSrc(apiUrl("/video_feed")); setImgKind("feed"); }
    else if (isEar) showCaseOrDrum(c);
    else setImgKind("none");
  };

  const selectRegion = (id) => {
    setRegion(id);
    setResp(null); setErrMsg(""); setLiveErr(false);
    if (!live) {
      setPhase("idle");
      if (feedOk.current) { setImgSrc(apiUrl("/video_feed")); setImgKind("feed"); }
      else if (id === "ear") showCaseOrDrum(currentCase);
      else setImgKind("none");
    }
  };

  const setLiveMode = (on) => {
    if (on === live) return;
    busy.current = false;
    setLive(on);
    setResp(null); setErrMsg(""); setLiveErr(false);
    if (on) setPhase("idle");
    else toIdle();
  };

  const activate = async () => {
    if (live || busy.current) return;
    busy.current = true;
    setPhase("analyzing");
    const [got] = await Promise.all([fetchActivation(region), delay(SCAN_MS)]);
    busy.current = false;
    if (got.__error) { setErrMsg(got.__error); setPhase("error"); return; }
    const data = got.__mock ? (isEar ? buildMockResponse(currentCase) : buildStubResponse(region)) : got;
    if (data.frame) { setImgSrc(data.frame); setImgKind("frozen"); }
    setResp(data);
    setPhase("active");
  };

  const onButton = () => {
    if (phase === "idle" || phase === "error") activate();
    else if (phase === "active") toIdle();
  };

  useEffect(() => { toIdle(); /* mount */ }, []); // eslint-disable-line

  useEffect(() => {
    let cancelled = false;
    fetch(apiUrl("/camera_status"))
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setCameraConnected(!!d.connected); })
      .catch(() => { if (!cancelled) setCameraConnected(false); });
    return () => { cancelled = true; };
  }, []);

  // Populate the camera picker: which local webcams exist + whichever
  // source (webcam/phone) the backend is already using.
  useEffect(() => {
    let cancelled = false;
    fetch(apiUrl("/camera_options"))
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        setWebcamOptions(d.webcams || []);
        if (d.source) {
          setCamType(d.source.type);
          setWebcamIndex(d.source.webcam_index ?? 0);
          setPhoneUrlInput(d.source.phone_url || "");
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // Switch the backend's active camera source, then force the feed/live
  // <img> to remount (open_camera() is only re-resolved for a FRESH MJPEG
  // connection, so the old one would otherwise keep streaming the old source).
  const applyCamera = async (payload) => {
    setCamBusy(true);
    setCamStatusMsg("");
    try {
      const r = await fetch(apiUrl("/camera_source"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await r.json();
      if (!r.ok || data.error) { setCamStatusMsg(data.error || `HTTP ${r.status}`); return; }
      if (data.source) {
        setCamType(data.source.type);
        setWebcamIndex(data.source.webcam_index ?? 0);
        setPhoneUrlInput(data.source.phone_url || "");
      }
      setCameraConnected(!!data.connected);
      setCamStatusMsg(data.connected ? "Connected" : "Not reachable — showing sample views.");
      feedOk.current = true;
      setLiveErr(false);
      setCamVersion((v) => v + 1);
      if (!live) toIdle();
    } catch {
      setCamStatusMsg("Could not reach the backend.");
    } finally {
      setCamBusy(false);
    }
  };

  const selectCamType = (type) => {
    setCamType(type);
    if (type === "webcam") applyCamera({ type: "webcam", index: webcamIndex });
    // "phone" waits for the explicit Connect click below — the URL usually needs editing first.
  };

  const connectPhone = () => {
    const url = phoneUrlInput.trim();
    if (url) applyCamera({ type: "phone", url });
  };

  // Live mode: poll the latest detection so the findings panel keeps updating.
  // Cleanup clears the interval when leaving Live mode, switching region, or
  // unmounting. (The /stream_detect connection itself closes when React
  // unmounts the <img> below.)
  useEffect(() => {
    if (!live) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(apiUrl(`/last_result?mode=${region}`));
        const data = await res.json();
        if (!cancelled && data && data.results && data.results.length) setResp(data);
      } catch { /* transient poll error — keep the last result */ }
    };
    poll();
    const id = setInterval(poll, LIVE_POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [live, region]);

  const r = resp && resp.results && resp.results[0];
  const pct = r ? Math.round((r.confidence || 0) * 100) : 0;
  const showDiagnosis = !!r && (live || phase === "active");
  const stageState = live ? "live" : (phase === "error" ? "idle" : phase);
  const gridReadout = resp?.grid
    ? (<><b>{resp.grid.rows}×{resp.grid.cols}</b> grid · {resp.grid.highlighted_cells?.length || 0} cell(s)</>)
    : (<><b>720p</b></>);

  const countText =
    showDiagnosis && r ? (r.confidence > 0 ? `${r.label} · ${pct}%` : "Model not trained yet")
    : live ? "Detecting…"
    : phase === "analyzing" ? "Scanning…"
    : phase === "error" ? "Scan failed"
    : "Awaiting scan";

  return (
    <div className="shell">
      <header className="topbar">
        <a className="back" href="#/">
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M13.5 8h-11M7 3.5 2.5 8 7 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
          MentoScope
        </a>
        <div className="mode" data-mode={live ? "live" : phase} role="status" aria-live="polite">
          <span className="mode__dot" aria-hidden="true"></span>
          <span className="mode__label">{live ? "Live" : MODE_LABEL[phase]}</span>
        </div>
      </header>

      <main className="workbench">
        <section className="panel scope" aria-label="Endoscope view">
          <div className="cases" role="group" aria-label="Region">
            <span className="cases__label">Region</span>
            <div className="cases__group">
              {REGIONS.map((rgn) => (
                <button
                  key={rgn.id} type="button" className="case-btn"
                  aria-pressed={region === rgn.id} aria-label={rgn.label}
                  onClick={() => selectRegion(rgn.id)}
                >
                  {region === rgn.id && <CheckIcon />}
                  {rgn.label}
                </button>
              ))}
            </div>
          </div>

          <div className="cases" role="group" aria-label="Camera source">
            <span className="cases__label">Camera</span>
            <div className="cases__group">
              <button type="button" className="case-btn" aria-pressed={camType === "webcam"} onClick={() => selectCamType("webcam")}>
                {camType === "webcam" && <CheckIcon />}Webcam
              </button>
              <button type="button" className="case-btn" aria-pressed={camType === "phone"} onClick={() => selectCamType("phone")}>
                {camType === "phone" && <CheckIcon />}ENT cam
              </button>
            </div>
          </div>

          {camType === "webcam" ? (
            webcamOptions.length > 1 && (
              <div className="camera-picker">
                <select
                  className="camera-picker__input" value={webcamIndex}
                  onChange={(e) => { const idx = Number(e.target.value); setWebcamIndex(idx); applyCamera({ type: "webcam", index: idx }); }}
                >
                  {webcamOptions.map((i) => <option key={i} value={i}>Webcam {i}</option>)}
                </select>
              </div>
            )
          ) : (
            <div className="camera-picker">
              <input
                type="text" className="camera-picker__input" placeholder="http://192.168.x.x:8080/stream"
                value={phoneUrlInput} onChange={(e) => setPhoneUrlInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") connectPhone(); }}
              />
              <button type="button" className="camera-picker__btn" onClick={connectPhone} disabled={camBusy}>
                {camBusy ? "Connecting…" : "Connect"}
              </button>
            </div>
          )}
          {camStatusMsg && <p className="camera-note">{camStatusMsg}</p>}

          {cameraConnected === false && !camStatusMsg && (
            <p className="camera-note">No endoscope detected — showing sample views.</p>
          )}

          <div className="scope__stage" data-state={stageState}>
            <div className={`scope__disc${((!isEar && imgKind === "none") || (live && liveErr && !isEar)) ? " is-soon" : ""}`}>
              {isEar && <div className="eardrum"><div className="eardrum__glare"></div></div>}

              {live ? (
                !liveErr && (
                  <img
                    key={`live-${region}-${camVersion}`} className="scope__img"
                    src={apiUrl(`/stream_detect?mode=${region}`)} onError={() => setLiveErr(true)}
                    alt={`Live ${regionLabel.toLowerCase()} detection`}
                  />
                )
              ) : (
                imgKind !== "none" && (
                  <img
                    key={`scope-img-${camVersion}`} className="scope__img" src={imgSrc} onError={onImgError}
                    alt={isEar ? "Otoscopic view of the tympanic membrane" : `Live ${regionLabel.toLowerCase()} view`}
                  />
                )
              )}

              {((!isEar && !live && imgKind === "none") || (!isEar && live && liveErr)) && (
                <div className="soon">
                  <span className="soon__label">{regionLabel}</span>
                  <span className="soon__tag">{live ? "Live unavailable" : "No preview image"}</span>
                </div>
              )}

              <div className="scope__vignette"></div>
              <div className="scan" aria-hidden="true">
                <div className="scan__line"></div>
                <div className="scan__reticle"><span className="scan__ring"></span></div>
              </div>
            </div>
            <svg className="scope__progress" viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="48" /></svg>
            <div className="scope__brackets" aria-hidden="true">
              <span className="bracket bracket--tl"></span><span className="bracket bracket--tr"></span>
              <span className="bracket bracket--bl"></span><span className="bracket bracket--br"></span>
            </div>
            {/* Adaptive grid overlay: grid resolution + highlighted cells come
                from THIS detection's response — not fixed or user-chosen. Live
                mode's grid is pulled from /last_result polling; when there's no
                result yet, no overlay is drawn. */}
            <div className="scope__overlay" aria-hidden="true">
              {showDiagnosis && resp?.grid && <ScopeGrid grid={resp.grid} result={r} />}
            </div>
          </div>

          <div className="scope__readout">
            <span>{live ? READOUT.live : READOUT[phase]}</span>
            <span>⌀ 4 mm · {gridReadout}</span>
          </div>

          <div className="controls">
            <div className="livetoggle" role="group" aria-label="Detection mode">
              <button type="button" className="lt-btn" aria-pressed={!live} onClick={() => setLiveMode(false)}>Freeze</button>
              <button type="button" className="lt-btn" aria-pressed={live} onClick={() => setLiveMode(true)}>Live</button>
            </div>
            {!live && (
              <button
                className={`btn ${phase === "active" ? "btn--ghost" : "btn--primary"}`}
                type="button" onClick={onButton}
                disabled={phase === "analyzing"} data-loading={phase === "analyzing"}
              >
                <svg className="btn__spinner" viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" /><path d="M10 2.5a7.5 7.5 0 0 1 7.5 7.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
                {phase === "analyzing" ? "Analyzing…" : phase === "active" ? "Reset" : "Activate"}
              </button>
            )}
            {live && <p className="controls__hint">Continuous detection — move the scope to inspect.</p>}
          </div>
        </section>

        <aside className="panel findings" aria-label="Findings">
          <div className="findings__head">
            <h2>Findings</h2>
            <span className="findings__count mono">{countText}</span>
          </div>
          <div className="findings__body" aria-live="polite">
            {showDiagnosis && r ? (
              <DiagnosisPanel result={r} />
            ) : live ? (
              <p className="findings__idle">Detecting…</p>
            ) : phase === "analyzing" ? (
              <div className="skeleton-list" aria-hidden="true">
                <div className="skel skel--chip"></div>
                <div className="skel skel--title"></div>
                <div className="skel skel--line"></div>
                <div className="skel skel--short"></div>
              </div>
            ) : phase === "error" ? (
              <div className="errbox">
                <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 3 18 16H2L10 3Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /><path d="M10 8.5v3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><circle cx="10" cy="14.4" r="0.9" fill="currentColor" /></svg>
                <div><h3>Scan failed</h3><p>{errMsg || "Capture or classification failed. Check the camera and try again."}</p></div>
              </div>
            ) : (
              <p className="findings__idle">No overlay yet.</p>
            )}
          </div>
        </aside>
      </main>

      <footer className="disclaimer">
        Training aid only — not a substitute for clinical examination or diagnosis.
      </footer>
    </div>
  );
}
