import { useEffect, useRef, useState } from "react";
import { CLASS_META, CLASS_ORDER, MOCK_BOX, DiagnosisPanel, ScopeGrid, adaptiveGridFromBoxNorm, cellsOverlappingBoxNorm } from "../lib/diagnosis.jsx";
import { apiUrl } from "../lib/api.js";
import { analyzeImageClientSide } from "../lib/clientClassifier.js";

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

const MOCK_SCORES = {
  Normal:           { Normal: 0.92, Myringosclerosis: 0.04, Cerumen: 0.02, AOM: 0.01, CSOM: 0.01 },
  AOM:              { AOM: 0.88, CSOM: 0.07, Cerumen: 0.03, Normal: 0.01, Myringosclerosis: 0.01 },
  Cerumen:          { Cerumen: 0.90, CSOM: 0.05, Normal: 0.03, AOM: 0.01, Myringosclerosis: 0.01 },
  CSOM:             { CSOM: 0.85, AOM: 0.07, Cerumen: 0.05, Myringosclerosis: 0.02, Normal: 0.01 },
  Myringosclerosis: { Myringosclerosis: 0.86, Normal: 0.08, CSOM: 0.03, Cerumen: 0.02, AOM: 0.01 },
};

const REDUCED = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const SCAN_MS = REDUCED ? 300 : 1600;
const MODE_LABEL = { idle: "Self-Check", analyzing: "Analyzing", active: "Active", error: "Error", live: "Live" };
const READOUT = { idle: "SELF-CHECK", analyzing: "SCANNING", active: "AI OVERLAY", error: "ERROR", live: "LIVE DETECT" };

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

function buildMockResponse(c) {
  const dist = MOCK_SCORES[c.cls] || MOCK_SCORES.Normal;
  const meta = CLASS_META[c.cls] || CLASS_META.Normal;
  return {
    mode: "ear", localizer: "stub", classifier: "demo", frame: null,
    grid: { rows: 3, cols: 3, highlighted_cells: [{ row: 1, col: 1, label: c.cls }] },
    results: [{
      class: c.cls, label: meta.label, status: meta.status, box_norm: MOCK_BOX,
      confidence: dist[c.cls] || 0.88, explanation: meta.explanation,
      scores: CLASS_ORDER.map((k) => ({ class: k, label: CLASS_META[k].label, p: dist[k] || 0 })),
    }],
  };
}

const CheckIcon = () => (
  <svg className="pill-check" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <path d="M2.2 6.3 4.8 8.8 9.8 3.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function Practice() {
  const [phase, setPhase] = useState("idle");
  const [live, setLive] = useState(false);
  const [region, setRegion] = useState("ear");
  const [resp, setResp] = useState(null);
  const [frozenImg, setFrozenImg] = useState(null);
  const [activeCaseIdx, setActiveCaseIdx] = useState(0);

  // Camera & Stream State
  const [camSource, setCamSource] = useState("browser"); // browser | sample
  const [facingMode, setFacingMode] = useState("environment"); // environment (back/otoscopy) | user (front)
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState("");

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const busy = useRef(false);

  const isEar = region === "ear";
  const regionLabel = REGIONS.find((rg) => rg.id === region).label;
  const currentCase = CASES[activeCaseIdx] || CASES[0];

  // Request browser camera stream
  const startBrowserCamera = async (facing = facingMode) => {
    stopBrowserCamera();
    setCameraError("");
    try {
      const constraints = {
        video: {
          facingMode: facing,
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play().catch(() => {});
      }
      setCameraActive(true);
      setCamSource("browser");
    } catch (err) {
      console.warn("Browser camera access error:", err);
      setCameraActive(false);
      setCameraError("Camera permission denied or unavailable. Using simulated views.");
      setCamSource("sample");
    }
  };

  const stopBrowserCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setCameraActive(false);
  };

  // Toggle front / back camera
  const toggleFacing = () => {
    const nextFacing = facingMode === "environment" ? "user" : "environment";
    setFacingMode(nextFacing);
    startBrowserCamera(nextFacing);
  };

  // Initialize camera on mount
  useEffect(() => {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      startBrowserCamera("environment");
    } else {
      setCamSource("sample");
    }
    return () => stopBrowserCamera();
  }, []);

  const selectRegion = (id) => {
    setRegion(id);
    setResp(null);
    setPhase("idle");
    setFrozenImg(null);
  };

  const toIdle = () => {
    setPhase("idle");
    setResp(null);
    setFrozenImg(null);
  };

  // Capture frame from video or sample
  const grabCurrentFrame = () => {
    if (camSource === "browser" && videoRef.current && cameraActive) {
      try {
        const video = videoRef.current;
        const canvas = canvasRef.current || document.createElement("canvas");
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.85);
      } catch (e) {
        console.warn("Could not grab video frame:", e);
      }
    }
    return null;
  };

  const activate = async () => {
    if (live || busy.current) return;
    busy.current = true;
    setPhase("analyzing");

    const frameData = grabCurrentFrame();
    if (frameData) setFrozenImg(frameData);

    const [analysis] = await Promise.all([
      (async () => {
        // 1. Try local Flask backend if reachable
        try {
          const r = await fetch(apiUrl(`/activate?mode=${region}`), { method: "POST" });
          const data = await r.json();
          if (r.ok && !data.error && data.results && data.results.length) return data;
        } catch {}

        // 2. Client-side browser analysis on captured frame or sample
        if (frameData) {
          const img = new Image();
          img.src = frameData;
          return await analyzeImageClientSide(img, region);
        }

        // 3. Simulated sample case fallback
        return isEar ? buildMockResponse(currentCase) : {
          mode: region, localizer: "stub", classifier: "sample",
          results: [{ class: "Normal", label: "Normal", status: "normal", confidence: 0.91, explanation: "Standard mucosal appearance.", scores: [] }]
        };
      })(),
      delay(SCAN_MS),
    ]);

    busy.current = false;
    setResp(analysis);
    setPhase("active");
  };

  const onButton = () => {
    if (phase === "idle" || phase === "error") activate();
    else if (phase === "active") toIdle();
  };

  // Live Mode periodic detection
  useEffect(() => {
    if (!live) return;
    let timer;
    const runLive = async () => {
      const frameData = grabCurrentFrame();
      if (frameData) {
        const img = new Image();
        img.src = frameData;
        const result = await analyzeImageClientSide(img, region);
        setResp(result);
      } else {
        setResp(buildMockResponse(currentCase));
      }
      timer = setTimeout(runLive, 800);
    };
    runLive();
    return () => clearTimeout(timer);
  }, [live, region, currentCase, camSource, cameraActive]);

  const r = resp && resp.results && resp.results[0];
  const pct = r ? Math.round((r.confidence || 0) * 100) : 0;
  const showDiagnosis = !!r && (live || phase === "active");
  const stageState = live ? "live" : (phase === "error" ? "idle" : phase);

  const gridReadout = resp?.grid
    ? (<><b>{resp.grid.rows}×{resp.grid.cols}</b> grid · {resp.grid.highlighted_cells?.length || 0} cell(s)</>)
    : (<><b>720p</b></>);

  const countText =
    showDiagnosis && r ? (r.confidence > 0 ? `${r.label} · ${pct}%` : "Model verified")
    : live ? "Live Scanning…"
    : phase === "analyzing" ? "Analyzing…"
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
          {/* Region Picker */}
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

          {/* Camera Controls */}
          <div className="cases" role="group" aria-label="Camera Source">
            <span className="cases__label">Source</span>
            <div className="cases__group">
              <button
                type="button" className="case-btn"
                aria-pressed={camSource === "browser" && cameraActive}
                onClick={() => startBrowserCamera(facingMode)}
              >
                {camSource === "browser" && cameraActive && <CheckIcon />}
                Camera {cameraActive ? "🟢" : "📷"}
              </button>
              <button
                type="button" className="case-btn"
                aria-pressed={camSource === "sample"}
                onClick={() => { stopBrowserCamera(); setCamSource("sample"); }}
              >
                {camSource === "sample" && <CheckIcon />}
                Samples
              </button>
              {cameraActive && (
                <button type="button" className="case-btn" onClick={toggleFacing} title="Flip camera">
                  🔄 Flip
                </button>
              )}
            </div>
          </div>

          {/* Case Picker if in Sample mode */}
          {camSource === "sample" && isEar && (
            <div className="cases" role="group" aria-label="Sample cases" style={{ marginTop: "6px" }}>
              <span className="cases__label">Case</span>
              <div className="cases__group">
                {CASES.map((c, i) => (
                  <button
                    key={c.id} type="button" className="case-btn"
                    aria-pressed={activeCaseIdx === i}
                    onClick={() => { setActiveCaseIdx(i); toIdle(); }}
                  >
                    {activeCaseIdx === i && <CheckIcon />}
                    {c.cls}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Hidden Canvas for Frame Grab */}
          <canvas ref={canvasRef} style={{ display: "none" }} />

          {/* Scope Stage Viewport */}
          <div className="scope__stage" data-state={stageState}>
            <div className="scope__disc">
              {/* Video Element for Browser Camera */}
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="scope__img"
                style={{
                  display: (camSource === "browser" && cameraActive && phase !== "active" && !frozenImg) ? "block" : "none",
                  objectFit: "cover",
                  width: "100%",
                  height: "100%",
                }}
              />

              {/* Frozen Capture or Sample Image */}
              {phase === "active" && frozenImg ? (
                <img className="scope__img" src={frozenImg} alt="Frozen capture" />
              ) : camSource === "sample" && isEar ? (
                <img className="scope__img" src={currentCase.img} alt="Sample otoscopy view" />
              ) : !cameraActive ? (
                <div className="soon">
                  <span className="soon__label">Camera Ready</span>
                  <span className="soon__tag">Press "Camera 📷" to start feed</span>
                </div>
              ) : null}

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
              <button type="button" className="lt-btn" aria-pressed={!live} onClick={() => { setLive(false); toIdle(); }}>Freeze</button>
              <button type="button" className="lt-btn" aria-pressed={live} onClick={() => { setLive(true); setPhase("idle"); }}>Live</button>
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
            {live && <p className="controls__hint">Continuous detection — align camera to inspect.</p>}
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
              <p className="findings__idle">Live Scanning…</p>
            ) : phase === "analyzing" ? (
              <div className="skeleton-list" aria-hidden="true">
                <div className="skel skel--chip"></div>
                <div className="skel skel--title"></div>
                <div className="skel skel--line"></div>
                <div className="skel skel--short"></div>
              </div>
            ) : (
              <p className="findings__idle">No overlay yet. Align view and press Activate.</p>
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
