/* Ambient bottom light — a deep-blue-into-teal aura at the base of the
   viewport with slow, softly-glowing light motes drifting up. Fixed, behind
   all content, pointer-events-none. Reduced-motion keeps the static glow and
   drops the drifting motes. */
const MOTES = [
  { left: "6%",  size: 6,  dur: 22, delay: 0,  drift: "18px" },
  { left: "14%", size: 10, dur: 27, delay: 7,  drift: "-12px" },
  { left: "22%", size: 5,  dur: 19, delay: 3,  drift: "14px" },
  { left: "31%", size: 8,  dur: 30, delay: 11, drift: "-20px" },
  { left: "39%", size: 12, dur: 24, delay: 2,  drift: "22px" },
  { left: "47%", size: 6,  dur: 28, delay: 9,  drift: "-14px" },
  { left: "55%", size: 9,  dur: 21, delay: 5,  drift: "16px" },
  { left: "63%", size: 5,  dur: 26, delay: 13, drift: "-10px" },
  { left: "71%", size: 11, dur: 23, delay: 1,  drift: "20px" },
  { left: "79%", size: 6,  dur: 29, delay: 8,  drift: "-18px" },
  { left: "87%", size: 8,  dur: 20, delay: 4,  drift: "12px" },
  { left: "94%", size: 5,  dur: 25, delay: 10, drift: "-8px" },
];

export default function AmbientGlow() {
  return (
    <div className="ambient" aria-hidden="true">
      <div className="ambient__glow"></div>
      <div className="ambient__motes">
        {MOTES.map((m, i) => (
          <span
            key={i}
            className="mote"
            style={{
              left: m.left,
              "--size": `${m.size}px`,
              "--dur": `${m.dur}s`,
              "--delay": `${m.delay}s`,
              "--drift": m.drift,
            }}
          />
        ))}
      </div>
    </div>
  );
}
