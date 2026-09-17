import { CHAPTERS } from "../content/chapters.js";

export default function TutorBook() {
  return (
    <div className="shell">
      <header className="topbar">
        <a className="back" href="#/">
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M13.5 8h-11M7 3.5 2.5 8 7 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          MentoScope
        </a>
        <div className="mode" data-mode="idle">
          <span className="mode__dot"></span>
          <span className="mode__label">TUTOR BOOK</span>
        </div>
      </header>

      <div className="tb-hero">
        <p className="theory__kicker">Tutor Book</p>
        <h1 className="tb-title">คู่มือสำหรับผู้เรียน</h1>
        <p className="theory__note">เลือกบทเรียนเพื่อเริ่มอ่าน</p>
      </div>

      <div className="tb-grid">
        {CHAPTERS.map((ch) => (
          <a key={ch.id} href={`#/tutor/${ch.id}`} className="tb-card">
            <div className="tb-card__num">{ch.num}</div>
            <div className="tb-card__body">
              <h2 className="tb-card__title">{ch.title}</h2>
              <p className="tb-card__sub">{ch.subtitle}</p>
              <p className="tb-card__desc">{ch.description}</p>
            </div>
            <svg className="tb-card__arrow" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </a>
        ))}
      </div>

      <footer className="disclaimer">
        Training aid only — not a substitute for clinical examination or diagnosis.
      </footer>
    </div>
  );
}
