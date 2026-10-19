"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { FileSpreadsheet, Search, Users } from "lucide-react";

export interface PickerStudent {
  id: number;
  name: string;
  guardian: string | null;
  className: string;
  roll: string;
  section: string;
}

const CLASS_ORDER = [
  "Nursery", "U/N", "One", "Two", "Three", "Four", "Five",
  "Six", "Seven", "Eight", "Nine", "Ten",
];

function rollNum(roll: string): number {
  const m = roll.match(/\d+/);
  return m ? parseInt(m[0], 10) : 999999;
}

export default function StudentPickerClient({ students }: { students: PickerStudent[] }) {
  const [activeClass, setActiveClass] = useState("all");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"roll" | "name">("roll");

  const presentClasses = useMemo(() => {
    const set = new Set(students.map((s) => s.className));
    return CLASS_ORDER.filter((c) => set.has(c));
  }, [students]);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = students.filter((s) => {
      const classOk = activeClass === "all" || s.className === activeClass;
      const textOk =
        q === "" ||
        s.name.toLowerCase().includes(q) ||
        s.roll.toLowerCase().includes(q) ||
        String(s.id).includes(q);
      return classOk && textOk;
    });
    filtered.sort((a, b) =>
      sortBy === "name"
        ? a.name.localeCompare(b.name)
        : rollNum(a.roll) - rollNum(b.roll) || a.roll.localeCompare(b.roll)
    );
    return filtered;
  }, [students, activeClass, search, sortBy]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[17px] font-bold text-[#22302f]">Select a Student</h2>
          <p className="text-[12.5px] text-[#7f8c8d]">
            Choose a student to open their Term, Monthly and Annual marksheets.
          </p>
        </div>
        <div className="inline-flex items-center gap-1.5 rounded-full bg-[var(--primary-soft)] px-3 py-1.5 text-[12px] font-semibold text-[var(--primary-dark)]">
          <Users size={13} /> {students.length} students
        </div>
      </div>

      {/* Class filter chips */}
      <div className="mb-4 flex flex-wrap gap-2">
        {["all", ...presentClasses].map((c) => {
          const active = activeClass === c;
          return (
            <button
              key={c}
              onClick={() => setActiveClass(c)}
              className={`rounded-full border-2 px-4 py-1.5 text-[12.5px] font-semibold transition ${
                active
                  ? "border-[var(--primary-color)] bg-[var(--primary-color)] text-white shadow-sm"
                  : "border-[#ddd8ca] bg-white text-[#4a5450] hover:border-[var(--primary-color)] hover:text-[var(--primary-dark)]"
              }`}
            >
              {c === "all" ? "All" : c}
            </button>
          );
        })}
      </div>

      {/* Search + sort */}
      <div className="mb-4 flex flex-wrap gap-2.5">
        <div className="relative min-w-[240px] flex-1">
          <Search
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#9aa5a1]"
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, roll or ID..."
            className="w-full rounded-lg border border-[#d8d4c6] bg-white py-2.5 pl-9 pr-3 text-[13.5px] shadow-sm outline-none transition focus:border-[var(--primary-color)]"
          />
        </div>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as "roll" | "name")}
          className="rounded-lg border border-[#d8d4c6] bg-white px-3 py-2.5 text-[13px] font-medium shadow-sm outline-none focus:border-[var(--primary-color)]"
        >
          <option value="roll">Sort: Roll No</option>
          <option value="name">Sort: Name</option>
        </select>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-[#e2ddcf] bg-white shadow-sm">
        <table className="w-full border-collapse text-[13.5px]">
          <thead>
            <tr className="border-b border-[#eee9dc] bg-[#faf9f4] text-left text-[11.5px] font-bold uppercase tracking-wide text-[#8a938f]">
              <th className="px-4 py-3">SL</th>
              <th className="px-4 py-3">Student Name</th>
              <th className="px-4 py-3">Guardian</th>
              <th className="px-4 py-3">Class</th>
              <th className="px-4 py-3">Roll</th>
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => (
              <tr
                key={s.id}
                className="border-b border-[#f1ede2] transition last:border-0 hover:bg-[#f6faf9]"
              >
                <td className="px-4 py-3 text-[#8a938f]">{i + 1}</td>
                <td className="px-4 py-3 font-semibold text-[#22302f]">{s.name}</td>
                <td className="px-4 py-3 text-[12.5px] text-[#8a938f]">{s.guardian ?? "-"}</td>
                <td className="px-4 py-3">{s.className}</td>
                <td className="px-4 py-3">{s.roll}</td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={`/admin/marksheet?student=${s.id}`}
                    className="inline-flex items-center gap-1.5 rounded-full bg-[#e7f4ec] px-3 py-1.5 text-[12px] font-bold text-[#1e7e34] transition hover:bg-[#d4edda]"
                  >
                    <FileSpreadsheet size={13} /> View Marks
                  </Link>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center">
                  <div className="text-[14px] font-semibold text-[#4a5450]">
                    No students match your filters
                  </div>
                  <p className="mt-1 text-[12.5px] text-[#8a938f]">
                    Try a different class chip or clear the search box.
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
