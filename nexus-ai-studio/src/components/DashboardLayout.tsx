"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import CommandPalette from "./CommandPalette";

interface DashboardLayoutProps {
  children: React.ReactNode;
  fullScreen?: boolean;
}

export default function DashboardLayout({ children, fullScreen = false }: DashboardLayoutProps) {
  const pathname = usePathname();
  const [status, setStatus] = useState<any>({
    status: "Ready",
    current_source_type: "file",
    loaded_files: [],
    sql_connected: false,
    db_flavor: null,
    sql_tables: [],
    settings: { model: "Qwen2.5:7B", explain_mode: true }
  });

  const fetchStatus = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/status");
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (err) {
      console.error("Error fetching status from API backend", err);
    }
  };

  useEffect(() => {
    fetchStatus();
    // Poll status every 5 seconds to keep sidebar/status bar synced
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-surface text-on-surface flex overflow-hidden font-headline">
      {/* Sidebar */}
      <Sidebar
        statusText={status.status}
        loadedFiles={status.loaded_files}
        sqlConnected={status.sql_connected}
      />

      {/* Main Content Area */}
      <div className="flex-grow main-content-offset flex flex-col h-screen relative pb-[32px] md:pb-[32px]">
        {/* Top Header */}
        <header className="bg-surface border-b border-outline-variant/30 flex justify-between items-center h-16 px-6 md:px-8 w-full z-40 sticky top-0 shrink-0">
          <div className="flex items-center gap-8 h-full">
            <h2 className="text-lg font-black text-deep-navy md:hidden leading-none">QueryIQ</h2>
            <nav className="hidden md:flex gap-6 h-full text-sm items-center font-semibold">
              <Link
                href="/"
                className={`h-full flex items-center px-1 border-b-2 transition-all ${
                  pathname === "/"
                    ? "border-vibrant-blue text-vibrant-blue"
                    : "border-transparent text-on-surface-variant hover:text-vibrant-blue"
                }`}
              >
                Workspace
              </Link>
              <Link
                href="/connect"
                className={`h-full flex items-center px-1 border-b-2 transition-all ${
                  pathname === "/connect" || pathname === "/explorer"
                    ? "border-vibrant-blue text-vibrant-blue"
                    : "border-transparent text-on-surface-variant hover:text-vibrant-blue"
                }`}
              >
                Datasets
              </Link>
              <Link
                href="/query"
                className={`h-full flex items-center px-1 border-b-2 transition-all ${
                  pathname === "/query"
                    ? "border-vibrant-blue text-vibrant-blue"
                    : "border-transparent text-on-surface-variant hover:text-vibrant-blue"
                }`}
              >
                Analytics
              </Link>
            </nav>
          </div>

          <div className="flex items-center gap-4">
            <div className="relative hidden lg:block">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">
                search
              </span>
              <input
                className="bg-surface-container-low border border-outline-variant/50 rounded-lg pl-10 pr-4 py-1.5 text-xs focus:outline-none focus:border-vibrant-blue w-64 transition-all placeholder:text-outline text-on-surface"
                placeholder="Search workspace, datasets..."
                type="text"
              />
            </div>
            <button className="text-on-surface-variant hover:text-vibrant-blue transition-colors flex items-center justify-center p-2 rounded-full hover:bg-surface-container-low">
              <span className="material-symbols-outlined text-[20px]">notifications</span>
            </button>
            <Link href="/settings" className="text-on-surface-variant hover:text-vibrant-blue transition-colors flex items-center justify-center p-2 rounded-full hover:bg-surface-container-low">
              <span className="material-symbols-outlined text-[20px]">settings</span>
            </Link>
            <div className="ml-2 w-8 h-8 rounded-full border border-outline-variant overflow-hidden">
              <img
                alt="User Profile"
                className="w-full h-full object-cover"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuBfy7yGtB7N0lXAzEdFndpsnrCYH02g5LzMbV4YCGPFoWgiEoSUsJHuoCMck1ks03jE9j3wu4oJgHlzkTRxXu-kEEgfZEFfmeBJJzVOC4oehFH07YlpNdPdqilY88exRgC7ygbSywIKXyIH0Fg6I8gw__T0lfVPDMC-Zp1l7tDsO-5buaBVUBIeCT9bjGvF7An-um3xio4EADYtQ79LaF3K6e80b8ZNMmUub3d0j45NbaUTTnazN3zZ"
              />
            </div>
          </div>
        </header>

        {/* Dynamic Page Canvas */}
        {fullScreen ? (
          <main className="flex-grow overflow-hidden relative z-10 w-full">
            {children}
          </main>
        ) : (
          <main className="flex-grow overflow-y-auto px-6 md:px-8 py-8 relative z-10">
            <div className="hero-glow"></div>
            <div className="max-w-[1440px] mx-auto relative z-10">{children}</div>
          </main>
        )}

        {/* Bottom Status Bar */}
        <footer className="hidden md:flex bg-surface-container-highest border-t border-outline-variant/50 fixed bottom-0 footer-offset right-0 h-8 z-50 justify-between items-center px-6">
          <div className="flex gap-6">
            <div className="text-vibrant-blue flex items-center gap-1.5 text-xs font-semibold">
              <span className="material-symbols-outlined text-[16px]">psychology</span>
              <span>Model: {status.settings?.model || "Qwen2.5:7B"}</span>
            </div>
            <div className="text-on-surface-variant flex items-center gap-1.5 text-xs font-semibold">
              <span className="material-symbols-outlined text-[16px]">memory</span>
              <span>
                Source: {status.current_source_type === "sql" ? `${status.db_flavor} Connected` : `${status.loaded_files?.length || 0} files loaded`}
              </span>
            </div>
            <div className="text-on-surface-variant flex items-center gap-1.5 text-xs font-semibold">
              <span className="material-symbols-outlined text-[16px]">check_circle</span>
              <span>Status: Operational</span>
            </div>
          </div>
          <div className="text-deep-navy font-bold text-xs uppercase tracking-wider">
            QueryIQ
          </div>
        </footer>
      </div>
      <CommandPalette />
    </div>
  );
}
