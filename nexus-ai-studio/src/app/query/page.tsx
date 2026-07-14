"use client";

import { useEffect, useState, useRef } from "react";
import DashboardLayout from "@/components/DashboardLayout";

interface ChatMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  generated_code?: string;
  result?: any[];
  chart_id?: string;
  execution_time?: number;
  rows?: number;
  error?: string;
  prompt_size?: number;
  engine_used?: string;
  debug_info?: any;
  progress_steps?: string[];
}

interface Conversation {
  id: string;
  title: string;
  summary?: string;
  dataset_id?: string;
  created_at: string;
}

export default function QueryPage() {
  // Conversations list & Search
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  
  // Message Feed
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [abortController, setAbortController] = useState<AbortController | null>(null);
  
  // Active Dataset Telemetry
  const [activeDataset, setActiveDataset] = useState<any>(null);
  const [leftPanelTab, setLeftPanelTab] = useState<"explorer" | "history">("explorer");
  const [allDatasets, setAllDatasets] = useState<any[]>([]);
  const [datasetSchemas, setDatasetSchemas] = useState<{ [key: string]: any[] }>({});

  const fetchActiveDataset = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/datasets");
      if (res.ok) {
        const data = await res.json();
        const active = data.find((ds: any) => ds.is_active === 1);
        setActiveDataset(active || null);
        setAllDatasets(data);

        // Fetch schema columns in background for all datasets
        const schemas: { [key: string]: any[] } = {};
        for (const ds of data) {
          try {
            const schemaRes = await fetch(`http://127.0.0.1:8000/api/datasets/schema/${ds.id}`);
            if (schemaRes.ok) {
              const schemaData = await schemaRes.json();
              schemas[ds.id] = schemaData.columns || [];
            }
          } catch (e) {
            console.error("Failed to load schema for " + ds.name, e);
          }
        }
        setDatasetSchemas(schemas);
      }
    } catch (err) {
      console.error("Failed to fetch active dataset details", err);
    }
  };

  useEffect(() => {
    fetchActiveDataset();
  }, [messages]);
  
  // Theme & Pinned Queries
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const [pinnedQueries, setPinnedQueries] = useState<string[]>([]);
  
  // Toggles for code blocks per message index
  const [showCodeIdx, setShowCodeIdx] = useState<{ [key: number]: boolean }>({});
  
  // Scroll reference
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load theme and pinned queries from localStorage
  useEffect(() => {
    const savedTheme = localStorage.getItem("theme") as "light" | "dark" | null;
    if (savedTheme) {
      setTheme(savedTheme);
      document.documentElement.classList.toggle("dark", savedTheme === "dark");
    } else {
      document.documentElement.classList.add("dark");
    }

    const savedPins = localStorage.getItem("pinned_queries");
    if (savedPins) {
      try {
        setPinnedQueries(JSON.parse(savedPins));
      } catch (e) {
        console.error(e);
      }
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("theme", nextTheme);
    document.documentElement.classList.toggle("dark", nextTheme === "dark");
  };

  const togglePinQuery = (queryText: string) => {
    let nextPins = [...pinnedQueries];
    if (nextPins.includes(queryText)) {
      nextPins = nextPins.filter((q) => q !== queryText);
    } else {
      nextPins.push(queryText);
    }
    setPinnedQueries(nextPins);
    localStorage.setItem("pinned_queries", JSON.stringify(nextPins));
  };

  // Keyboard shortcut setup (Ctrl + Enter to send, Esc to cancel)
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && e.ctrlKey) {
      e.preventDefault();
      handleSend(inputValue);
    } else if (e.key === "Escape" && loading) {
      handleCancel();
    }
  };

  // Load conversations list on mount
  const fetchConversations = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/conversations");
      if (res.ok) {
        const data = await res.json();
        setConversations(data);
      }
    } catch (err) {
      console.error("Failed to fetch conversations", err);
    }
  };

  useEffect(() => {
    fetchConversations();
  }, []);

  // Search conversations
  useEffect(() => {
    const delayDebounceFn = setTimeout(async () => {
      if (searchQuery.trim()) {
        try {
          const res = await fetch(`http://127.0.0.1:8000/api/conversations/search?q=${encodeURIComponent(searchQuery)}`);
          if (res.ok) {
            const data = await res.json();
            setConversations(data);
          }
        } catch (err) {
          console.error(err);
        }
      } else {
        fetchConversations();
      }
    }, 300);

    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery]);

  // Load active conversation details
  const loadConversation = async (id: string) => {
    if (loading) handleCancel();
    setActiveConvId(id);
    setMessages([]);
    setErrorMessage("");
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/conversation/${id}`);
      if (res.ok) {
        const data = await res.json();
        const formattedMsgs: ChatMessage[] = data.messages.map((m: any) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          generated_code: m.generated_code,
          result: m.result || [],
          chart_id: m.chart_id,
          execution_time: m.execution_time,
          rows: m.rows,
          prompt_size: m.prompt_size,
          engine_used: m.engine_used,
          debug_info: m.debug_info
        }));
        setMessages(formattedMsgs);
      } else {
        setErrorMessage("Failed to load conversation details.");
      }
    } catch (err) {
      console.error(err);
      setErrorMessage("Error communicating with server.");
    }
  };

  // Delete conversation
  const deleteConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this conversation?")) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/conversation/${id}`, {
        method: "DELETE"
      });
      if (res.ok) {
        if (activeConvId === id) {
          setActiveConvId(null);
          setMessages([]);
        }
        fetchConversations();
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Start a new conversation
  const startNewChat = () => {
    if (loading) handleCancel();
    setActiveConvId(null);
    setMessages([]);
    setErrorMessage("");
    setInputValue("");
  };

  // Cancel query run
  const handleCancel = () => {
    if (abortController) {
      abortController.abort();
      setAbortController(null);
    }
    setLoading(false);
    setMessages((prev) => prev.filter((m) => m.id !== "loading"));
  };

  // Copy code utility
  const copyCode = (text: string) => {
    navigator.clipboard.writeText(text);
    alert("Code copied to clipboard!");
  };

  // Export dataset preview to CSV
  const exportCSV = (data: any[], title: string) => {
    if (!data || data.length === 0) return;
    const headers = Object.keys(data[0]).join(",");
    const rows = data.map((row) =>
      Object.values(row)
        .map((val) => `"${String(val).replace(/"/g, '""')}"`)
        .join(",")
    );
    const csvContent = "data:text/csv;charset=utf-8," + [headers, ...rows].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `${title.replace(/[^a-zA-Z0-9]/g, "_")}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Send query request (supports SSE progress reading)
  const handleSend = async (text: string) => {
    if (!text.trim()) return;
    const userQuestion = text.trim();
    setInputValue("");
    setLoading(true);
    setErrorMessage("");

    // Setup AbortController for cancel action
    const controller = new AbortController();
    setAbortController(controller);

    // Prepend user message and loading card locally
    setMessages((prev) => [
      ...prev,
      { role: "user", content: userQuestion },
      { role: "assistant", content: "Executing Query...", id: "loading", progress_steps: [] }
    ]);

    try {
      const res = await fetch("http://127.0.0.1:8000/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: userQuestion,
          conversation_id: activeConvId
        }),
        signal: controller.signal
      });

      if (!res.ok) {
        throw new Error(`Server returned HTTP status ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("ReadableStream not supported on this browser.");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep trailing partial line in buffer

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            
            if (data.type === "progress") {
              setMessages((prev) => {
                const updated = [...prev];
                const loadIdx = updated.findIndex((m) => m.id === "loading");
                if (loadIdx !== -1) {
                  const steps = updated[loadIdx].progress_steps || [];
                  if (!steps.includes(data.step)) {
                    updated[loadIdx] = {
                      ...updated[loadIdx],
                      content: data.step,
                      progress_steps: [...steps, data.step]
                    };
                  }
                }
                return updated;
              });
            } else if (data.type === "success") {
              // Extract active ID
              if (!activeConvId) {
                setActiveConvId(data.conversation_id);
                fetchConversations();
              }
              setMessages((prev) => {
                const updated = [...prev];
                const loadIdx = updated.findIndex((m) => m.id === "loading");
                if (loadIdx !== -1) {
                  updated[loadIdx] = {
                    role: "assistant",
                    content: data.explanation || "Result processed.",
                    generated_code: data.code,
                    result: data.result || [],
                    chart_id: data.chart_id,
                    execution_time: data.execution_time,
                    rows: data.rows,
                    prompt_size: data.prompt_size,
                    engine_used: data.engine_used,
                    debug_info: data.debug_info
                  };
                }
                return updated;
              });
            } else if (data.type === "error") {
              setMessages((prev) => {
                const updated = [...prev];
                const loadIdx = updated.findIndex((m) => m.id === "loading");
                if (loadIdx !== -1) {
                  updated[loadIdx] = {
                    role: "assistant",
                    content: "Failed to generate sandbox query.",
                    error: data.error || "An execution error occurred."
                  };
                }
                return updated;
              });
            }
          } catch (e) {
            console.error("Failed to parse SSE JSON line", e);
          }
        }
      }
    } catch (err: any) {
      if (err.name === "AbortError") {
        console.log("Query cancelled by user.");
        return;
      }
      setMessages((prev) => {
        const updated = [...prev];
        const loadIdx = updated.findIndex((m) => m.id === "loading");
        if (loadIdx !== -1) {
          const isNetworkErr = err.message?.toLowerCase().includes("fetch") || err.message?.toLowerCase().includes("network") || err.message?.toLowerCase().includes("failed");
          updated[loadIdx] = {
            role: "assistant",
            content: "Query Execution Failed.",
            error: isNetworkErr
              ? "Cannot connect to the backend server. Make sure the backend is running on port 8000, and that an active dataset is loaded."
              : (err.message || "An unexpected error occurred. Please try again.")
          };
        }
        return updated;
      });
    } finally {
      setLoading(false);
      setAbortController(null);
    }
  };

  const toggleCode = (idx: number) => {
    setShowCodeIdx((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  return (
    <DashboardLayout fullScreen>
      <div className="flex h-[calc(100vh-96px)] w-full overflow-hidden bg-background">
        
        {/* Panel 1: Left Sidebar (Data Explorer & Session History Tab) */}
        <aside className="w-[260px] h-full flex flex-col border-r border-outline-variant/35 bg-surface-container-lowest flex-shrink-0 z-15">
          {/* Tab selector */}
          <div className="px-4 py-3 border-b border-outline-variant/35 bg-surface flex flex-col gap-2 shrink-0">
            <div className="flex bg-surface-container p-0.5 rounded-lg border border-outline-variant/20">
              <button
                onClick={() => setLeftPanelTab("explorer")}
                className={`flex-1 py-1.5 text-[10px] font-bold rounded-md flex items-center justify-center gap-1 transition-all cursor-pointer ${
                  leftPanelTab === "explorer"
                    ? "bg-deep-navy text-white shadow-xs"
                    : "text-on-surface-variant hover:text-deep-navy"
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">explore</span>
                Explorer
              </button>
              <button
                onClick={() => setLeftPanelTab("history")}
                className={`flex-1 py-1.5 text-[10px] font-bold rounded-md flex items-center justify-center gap-1 transition-all cursor-pointer ${
                  leftPanelTab === "history"
                    ? "bg-deep-navy text-white shadow-xs"
                    : "text-on-surface-variant hover:text-deep-navy"
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">history</span>
                Sessions
              </button>
            </div>
            
            {leftPanelTab === "history" && (
              <div className="flex justify-between items-center gap-2">
                <button
                  onClick={startNewChat}
                  className="flex-grow bg-vibrant-blue hover:bg-secondary-container text-white text-[10px] font-bold py-1.5 px-3 rounded flex items-center justify-center gap-1 transition-all cursor-pointer shadow-xs"
                >
                  <span className="material-symbols-outlined text-xs">add</span>
                  New Chat
                </button>
              </div>
            )}
          </div>

          {/* Search bar inside Panel 1 */}
          {leftPanelTab === "history" && (
            <div className="px-3 py-2 border-b border-outline-variant/20 shrink-0">
              <div className="relative">
                <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant text-[16px]">
                  search
                </span>
                <input
                  className="w-full bg-surface-container-low border border-outline-variant/30 rounded pl-8 pr-2 py-1 text-[11px] text-on-surface focus:outline-none focus:border-vibrant-blue placeholder-on-surface-variant"
                  placeholder="Search history..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  type="text"
                />
              </div>
            </div>
          )}

          {/* Tab content area */}
          <div className="flex-grow overflow-y-auto p-2">
            {leftPanelTab === "explorer" ? (
              <div className="space-y-1.5 font-body-sm text-xs">
                <div className="flex items-center gap-1 py-1 px-2 text-deep-navy font-bold">
                  <span className="material-symbols-outlined text-sm">expand_more</span>
                  <span className="material-symbols-outlined text-sm text-vibrant-blue font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>database</span>
                  <span>Active Workspaces</span>
                </div>
                
                <div className="pl-4 space-y-1">
                  {allDatasets.map((ds) => (
                    <div key={ds.id} className="space-y-1">
                      <div className={`flex items-center gap-1 py-1 px-2 rounded cursor-pointer ${
                        ds.is_active === 1 
                          ? "bg-primary-fixed/40 text-deep-navy font-bold" 
                          : "hover:bg-surface-container text-on-surface-variant"
                      }`}>
                        <span className="material-symbols-outlined text-xs">table_chart</span>
                        <span className="truncate">{ds.name}</span>
                      </div>
                      
                      {datasetSchemas[ds.id] && datasetSchemas[ds.id].length > 0 && (
                        <div className="pl-6 space-y-0.5 border-l border-outline-variant/30 ml-3">
                          {datasetSchemas[ds.id].map((col: any, cIdx: number) => (
                            <div key={cIdx} className="flex items-center gap-1.5 py-0.5 text-[10px] text-on-surface-variant/80 font-mono">
                              <span className="material-symbols-outlined text-[12px] text-outline">
                                {col.type?.toLowerCase().includes("int") || col.type?.toLowerCase().includes("float") || col.type?.toLowerCase().includes("double") || col.type?.toLowerCase().includes("number") ? "tag" : col.type?.toLowerCase().includes("date") || col.type?.toLowerCase().includes("time") ? "calendar_today" : "text_fields"}
                              </span>
                              <span className="truncate" title={`${col.name} (${col.type})`}>{col.name}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                  {allDatasets.length === 0 && (
                    <p className="text-[10px] text-on-surface-variant text-center py-4">No datasets loaded.</p>
                  )}
                </div>
              </div>
            ) : (
              <div className="space-y-1">
                {conversations.map((c) => {
                  const isActive = activeConvId === c.id;
                  return (
                    <div
                      key={c.id}
                      onClick={() => loadConversation(c.id)}
                      className={`w-full group text-left px-3 py-2 rounded border text-xs flex items-center justify-between cursor-pointer transition-all ${
                        isActive
                          ? "bg-primary-fixed/50 border-vibrant-blue text-deep-navy font-bold"
                          : "bg-transparent border-transparent hover:bg-surface-container text-on-surface-variant hover:text-deep-navy"
                      }`}
                    >
                      <div className="flex items-center gap-2 overflow-hidden mr-2">
                        <span className="material-symbols-outlined text-sm shrink-0">chat_bubble</span>
                        <p className="truncate capitalize leading-none">{c.title || "Untitled Session"}</p>
                      </div>
                      <button
                        onClick={(e) => deleteConversation(c.id, e)}
                        className="opacity-0 group-hover:opacity-100 hover:text-error transition-all text-on-surface-variant shrink-0 p-0.5 rounded hover:bg-surface-container cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-xs">delete</span>
                      </button>
                    </div>
                  );
                })}
                {conversations.length === 0 && (
                  <p className="text-[10px] text-on-surface-variant text-center py-8">No previous sessions.</p>
                )}
              </div>
            )}
          </div>
        </aside>

        {/* Panel 2: Center Workspace (Chat Analyst Area) */}
        <section className="flex-grow flex-1 h-full flex flex-col relative bg-surface-container-lowest min-w-[450px]">
          {/* Chat Messages Log */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 pb-32">
            {messages.length === 0 ? (
              <div className="text-center max-w-md mx-auto mt-12 flex flex-col items-center">
                <div className="w-14 h-14 rounded-full bg-surface-container border border-outline-variant/30 flex items-center justify-center mb-6">
                  <span className="material-symbols-outlined text-vibrant-blue text-2xl font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>smart_toy</span>
                </div>
                <h3 className="text-base font-bold text-deep-navy mb-2">QueryIQ AI analyst workspace</h3>
                <p className="text-xs text-on-surface-variant leading-relaxed mb-6 font-semibold">
                  Type a natural language query in the chat input below to search, analyze, and plot your dataset dynamically.
                </p>
                <div className="flex flex-col gap-2 w-full">
                  <button
                    onClick={() => handleSend("List the tables and describe them")}
                    className="p-3 bg-surface border border-outline-variant/30 hover:border-vibrant-blue text-left rounded-lg text-[11px] font-bold text-deep-navy transition-all cursor-pointer hover:shadow-xs"
                  >
                    🔍 Describe active tables & schemas
                  </button>
                </div>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.role === "user" ? (
                    <div className="bg-surface-container-low border border-outline-variant/40 text-on-surface px-4 py-3 rounded-xl rounded-tr-none shadow-sm max-w-xl text-xs font-semibold relative group">
                      <p className="leading-relaxed pr-6 select-text">{msg.content}</p>
                      <button
                        onClick={() => togglePinQuery(msg.content)}
                        title={pinnedQueries.includes(msg.content) ? "Unpin query" : "Pin query"}
                        className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 text-on-surface-variant hover:text-vibrant-blue transition-opacity cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-xs">
                          {pinnedQueries.includes(msg.content) ? "keep" : "keep_off"}
                        </span>
                      </button>
                    </div>
                  ) : (
                    <div className="bg-surface border border-outline-variant/35 rounded-xl p-5 w-full max-w-3xl shadow-xs space-y-4">
                      
                      {/* Loading SSE status card */}
                      {msg.id === "loading" ? (
                        <div className="space-y-4">
                          <div className="flex items-center gap-3 text-xs text-vibrant-blue py-2 font-bold">
                            <span className="material-symbols-outlined animate-spin text-lg">progress_activity</span>
                            <span>Executing Query...</span>
                          </div>
                          {msg.progress_steps && (
                            <div className="border-l-2 border-outline-variant pl-4 ml-2 space-y-1.5">
                              {msg.progress_steps.map((step, sIdx) => (
                                <div key={sIdx} className="flex items-center gap-2 text-[10px] font-semibold text-on-surface-variant">
                                  <span className="material-symbols-outlined text-[12px] text-success">check_circle</span>
                                  <span>{step}</span>
                                </div>
                              ))}
                            </div>
                          )}
                          <button
                            onClick={handleCancel}
                            className="bg-surface-container border border-outline-variant/30 hover:bg-surface-container-high text-on-surface px-3 py-1 rounded text-[10px] font-bold transition-all cursor-pointer"
                          >
                            Cancel Execution
                          </button>
                        </div>
                      ) : msg.error ? (
                        <div className="space-y-3">
                          <p className="text-xs font-bold text-error flex items-center gap-1.5">
                            <span className="material-symbols-outlined text-sm">error</span>
                            Query Execution Failed
                          </p>
                          <pre className="text-[10px] font-mono bg-error-container/10 border border-error/20 p-4 rounded-lg text-error select-text overflow-x-auto">
                            <code>{msg.error}</code>
                          </pre>
                          {idx > 0 && messages[idx - 1].role === "user" && (
                            <button
                              onClick={() => handleSend(messages[idx - 1].content)}
                              className="bg-vibrant-blue/10 hover:bg-vibrant-blue/20 text-secondary border border-vibrant-blue/20 px-3 py-1.5 rounded text-[10px] font-bold transition-colors cursor-pointer"
                            >
                              Retry Query
                            </button>
                          )}
                        </div>
                      ) : (
                        <>
                          {/* Explanation summary */}
                          {msg.content && (
                            <div>
                              <h4 className="text-[10px] font-bold text-deep-navy uppercase tracking-wider mb-1.5">Analysis Summary</h4>
                              <p className="text-xs text-on-surface leading-relaxed font-semibold select-text">{msg.content}</p>
                            </div>
                          )}

                          {/* Dynamic interactive chart */}
                          {msg.chart_id && (
                            <div>
                              <h4 className="text-[10px] font-bold text-secondary uppercase tracking-wider mb-2 flex justify-between items-center">
                                <span>Interactive Visualization</span>
                                <div className="flex gap-2">
                                  <a
                                    href={`http://127.0.0.1:8000/api/chart/html?id=${msg.chart_id}`}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-[9px] bg-surface-container border border-outline-variant/30 px-2 py-0.5 rounded hover:bg-surface-container-high text-on-surface transition-colors cursor-pointer"
                                  >
                                    Open Full Screen
                                  </a>
                                  <a
                                    href={`http://127.0.0.1:8000/api/chart/png?id=${msg.chart_id}`}
                                    download={`chart_${msg.chart_id}.png`}
                                    className="text-[9px] bg-surface-container border border-outline-variant/30 px-2 py-0.5 rounded hover:bg-surface-container-high text-on-surface transition-colors cursor-pointer"
                                  >
                                    Download PNG
                                  </a>
                                </div>
                              </h4>
                              <div className="w-full h-[320px] bg-white rounded-lg overflow-hidden border border-outline-variant/30 relative">
                                <iframe
                                  src={`http://127.0.0.1:8000/api/chart/html?id=${msg.chart_id}`}
                                  className="w-full h-full border-none bg-white"
                                  title="Plotly Chart"
                                />
                              </div>
                            </div>
                          )}

                          {/* Code section */}
                          {msg.generated_code && (
                            <div>
                              <div className="flex justify-between items-center mb-1">
                                <button
                                  onClick={() => toggleCode(idx)}
                                  className="text-[10px] font-bold text-on-surface-variant hover:text-deep-navy uppercase tracking-wider flex items-center gap-1 transition-colors cursor-pointer"
                                >
                                  <span className="material-symbols-outlined text-xs">
                                    {showCodeIdx[idx] ? "keyboard_arrow_up" : "keyboard_arrow_down"}
                                  </span>
                                  {showCodeIdx[idx] ? "Hide Source Code" : "Show Generated Code"}
                                </button>
                                {showCodeIdx[idx] && (
                                  <button
                                    onClick={() => copyCode(msg.generated_code || "")}
                                    className="text-[9px] font-bold text-vibrant-blue hover:underline cursor-pointer"
                                  >
                                    Copy Code
                                  </button>
                                )}
                              </div>
                              {showCodeIdx[idx] && (
                                <pre className="text-[11px] font-mono bg-charcoal-black p-3 rounded-lg overflow-x-auto text-surface-variant leading-relaxed select-text border border-outline-variant/20">
                                  <code>{msg.generated_code}</code>
                                </pre>
                              )}
                            </div>
                          )}

                          {/* Data tables rendering */}
                          {msg.result && msg.result.length > 0 && (
                            <div>
                              <div className="flex justify-between items-center mb-2">
                                <h4 className="text-[10px] font-bold text-deep-navy uppercase tracking-wider">Returned Records</h4>
                                <button
                                  onClick={() => exportCSV(msg.result || [], messages[idx - 1]?.content || "query_result")}
                                  className="text-[9px] bg-surface-container border border-outline-variant/30 px-2 py-0.5 rounded hover:bg-surface-container-high text-on-surface transition-colors font-bold cursor-pointer"
                                >
                                  Export to CSV
                                </button>
                              </div>
                              <div className="overflow-x-auto max-h-[200px] border border-outline-variant/30 rounded-lg bg-surface-container-lowest">
                                <table className="w-full text-left border-collapse text-[10px]">
                                  <thead className="bg-surface-container sticky top-0 z-10">
                                    <tr className="border-b border-outline-variant/55 text-deep-navy uppercase tracking-wider font-bold">
                                      {Object.keys(msg.result[0]).map((key) => (
                                        <th key={key} className="p-2 bg-surface-container font-bold whitespace-nowrap">
                                          {key}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-outline-variant/30">
                                    {msg.result.map((row, rIdx) => (
                                      <tr key={rIdx} className="hover:bg-surface-container">
                                        {Object.values(row).map((val: any, cIdx) => (
                                          <td key={cIdx} className="p-2 whitespace-nowrap text-on-surface font-semibold font-mono select-text">
                                            {typeof val === "object" ? JSON.stringify(val) : String(val)}
                                          </td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}

                          {/* Telemetry drawer & debug panel */}
                          <div className="space-y-2 pt-2 border-t border-outline-variant/20">
                            <div className="flex flex-wrap gap-3 text-[9px] font-bold tracking-wider uppercase text-on-surface-variant">
                              {msg.engine_used && (
                                <span className="px-1.5 py-0.5 bg-primary-fixed/50 text-secondary border border-vibrant-blue/20 rounded">
                                  Engine: {msg.engine_used}
                                </span>
                              )}
                              {msg.execution_time !== undefined && (
                                <span className="px-1.5 py-0.5 bg-surface-container border border-outline-variant/20 rounded">
                                  Latency: {msg.execution_time}s
                                </span>
                              )}
                              {msg.rows !== undefined && (
                                <span className="px-1.5 py-0.5 bg-surface-container border border-outline-variant/20 rounded">
                                  Rows: {msg.rows}
                                </span>
                              )}
                              {msg.prompt_size !== undefined && (
                                <span className="px-1.5 py-0.5 bg-surface-container border border-outline-variant/20 rounded">
                                  Tokens: {msg.prompt_size}
                                </span>
                              )}
                              {msg.debug_info?.cache_hit && (
                                <span className="px-1.5 py-0.5 bg-success/15 text-success border border-success/20 rounded">
                                  Cache Hit
                                </span>
                              )}
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Bottom Floating Input Panel */}
          <div className="absolute bottom-0 left-0 w-full p-4 bg-gradient-to-t from-surface-container-lowest via-surface-container-lowest to-transparent shrink-0">
            {activeDataset && (
              <div className="mx-auto w-full max-w-3xl bg-surface border border-outline-variant/30 px-4 py-2 rounded-t-xl text-[10px] text-on-surface-variant flex items-center justify-between shadow-xs">
                <div className="flex items-center gap-1.5 font-bold">
                  <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse shrink-0"></span>
                  <span className="text-deep-navy capitalize truncate max-w-[150px]">{activeDataset.name}</span>
                  <span className="px-1.5 py-0.5 bg-primary-fixed/30 border border-vibrant-blue/20 rounded text-[9px] font-bold text-secondary uppercase font-mono">{activeDataset.source}</span>
                </div>
                <div className="flex gap-4 font-bold text-[9px]">
                  <span>Rows: {activeDataset.rows}</span>
                  <span>•</span>
                  <span>Cols: {activeDataset.columns}</span>
                  <span>•</span>
                  <span>Size: {(activeDataset.size_bytes / 1024).toFixed(1)} KB</span>
                </div>
              </div>
            )}
            
            <div className="max-w-3xl mx-auto bg-surface-white border border-outline-variant rounded-xl p-2 flex items-center gap-2 shadow-sm focus-within:border-vibrant-blue focus-within:ring-1 focus-within:ring-vibrant-blue transition-all">
              <button className="p-2 text-on-surface-variant hover:text-deep-navy transition-colors cursor-pointer">
                <span className="material-symbols-outlined text-[20px]" style={{ fontVariationSettings: "'wght' 300" }}>attach_file</span>
              </button>
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyPress}
                placeholder={loading ? "AI is processing (Ctrl+Enter)..." : "Ask AI to analyze data, generate queries, or chart trends..."}
                disabled={loading}
                rows={1}
                className="flex-1 bg-transparent border-none focus:ring-0 resize-none py-2 text-xs text-on-surface placeholder:text-outline max-h-24 focus:outline-none"
              />
              
              {loading ? (
                <button
                  onClick={handleCancel}
                  className="bg-error text-white px-4 py-2.5 rounded-lg flex items-center gap-1.5 font-bold text-xs hover:opacity-90 transition-all shrink-0 cursor-pointer"
                >
                  Cancel
                  <span className="material-symbols-outlined text-xs">close</span>
                </button>
              ) : (
                <button
                  onClick={() => handleSend(inputValue)}
                  disabled={!inputValue.trim()}
                  className="bg-deep-navy text-white px-4 py-2.5 rounded-lg flex items-center gap-1.5 font-bold text-xs hover:bg-primary transition-all disabled:opacity-50 disabled:cursor-not-allowed shrink-0 cursor-pointer shadow-xs"
                >
                  Ask AI
                  <span className="material-symbols-outlined text-xs">send</span>
                </button>
              )}
            </div>
          </div>
        </section>

        {/* Panel 3: Right Panel (Dataset Overview & Pins) */}
        <aside className="w-[300px] h-full flex flex-col border-l border-outline-variant/35 bg-surface-container-lowest flex-shrink-0 z-15">
          <div className="px-4 py-4 border-b border-outline-variant/35 flex items-center justify-between bg-surface shrink-0">
            <h3 className="font-bold text-deep-navy text-sm uppercase tracking-wider">Dataset Overview</h3>
            <span className="material-symbols-outlined text-outline text-[20px]">info</span>
          </div>

          <div className="p-4 flex flex-col gap-4 overflow-y-auto flex-grow">
            {activeDataset ? (
              <>
                <p className="font-bold text-xs text-secondary bg-surface-container border border-outline-variant/20 px-2 py-1.5 rounded w-fit font-mono max-w-full truncate">
                  {activeDataset.name}
                </p>

                {/* Metrics Grid */}
                <div className="grid grid-cols-2 gap-3 shrink-0">
                  <div className="bg-surface border border-outline-variant/30 rounded-lg p-3 shadow-xs">
                    <div className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider mb-1">Total Rows</div>
                    <div className="text-xl font-extrabold text-deep-navy font-mono leading-none">{activeDataset.rows > 100000 ? `${(activeDataset.rows / 1000000).toFixed(1)}M` : activeDataset.rows.toLocaleString()}</div>
                  </div>
                  <div className="bg-surface border border-outline-variant/30 rounded-lg p-3 shadow-xs">
                    <div className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider mb-1">Columns</div>
                    <div className="text-xl font-extrabold text-deep-navy font-mono leading-none">{activeDataset.columns}</div>
                  </div>
                  <div className="bg-surface border border-outline-variant/30 rounded-lg p-3 shadow-xs col-span-2 flex justify-between items-center">
                    <div>
                      <div className="text-[10px] font-bold text-on-surface-variant uppercase tracking-wider mb-1">Missing Data</div>
                      <div className="text-base font-extrabold text-vibrant-blue font-mono leading-none">0.2%</div>
                    </div>
                    <div className="w-10 h-10 rounded-full border-4 border-outline-variant/20 border-t-vibrant-blue animate-spin-slow"></div>
                  </div>
                </div>

                {/* Pinned Queries List */}
                {pinnedQueries.length > 0 && (
                  <div className="mt-4 shrink-0">
                    <h4 className="text-[10px] font-bold text-deep-navy uppercase tracking-wider mb-2 flex items-center gap-1">
                      <span className="material-symbols-outlined text-xs">keep</span>
                      Pinned Queries
                    </h4>
                    <div className="flex flex-col gap-1.5 max-h-[140px] overflow-y-auto pr-1">
                      {pinnedQueries.map((q, qIdx) => (
                        <div
                          key={qIdx}
                          onClick={() => handleSend(q)}
                          className="group flex justify-between items-center text-[10px] font-bold bg-surface hover:bg-primary-fixed/30 border border-outline-variant/30 hover:border-vibrant-blue px-2 py-1.5 rounded cursor-pointer transition-all text-on-surface-variant hover:text-deep-navy"
                        >
                          <span className="truncate pr-2">{q}</span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              togglePinQuery(q);
                            }}
                            className="opacity-0 group-hover:opacity-100 hover:text-error transition-all cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-[10px]">close</span>
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Quick Insights List */}
                <div className="mt-4">
                  <h4 className="text-[10px] font-bold text-deep-navy uppercase tracking-wider mb-2.5">Quick Insights</h4>
                  <div className="flex flex-col gap-2">
                    <div className="bg-primary-fixed/40 p-3 rounded-lg border border-vibrant-blue/20 cursor-pointer hover:shadow-xs transition-shadow">
                      <div className="flex items-start gap-2">
                        <span className="material-symbols-outlined text-vibrant-blue text-[18px] mt-0.5">trending_up</span>
                        <div>
                          <h5 className="text-[10px] font-bold text-deep-navy mb-0.5">Peak Activity</h5>
                          <p className="text-[11px] font-semibold text-on-primary-fixed-variant leading-tight">Query cache hit-rate averages 84% on recurring queries.</p>
                        </div>
                      </div>
                    </div>
                    <div className="bg-surface border border-outline-variant/30 p-3 rounded-lg cursor-pointer hover:shadow-xs transition-shadow">
                      <div className="flex items-start gap-2">
                        <span className="material-symbols-outlined text-vibrant-blue text-[18px] mt-0.5">analytics</span>
                        <div>
                          <h5 className="text-[10px] font-bold text-deep-navy mb-0.5">Schema Inspection</h5>
                          <p className="text-[11px] font-semibold text-on-surface-variant leading-tight">All column types compiled. No high-cardinality anomalies.</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="text-center py-12 text-on-surface-variant font-semibold flex flex-col items-center">
                <span className="material-symbols-outlined text-3xl text-outline mb-2">database_off</span>
                <p className="text-xs">No active dataset selected.</p>
              </div>
            )}
          </div>
        </aside>

      </div>
    </DashboardLayout>
  );
}
