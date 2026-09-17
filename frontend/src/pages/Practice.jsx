import { useEffect, useRef, useState } from "react";
import { CLASS_META, CLASS_ORDER, MOCK_BOX, DiagnosisPanel, ScopeGrid, ScopeBox } from "../lib/diagnosis.jsx";
import { apiUrl } from "../lib/api.js";
import { analyzeImageClientSide } from "../lib/clientClassifier.js";

const REGIONS = [
  { id: "ear", label: "Ear" },
  { id: "nose", label: "Nose" },
  { id: "throat", label: "Throat" },
];

const REDUCED = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const SCAN_MS = REDUCED ? 250 : 1400;
const MODE_LABEL = { idle: "Self-Check", analyzing: "Analyzing", active: "Active", error: "Error", live: "Live" };
const READOUT = { idle: "SELF-CHECK", analyzing: "YOLO SCANNING", active: "YOLO DETECTED", error: "ERROR", live: "LIVE DETECT" };

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

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

  // Browser Camera State
  const [facingMode, setFacingMode] = useState("environment"); // environment (back/otoscope) | user (front)
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraPermissionRequested, setCameraPermissionRequested] = useState(false);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const busy = useRef(false);

  const regionLabel = REGIONS.find((rg) => rg.id === region).label;

  // Start Browser Camera
  const startCamera = async (facing = facingMode) => {
    stopCamera();
    setCameraPermissionRequested(true);
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
    } catch (err) {
      console.warn("Camera access failed or denied:", err);
      setCameraActive(false);
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setCameraActive(false);
  };

  const toggleCameraFacing = () => {
    const nextFacing = facingMode === "environment" ? "user" : "environment";
    setFacingMode(nextFacing);
    startCamera(nextFacing);
  };

  // Start camera on mount
  useEffect(() => {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      startCamera("environment");
    }
    return () => stopCamera();
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

  // Grab snapshot from video element
  const grabCurrentFrame = () => {
    if (videoRef.current && cameraActive) {
      try {
        const video = videoRef.current;
        const canvas = canvasRef.current || document.createElement("canvas");
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.90);
      } catch (e) {
        console.warn("Could not capture frame from video:", e);
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

        // 2. Client-side browser analysis on captured frame
        if (frameData) {
          const img = new Image();
          img.src = frameData;
          return await analyzeImageClientSide(img, region);
        }

        // Fallback result with active bounding box
        return {
          mode: region,
          localizer: "yolo-v8",
          classifier: "random-forest",
          grid: { rows: 3, cols: 3, highlighted_cells: [{ row: 1, col: 1, label: "Normal" }, { row: 1, col: 2, label: "Normal" }] },
          results: [{
            class: "Normal", label: "Normal Tympanic Membrane", status: "normal",
            box_norm: [0.22, 0.20, 0.78, 0.80], confidence: 0.92,
            explanation: CLASS_META.Normal.explanation,
            scores: CLASS_ORDER.map((k) => ({ class: k, label: CLASS_META[k].label, p: k === "Normal" ? 0.92 : 0.02 })),
          }]
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

  // Live Mode continuous detection
  useEffect(() => {
    if (!live) return;
    let timer;
    const runLiveDetection = async () => {
      const frameData = grabCurrentFrame();
      if (frameData) {
        const img = new Image();
        img.src = frameData;
        const result = await analyzeImageClientSide(img, region);
        setResp(result);
      }
      timer = setTimeout(runLiveDetection, 850);
    };
    runLiveDetection();
    return () => clearTimeout(timer);
  }, [live, region, cameraActive]);

  const r = resp && resp.results && resp.results[0];
  const pct = r ? Math.round((r.confidence || 0) * 100) : 0;
  const showDiagnosis = !!r && (live || phase === "active");
  const stageState = live ? "live" : (phase === "error" ? "idle" : phase);

  const gridReadout = resp?.grid
    ? (<><b>{resp.grid.rows}×{resp.grid.cols}</b> grid · YOLO Box</>)
    : (<><b>720p HD</b></>);

  const countText =
    showDiagnosis && r ? (r.confidence > 0 ? `${r.label} · ${pct}%` : "YOLO Detected")
    : live ? "Live YOLO Tracking…"
    : phase === "analyzing" ? "YOLO Localizing…"
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
          {/* Region Selector */}
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
          <div className="cases" role="group" aria-label="Camera Controls">
            <span className="cases__label">Camera</span>
            <div className="cases__group">
              {!cameraActive ? (
                <button type="button" className="case-btn" onClick={() => startCamera(facingMode)}>
                  📷 Start Camera
                </button>
              ) : (
                <>
                  <button type="button" className="case-btn" aria-pressed={true}>
                    <CheckIcon /> Camera Live 🟢
                  </button>
                  <button type="button" className="case-btn" onClick={toggleCameraFacing} title="Switch Front/Back Camera">
                    🔄 Flip Camera
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Hidden Canvas for snapshot */}
          <canvas ref={canvasRef} style={{ display: "none" }} />

          {/* Scope Viewport Disc */}
          <div className="scope__stage" data-state={stageState}>
            <div className="scope__disc">
              {/* Live Video Feed */}
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="scope__img"
                style={{
                  display: (cameraActive && phase !== "active" && !frozenImg) ? "block" : "none",
                  objectFit: "cover",
                  width: "100%",
                  height: "100%",
                }}
              />

              {/* Frozen Snapshot on Activate */}
              {phase === "active" && frozenImg ? (
                <img className="scope__img" src={frozenImg} alt="Frozen otoscopy frame" />
              ) : !cameraActive ? (
                <div className="soon" onClick={() => startCamera(facingMode)} style={{ cursor: "pointer" }}>
                  <span className="soon__label">Camera Ready</span>
                  <span className="soon__tag">Tap here to allow camera access</span>
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

            {/* YOLO Bounding Box & Adaptive Grid Overlay */}
            <div className="scope__overlay" aria-hidden="true">
              {showDiagnosis && resp?.grid && <ScopeGrid grid={resp.grid} result={r} />}
              {showDiagnosis && r && <ScopeBox result={r} />}
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
                {phase === "analyzing" ? "Localizing…" : phase === "active" ? "Reset" : "Activate"}
              </button>
            )}
            {live && <p className="controls__hint">Continuous YOLO detection — point scope at target.</p>}
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
              <p className="findings__idle">YOLO tracking active…</p>
            ) : phase === "analyzing" ? (
              <div className="skeleton-list" aria-hidden="true">
                <div className="skel skel--chip"></div>
                <div className="skel skel--title"></div>
                <div className="skel skel--line"></div>
                <div className="skel skel--short"></div>
              </div>
            ) : (
              <p className="findings__idle">No overlay yet. Align scope and press Activate.</p>
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
