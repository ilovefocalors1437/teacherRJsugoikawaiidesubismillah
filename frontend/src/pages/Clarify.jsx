import { useEffect, useRef, useState } from "react";
import { DiagnosisPanel, ScopeGrid } from "../lib/diagnosis.jsx";
import { apiUrl } from "../lib/api.js";

const REGIONS = [
  { id: "ear", label: "Ear" },
  { id: "nose", label: "Nose" },
  { id: "throat", label: "Throat" },
];

const ACCEPT_EXT = [".png", ".jpg", ".jpeg"];
const ACCEPT_TYPES = ["image/png", "image/jpeg"];
const MODE_LABEL = { empty: "Upload", analyzing: "Analysing", result: "Result", error: "Error" };
const READOUT = { empty: "UPLOAD", analyzing: "ANALYSING", result: "IMAGE ANALYSED", error: "ERROR" };

function isAllowed(file) {
  const name = (file.name || "").toLowerCase();
  const okExt = ACCEPT_EXT.some((e) => name.endsWith(e));
  const okType = !file.type || ACCEPT_TYPES.includes(file.type);
  return okExt && okType;
}

async function classifyUpload(file, mode) {
  const fd = new FormData();
  fd.append("image", file);
  try {
    const res = await fetch(apiUrl(`/classify_upload?mode=${mode}`), { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok || data.error) return { __error: (data && data.error) || `HTTP ${res.status}` };
    return data;
  } catch {
    return { __error: "Upload failed — is the server running?" };
  }
}

const CheckIcon = () => (
  <svg className="pill-check" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <path d="M2.2 6.3 4.8 8.8 9.8 3.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function Clarify() {
  const [status, setStatus] = useState("empty"); // empty | analyzing | result | error
  const [region, setRegion] = useState("ear");
  const [resp, setResp] = useState(null);
  const [errMsg, setErrMsg] = useState("");
  const [previewSrc, setPreviewSrc] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);
  const previewUrl = useRef(null);

  const regionLabel = REGIONS.find((rg) => rg.id === region).label;

  const clearPreview = () => {
    if (previewUrl.current) { URL.revokeObjectURL(previewUrl.current); previewUrl.current = null; }
  };
  useEffect(() => clearPreview, []); // revoke object URL on unmount

  const resetToEmpty = () => {
    clearPreview();
    setStatus("empty"); setResp(null); setErrMsg(""); setPreviewSrc(null);
  };

  const selectRegion = (id) => {
    setRegion(id);
    resetToEmpty(); // a fresh region needs a fresh upload
  };

  const handleFiles = async (files) => {
    if (!files || !files.length) return;
    const file = files[0];
    if (!isAllowed(file)) {
      clearPreview();
      setResp(null); setPreviewSrc(null);
      setErrMsg("Unsupported file type. Please upload a PNG or JPG image.");
      setStatus("error");
      return;
    }
    clearPreview();
    previewUrl.current = URL.createObjectURL(file);
    setPreviewSrc(previewUrl.current);
    setResp(null); setErrMsg("");
    setStatus("analyzing");

    const got = await classifyUpload(file, region);
    if (got.__error) { setErrMsg(got.__error); setStatus("error"); return; }
    setResp(got);
    setStatus("result");
  };

  const onDrop = (e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); };
  const onDragOver = (e) => { e.preventDefault(); setDragOver(true); };
  const onDragLeave = () => setDragOver(false);
  const openPicker = () => fileRef.current && fileRef.current.click();

  const r = resp && resp.results && resp.results[0];
  const pct = r ? Math.round((r.confidence || 0) * 100) : 0;
  const showDropzone = status === "empty" || status === "error";
  const stageState = status === "analyzing" ? "analyzing" : "idle";

  const countText =
    status === "result" && r ? (r.confidence > 0 ? `${r.label} · ${pct}%` : "Model not trained yet")
    : status === "analyzing" ? "Analysing…"
    : status === "error" ? "Upload failed"
    : "Awaiting image";

  const btnLabel = status === "analyzing" ? "Analysing…" : status === "result" ? "Upload another" : "Choose image";

  return (
    <div className="shell">
      <header className="topbar">
        <a className="back" href="#/">
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M13.5 8h-11M7 3.5 2.5 8 7 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
          MentoScope
        </a>
        <div className="mode" data-mode={status === "result" ? "active" : status === "analyzing" ? "analyzing" : status === "error" ? "error" : "idle"} role="status" aria-live="polite">
          <span className="mode__dot" aria-hidden="true"></span>
          <span className="mode__label">{MODE_LABEL[status]}</span>
        </div>
      </header>

      <main className="workbench">
        <section className="panel scope" aria-label="Image analysis">
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

          <div className="scope__stage" data-state={stageState}>
            <div
              className={`scope__disc${showDropzone ? " scope__disc--drop" : ""}${dragOver ? " is-drag" : ""}`}
              onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
            >
              {showDropzone ? (
                <button type="button" className="dropzone" onClick={openPicker}>
                  <svg className="dropzone__icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M12 15.5V4M12 4 7.5 8.5M12 4l4.5 4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M4.5 15v3.5A1.5 1.5 0 0 0 6 20h12a1.5 1.5 0 0 0 1.5-1.5V15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                  </svg>
                  <span className="dropzone__title">Drop image or click to browse</span>
                  <span className="dropzone__hint">PNG or JPG</span>
                </button>
              ) : (
                <img className="scope__img" src={status === "result" ? resp.frame : previewSrc} alt="Uploaded image for analysis" />
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
            <div className="scope__overlay" aria-hidden="true">
              {status === "result" && r && <ScopeGrid grid={resp.grid} result={r} />}
            </div>
          </div>

          <div className="scope__readout">
            <span>{READOUT[status]}</span>
            <span>PNG / JPG · <b>{regionLabel}</b>{resp?.grid ? ` · ${resp.grid.rows}×${resp.grid.cols}` : ""}</span>
          </div>

          <div className="controls">
            <button
              className={`btn ${status === "result" ? "btn--ghost" : "btn--primary"}`}
              type="button" onClick={openPicker}
              disabled={status === "analyzing"} data-loading={status === "analyzing"}
            >
              <svg className="btn__spinner" viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" /><path d="M10 2.5a7.5 7.5 0 0 1 7.5 7.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
              {btnLabel}
            </button>
          </div>

          <input
            ref={fileRef} type="file" hidden
            accept="image/png,image/jpeg,.png,.jpg,.jpeg"
            onChange={(e) => { handleFiles(e.target.files); e.target.value = ""; }}
          />
        </section>

        <aside className="panel findings" aria-label="Findings">
          <div className="findings__head">
            <h2>Findings</h2>
            <span className="findings__count mono">{countText}</span>
          </div>
          <div className="findings__body" aria-live="polite">
            {status === "result" && r ? (
              <DiagnosisPanel result={r} />
            ) : status === "analyzing" ? (
              <div className="skeleton-list" aria-hidden="true">
                <div className="skel skel--chip"></div>
                <div className="skel skel--title"></div>
                <div className="skel skel--line"></div>
                <div className="skel skel--short"></div>
              </div>
            ) : status === "error" ? (
              <div className="errbox">
                <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 3 18 16H2L10 3Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" /><path d="M10 8.5v3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /><circle cx="10" cy="14.4" r="0.9" fill="currentColor" /></svg>
                <div><h3>Couldn't analyse that image</h3><p>{errMsg || "Please try a different PNG or JPG file."}</p></div>
              </div>
            ) : (
              <p className="findings__idle">Upload a PNG or JPG to detect.</p>
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
