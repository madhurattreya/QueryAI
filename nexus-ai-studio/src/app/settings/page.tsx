"use client";

import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";

export default function SettingsPage() {
  const [model, setModel] = useState("qwen2.5:7b");
  const [explainMode, setExplainMode] = useState(true);
  const [debugMode, setDebugMode] = useState(false);
  const [fastMode, setFastMode] = useState(false);
  const [technicalMode, setTechnicalMode] = useState(false);
  const [hasGeminiKey, setHasGeminiKey] = useState(false);
  
  const [saveStatus, setSaveStatus] = useState<{ type: "idle" | "success" | "error"; message: string }>({
    type: "idle",
    message: ""
  });

  useEffect(() => {
    // Load initial settings
    const loadSettings = async () => {
      try {
        const res = await fetch("http://127.0.0.1:8000/api/status");
        if (res.ok) {
          const data = await res.json();
          setHasGeminiKey(data.has_gemini_key);
          if (data.settings) {
            setModel(data.settings.model);
            setExplainMode(data.settings.explain_mode);
            setDebugMode(data.settings.debug_mode);
            setFastMode(data.settings.fast_mode);
            setTechnicalMode(data.settings.technical_mode || false);
          }
        }
      } catch (err) {
        console.error(err);
      }
    };
    loadSettings();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveStatus({ type: "idle", message: "" });
    try {
      const res = await fetch("http://127.0.0.1:8000/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          explain_mode: explainMode,
          debug_mode: debugMode,
          fast_mode: fastMode,
          technical_mode: technicalMode
        })
      });
      if (res.ok) {
        setSaveStatus({ type: "success", message: "Settings updated successfully!" });
      } else {
        setSaveStatus({ type: "error", message: "Failed to update settings." });
      }
    } catch (err) {
      setSaveStatus({ type: "error", message: "Network error occurred." });
    }
  };

  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-deep-navy tracking-tight">Application Settings</h1>
        <p className="text-sm text-on-surface-variant mt-1">
          Configure model parameters, explanation defaults, and debug options for the AI Data Analyst.
        </p>
      </div>

      <div className="max-w-2xl bg-surface-white border border-outline-variant/35 rounded-xl p-8 shadow-sm">
        <form onSubmit={handleSave} className="space-y-6">
          {/* LLM Model Selection */}
          <div className="space-y-3">
            <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider">
              Core LLM Model Selector
            </h3>
            <p className="text-xs text-on-surface-variant leading-relaxed font-semibold">
              Choose between your locally running Ollama models or use the high-performance Gemini API.
            </p>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full bg-surface-container border border-outline-variant/30 rounded-lg px-4 py-3 text-xs text-on-surface focus:outline-none focus:border-vibrant-blue font-semibold cursor-pointer"
            >
              <option value="qwen2.5:7b">Ollama: Qwen 2.5 (7B)</option>
              <option value="gemma4:latest">Ollama: Gemma 4 (Latest)</option>
              <option value="gemini-1.5-flash" disabled={!hasGeminiKey}>
                Gemini API: Gemini 1.5 Flash {!hasGeminiKey && "(Needs GEMINI_API_KEY in .env)"}
              </option>
            </select>
            {!hasGeminiKey && (
              <p className="text-[10px] text-error font-semibold">
                * To enable Gemini, add your `GEMINI_API_KEY` to the `.env` file in the workspace directory.
              </p>
            )}
          </div>

          <hr className="border-outline-variant/35" />

          {/* Mode Toggles */}
          <div className="space-y-4">
            <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider">
              Execution & Interpretation Modes
            </h3>

            {/* Explain Mode */}
            <div className="flex items-start gap-4">
              <input
                id="explainMode"
                type="checkbox"
                checked={explainMode}
                onChange={(e) => setExplainMode(e.target.checked)}
                className="w-4 h-4 rounded bg-surface-container border-outline-variant/30 text-vibrant-blue focus:ring-vibrant-blue focus:ring-offset-background cursor-pointer"
              />
              <div className="text-xs leading-none">
                <label htmlFor="explainMode" className="font-bold text-deep-navy cursor-pointer">
                  Conversational Explanations
                </label>
                <p className="text-[10px] text-on-surface-variant mt-1 leading-relaxed font-semibold">
                  Generate natural language summary reports explaining what the calculated result tables mean.
                </p>
              </div>
            </div>

            {/* Debug Mode */}
            <div className="flex items-start gap-4">
              <input
                id="debugMode"
                type="checkbox"
                checked={debugMode}
                onChange={(e) => setDebugMode(e.target.checked)}
                className="w-4 h-4 rounded bg-surface-container border-outline-variant/30 text-vibrant-blue focus:ring-vibrant-blue focus:ring-offset-background cursor-pointer"
              />
              <div className="text-xs leading-none">
                <label htmlFor="debugMode" className="font-bold text-deep-navy cursor-pointer">
                  System Debug Logging
                </label>
                <p className="text-[10px] text-on-surface-variant mt-1 leading-relaxed font-semibold">
                  Print the full generated prompt, intermediate queries, and engine logs to standard outputs.
                </p>
              </div>
            </div>

            {/* Fast Mode */}
            <div className="flex items-start gap-4">
              <input
                id="fastMode"
                type="checkbox"
                checked={fastMode}
                onChange={(e) => setFastMode(e.target.checked)}
                className="w-4 h-4 rounded bg-surface-container border-outline-variant/30 text-vibrant-blue focus:ring-vibrant-blue focus:ring-offset-background cursor-pointer"
              />
              <div className="text-xs leading-none">
                <label htmlFor="fastMode" className="font-bold text-deep-navy cursor-pointer">
                  Fast Results-Only Mode
                </label>
                <p className="text-[10px] text-on-surface-variant mt-1 leading-relaxed font-semibold">
                  Skip secondary suggestions, conversational summaries, and code rendering to optimize run speeds.
                </p>
              </div>
            </div>

            {/* Technical Mode */}
            <div className="flex items-start gap-4">
              <input
                id="technicalMode"
                type="checkbox"
                checked={technicalMode}
                onChange={(e) => setTechnicalMode(e.target.checked)}
                className="w-4 h-4 rounded bg-surface-container border-outline-variant/30 text-vibrant-blue focus:ring-vibrant-blue focus:ring-offset-background cursor-pointer"
              />
              <div className="text-xs leading-none">
                <label htmlFor="technicalMode" className="font-bold text-deep-navy cursor-pointer">
                  Technical mode
                </label>
                <p className="text-[10px] text-on-surface-variant mt-1 leading-relaxed font-semibold">
                  Show raw code, SQL scripts, execution details, and planner metrics in the conversation.
                </p>
              </div>
            </div>
          </div>

          <hr className="border-outline-variant/35" />

          {saveStatus.message && (
            <div
              className={`p-4 rounded-lg text-xs font-bold ${
                saveStatus.type === "success"
                  ? "bg-primary-fixed/40 text-secondary border border-vibrant-blue/20"
                  : "bg-error-container/20 text-error border border-error/20"
              }`}
            >
              {saveStatus.message}
            </div>
          )}

          <button
            type="submit"
            className="w-full bg-deep-navy text-white text-sm font-bold py-3 rounded-lg hover:bg-primary transition-all cursor-pointer shadow-xs"
          >
            Apply Configurations
          </button>
        </form>
      </div>
    </DashboardLayout>
  );
}
