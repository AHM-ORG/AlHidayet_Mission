/* Client-safe view models and pure helpers (no DB imports). */

export function gradeFromPercent(pct: number): string {
  if (pct >= 90) return "AA";
  if (pct >= 80) return "A+";
  if (pct >= 60) return "A";
  if (pct >= 45) return "B+";
  if (pct >= 35) return "B";
  if (pct >= 25) return "C";
  return "D";
}

/** The printed MARKS RANGE reference table (per-subject, out of 200). */
export const MARKS_RANGE: { range: string; grade: string }[] = [
  { range: "180 - 200", grade: "AA" },
  { range: "160 - 179", grade: "A+" },
  { range: "120 - 159", grade: "A" },
  { range: "90 - 119", grade: "B+" },
  { range: "70 - 89", grade: "B" },
  { range: "50 - 69", grade: "C" },
  { range: "BELOW 50", grade: "D" },
];

export function fmt(val: number | null | undefined, limit?: number | null): string {
  if (val === null || val === undefined) return "-";
  const s = Number.isInteger(val) ? String(val) : String(Math.round(val * 10) / 10);
  return limit !== null && limit !== undefined ? `${s}/${limit}` : s;
}

export function remarksForGrade(grade: string, passed: boolean): string {
  if (!passed) return "Has not met the minimum requirement. Remedial support recommended.";
  switch (grade) {
    case "AA": return "Outstanding performance. A credit to the class!";
    case "A+": return "Excellent result. Keep up the great work.";
    case "A": return "Very good performance with consistent effort.";
    case "B+": return "Good result. Aim higher with regular revision.";
    case "B": return "Fairly good. More attention to weak subjects advised.";
    case "C": return "Average. Needs steadier study habits.";
    default: return "Just passed. Significant improvement required.";
  }
}

export type TermKind = "unit" | "final" | "plain";
export function termKind(term: string): TermKind {
  if (["1st Unit", "2nd Unit", "1st Term", "2nd Term"].includes(term)) return "unit";
  if (["Final Exam", "Annual Exam", "Annual"].includes(term)) return "final";
  return "plain";
}

export interface SubjectMarkView {
  subject: string;
  isArt: boolean;
  oral: number | null;
  oralLimit: number | null;
  written: number | null;
  writtenLimit: number | null;
  ct: number | null;
  ctLimit: number | null;
  obtained: number | null;
  total: number | null;
  grade: string;
}

export interface AdditionalView {
  subject: string;
  fullMarks: number;
  obtained: number | null;
}

export interface TermView {
  term: string;
  kind: TermKind;
  subjects: SubjectMarkView[];
  art: SubjectMarkView | null;
  additional: AdditionalView[];
  totalObtained: number;
  totalPossible: number;
  percent: number;
  grade: string;
  passed: boolean;
  hasData: boolean;
}

export interface MonthlyCell {
  obtained: string;
  full: string;
}
export interface MonthlyRow {
  name: string;
  cells: Record<string, MonthlyCell>;
  totalObt: string;
  totalPos: string;
  grade: string;
}
export interface MonthlyView {
  terms: string[];
  short: Record<string, string>;
  columnFull: Record<string, string>;
  rows: MonthlyRow[];
  grandObt: number;
  grandPos: number;
  percent: number;
  grade: string;
  passed: boolean;
  hasData: boolean;
}

export interface AnnualSubject {
  name: string;
  u1O: string; u1W: string; u1Tot: string;
  u2O: string; u2W: string; u2Tot: string;
  fO: string; fW: string; fCt: string; fTot: string;
  grand: string;
  grade: string;
}
export interface AnnualView {
  subjects: AnnualSubject[];
  art: { u1: string; u2: string; f: string; grand: string; grade: string };
  sums: {
    u1O: string; u1W: string; u1Tot: string;
    u2O: string; u2W: string; u2Tot: string;
    fO: string; fW: string; fCt: string; fTot: string;
    grand: string; grade: string;
  };
  additional: AdditionalView[];
  additionalFmTotal: number;
  additionalObtTotal: number;
  maxMarks: number;
  totalObtained: number;
  percent: number;
  overallGrade: string;
  passed: boolean;
  rank: string;
  hasData: boolean;
}

export interface MarksheetPayload {
  student: {
    id: number;
    name: string;
    className: string;
    roll: string;
    section: string;
    guardian: string | null;
  };
  terms: TermView[];
  monthly: MonthlyView;
  annual: AnnualView | null;
  defaultTab: "term" | "monthly" | "annual";
}
