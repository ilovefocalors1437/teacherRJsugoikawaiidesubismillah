import { useEffect, useRef } from "react";

const CONTENT = {
  practice: {
    kicker: "PRACTICE MODE",
    sub: "Practice with Assistant",
    img: "./practice-card.png",
    href: "#/practice",
  },
  clarify: {
    kicker: "CLARIFY",
    sub: "Detect with Image",
    img: "./clarify-card.png",
    href: "#/clarify",
  },
  theory: {
    kicker: "TUTOR BOOK",
    sub: "Usage guideline",
    img: "./theory-card.png",
    href: "#/theory",
  },
  tutor: {
    kicker: "TUTOR BOOK",
    sub: "ENT Endoscopy Textbook",
    img: "./theory-card.png",
    href: "#/tutor",
  },
};

// 6 panels — two of each destination — so the ring reads full and balanced.
const PANELS = ["practice", "clarify", "tutor", "practice", "clarify", "tutor"];

const RADIUS_DESKTOP = 240;
const RADIUS_MOBILE = 150;
const BREAKPOINT = 720;
const DRAG_SENS = 0.32;
const WHEEL_SENS = 0.05;
const MAX_VELOCITY = 7;
const FRICTION = 0.94;
const DRAG_THRESHOLD = 6; // px of movement before a press counts as a drag, not a click
const TILT_RANGE_X = 20;
const TILT_RANGE_Y = 24;

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export default function Landing() {
  const stageRef = useRef(null);
  const ringRef = useRef(null);
  const parallaxRef = useRef(null);
  const panelRefs = useRef([]);

  useEffect(() => {
    const stage = stageRef.current;
    const ring = ringRef.current;
    const parallax = parallaxRef.current;
    const panels = panelRefs.current;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const radiusFor = () => (window.innerWidth <= BREAKPOINT ? RADIUS_MOBILE : RADIUS_DESKTOP);

    function positionPanels() {
      const r = radiusFor();
      const count = panels.length;
      panels.forEach((el, i) => {
        if (!el) return;
        const angle = (360 / count) * i;
        const tilt = Math.sin((i / count) * Math.PI * 2) * 6;
        el.style.setProperty("--ry", angle + "deg");
        el.style.setProperty("--tz", r + "px");
        el.style.setProperty("--rz", tilt.toFixed(2) + "deg");
      });
    }
    positionPanels();

    let resizeTimer;
    const onResize = () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(positionPanels, 200); };
    window.addEventListener("resize", onResize);

    // ---- ring rotation: drag + momentum + gentle auto-drift ----
    let rotation = 0;
    let velocity = 0;
    const baseDrift = reduced ? 0 : 0.1;
    let dragging = false;
    let lastX = 0;
    let dragDist = 0;
    let wasDrag = false;

    function onPointerDown(e) {
      dragging = true;
      dragDist = 0;
      wasDrag = false;
      lastX = e.clientX;
      velocity = 0;
      stage.classList.add("is-dragging");
    }
    function onPointerMove(e) {
      if (!dragging) return;
      const dx = e.clientX - lastX;
      lastX = e.clientX;
      dragDist += Math.abs(dx);
      if (dragDist > DRAG_THRESHOLD) wasDrag = true;
      const step = dx * DRAG_SENS;
      rotation += step;
      velocity = clamp(step, -MAX_VELOCITY, MAX_VELOCITY);
    }
    function endDrag() {
      if (!dragging) return;
      dragging = false;
      stage.classList.remove("is-dragging");
    }
    // A drag that moved past the threshold shouldn't also fire the anchor's navigation.
    function onClickCapture(e) {
      if (wasDrag) {
        e.preventDefault();
        e.stopPropagation();
        wasDrag = false;
      }
    }

    stage.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", endDrag);
    window.addEventListener("pointercancel", endDrag);
    stage.addEventListener("click", onClickCapture, true);

    function onWheel(e) {
      if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        e.preventDefault();
        velocity = clamp(velocity + e.deltaX * WHEEL_SENS, -MAX_VELOCITY, MAX_VELOCITY);
      }
    }
    stage.addEventListener("wheel", onWheel, { passive: false });

    // ---- mouse parallax tilt ----
    let targetX = 0, targetY = 0, curX = 0, curY = 0;
    function onMouseMove(e) {
      const mx = e.clientX / window.innerWidth - 0.5;
      const my = e.clientY / window.innerHeight - 0.5;
      targetY = mx * TILT_RANGE_Y;
      targetX = -my * TILT_RANGE_X;
    }
    if (!reduced) window.addEventListener("mousemove", onMouseMove);

    // ---- single animation loop ----
    let raf;
    function frame() {
      if (!dragging) {
        rotation += baseDrift + velocity;
        velocity *= FRICTION;
        if (Math.abs(velocity) < 0.0015) velocity = 0;
      }
      ring.style.transform = `rotateY(${rotation.toFixed(3)}deg)`;
      if (!reduced) {
        curX += (targetX - curX) * 0.06;
        curY += (targetY - curY) * 0.06;
        parallax.style.transform = `rotateX(${curX.toFixed(2)}deg) rotateY(${curY.toFixed(2)}deg)`;
      }
      raf = requestAnimationFrame(frame);
    }
    frame();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", endDrag);
      window.removeEventListener("pointercancel", endDrag);
      window.removeEventListener("mousemove", onMouseMove);
      stage.removeEventListener("pointerdown", onPointerDown);
      stage.removeEventListener("click", onClickCapture, true);
      stage.removeEventListener("wheel", onWheel);
    };
  }, []);

  return (
    <div className="orbit-hero">
      <div className="orbit-aura" aria-hidden="true"></div>
      <div className="orbit-stage" ref={stageRef}>
        <div className="orbit-parallax" ref={parallaxRef}>
          <div className="orbit-tilt">
            <div className="orbit-ring" ref={ringRef}>
              {PANELS.map((type, i) => {
                const c = CONTENT[type];
                return (
                  <a
                    key={i}
                    href={c.href}
                    className="orbit-panel"
                    ref={(el) => (panelRefs.current[i] = el)}
                    aria-label={`${c.kicker} — ${c.sub}`}
                  >
                    <img src={c.img} alt="" draggable="false" />
                    <span className="orbit-scrim" aria-hidden="true"></span>
                    <span className="orbit-cap" aria-hidden="true">
                      <span className="orbit-kicker">{c.kicker}</span>
                      <span className="orbit-sub">{c.sub}</span>
                    </span>
                  </a>
                );
              })}
            </div>
          </div>

          <div className="orbit-center">
            <p className="orbit-eyebrow">ENT · ENDOSCOPY TRAINER</p>
            <h1>MentoScope</h1>
            <p className="orbit-sub-text">Assistant for endoscopy training for nursing and medical students.</p>
          </div>
        </div>
      </div>
      <p className="orbit-hint" aria-hidden="true">Select your card</p>
      
    </div>
  );
}
