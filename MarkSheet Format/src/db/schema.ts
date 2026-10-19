import {
  pgTable,
  serial,
  varchar,
  integer,
  boolean,
  index,
} from "drizzle-orm/pg-core";

export const students = pgTable(
  "students",
  {
    id: serial("id").primaryKey(),
    name: varchar("name", { length: 120 }).notNull(),
    guardianName: varchar("guardian_name", { length: 120 }),
    className: varchar("class_name", { length: 40 }).notNull(),
    rollNumber: varchar("roll_number", { length: 20 }).notNull(),
    section: varchar("section", { length: 10 }).notNull().default("A"),
  },
  (t) => [index("students_class_idx").on(t.className, t.section)]
);

/**
 * One row per subject per exam.
 * examGroup: 'term' (1st Unit / 2nd Unit / Final Exam) or 'monthly' (monthly class tests)
 * Component columns (oral/written/ct) are null when not applicable to the exam kind.
 */
export const marks = pgTable(
  "marks",
  {
    id: serial("id").primaryKey(),
    studentId: integer("student_id")
      .notNull()
      .references(() => students.id, { onDelete: "cascade" }),
    examGroup: varchar("exam_group", { length: 20 }).notNull(),
    term: varchar("term", { length: 40 }).notNull(),
    subject: varchar("subject", { length: 60 }).notNull(),
    isArt: boolean("is_art").notNull().default(false),
    oral: integer("oral"),
    oralLimit: integer("oral_limit"),
    written: integer("written"),
    writtenLimit: integer("written_limit"),
    ct: integer("ct"),
    ctLimit: integer("ct_limit"),
    obtained: integer("obtained").notNull(),
    total: integer("total").notNull(),
  },
  (t) => [
    index("marks_student_idx").on(t.studentId, t.examGroup, t.term),
  ]
);

/** Co-curricular / additional subjects (Physical Education, Behaviour, ...). */
export const additionalMarks = pgTable(
  "additional_marks",
  {
    id: serial("id").primaryKey(),
    studentId: integer("student_id")
      .notNull()
      .references(() => students.id, { onDelete: "cascade" }),
    term: varchar("term", { length: 40 }).notNull(),
    subject: varchar("subject", { length: 60 }).notNull(),
    fullMarks: integer("full_marks").notNull(),
    obtained: integer("obtained").notNull(),
  },
  (t) => [index("add_marks_student_idx").on(t.studentId, t.term)]
);

export type StudentRow = typeof students.$inferSelect;
export type MarkRow = typeof marks.$inferSelect;
export type AdditionalRow = typeof additionalMarks.$inferSelect;
