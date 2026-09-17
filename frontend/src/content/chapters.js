// Chapter metadata + raw markdown imports.
// Content lives in the .md files — this just wires them up.
// Add a new chapter by dropping a .md file and adding one entry here.

import earMd from "./01_ear.md?raw";
import noseMd from "./02_nose.md?raw";
import larynxMd from "./03_larynx.md?raw";
import reasoningMd from "./04_diagnostic_reasoning.md?raw";

export const CHAPTERS = [
  {
    id: "ear",
    num: "01",
    title: "การส่องตรวจหู",
    subtitle: "Otoscopy",
    description: "กายวิภาคเยื่อแก้วหู เทคนิคการตรวจ และภาวะอันตราย NOE",
    md: earMd,
  },
  {
    id: "nose",
    num: "02",
    title: "การส่องตรวจจมูกและไซนัส",
    subtitle: "Nasal Endoscopy",
    description: "เทคนิคสามขั้นตอน ความแปรผันทางกายวิภาค และ EPOS 2020",
    md: noseMd,
  },
  {
    id: "larynx",
    num: "03",
    title: "การส่องตรวจกล่องเสียง",
    subtitle: "Laryngoscopy",
    description: "เทคนิค TFEL แยกโรค 3 กลุ่มที่ทำให้เสียงแหบเรื้อรัง",
    md: larynxMd,
  },
  {
    id: "reasoning",
    num: "04",
    title: "กระบวนการคิดวิเคราะห์ทางคลินิก",
    subtitle: "Diagnostic Reasoning",
    description: "กระบวนการคิด 4 ขั้น และ Red Flags รวม 3 ระบบ",
    md: reasoningMd,
  },
];
