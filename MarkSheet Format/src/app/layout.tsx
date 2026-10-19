import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@fontsource/outfit/400.css";
import "@fontsource/outfit/500.css";
import "@fontsource/outfit/600.css";
import "@fontsource/outfit/700.css";
import "@fontsource/outfit/800.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Marksheet - Al Hidayet Mission",
  description:
    "Printable Term, Monthly Class Test and Annual Progress Report marksheets for Bhogram Al-Hidayet Mission.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
