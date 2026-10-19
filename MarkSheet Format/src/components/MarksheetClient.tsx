"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Award,
  Calendar,
  FileSpreadsheet,
  Printer,
} from "lucide-react";
import type { MarksheetPayload, TermView } from "@/lib/marksheet-types";
import {
  AbbrNote,
  AdditionalTable,
  AnnualSheet,
  InfoRow,
  MarksRangeTable,
  MonthlySheet,
  RemarksBox,
  ResultAbstract,
  SheetHeader,
  SignatureRow,
  StampBox,
  TermSheet,
} from "@/components/sheet";

type Tab = "term" | "monthly" | "annual";

function TermFooter({ term }: { term: TermView }) {
  return (
    <div className="footer-wrapper">
      <div className="footer-col">
        <AdditionalTable rows={term.additional} />
        <ResultAbstract
          maxMarks={term.totalPossible}
          obtained={term.totalObtained}
          percent={term.percent}
          grade={term.grade}
          passed={term.passed}
        />
        <RemarksBox grade={term.grade} passed={term.passed} />
      </div>
      <div className="footer-col">
        <MarksRangeTable />
        <StampBox passed={term.passed} />
      </div>
    </div>
  );
}

function PageFrame({
  title,
  payload,
  children,
  footer,
}: {
  title: string;
  payload: MarksheetPayload;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="annual-page">
      <div className="watermark" />
      <div className="border-container">
        <div>
          <SheetHeader title={title} />
          <InfoRow
            name={payload.student.name}
            className={payload.student.className}
            roll={payload.student.roll}
            section={payload.student.section}
          />
          {children}
        </div>
        <div>
          {footer}
          <div style={{ marginTop: "3mm" }}>
            <AbbrNote />
          </div>
          <SignatureRow />
        </div>
      </div>
    </div>
  );
}

function EmptyFrame({
  title,
  payload,
  message,
}: {
  title: string;
  payload: MarksheetPayload;
  message: string;
}) {
  return (
    <div className="annual-page">
      <div className="watermark" />
      <div className="border-container">
        <div>
          <SheetHeader title={title} />
          <InfoRow
            name={payload.student.name}
            className={payload.student.className}
            roll={payload.student.roll}
            section={payload.student.section}
          />
          <div className="sheet-empty">{message}</div>
        </div>
        <SignatureRow />
      </div>
    </div>
  );
}

export default function MarksheetClient({ payload }: { payload: MarksheetPayload }) {
  const [tab, setTab] = useState<Tab>(payload.defaultTab);
  const firstTerm = payload.terms.find((t) => t.hasData)?.term ?? payload.terms[0]?.term ?? "";
  const [termName, setTermName] = useState(firstTerm);

  const activeTerm = useMemo(
    () => payload.terms.find((t) => t.term === termName) ?? payload.terms[0],
    [payload.terms, termName]
  );

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "term", label: "Term Exams", icon: <Award size={15} /> },
    { id: "monthly", label: "Monthly Tests", icon: <Calendar size={15} /> },
    { id: "annual", label: "Annual Progress Report", icon: <FileSpreadsheet size={15} /> },
  ];

  return (
    <div>
      {/* Toolbar card */}
      <div className="toolbar print-hide mx-auto w-full max-w-[210mm] px-1 pb-5">
        <div className="overflow-hidden rounded-xl border border-[#e2ddcf] bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <Link
                href="/admin/marksheet"
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-[#d8d4c6] bg-white px-3 py-2 text-[12.5px] font-semibold text-[#145058] shadow-sm transition hover:bg-[#eef6f6]"
              >
                <ArrowLeft size={14} /> Student list
              </Link>
              <div className="hidden h-7 w-px bg-[#e5e0d2] sm:block" />
              <div className="min-w-0 leading-tight">
                <div className="truncate text-[13.5px] font-bold text-[#22302f]">
                  {payload.student.name}
                </div>
                <div className="text-[11px] font-medium text-[#8a938f]">
                  Class {payload.student.className} &middot; Roll {payload.student.roll} &middot;
                  Sec {payload.student.section}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2.5">
              {tab === "term" && payload.terms.length > 0 && (
                <label className="flex items-center gap-2 text-[12.5px] font-semibold text-[#4a5450]">
                  Exam
                  <select
                    value={termName}
                    onChange={(e) => setTermName(e.target.value)}
                    className="rounded-lg border border-[#d8d4c6] bg-white px-2.5 py-2 text-[12.5px] font-medium shadow-sm outline-none focus:border-[var(--primary-color)]"
                  >
                    {payload.terms.map((t) => (
                      <option key={t.term} value={t.term}>
                        {t.term}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <button
                onClick={() => window.print()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--primary-color)] px-4 py-2 text-[12.5px] font-semibold text-white shadow-sm transition hover:bg-[var(--primary-dark)]"
              >
                <Printer size={14} /> Print
              </button>
            </div>
          </div>

          <div className="flex gap-1 border-t border-[#f0ece1] bg-[#fbfaf6] px-3">
            {tabs.map((t) => {
              const active = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`-mb-px inline-flex items-center gap-2 border-b-[3px] px-4 py-2.5 text-[13px] font-semibold transition ${
                    active
                      ? "border-[var(--primary-color)] bg-white text-[var(--primary-color)]"
                      : "border-transparent text-[#7f8c8d] hover:text-[var(--primary-color)]"
                  }`}
                >
                  {t.icon}
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="sheet-scroll">
        {/* ---------------- TERM ---------------- */}
        <div
          className={`tab-pane ${tab === "term" ? "print-active" : ""}`}
          style={{ display: tab === "term" ? "block" : "none" }}
        >
          {activeTerm && activeTerm.hasData ? (
            <PageFrame
              title={`${activeTerm.term.toUpperCase()} - 2025`}
              payload={payload}
              footer={<TermFooter term={activeTerm} />}
            >
              <TermSheet term={activeTerm} />
            </PageFrame>
          ) : (
            <EmptyFrame
              title="TERM RESULT - 2025"
              payload={payload}
              message="No Term Exam marks recorded for this student."
            />
          )}
        </div>

        {/* ---------------- MONTHLY ---------------- */}
        <div
          className={`tab-pane ${tab === "monthly" ? "print-active" : ""}`}
          style={{ display: tab === "monthly" ? "block" : "none" }}
        >
          {payload.monthly.hasData ? (
            <PageFrame
              title="MONTHLY CLASS TESTS - 2025"
              payload={payload}
              footer={
                <div className="footer-wrapper">
                  <div className="footer-col">
                    <ResultAbstract
                      maxMarks={payload.monthly.grandPos}
                      obtained={payload.monthly.grandObt}
                      percent={payload.monthly.percent}
                      grade={payload.monthly.grade}
                      passed={payload.monthly.passed}
                    />
                    <RemarksBox grade={payload.monthly.grade} passed={payload.monthly.passed} />
                  </div>
                  <div className="footer-col">
                    <MarksRangeTable />
                    <StampBox passed={payload.monthly.passed} />
                  </div>
                </div>
              }
            >
              <MonthlySheet monthly={payload.monthly} />
            </PageFrame>
          ) : (
            <EmptyFrame
              title="MONTHLY CLASS TESTS - 2025"
              payload={payload}
              message="No Monthly Class Test marks recorded for this student."
            />
          )}
        </div>

        {/* ---------------- ANNUAL ---------------- */}
        <div
          className={`tab-pane ${tab === "annual" ? "print-active" : ""}`}
          style={{ display: tab === "annual" ? "block" : "none" }}
        >
          {payload.annual ? (
            <PageFrame
              title="ANNUAL RESULT - 2025"
              payload={payload}
              footer={
                <div className="footer-wrapper">
                  <div className="footer-col">
                    <AdditionalTable
                      rows={payload.annual.additional}
                      fmTotal={payload.annual.additionalFmTotal}
                      obtTotal={payload.annual.additionalObtTotal}
                    />
                    <ResultAbstract
                      maxMarks={payload.annual.maxMarks}
                      obtained={payload.annual.totalObtained}
                      percent={payload.annual.percent}
                      grade={payload.annual.overallGrade}
                      rank={payload.annual.rank}
                      passed={payload.annual.passed}
                    />
                    <RemarksBox
                      grade={payload.annual.overallGrade}
                      passed={payload.annual.passed}
                    />
                  </div>
                  <div className="footer-col">
                    <MarksRangeTable />
                    <StampBox passed={payload.annual.passed} />
                  </div>
                </div>
              }
            >
              <AnnualSheet annual={payload.annual} />
            </PageFrame>
          ) : (
            <EmptyFrame
              title="ANNUAL RESULT - 2025"
              payload={payload}
              message="No academic marks recorded to compute Annual Progress Report."
            />
          )}
        </div>
      </div>
    </div>
  );
}
