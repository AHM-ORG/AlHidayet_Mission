import { db } from "@/db";
import { students } from "@/db/schema";
import { count } from "drizzle-orm";
import { ensureSeeded } from "@/lib/seed";
import { buildMarksheet, listStudents } from "@/lib/marksheet";
import AppShell from "@/components/AppShell";
import MarksheetClient from "@/components/MarksheetClient";
import StudentPickerClient from "@/components/StudentPickerClient";

export const dynamic = "force-dynamic";

export default async function MarksheetPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  await ensureSeeded();
  const params = await searchParams;
  const raw = params.student;
  const studentId = typeof raw === "string" ? parseInt(raw, 10) : NaN;

  if (!Number.isNaN(studentId)) {
    const payload = await buildMarksheet(studentId);
    if (payload) {
      return (
        <AppShell active="marksheet" title="Student Marksheet">
          <MarksheetClient payload={payload} />
        </AppShell>
      );
    }
  }

  const list = await listStudents();
  const [{ value: total }] = await db.select({ value: count() }).from(students);
  void total;

  return (
    <AppShell active="marksheet" title="Student Marksheet">
      <StudentPickerClient
        students={list.map((s) => ({
          id: s.id,
          name: s.name,
          guardian: s.guardianName,
          className: s.className,
          roll: s.rollNumber,
          section: s.section,
        }))}
      />
    </AppShell>
  );
}
