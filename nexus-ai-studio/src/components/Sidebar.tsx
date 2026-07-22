"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface SidebarProps {
  statusText?: string;
  loadedFiles?: string[];
  sqlConnected?: boolean;
}

export default function Sidebar({ statusText = "Ready", loadedFiles = [], sqlConnected = false }: SidebarProps) {
  const pathname = usePathname();

  const navItems = [
    { name: "Home", href: "/", icon: "home" },
    { name: "Datasets", href: "/connect", icon: "database" },
    { name: "SQL Explorer", href: "/explorer", icon: "code" },
    { name: "Chat Analyst", href: "/query", icon: "history" },
    { name: "Agent Loop", href: "/agent", icon: "psychology" },
    { name: "Visualizations", href: "/visualizations", icon: "monitoring" },
    { name: "Business Insights", href: "/insights", icon: "insights" },
    { name: "Settings", href: "/settings", icon: "settings" },
  ];

  return (
    <aside className="hidden md:flex bg-charcoal-black font-headline text-body-md fixed left-0 top-0 h-full w-[260px] border-r border-charcoal-black flex-col py-6 z-50">
      {/* Brand logo */}
      <div className="px-6 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded bg-vibrant-blue flex items-center justify-center text-white font-bold text-xl">
            <span className="material-symbols-outlined font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>
              analytics
            </span>
          </div>
          <div>
            <h1 className="text-xl font-bold text-white tracking-tight leading-none">QueryIQ</h1>
            <p className="text-[11px] font-bold uppercase tracking-wider text-vibrant-blue mt-1">AI Data Engine</p>
          </div>
        </div>
      </div>

      {/* New Analysis Button */}
      <div className="px-4 mb-6">
        <Link href="/query">
          <button className="w-full bg-vibrant-blue text-white rounded font-headline font-semibold py-2.5 flex items-center justify-center gap-2 hover:bg-secondary-container transition-colors shadow-sm cursor-pointer">
            <span className="material-symbols-outlined text-[18px]">add</span>
            New Analysis
          </button>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 px-2 flex-grow overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all duration-150 ${
                isActive
                  ? "bg-primary-container text-vibrant-blue border-l-4 border-vibrant-blue font-semibold scale-95"
                  : "text-on-surface-variant hover:bg-tertiary-container hover:text-white"
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
              <span className="font-body-md text-sm">{item.name}</span>
            </Link>
          );
        })}
      </nav>

      {/* Bottom section (Documentation & Support) */}
      <div className="px-2 mt-auto border-t border-tertiary-container pt-4">
        <a
          href="#"
          className="flex items-center gap-3 px-4 py-2 rounded-lg text-on-surface-variant hover:text-white transition-all"
        >
          <span className="material-symbols-outlined text-[20px]">help</span>
          <span className="font-body-sm text-xs">Documentation</span>
        </a>
        <a
          href="#"
          className="flex items-center gap-3 px-4 py-2 rounded-lg text-on-surface-variant hover:text-white transition-all"
        >
          <span className="material-symbols-outlined text-[20px]">contact_support</span>
          <span className="font-body-sm text-xs">Support</span>
        </a>
      </div>
    </aside>
  );
}
