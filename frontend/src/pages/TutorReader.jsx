import { useState, useRef, useEffect, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CHAPTERS } from "../content/chapters.js";

const MAX_CHARS_PER_PAGE = 800;

/**
 * Split markdown into pages. Strategy:
 * - Split by ## headings (each section starts on a new page)
 * - If a section is too long, split by paragraphs at ~MAX_CHARS_PER_PAGE
 * - Tables are NEVER split — they stay on one page even if over the limit
 * - The ```diagram code block is detected and rendered as a flow chart
 */
function paginate(md) {
  const lines = md.split("\n");
  const pages = [];
  let current = [];
  let inTable = false;
  let inDiagram = false;

  const flush = () => {
    if (current.length > 0) {
      const text = current.join("\n").trim();
      if (text) pages.push(text);
      current = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Detect diagram code block
    if (line.trim().startsWith("```diagram")) {
      flush();
      inDiagram = true;
      continue;
    }
    if (inDiagram) {
      if (line.trim() === "```") {
        // Collect diagram content
        const diagContent = current.join("\n");
        pages.push("__DIAGRAM__\n" + diagContent);
        current = [];
        inDiagram = false;
      } else {
        current.push(line);
      }
      continue;
    }

    // Detect table blocks — accumulate whole table, don't split
    if (line.trim().startsWith("|")) {
      if (!inTable) {
        flush();
        inTable = true;
      }
      current.push(line);
      continue;
    } else if (inTable) {
      inTable = false;
    }

    // New ## heading → start a new page (but not the first one)
    if (line.startsWith("## ") && current.length > 0) {
      flush();
    }

    current.push(line);
  }
  flush();

  // Second pass: split overly long non-table, non-diagram pages by paragraph
  const finalPages = [];
  for (const page of pages) {
    if (page.startsWith("__DIAGRAM__")) {
      finalPages.push(page);
      continue;
    }
    if (page.length <= MAX_CHARS_PER_PAGE || page.includes("|---|")) {
      finalPages.push(page);
      continue;
    }
    // Split by double-newline (paragraph boundaries)
    const paras = page.split(/\n\n+/);
    let chunk = "";
    for (const para of paras) {
      if ((chunk + para).length > MAX_CHARS_PER_PAGE && chunk) {
        finalPages.push(chunk.trim());
        chunk = "";
      }
      chunk += para + "\n\n";
    }
    if (chunk.trim()) finalPages.push(chunk.trim());
  }

  return finalPages;
}

/** Parse the diagram code block into structured steps */
function parseDiagram(text) {
  const lines = text.split("\n").filter((l) => l.trim() && !l.trim().startsWith("```"));
  const steps = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === "↓" || trimmed.startsWith("---")) continue;
    // Lines like "1. Title\n   description"
    const match = trimmed.match(/^(\d+)\.\s+(.+)/);
    if (match) {
      steps.push({ num: match[1], title: match[2] });
    } else if (steps.length > 0) {
      // Continuation of previous step
      steps[steps.length - 1].title += " " + trimmed;
    }
  }
  return steps;
}

function DiagramFlow({ steps }) {
  return (
    <div className="tb-diagram">
      {steps.map((step, i) => (
        <div key={i} className="tb-diagram__item">
          <div className="tb-diagram__box">
            <span className="tb-diagram__num">{step.num}</span>
            <span className="tb-diagram__text">{step.title}</span>
          </div>
          {i < steps.length - 1 && (
            <div className="tb-diagram__arrow" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <path d="M12 4v14M6 12l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function TutorReader({ chapterId }) {
  const chapter = CHAPTERS.find((c) => c.id === chapterId) || CHAPTERS[0];
  const pages = useMemo(() => paginate(chapter.md), [chapter]);
  const [pageNum, setPageNum] = useState(0);
  const [flipDir, setFlipDir] = useState(null);
  const touchStart = useRef(null);

  useEffect(() => {
    setPageNum(0);
  }, [chapterId]);

  const goNext = () => {
    if (pageNum < pages.length - 1) {
      setFlipDir("next");
      setTimeout(() => { setPageNum(pageNum + 1); setFlipDir(null); }, 300);
    }
  };
  const goPrev = () => {
    if (pageNum > 0) {
      setFlipDir("prev");
      setTimeout(() => { setPageNum(pageNum - 1); setFlipDir(null); }, 300);
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pageNum, pages.length]);

  // Swipe navigation
  const onTouchStart = (e) => { touchStart.current = e.touches[0].clientX; };
  const onTouchEnd = (e) => {
    if (!touchStart.current) return;
    const dx = e.changedTouches[0].clientX - touchStart.current;
    if (Math.abs(dx) > 50) { if (dx > 0) goPrev(); else goNext(); }
    touchStart.current = null;
  };

  const page = pages[pageNum] || "";
  const isDiagram = page.startsWith("__DIAGRAM__");
  const diagramSteps = isDiagram ? parseDiagram(page.replace("__DIAGRAM__\n", "")) : [];
  const progress = ((pageNum + 1) / pages.length) * 100;

  return (
    <div className="shell tb-reader">
      <header className="topbar">
        <a className="back" href="#/tutor">
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M13.5 8h-11M7 3.5 2.5 8 7 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Tutor Book
        </a>
        <span className="mode__label" style={{ color: "var(--text-faint)" }}>
          {chapter.num} · {chapter.subtitle}
        </span>
      </header>

      {/* Progress bar */}
      <div className="tb-progress">
        <div className="tb-progress__bar" style={{ width: `${progress}%` }}></div>
      </div>

      {/* Page content with flip animation */}
      <div
        className={`tb-page-container${flipDir ? ` tb-page-container--${flipDir}` : ""}`}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        <div className="tb-page" key={pageNum}>
          {isDiagram ? (
            <DiagramFlow steps={diagramSteps} />
          ) : (
            <div className="tb-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{page}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>

      {/* Navigation footer */}
      <div className="tb-nav">
        <button
          className="tb-nav__btn"
          onClick={goPrev}
          disabled={pageNum === 0}
          aria-label="Previous page"
        >
          <svg viewBox="0 0 16 16" fill="none"><path d="M10 3 5 8l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        <span className="tb-nav__count mono">{pageNum + 1} / {pages.length}</span>
        <button
          className="tb-nav__btn"
          onClick={goNext}
          disabled={pageNum === pages.length - 1}
          aria-label="Next page"
        >
          <svg viewBox="0 0 16 16" fill="none"><path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
      </div>
    </div>
  );
}
