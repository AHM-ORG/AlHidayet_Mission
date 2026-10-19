import Link from "next/link";
import { FileSpreadsheet, LayoutDashboard } from "lucide-react";
import type { ReactNode } from "react";

export default function AppShell({
  active,
  title,
  children,
}: {
  active: "dashboard" | "marksheet";
  title: string;
  children: ReactNode;
}) {
  const items = [
    { id: "dashboard" as const, href: "/", label: "Dashboard", icon: LayoutDashboard },
    {
      id: "marksheet" as const,
      href: "/admin/marksheet",
      label: "Marksheet",
      icon: FileSpreadsheet,
    },
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar app-chrome">
        <div className="flex items-center gap-2.5 border-b border-white/10 px-4 py-4">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/images/ahm-logo.png"
            alt="AHM"
            className="h-9 w-9 rounded-lg bg-white object-contain p-0.5"
          />
          <div className="leading-tight">
            <div className="text-[14px] font-bold text-white">Al Hidayet Mission</div>
            <div className="text-[10.5px] font-medium tracking-wide text-[#7fa8a3]">
              BHOGRAM &middot; HEMTABAD
            </div>
          </div>
        </div>
        <nav className="flex-1 pb-4">
          <div className="sidebar-label">Docs &amp; Cards</div>
          {items.map((it) => {
            const Icon = it.icon;
            return (
              <Link
                key={it.id}
                href={it.href}
                className={`sidebar-item ${active === it.id ? "active" : ""}`}
              >
                <Icon size={16} />
                {it.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-white/10 px-5 py-3 text-[10.5px] font-medium tracking-wide text-[#6f948f]">
          ACADEMIC YEAR 2025
        </div>
      </aside>

      <div className="main-area min-w-0 flex-1">
        <header className="top-bar app-chrome">
          <div className="text-[15px] font-bold text-[#145058]">{title}</div>
          <div className="text-[12px] font-medium text-[#8a938f]">
            Bhogram Al-Hidayet Mission
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
