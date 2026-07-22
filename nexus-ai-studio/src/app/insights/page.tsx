"use client";

import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { ApiClient } from "@/lib/apiClient";

interface Insight {
  title: string;
  metric: string;
  description: string;
  sql_or_python: string;
}

export default function InsightsPage() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(true);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState("");

  const fetchInsights = async () => {
    setLoading(true);
    setErrorMsg("");
    try {
      const res = await ApiClient.request("/api/insights");
      if (res.ok) {
        const data = await res.json();
        setInsights(data.insights || []);
      } else {
        setErrorMsg("Failed to generate AI insights.");
      }
    } catch (err) {
      console.error(err);
      setErrorMsg("Error communicating with AI analysis backend.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInsights();
  }, []);

  const handleCopy = (code: string, idx: number) => {
    navigator.clipboard.writeText(code);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  return (
    <DashboardLayout>
      <div className="mb-8 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-deep-navy tracking-tight">AI Business Insights</h1>
          <p className="text-sm text-on-surface-variant mt-1">
            Auto-generated business discoveries and analysis models curated by your AI analyst.
          </p>
        </div>
        <button
          onClick={fetchInsights}
          disabled={loading}
          className="text-xs bg-surface-container border border-outline-variant/30 rounded-lg py-1.5 px-3 hover:bg-surface-container-high text-deep-navy font-bold transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer shadow-xs"
        >
          <span className="material-symbols-outlined text-xs animate-none">sync</span>
          Regenerate Insights
        </button>
      </div>

      {errorMsg && (
        <div className="p-4 bg-error-container/20 border border-error/20 text-error rounded-xl text-xs mb-6 font-semibold">
          {errorMsg}
        </div>
      )}

      {loading ? (
        <div className="bg-surface-white border border-outline-variant/35 rounded-xl p-16 text-center flex flex-col justify-center items-center gap-4 min-h-[400px] shadow-sm">
          <span className="material-symbols-outlined animate-spin text-3xl text-vibrant-blue">progress_activity</span>
          <div className="max-w-xs">
            <p className="text-sm font-bold text-deep-navy">QueryIQ AI is analyzing...</p>
            <p className="text-xs text-on-surface-variant mt-1 leading-relaxed font-semibold">
              Scanning datasets metadata, parsing table definitions, and executing high-level strategic reasoning...
            </p>
          </div>
        </div>
      ) : insights.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {insights.map((insight, idx) => (
            <div key={idx} className="bg-surface-white border border-outline-variant/35 rounded-xl p-6 md:p-8 flex flex-col justify-between shadow-sm">
              <div>
                <div className="flex justify-between items-start mb-4">
                  <span className="text-[10px] bg-primary-fixed/40 border border-vibrant-blue/20 text-secondary px-2.5 py-0.5 rounded font-bold uppercase tracking-widest font-mono">
                    {insight.metric || "Key KPI"}
                  </span>
                </div>
                <h3 className="text-base font-bold text-deep-navy mb-2">{insight.title}</h3>
                <p className="text-xs leading-relaxed text-on-surface-variant mb-6 font-semibold">{insight.description}</p>
              </div>

              <div className="space-y-3 mt-auto">
                <div className="flex justify-between items-center text-[10px] text-on-surface-variant/80 uppercase font-bold tracking-wider">
                  <span>Execution Formula</span>
                  <button
                    onClick={() => handleCopy(insight.sql_or_python, idx)}
                    className="hover:text-vibrant-blue flex items-center gap-1 transition-colors cursor-pointer font-bold"
                  >
                    <span className="material-symbols-outlined text-xs">
                      {copiedIdx === idx ? "check" : "content_copy"}
                    </span>
                    {copiedIdx === idx ? "Copied" : "Copy"}
                  </button>
                </div>
                <pre className="text-[11px] font-mono bg-charcoal-black border border-outline-variant/20 p-3 rounded-lg overflow-x-auto text-surface-variant">
                  <code>{insight.sql_or_python}</code>
                </pre>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-surface-white border border-outline-variant/35 rounded-xl p-12 text-center text-on-surface-variant shadow-sm flex flex-col items-center">
          <span className="material-symbols-outlined text-4xl mb-4 text-vibrant-blue font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>psychology</span>
          <p className="text-sm font-semibold">No insights available. Please load a data source on the Connection Manager page.</p>
        </div>
      )}
    </DashboardLayout>
  );
}
