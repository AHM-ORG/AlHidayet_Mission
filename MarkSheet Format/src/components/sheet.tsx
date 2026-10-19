import type {
  TermView,
  MonthlyView,
  AnnualView,
  AdditionalView,
} from "@/lib/marksheet-types";
import { MARKS_RANGE, fmt, remarksForGrade } from "@/lib/marksheet-types";

/* ------------------------------------------------------------------ */

export function SheetHeader({ title }: { title: string }) {
  return (
    <div className="sheet-header">
      <img src="/images/ahm-logo.png" alt="AHM crest" className="sheet-logo left" />
      <img src="/images/ahm-logo.png" alt="AHM crest" className="sheet-logo right" />
      <h1 className="ahm-h1">BHOGRAM AL-HIDAYET MISSION</h1>
      <div className="sheet-addr">
        BHOGRAM, P.O &ndash; BHOGRAM, P.S &ndash; HEMTABAD, U / DINAJPUR, 733134
      </div>
      <div className="sheet-title">{title}</div>
    </div>
  );
}

export function InfoRow({
  name,
  className,
  roll,
  section,
}: {
  name: string;
  className: string;
  roll: string;
  section: string;
}) {
  return (
    <table className="info-tbl">
      <colgroup>
        <col style={{ width: "11%" }} />
        <col style={{ width: "39%" }} />
        <col style={{ width: "10%" }} />
        <col style={{ width: "10%" }} />
        <col style={{ width: "9%" }} />
        <col style={{ width: "11%" }} />
        <col style={{ width: "8%" }} />
        <col style={{ width: "2%" }} />
      </colgroup>
      <tbody>
        <tr>
          <td className="lbl">NAME</td>
          <td>
            <span className="val green">{name || "N/A"}</span>
          </td>
          <td className="lbl">CLASS</td>
          <td>
            <span className="val">{className || "N/A"}</span>
          </td>
          <td className="lbl">ROLL</td>
          <td>
            <span className="val">{roll || "N/A"}</span>
          </td>
          <td className="lbl">SEC</td>
          <td>
            <span className="val">{section || "A"}</span>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

export function MarksRangeTable() {
  return (
    <table className="sub-table">
      <colgroup>
        <col style={{ width: "55%" }} />
        <col style={{ width: "45%" }} />
      </colgroup>
      <thead>
        <tr>
          <th colSpan={2} className="sub-header">MARKS RANGE</th>
        </tr>
        <tr className="zebra">
          <th>RANGE</th>
          <th>GRADE</th>
        </tr>
      </thead>
      <tbody>
        {MARKS_RANGE.map((r) => (
          <tr key={r.grade}>
            <td>{r.range}</td>
            <td>{r.grade}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AdditionalTable({
  rows,
  fmTotal,
  obtTotal,
}: {
  rows: AdditionalView[];
  fmTotal?: number;
  obtTotal?: number;
}) {
  if (rows.length === 0) return null;
  const fm = fmTotal ?? rows.reduce((s, r) => s + r.fullMarks, 0);
  const obt = obtTotal ?? rows.reduce((s, r) => s + (r.obtained ?? 0), 0);
  return (
    <table className="sub-table">
      <colgroup>
        <col style={{ width: "55%" }} />
        <col style={{ width: "22.5%" }} />
        <col style={{ width: "22.5%" }} />
      </colgroup>
      <thead>
        <tr>
          <th colSpan={3} className="sub-header">ADDITIONAL SUBJECTS</th>
        </tr>
        <tr className="zebra">
          <th style={{ textAlign: "left", paddingLeft: 4 }}>SUBJECT</th>
          <th>F.M</th>
          <th>OBT</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.subject}>
            <td className="lbl-cell" style={{ fontWeight: 400, textTransform: "uppercase" }}>
              {r.subject}
            </td>
            <td>{fmt(r.fullMarks)}</td>
            <td>{fmt(r.obtained)}</td>
          </tr>
        ))}
        {fmTotal !== undefined && (
          <tr className="bg-total" style={{ background: "#fff9db" }}>
            <td className="lbl-cell">TOTAL</td>
            <td>{fmt(fm)}</td>
            <td>{fmt(obt)}</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

export function ResultAbstract({
  maxMarks,
  obtained,
  percent,
  grade,
  rank,
  passed,
}: {
  maxMarks: number;
  obtained: number;
  percent: number;
  grade: string;
  rank?: string;
  passed: boolean;
}) {
  return (
    <table className="sub-table">
      <colgroup>
        <col style={{ width: "62%" }} />
        <col style={{ width: "38%" }} />
      </colgroup>
      <thead>
        <tr>
          <th colSpan={2} className="sub-header">RESULT ABSTRACT</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td className="lbl-cell">GRAND TOTAL ({fmt(maxMarks)})</td>
          <td style={{ fontWeight: 700 }}>{fmt(obtained)}</td>
        </tr>
        <tr>
          <td className="lbl-cell">PERCENTAGE</td>
          <td style={{ fontWeight: 700 }}>{percent}%</td>
        </tr>
        {rank !== undefined && (
          <tr>
            <td className="lbl-cell">CLASS RANK</td>
            <td style={{ fontWeight: 700 }}>{rank}</td>
          </tr>
        )}
        <tr className="tint">
          <td className="lbl-cell">OVERALL GRADE</td>
          <td style={{ color: passed ? "#2e7d32" : "#c62828", fontSize: "10pt", fontWeight: 900 }}>
            {grade}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

export function RemarksBox({ grade, passed }: { grade: string; passed: boolean }) {
  return (
    <table className="sub-table">
      <colgroup>
        <col style={{ width: "26%" }} />
        <col style={{ width: "74%" }} />
      </colgroup>
      <tbody>
        <tr>
          <td className="lbl-cell" style={{ background: "#333", color: "#fff" }}>
            REMARKS
          </td>
          <td style={{ textAlign: "left", paddingLeft: 6, fontStyle: "italic" }}>
            {remarksForGrade(grade, passed)}
          </td>
        </tr>
      </tbody>
    </table>
  );
}

export function AbbrNote() {
  return (
    <div
      style={{
        fontSize: "7pt",
        color: "#555",
        textAlign: "center",
        letterSpacing: 0.3,
        fontFamily: "'Outfit', sans-serif",
      }}
    >
      OR = Oral &nbsp;&middot;&nbsp; WR = Written &nbsp;&middot;&nbsp; CT = Class Test
      &nbsp;&middot;&nbsp; TOT = Total &nbsp;&middot;&nbsp; F.M = Full Marks
      &nbsp;&middot;&nbsp; OBT = Obtained &nbsp;&middot;&nbsp; GR = Grade
    </div>
  );
}

export function StampBox({ passed }: { passed: boolean }) {
  return (
    <div className="stamp-container">
      <img src="/images/ahm-seal.png" alt="School seal" />
      <div className={`status-stamp ${passed ? "passed" : "failed"}`}>
        {passed ? "PASSED" : "FAILED"}
      </div>
    </div>
  );
}

export function SignatureRow() {
  return (
    <div className="sig-wrapper">
      <div className="sig-box">Signature of Guardian</div>
      <div className="sig-box">Signature of Class Teacher</div>
      <div className="sig-box">
        <svg
          viewBox="0 0 120 40"
          style={{
            position: "absolute",
            bottom: 14,
            left: "50%",
            transform: "translateX(-50%)",
            width: 62,
            zIndex: 5,
            pointerEvents: "none",
            opacity: 0.8,
          }}
          fill="none"
          stroke="#1a3a6b"
          strokeWidth="1.6"
          strokeLinecap="round"
        >
          <path d="M6 30 C 18 8, 26 8, 30 24 C 33 34, 40 12, 48 16 C 56 20, 52 30, 62 22 C 72 14, 78 26, 88 18 C 96 12, 104 24, 114 16" />
          <path d="M20 33 C 45 29, 75 31, 102 28" strokeWidth="1" />
        </svg>
        Signature of T.I.C
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* TERM SHEET                                                          */
/* ------------------------------------------------------------------ */

const KIND_COLORS: Record<string, { head: string; sub: string; row: string }> = {
  "1st Unit": { head: "#0056b3", sub: "#cce5ff", row: "bg-unit1" },
  "1st Term": { head: "#0056b3", sub: "#cce5ff", row: "bg-unit1" },
  "2nd Unit": { head: "#1e7e34", sub: "#d4edda", row: "bg-unit2" },
  "2nd Term": { head: "#1e7e34", sub: "#d4edda", row: "bg-unit2" },
  "Final Exam": { head: "#bd2130", sub: "#f8d7da", row: "bg-final" },
  Annual: { head: "#bd2130", sub: "#f8d7da", row: "bg-final" },
};

export function TermSheet({ term }: { term: TermView }) {
  const colors = KIND_COLORS[term.term] ?? { head: "#333", sub: "#eee", row: "bg-grade" };
  const cols = term.kind === "unit" ? 3 : term.kind === "final" ? 4 : 2;
  return (
    <table className="annual-tbl">
      <thead>
        <tr>
          <th
            rowSpan={2}
            className="th-main"
            style={{ width: "34%", verticalAlign: "middle" }}
          >
            SUBJECT
          </th>
          <th
            colSpan={cols}
            style={{ background: colors.head, color: "#fff", verticalAlign: "middle" }}
          >
            {term.term.toUpperCase()}
          </th>
          <th rowSpan={2} className="th-main" style={{ width: "12%", verticalAlign: "middle" }}>
            GR
          </th>
        </tr>
        <tr>
          {term.kind === "unit" && (
            <>
              <th style={{ background: colors.sub }}>OR</th>
              <th style={{ background: colors.sub }}>WR</th>
              <th style={{ background: colors.sub }} className="sub-tot">TOT</th>
            </>
          )}
          {term.kind === "final" && (
            <>
              <th style={{ background: colors.sub }}>OR</th>
              <th style={{ background: colors.sub }}>WR</th>
              <th style={{ background: colors.sub }}>CT</th>
              <th style={{ background: colors.sub }} className="sub-tot">TOT</th>
            </>
          )}
          {term.kind === "plain" && (
            <>
              <th style={{ background: colors.sub }}>F.M</th>
              <th style={{ background: colors.sub }} className="sub-tot">OBT</th>
            </>
          )}
        </tr>
      </thead>
      <tbody>
        {term.subjects.map((s) => (
          <tr key={s.subject}>
            <td className="subj">{s.subject}</td>
            {term.kind === "unit" && (
              <>
                <td className={colors.row}>{fmt(s.oral, s.oralLimit)}</td>
                <td className={colors.row}>{fmt(s.written, s.writtenLimit)}</td>
                <td className={`${colors.row} sub-tot`}>{fmt(s.obtained, s.total)}</td>
              </>
            )}
            {term.kind === "final" && (
              <>
                <td className={colors.row}>{fmt(s.oral, s.oralLimit)}</td>
                <td className={colors.row}>{fmt(s.written, s.writtenLimit)}</td>
                <td className={colors.row}>{fmt(s.ct, s.ctLimit)}</td>
                <td className={`${colors.row} sub-tot`}>{fmt(s.obtained, s.total)}</td>
              </>
            )}
            {term.kind === "plain" && (
              <>
                <td className={colors.row}>{fmt(s.total)}</td>
                <td className={`${colors.row} sub-tot`}>{fmt(s.obtained, s.total)}</td>
              </>
            )}
            <td className="bg-grade">{s.grade}</td>
          </tr>
        ))}
        {term.art && (
          <tr style={{ background: "#fafafa" }}>
            <td className="subj">{term.art.subject}</td>
            <td colSpan={cols} className={`${colors.row} sub-tot`}>
              {fmt(term.art.obtained, term.art.total)}
            </td>
            <td className="bg-grade">{term.art.grade}</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

/* ------------------------------------------------------------------ */
/* MONTHLY SHEET                                                       */
/* ------------------------------------------------------------------ */

export function MonthlySheet({ monthly }: { monthly: MonthlyView }) {
  return (
    <table className="annual-tbl">
      <thead>
        <tr>
          <th rowSpan={3} className="th-main" style={{ width: "18%", verticalAlign: "middle" }}>
            SUBJECT
          </th>
          <th
            colSpan={monthly.terms.length}
            className="th-main"
            style={{ verticalAlign: "middle" }}
          >
            MONTHLY CLASS TESTS
          </th>
          <th
            colSpan={2}
            style={{ background: "#d39e00", color: "#fff", verticalAlign: "middle" }}
          >
            TOTAL
          </th>
          <th rowSpan={3} className="th-main" style={{ width: "7%", verticalAlign: "middle" }}>
            GR
          </th>
        </tr>
        <tr>
          {monthly.terms.map((t) => (
            <th key={t} className="th-neutral">
              {monthly.short[t] ?? t}
            </th>
          ))}
          <th rowSpan={2} className="th-total">OBT</th>
          <th rowSpan={2} className="th-total">F.M</th>
        </tr>
        <tr>
          {monthly.terms.map((t) => (
            <th key={t} className="th-neutral" style={{ fontSize: "7pt" }}>
              {monthly.columnFull[t]}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {monthly.rows.map((r) => (
          <tr key={r.name}>
            <td className="subj">{r.name}</td>
            {monthly.terms.map((t) => (
              <td key={t} className="bg-monthly">
                {r.cells[t]?.obtained ?? "-"}
              </td>
            ))}
            <td className="bg-total">{r.totalObt}</td>
            <td className="bg-total">{r.totalPos}</td>
            <td className="bg-grade">{r.grade}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ------------------------------------------------------------------ */
/* ANNUAL SHEET                                                        */
/* ------------------------------------------------------------------ */

export function AnnualSheet({ annual }: { annual: AnnualView }) {
  const s = annual.sums;
  return (
    <table className="annual-tbl">
      <thead>
        <tr>
          <th rowSpan={3} className="th-main" style={{ width: "20%", verticalAlign: "middle" }}>
            SUBJECT
          </th>
          <th colSpan={3} style={{ background: "#0056b3", color: "#fff" }}>1ST UNIT</th>
          <th colSpan={3} style={{ background: "#1e7e34", color: "#fff" }}>2ND UNIT</th>
          <th colSpan={4} style={{ background: "#bd2130", color: "#fff" }}>FINAL EXAM</th>
          <th rowSpan={3} style={{ background: "#d39e00", color: "#fff" }}>
            TOTAL
            <br />(200)
          </th>
          <th rowSpan={3} className="th-main">GR</th>
        </tr>
        <tr>
          <th className="th-u1">OR</th><th className="th-u1">WR</th><th className="th-u1 sub-tot">TOT</th>
          <th className="th-u2">OR</th><th className="th-u2">WR</th><th className="th-u2 sub-tot">TOT</th>
          <th className="th-final">OR</th><th className="th-final">WR</th><th className="th-final">CT</th>
          <th className="th-final sub-tot">TOT</th>
        </tr>
        <tr>
          <th className="th-u1" style={{ fontSize: "7pt" }}>10</th>
          <th className="th-u1" style={{ fontSize: "7pt" }}>40</th>
          <th className="th-u1 sub-tot" style={{ fontSize: "7pt" }}>50</th>
          <th className="th-u2" style={{ fontSize: "7pt" }}>10</th>
          <th className="th-u2" style={{ fontSize: "7pt" }}>40</th>
          <th className="th-u2 sub-tot" style={{ fontSize: "7pt" }}>50</th>
          <th className="th-final" style={{ fontSize: "7pt" }}>20</th>
          <th className="th-final" style={{ fontSize: "7pt" }}>70</th>
          <th className="th-final" style={{ fontSize: "7pt" }}>10</th>
          <th className="th-final sub-tot" style={{ fontSize: "7pt" }}>100</th>
        </tr>
      </thead>
      <tbody>
        {annual.subjects.map((sub) => (
          <tr key={sub.name}>
            <td className="subj" style={{ paddingLeft: 5 }}>{sub.name}</td>
            <td className="bg-unit1">{sub.u1O}</td>
            <td className="bg-unit1">{sub.u1W}</td>
            <td className="bg-unit1 sub-tot">{sub.u1Tot}</td>
            <td className="bg-unit2">{sub.u2O}</td>
            <td className="bg-unit2">{sub.u2W}</td>
            <td className="bg-unit2 sub-tot">{sub.u2Tot}</td>
            <td className="bg-final">{sub.fO}</td>
            <td className="bg-final">{sub.fW}</td>
            <td className="bg-final">{sub.fCt}</td>
            <td className="bg-final sub-tot">{sub.fTot}</td>
            <td className="bg-total">{sub.grand}</td>
            <td className="bg-grade">{sub.grade}</td>
          </tr>
        ))}
        <tr style={{ borderTop: "2px solid #000" }}>
          <td className="subj" style={{ paddingLeft: 5 }}>ART</td>
          <td colSpan={3} className="bg-unit1">{annual.art.u1}</td>
          <td colSpan={3} className="bg-unit2">{annual.art.u2}</td>
          <td colSpan={4} className="bg-final">{annual.art.f}</td>
          <td className="bg-total">{annual.art.grand}</td>
          <td className="bg-grade">{annual.art.grade}</td>
        </tr>
        <tr style={{ borderTop: "2px solid #000", fontWeight: 700 }}>
          <td className="subj" style={{ paddingLeft: 5 }}>TOTAL</td>
          <td className="bg-unit1">{s.u1O}</td>
          <td className="bg-unit1">{s.u1W}</td>
          <td className="bg-unit1 sub-tot">{s.u1Tot}</td>
          <td className="bg-unit2">{s.u2O}</td>
          <td className="bg-unit2">{s.u2W}</td>
          <td className="bg-unit2 sub-tot">{s.u2Tot}</td>
          <td className="bg-final">{s.fO}</td>
          <td className="bg-final">{s.fW}</td>
          <td className="bg-final">{s.fCt}</td>
          <td className="bg-final sub-tot">{s.fTot}</td>
          <td className="bg-total">{s.grand}</td>
          <td className="bg-grade">{s.grade}</td>
        </tr>
      </tbody>
    </table>
  );
}
