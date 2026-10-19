import Link from "next/link";
import { ArrowRight, FileSpreadsheet, GraduationCap, Layers } from "lucide-react";
import { db } from "@/db";
import { students, marks } from "@/db/schema";
import { count } from "drizzle-orm";
import { ensureSeeded } from "@/lib/seed";
import AppShell from "@/components/AppShell";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  await ensureSeeded();

  const [{ value: studentCount }] = await db.select({ value: count() }).from(students);
  const [{ value: markCount }] = await db.select({ value: count() }).from(marks);
  const classRows = await db
    .selectDistinct({ className: students.className })
    .from(students);

  const stats = [
    {
      label: "Enrolled Students",
      value: studentCount,
      icon: GraduationCap,
      tint: "bg-[#e7f4ec] text-[#1e7e34]",
    },
    {
      label: "Active Classes",
      value: classRows.length,
      icon: Layers,
      tint: "bg-[#e8f0fb] text-[#0056b3]",
    },
    {
      label: "Mark Records",
      value: markCount,
      icon: FileSpreadsheet,
      tint: "bg-[#fdf3e0] text-[#b26a00]",
    },
  ];

  return (
    <AppShell active="dashboard" title="Dashboard">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-7">
          <h1 className="text-[20px] font-bold text-[#22302f]">
            Bhogram Al-Hidayet Mission
          </h1>
          <p className="text-[13px] text-[#7f8c8d]">
            Examination records &amp; printable marksheets &mdash; Academic Year 2025.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          {stats.map((s) => {
            const Icon = s.icon;
            return (
              <div
                key={s.label}
                className="rounded-xl border border-[#e2ddcf] bg-white p-5 shadow-sm"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-[12px] font-semibold uppercase tracking-wide text-[#8a938f]">
                      {s.label}
                    </div>
                    <div className="mt-1 text-[26px] font-bold text-[#22302f]">
                      {s.value}
                    </div>
                  </div>
                  <div className={`rounded-xl p-3 ${s.tint}`}>
                    <Icon size={20} />
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-6 flex flex-col items-start justify-between gap-4 rounded-xl border border-[#cfe5e7] bg-gradient-to-r from-[#eef6f6] to-[#f7fbf8] p-6 sm:flex-row sm:items-center">
          <div>
            <div className="text-[15px] font-bold text-[#145058]">
              Generate a student marksheet
            </div>
            <p className="mt-1 max-w-xl text-[13px] text-[#5c6b67]">
              Open the marksheet module to browse the student directory, then print
              Term Exam, Monthly Class Test and Annual Progress Report sheets on A4.
            </p>
          </div>
          <Link
            href="/admin/marksheet"
            className="inline-flex shrink-0 items-center gap-2 rounded-lg bg-[var(--primary-color)] px-5 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:bg-[var(--primary-dark)]"
          >
            Open Marksheet <ArrowRight size={15} />
          </Link>
        </div>

        <div className="mt-4 text-[11.5px] text-[#9aa5a1]">
          Data source: school PostgreSQL database &middot; records seeded for demonstration
        </div>
      </div>
    </AppShell>
  );
}
