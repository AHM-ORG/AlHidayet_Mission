import { eq, and } from "drizzle-orm";
import { db } from "@/db";
import { students, marks, additionalMarks } from "@/db/schema";
import type { MarkRow, AdditionalRow, StudentRow } from "@/db/schema";
import {
  gradeFromPercent,
  termKind,
  fmt,
  type SubjectMarkView,
  type AdditionalView,
  type TermView,
  type MonthlyView,
  type MonthlyRow,
  type MonthlyCell,
  type AnnualView,
  type AnnualSubject,
  type MarksheetPayload,
} from "@/lib/marksheet-types";

export * from "@/lib/marksheet-types";

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function pct(obt: number, pos: number): number {
  if (pos <= 0) return 0;
  return Math.round((obt / pos) * 1000) / 10;
}

function toSubjectView(m: MarkRow): SubjectMarkView {
  const p = m.total ? pct(m.obtained, m.total) : 0;
  return {
    subject: m.subject,
    isArt: m.isArt,
    oral: m.oral,
    oralLimit: m.oralLimit,
    written: m.written,
    writtenLimit: m.writtenLimit,
    ct: m.ct,
    ctLimit: m.ctLimit,
    obtained: m.obtained,
    total: m.total,
    grade: gradeFromPercent(p),
  };
}

const MONTH_SHORT: Record<string, string> = {
  January: "JAN", February: "FEB", March: "MAR", April: "APR",
  May: "MAY", June: "JUN", July: "JUL", August: "AUG",
  September: "SEP", October: "OCT", November: "NOV", December: "DEC",
};

const TERM_ORDER = ["1st Unit", "2nd Unit", "Final Exam"];

/* ------------------------------------------------------------------ */
/* Builders                                                            */
/* ------------------------------------------------------------------ */

function buildTerms(allMarks: MarkRow[], allAdd: AdditionalRow[]): TermView[] {
  const termRows = allMarks.filter((m) => m.examGroup === "term");
  const byTerm = new Map<string, MarkRow[]>();
  for (const m of termRows) {
    const arr = byTerm.get(m.term) ?? [];
    arr.push(m);
    byTerm.set(m.term, arr);
  }
  const termNames = [...byTerm.keys()].sort((a, b) => {
    const ia = TERM_ORDER.indexOf(a);
    const ib = TERM_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b);
  });

  return termNames.map((term) => {
    const rows = byTerm.get(term)!;
    const subjects = rows
      .filter((r) => !r.isArt)
      .map(toSubjectView)
      .sort((a, b) => a.subject.localeCompare(b.subject));
    const artRow = rows.find((r) => r.isArt);

    let totalObtained = 0;
    let totalPossible = 0;
    for (const r of rows) {
      totalObtained += r.obtained ?? 0;
      totalPossible += r.total ?? 0;
    }

    const additional: AdditionalView[] = allAdd
      .filter((a) => a.term === term)
      .map((a) => ({ subject: a.subject, fullMarks: a.fullMarks, obtained: a.obtained }));

    const percent = pct(totalObtained, totalPossible);
    return {
      term,
      kind: termKind(term),
      subjects,
      art: artRow ? toSubjectView(artRow) : null,
      additional,
      totalObtained,
      totalPossible,
      percent,
      grade: gradeFromPercent(percent),
      passed: percent >= 35,
      hasData: rows.length > 0,
    };
  });
}

function buildMonthly(allMarks: MarkRow[]): MonthlyView {
  const rows = allMarks.filter((m) => m.examGroup === "monthly");
  const empty: MonthlyView = {
    terms: [], short: {}, columnFull: {}, rows: [],
    grandObt: 0, grandPos: 0, percent: 0, grade: "D", passed: false, hasData: false,
  };
  if (rows.length === 0) return empty;

  const monthOrder = Array.from(new Set(rows.map((r) => r.term)));
  const calendar = Object.keys(MONTH_SHORT);
  monthOrder.sort((a, b) => calendar.indexOf(a) - calendar.indexOf(b));

  const subjects = Array.from(new Set(rows.map((r) => r.subject))).sort((a, b) =>
    a.localeCompare(b)
  );

  const lookup = new Map<string, MarkRow>();
  for (const r of rows) lookup.set(`${r.subject}::${r.term}`, r);

  const columnFull: Record<string, string> = {};
  for (const t of monthOrder) {
    const sample = rows.find((r) => r.term === t);
    columnFull[t] = sample ? fmt(sample.total) : "-";
  }

  const grid: MonthlyRow[] = subjects.map((sub) => {
    const cells: Record<string, MonthlyCell> = {};
    let obt = 0;
    let pos = 0;
    let any = false;
    for (const t of monthOrder) {
      const m = lookup.get(`${sub}::${t}`);
      if (m) {
        cells[t] = { obtained: fmt(m.obtained), full: fmt(m.total) };
        obt += m.obtained ?? 0;
        pos += m.total ?? 0;
        any = true;
      } else {
        cells[t] = { obtained: "-", full: columnFull[t] };
      }
    }
    return {
      name: sub,
      cells,
      totalObt: any ? fmt(obt) : "-",
      totalPos: any ? fmt(pos) : "-",
      grade: any ? gradeFromPercent(pct(obt, pos)) : "-",
    };
  });

  const grandObt = rows.reduce((s, r) => s + (r.obtained ?? 0), 0);
  const grandPos = rows.reduce((s, r) => s + (r.total ?? 0), 0);
  const percent = pct(grandObt, grandPos);

  return {
    terms: monthOrder,
    short: MONTH_SHORT,
    columnFull,
    rows: grid,
    grandObt,
    grandPos,
    percent,
    grade: gradeFromPercent(percent),
    passed: percent >= 35,
    hasData: true,
  };
}

interface AnnualAgg {
  subjects: AnnualSubject[];
  art: AnnualView["art"];
  sums: AnnualView["sums"];
  additional: AdditionalView[];
  additionalFmTotal: number;
  additionalObtTotal: number;
  maxMarks: number;
  totalObtained: number;
  percent: number;
  overallGrade: string;
  passed: boolean;
  hasData: boolean;
}

function aggregateAnnual(allMarks: MarkRow[], allAdd: AdditionalRow[]): AnnualAgg {
  const termRows = allMarks.filter((m) => m.examGroup === "term");
  const subjects = Array.from(
    new Set(termRows.filter((r) => !r.isArt).map((r) => r.subject))
  ).sort((a, b) => a.localeCompare(b));

  const byKey = new Map<string, MarkRow>();
  for (const r of termRows) byKey.set(`${r.subject}::${r.term}`, r);
  const pick = (sub: string, term: string) => byKey.get(`${sub}::${term}`);

  let sumU1O = 0, sumU1W = 0, sumU1T = 0;
  let sumU2O = 0, sumU2W = 0, sumU2T = 0;
  let sumFO = 0, sumFW = 0, sumFCt = 0, sumFT = 0;
  let sumGrand = 0;

  const out: AnnualSubject[] = subjects.map((sub) => {
    const u1 = pick(sub, "1st Unit");
    const u2 = pick(sub, "2nd Unit");
    const f = pick(sub, "Final Exam");
    const grand = (u1?.obtained ?? 0) + (u2?.obtained ?? 0) + (f?.obtained ?? 0);
    sumU1O += u1?.oral ?? 0; sumU1W += u1?.written ?? 0; sumU1T += u1?.obtained ?? 0;
    sumU2O += u2?.oral ?? 0; sumU2W += u2?.written ?? 0; sumU2T += u2?.obtained ?? 0;
    sumFO += f?.oral ?? 0; sumFW += f?.written ?? 0; sumFCt += f?.ct ?? 0; sumFT += f?.obtained ?? 0;
    sumGrand += grand;
    return {
      name: sub,
      u1O: fmt(u1?.oral), u1W: fmt(u1?.written), u1Tot: fmt(u1?.obtained),
      u2O: fmt(u2?.oral), u2W: fmt(u2?.written), u2Tot: fmt(u2?.obtained),
      fO: fmt(f?.oral), fW: fmt(f?.written), fCt: fmt(f?.ct), fTot: fmt(f?.obtained),
      grand: fmt(grand || null),
      grade: gradeFromPercent(pct(grand, 200)),
    };
  });

  const artU1 = pick("Art", "1st Unit");
  const artU2 = pick("Art", "2nd Unit");
  const artF = pick("Art", "Final Exam");
  const artGrand = (artU1?.obtained ?? 0) + (artU2?.obtained ?? 0) + (artF?.obtained ?? 0);
  const artMax = (artU1?.total ?? 0) + (artU2?.total ?? 0) + (artF?.total ?? 0);

  const additional: AdditionalView[] = allAdd
    .filter((a) => a.term === "Annual")
    .map((a) => ({ subject: a.subject, fullMarks: a.fullMarks, obtained: a.obtained }));
  const additionalFmTotal = additional.reduce((s, a) => s + a.fullMarks, 0);
  const additionalObtTotal = additional.reduce((s, a) => s + (a.obtained ?? 0), 0);

  const totalObtained = sumGrand + artGrand + additionalObtTotal;
  const maxMarks = subjects.length * 200 + artMax + additionalFmTotal;
  const percent = pct(totalObtained, maxMarks);

  return {
    subjects: out,
    art: {
      u1: fmt(artU1?.obtained), u2: fmt(artU2?.obtained), f: fmt(artF?.obtained),
      grand: fmt(artGrand || null),
      grade: gradeFromPercent(pct(artGrand, artMax)),
    },
    sums: {
      u1O: fmt(sumU1O || null), u1W: fmt(sumU1W || null), u1Tot: fmt(sumU1T || null),
      u2O: fmt(sumU2O || null), u2W: fmt(sumU2W || null), u2Tot: fmt(sumU2T || null),
      fO: fmt(sumFO || null), fW: fmt(sumFW || null), fCt: fmt(sumFCt || null), fTot: fmt(sumFT || null),
      grand: fmt(sumGrand || null),
      grade: gradeFromPercent(pct(sumGrand, subjects.length * 200)),
    },
    additional,
    additionalFmTotal,
    additionalObtTotal,
    maxMarks,
    totalObtained,
    percent,
    overallGrade: gradeFromPercent(percent),
    passed: percent >= 35,
    hasData: termRows.length > 0,
  };
}

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */

export async function listStudents(): Promise<StudentRow[]> {
  return db.select().from(students).orderBy(students.className, students.rollNumber);
}

export async function buildMarksheet(studentId: number): Promise<MarksheetPayload | null> {
  const [student] = await db.select().from(students).where(eq(students.id, studentId)).limit(1);
  if (!student) return null;

  const [allMarks, allAdd] = await Promise.all([
    db.select().from(marks).where(eq(marks.studentId, studentId)),
    db.select().from(additionalMarks).where(eq(additionalMarks.studentId, studentId)),
  ]);

  const terms = buildTerms(allMarks, allAdd);
  const monthly = buildMonthly(allMarks);
  const agg = aggregateAnnual(allMarks, allAdd);

  let rank = "-";
  if (agg.hasData) {
    const peers = await db
      .select({ id: students.id })
      .from(students)
      .where(
        and(eq(students.className, student.className), eq(students.section, student.section))
      );
    const totals: { id: number; total: number }[] = [];
    for (const p of peers) {
      const pm = await db.select().from(marks).where(eq(marks.studentId, p.id));
      const pa = await db.select().from(additionalMarks).where(eq(additionalMarks.studentId, p.id));
      const pAgg = aggregateAnnual(pm, pa);
      if (pAgg.hasData) totals.push({ id: p.id, total: pAgg.totalObtained });
    }
    totals.sort((a, b) => b.total - a.total);
    const idx = totals.findIndex((t) => t.id === studentId);
    if (idx >= 0) rank = `${idx + 1} / ${totals.length}`;
  }

  const annual: AnnualView | null = agg.hasData ? { ...agg, rank } : null;

  const defaultTab: MarksheetPayload["defaultTab"] =
    terms.some((t) => t.hasData) ? "term" : monthly.hasData ? "monthly" : "annual";

  return {
    student: {
      id: student.id,
      name: student.name,
      className: student.className,
      roll: student.rollNumber,
      section: student.section,
      guardian: student.guardianName,
    },
    terms,
    monthly,
    annual,
    defaultTab,
  };
}
