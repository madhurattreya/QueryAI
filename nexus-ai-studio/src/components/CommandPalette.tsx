"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";

export default function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any>({
    datasets: [],
    semantic_model: [],
    dashboards: [],
    reports: [],
    favorites: [],
    chat_history: []
  });
  const [selectedIndex, setSelectedIndex] = useState(0);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === "Escape") {
        setIsOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setSelectedIndex(0);
    } else {
      setQuery("");
      setResults({
        datasets: [],
        semantic_model: [],
        dashboards: [],
        reports: [],
        favorites: [],
        chat_history: []
      });
    }
  }, [isOpen]);

  useEffect(() => {
    if (!query || !query.trim()) {
      setResults({
        datasets: [],
        semantic_model: [],
        dashboards: [],
        reports: [],
        favorites: [],
        chat_history: []
      });
      return;
    }

    const delayDebounce = setTimeout(async () => {
      try {
        const res = await fetch(`http://127.0.0.1:8000/api/search?q=${encodeURIComponent(query)}`);
        if (res.ok) {
          const data = await res.json();
          if (data.status === "success") {
            setResults(data.results);
          }
        }
      } catch (err) {
        console.error("Search error:", err);
      }
    }, 150);

    return () => clearTimeout(delayDebounce);
  }, [query]);

  const flatItems = [
    ...results.datasets.map((x: any) => ({ ...x, category: "Dataset", url: "/connect" })),
    ...results.semantic_model.map((x: any) => ({ ...x, name: x.name, category: "Semantic Column", url: "/settings" })),
    ...results.dashboards.map((x: any) => ({ ...x, name: x.title, category: "Dashboard", url: `/visualizations?id=${x.id}` })),
    ...results.reports.map((x: any) => ({ ...x, name: `Report for ${x.email_recipient}`, category: "Report", url: "/settings" })),
    ...results.favorites.map((x: any) => ({ ...x, name: x.title || x.query, category: "Bookmark", url: `/query?q=${encodeURIComponent(x.query)}` })),
    ...results.chat_history.map((x: any) => ({ ...x, name: x.content, category: "Chat History", url: `/query?conv=${x.conversation_id}` }))
  ];

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % Math.max(1, flatItems.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + flatItems.length) % Math.max(1, flatItems.length));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (flatItems[selectedIndex]) {
        handleSelect(flatItems[selectedIndex]);
      }
    }
  };

  const handleSelect = (item: any) => {
    setIsOpen(false);
    router.push(item.url);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-charcoal-black/60 backdrop-blur-sm z-9999 flex items-start justify-center pt-[15vh]">
      <div className="bg-surface border border-outline-variant/40 rounded-xl shadow-2xl w-full max-w-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Search Input */}
        <div className="relative border-b border-outline-variant/30 flex items-center px-4 py-3">
          <span className="material-symbols-outlined text-outline text-[22px] mr-3">search</span>
          <input
            ref={inputRef}
            type="text"
            className="w-full bg-transparent border-none text-on-surface placeholder:text-outline/70 focus:outline-none text-sm"
            placeholder="Search datasets, columns, dashboards, history... (Ctrl+K to close)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-medium text-outline bg-surface-container border border-outline-variant/50 rounded shadow-sm">
            ESC
          </kbd>
        </div>

        {/* Results list */}
        <div className="max-h-[350px] overflow-y-auto py-2">
          {flatItems.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <span className="material-symbols-outlined text-[36px] text-outline/50 mb-2">search_off</span>
              <p className="text-xs text-on-surface-variant">No results found for "{query}"</p>
            </div>
          ) : (
            flatItems.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={idx}
                  onClick={() => handleSelect(item)}
                  className={`flex items-center justify-between px-4 py-2.5 cursor-pointer transition-colors ${
                    isSelected ? "bg-primary-container/20 text-vibrant-blue border-l-4 border-vibrant-blue font-semibold scale-[0.99]" : "text-on-surface hover:bg-surface-container"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span className="material-symbols-outlined text-[18px] text-outline-variant">
                      {item.category === "Dataset" && "database"}
                      {item.category === "Semantic Column" && "settings_accessibility"}
                      {item.category === "Dashboard" && "dashboard"}
                      {item.category === "Report" && "mail"}
                      {item.category === "Bookmark" && "star"}
                      {item.category === "Chat History" && "forum"}
                    </span>
                    <span className="text-xs truncate max-w-[450px]">{item.name || item.title || item.query}</span>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-outline bg-surface-container px-2 py-0.5 rounded border border-outline-variant/25">
                    {item.category}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="bg-surface-container-low border-t border-outline-variant/30 px-4 py-2 flex justify-between items-center text-[10px] text-outline font-semibold">
          <div className="flex items-center gap-3">
            <span>↑↓ to navigate</span>
            <span>↵ to select</span>
          </div>
          <div>QueryIQ Search Engine</div>
        </div>
      </div>
    </div>
  );
}
