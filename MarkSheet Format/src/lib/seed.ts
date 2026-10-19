import { db } from "@/db";
import { students, marks, additionalMarks } from "@/db/schema";
import { count } from "drizzle-orm";

const SUBJECTS = ["Arabic", "Bengali", "E.V.S", "English", "G.K.", "Hindi", "Mathematics", "Science"];
const ADDITIONAL = ["Physical Education", "Work Education", "Hand Writing", "Behaviour", "Attendance"];
const MONTHS = ["January", "February", "March", "April"];
const MONTHLY_FM = 20;

interface SeedStudent {
  name: string;
  guardian: string;
  className: string;
  roll: string;
  section: string;
  profile: number; // 0..1 ability level
}

const ROSTER: SeedStudent[] = [
  { name: "Mahir Rahaman", guardian: "Rafiqul Rahaman", className: "U/N", roll: "1", section: "A", profile: 0.88 },
  { name: "Ayesha Khatun", guardian: "Jamil Ahmed", className: "U/N", roll: "2", section: "A", profile: 0.62 },
  { name: "Rohan Ali", guardian: "Sekendar Ali", className: "One", roll: "1", section: "A", profile: 0.93 },
  { name: "Sumaiya Akter", guardian: "Habibur Rahman", className: "One", roll: "2", section: "A", profile: 0.28 },
  { name: "Imran Hossain", guardian: "Mokbul Hossain", className: "Two", roll: "1", section: "A", profile: 0.55 },
  { name: "Nusrat Jahan", guardian: "Anwarul Islam", className: "Two", roll: "2", section: "A", profile: 0.81 },
  { name: "Sabbir Ahmed", guardian: "Nurul Ahmed", className: "Three", roll: "1", section: "A", profile: 0.47 },
  { name: "Fatema Begum", guardian: "Abdul Karim", className: "Three", roll: "2", section: "A", profile: 0.72 },
];

/** Tiny deterministic PRNG so re-seeds are stable. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function around(rand: () => number, profile: number, limit: number): number {
  const jitter = (rand() - 0.5) * 0.22;
  const ratio = Math.min(0.99, Math.max(0.08, profile + jitter));
  return Math.round(ratio * limit);
}

export async function ensureSeeded(): Promise<void> {
  try {
    const [{ value: n }] = await db.select({ value: count() }).from(students);
    if (n > 0) return;

    for (let i = 0; i < ROSTER.length; i++) {
      const s = ROSTER[i];
      const [student] = await db
        .insert(students)
        .values({
          name: s.name,
          guardianName: s.guardian,
          className: s.className,
          rollNumber: s.roll,
          section: s.section,
        })
        .returning({ id: students.id });
      const sid = student.id;
      const rand = rng(sid * 7919 + 13);

      const markRows: typeof marks.$inferInsert[] = [];

      for (const sub of SUBJECTS) {
        // 1st Unit: OR/10 + WR/40
        const u1o = around(rand, s.profile, 10);
        const u1w = around(rand, s.profile, 40);
        markRows.push({
          studentId: sid, examGroup: "term", term: "1st Unit", subject: sub,
          oral: u1o, oralLimit: 10, written: u1w, writtenLimit: 40,
          obtained: u1o + u1w, total: 50,
        });
        // 2nd Unit
        const u2o = around(rand, s.profile, 10);
        const u2w = around(rand, s.profile, 40);
        markRows.push({
          studentId: sid, examGroup: "term", term: "2nd Unit", subject: sub,
          oral: u2o, oralLimit: 10, written: u2w, writtenLimit: 40,
          obtained: u2o + u2w, total: 50,
        });
        // Final Exam: OR/20 + WR/70 + CT/10
        const fo = around(rand, s.profile, 20);
        const fw = around(rand, s.profile, 70);
        const fc = around(rand, s.profile, 10);
        markRows.push({
          studentId: sid, examGroup: "term", term: "Final Exam", subject: sub,
          oral: fo, oralLimit: 20, written: fw, writtenLimit: 70, ct: fc, ctLimit: 10,
          obtained: fo + fw + fc, total: 100,
        });
        // Monthly tests
        for (const m of MONTHS) {
          const obt = around(rand, s.profile, MONTHLY_FM);
          markRows.push({
            studentId: sid, examGroup: "monthly", term: m, subject: sub,
            obtained: obt, total: MONTHLY_FM,
          });
        }
      }

      // Art (co-scholastic, single figure per exam)
      const artU1 = around(rand, s.profile, 50);
      const artU2 = around(rand, s.profile, 50);
      const artF = around(rand, s.profile, 100);
      markRows.push(
        { studentId: sid, examGroup: "term", term: "1st Unit", subject: "Art", isArt: true, obtained: artU1, total: 50 },
        { studentId: sid, examGroup: "term", term: "2nd Unit", subject: "Art", isArt: true, obtained: artU2, total: 50 },
        { studentId: sid, examGroup: "term", term: "Final Exam", subject: "Art", isArt: true, obtained: artF, total: 100 }
      );

      await db.insert(marks).values(markRows);

      // Additional subjects per term + Annual composite
      const addRows: typeof additionalMarks.$inferInsert[] = [];
      for (const term of ["1st Unit", "2nd Unit", "Final Exam", "Annual"]) {
        for (const a of ADDITIONAL) {
          addRows.push({
            studentId: sid, term, subject: a,
            fullMarks: 100,
            obtained: around(rand, s.profile, 100),
          });
        }
      }
      await db.insert(additionalMarks).values(addRows);
    }
  } catch (err) {
    // Tables may not exist yet on first boot; the page layer retries.
    console.warn("[seed] skipped:", err instanceof Error ? err.message : err);
  }
}
