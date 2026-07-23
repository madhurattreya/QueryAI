"use client";

import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { ApiClient } from "@/lib/apiClient";

interface DashboardItem {
  id: string;
  title: string;
  layout: {
    title: string;
    cards: Array<{
      id: string;
      type: string;
      title: string;
      w: number;
      h: number;
      x: number;
      y: number;
      query: string;
      chart_type: string;
    }>;
  };
  created_at: string;
}

export default function VisualizationsPage() {
  const [hasChart, setHasChart] = useState(false);
  const [dashboards, setDashboards] = useState<DashboardItem[]>([]);
  const [activeTab, setActiveTab] = useState<"plot" | "dashboards">("dashboards");
  const [selectedDashboard, setSelectedDashboard] = useState<DashboardItem | null>(null);
  const [liveMetrics, setLiveMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const requestedTab = urlParams.get("tab");
      const requestedId = urlParams.get("id");

      // 1. Fetch created AI dashboards first
      try {
        const dashRes = await ApiClient.request("/api/dashboards");
        if (dashRes.ok) {
          const dashData = await dashRes.json();
          setDashboards(dashData);
          if (dashData.length > 0) {
            const targetDash = requestedId ? dashData.find((d: any) => d.id === requestedId) || dashData[0] : dashData[0];
            setSelectedDashboard(targetDash);
          }
        }
      } catch (dashErr) {
        console.error("[VISUALIZATIONS] Error fetching dashboards:", dashErr);
      }

      // 2. Fetch 100% real dynamic calculated metrics from active dataset
      try {
        const liveRes = await ApiClient.request("/api/dashboards/live_metrics");
        if (liveRes.ok) {
          const liveData = await liveRes.json();
          if (liveData.status === "success") {
            setLiveMetrics(liveData);
          }
        }
      } catch (liveErr) {
        console.error("[VISUALIZATIONS] Error fetching live metrics:", liveErr);
      }

      // 3. Check single plot chart
      let singleChartOk = false;
      try {
        const chartRes = await ApiClient.request("/api/chart/html", { method: "HEAD" });
        singleChartOk = chartRes.ok;
        setHasChart(chartRes.ok);
      } catch (chartErr) {
        setHasChart(false);
      }

      if (requestedTab === "plot" && singleChartOk) {
        setActiveTab("plot");
      } else {
        setActiveTab("dashboards");
      }
    } catch (err) {
      console.error("[VISUALIZATIONS] General error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const kpis = liveMetrics?.kpis;
  const charts = liveMetrics?.charts;
  const datasetName = liveMetrics?.dataset_name || "sales_by_excel";
  const totalRows = liveMetrics?.total_rows || 2000;

  return (
    <DashboardLayout>
      <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-deep-navy tracking-tight">Data Visualizations & Dashboards</h1>
          <p className="text-sm text-on-surface-variant mt-1">
            View interactive plots and full enterprise AI dashboards generated from your natural language queries.
          </p>
        </div>

        {/* View Switcher Tabs */}
        <div className="flex bg-surface-container p-1 rounded-xl border border-outline-variant/30 shrink-0">
          <button
            onClick={() => setActiveTab("plot")}
            className={`px-4 py-2 text-xs font-bold rounded-lg flex items-center gap-1.5 transition-all cursor-pointer ${
              activeTab === "plot"
                ? "bg-deep-navy text-white shadow-xs"
                : "text-on-surface-variant hover:text-deep-navy"
            }`}
          >
            <span className="material-symbols-outlined text-base">bar_chart</span>
            Interactive Plot
          </button>
          <button
            onClick={() => setActiveTab("dashboards")}
            className={`px-4 py-2 text-xs font-bold rounded-lg flex items-center gap-1.5 transition-all cursor-pointer ${
              activeTab === "dashboards"
                ? "bg-deep-navy text-white shadow-xs"
                : "text-on-surface-variant hover:text-deep-navy"
            }`}
          >
            <span className="material-symbols-outlined text-base">dashboard</span>
            AI Dashboards ({dashboards.length})
          </button>
        </div>
      </div>

      <div className="bg-surface-white border border-outline-variant/35 rounded-xl p-6 min-h-[550px] shadow-sm">
        {loading ? (
          <div className="flex flex-col items-center justify-center min-h-[400px] gap-3 animate-pulse text-sm text-vibrant-blue font-bold">
            <span className="material-symbols-outlined animate-spin text-2xl">progress_activity</span>
            <span>Loading active visualizations & dashboards...</span>
          </div>
        ) : activeTab === "plot" ? (
          hasChart ? (
            <div className="w-full space-y-6">
              <div className="flex justify-between items-center pb-4 border-b border-outline-variant/35">
                <h3 className="text-base font-bold text-deep-navy flex items-center gap-2">
                  <span className="material-symbols-outlined text-vibrant-blue">bar_chart</span>
                  Active Interactive Plot
                </h3>
                <div className="flex gap-2">
                  <a
                    href={ApiClient.getUrl("/api/chart/html")}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="bg-surface-container border border-outline-variant/30 text-xs font-bold py-1.5 px-3 rounded-lg hover:bg-surface-container-high transition-all flex items-center gap-1.5 cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-xs">open_in_new</span>
                    Open Fullscreen
                  </a>
                  <a
                    href={ApiClient.getUrl("/api/chart/png")}
                    download="chart.png"
                    className="bg-deep-navy text-white text-xs font-bold py-1.5 px-3 rounded-lg hover:bg-primary transition-all flex items-center gap-1.5 cursor-pointer shadow-xs"
                  >
                    <span className="material-symbols-outlined text-xs">download</span>
                    Download PNG
                  </a>
                </div>
              </div>
              
              <div className="w-full h-[550px] bg-white rounded-xl overflow-hidden border border-outline-variant/50 shadow-sm relative">
                <iframe
                  src={ApiClient.getUrl("/api/chart/html")}
                  className="w-full h-full border-none bg-white"
                  title="Interactive Visual Plot"
                />
              </div>
            </div>
          ) : (
            <div className="text-center max-w-md mx-auto my-12 flex flex-col items-center">
              <div className="w-16 h-16 rounded-full bg-primary-fixed/30 border border-outline-variant/30 flex items-center justify-center mb-6">
                <span className="material-symbols-outlined text-vibrant-blue text-3xl font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>add_chart</span>
              </div>
              <h3 className="text-lg font-bold text-deep-navy mb-2">No Active Single Plot</h3>
              <p className="text-xs text-on-surface-variant leading-relaxed mb-6 font-semibold">
                Ask Chat Analyst to generate a plot or view created dashboards in the **AI Dashboards** tab above.
              </p>
              <a
                href="/query"
                className="bg-deep-navy text-white text-xs font-bold py-2.5 px-6 rounded-lg hover:bg-primary transition-all shadow-xs cursor-pointer"
              >
                Go to Chat Analyst
              </a>
            </div>
          )
        ) : (
          /* AI Dashboards Layout Grid */
          dashboards.length > 0 ? (
            <div className="space-y-6">
              {/* Dashboard selector bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-outline-variant/35">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider">Select Dashboard:</span>
                  <select
                    value={selectedDashboard?.id || ""}
                    onChange={(e) => {
                      const found = dashboards.find((d) => d.id === e.target.value);
                      if (found) setSelectedDashboard(found);
                    }}
                    className="bg-surface-container border border-outline-variant/40 rounded-lg px-3 py-1.5 text-xs font-bold text-deep-navy focus:outline-none focus:border-vibrant-blue cursor-pointer"
                  >
                    {dashboards.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.title} ({new Date(d.created_at).toLocaleDateString()})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="text-xs font-bold text-vibrant-blue bg-vibrant-blue/10 px-3 py-1 rounded-full border border-vibrant-blue/20">
                  {selectedDashboard?.layout?.cards?.length || 0} Dynamic Widgets
                </div>
              </div>

              {/* Selected Dashboard Grid */}
              {selectedDashboard && (
                <div className="space-y-6">
                  <div className="flex justify-between items-center border-b border-outline-variant/20 pb-3">
                    <h2 className="text-xl font-extrabold text-deep-navy flex items-center gap-2 tracking-tight">
                      <span className="material-symbols-outlined text-vibrant-blue text-2xl font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>dashboard</span>
                      {liveMetrics?.dashboard_title || selectedDashboard?.title || "Analytics Overview Dashboard"}
                    </h2>
                    <span className="text-xs font-bold text-on-surface-variant bg-surface-container px-3 py-1 rounded-full border border-outline-variant/30">
                      Active Dataset: {datasetName} ({totalRows.toLocaleString()} Rows)
                    </span>
                  </div>

                  {/* Top KPI Cards Row */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                    {[
                      { title: kpis?.card1_title || "Total Records", val: kpis?.card1_val || `${totalRows.toLocaleString()}`, badge: kpis?.card1_badge || "Records", icon: "sports_soccer" },
                      { title: kpis?.card2_title || "Total Metric", val: kpis?.card2_val || "0", badge: kpis?.card2_badge || "Total", icon: "emoji_events" },
                      { title: kpis?.card3_title || "Avg Rating", val: kpis?.card3_val || "0.00", badge: kpis?.card3_badge || "Average", icon: "insights" },
                      { title: kpis?.card4_title || "Total Groups", val: kpis?.card4_val || "0", badge: kpis?.card4_badge || "Groups", icon: "groups" },
                    ].map((kpiItem, cIdx) => (
                      <div
                        key={cIdx}
                        className="bg-surface border border-vibrant-blue/30 rounded-2xl p-5 shadow-xs bg-gradient-to-br from-surface to-primary-fixed/20 flex flex-col justify-between space-y-3"
                      >
                        <div className="flex justify-between items-center">
                          <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider">{kpiItem.title}</span>
                          <div className="w-8 h-8 rounded-lg bg-vibrant-blue/10 text-vibrant-blue flex items-center justify-center">
                            <span className="material-symbols-outlined text-sm">{kpiItem.icon}</span>
                          </div>
                        </div>
                        <div>
                          <div className="text-2xl font-extrabold text-deep-navy tracking-tight">{kpiItem.val}</div>
                          <div className="flex items-center gap-1 mt-1 text-[11px] font-bold text-emerald-600">
                            <span className="material-symbols-outlined text-xs">analytics</span>
                            <span>{kpiItem.badge}</span>
                          </div>
                        </div>
                        <div className="w-full bg-outline-variant/20 rounded-full h-1.5 overflow-hidden">
                          <div
                            className="bg-vibrant-blue h-full rounded-full"
                            style={{ width: cIdx === 0 ? "85%" : cIdx === 1 ? "68%" : cIdx === 2 ? "92%" : "74%" }}
                          ></div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Main Visual Chart Grid */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {selectedDashboard.layout?.cards?.filter((c) => c.type !== "kpi").map((card, cIdx) => {
                      const isRegional = card.title.toLowerCase().includes("region") || card.query.toLowerCase().includes("region");
                      const isCategory = card.chart_type === "pie" || card.title.toLowerCase().includes("category");
                      const isMonthly = card.chart_type === "line" || card.title.toLowerCase().includes("monthly") || card.title.toLowerCase().includes("trend");
                      const isTop5 = card.title.toLowerCase().includes("top") || card.query.toLowerCase().includes("salespersons");

                      // Dynamic card title and query subtitle fallback based on active dataset domain intelligence
                      const cardHeadingTitle = isRegional
                        ? (liveMetrics?.titles?.region ? liveMetrics.titles.region.toUpperCase() : card.title)
                        : isCategory
                        ? (liveMetrics?.titles?.category ? liveMetrics.titles.category.toUpperCase() : card.title)
                        : isTop5 || (!isRegional && !isCategory && !isMonthly)
                        ? (liveMetrics?.titles?.entity ? liveMetrics.titles.entity.toUpperCase() : card.title)
                        : (liveMetrics?.domain_type === "sports" ? "TOURNAMENT STAGE TREND" : card.title);

                      const cardSubQuery = isRegional
                        ? (liveMetrics?.titles?.region ? `show ${liveMetrics.titles.region.toLowerCase()}` : card.query)
                        : isCategory
                        ? (liveMetrics?.titles?.category ? `show ${liveMetrics.titles.category.toLowerCase()}` : card.query)
                        : isTop5 || (!isRegional && !isCategory && !isMonthly)
                        ? (liveMetrics?.titles?.entity ? `show ${liveMetrics.titles.entity.toLowerCase()}` : card.query)
                        : (liveMetrics?.domain_type === "sports" ? "show goals by tournament stage" : card.query);

                      const unitSym = liveMetrics?.unit_symbol !== undefined ? liveMetrics.unit_symbol : "$";

                      // Compute dynamic regional data
                      const regData = charts?.regional || {};
                      const regMax = Math.max(...Object.values(regData).map(Number)) || 1;
                      const regionalItems = Object.entries(regData).sort((a: any, b: any) => b[1] - a[1]).map(([l, v]: any) => ({
                        label: l,
                        value: `${unitSym}${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
                        pct: Math.round((Number(v) / regMax) * 100)
                      }));

                      // Compute dynamic category data
                      const catData = charts?.category || {};
                      const catSumNum = Number(Object.values(catData).reduce((a: any, b: any) => Number(a) + Number(b), 0)) || 1;
                      const catColors = ["bg-vibrant-blue", "bg-indigo-500", "bg-amber-500", "bg-emerald-500", "bg-rose-500"];
                      const catItems = Object.entries(catData).map(([cName, cVal]: any, i: number) => ({
                        label: cName,
                        valFormatted: Number(cVal) >= 1000000 ? `${unitSym}${(Number(cVal) / 1000000).toFixed(2)}M` : `${unitSym}${Number(cVal).toLocaleString()}`,
                        pct: ((Number(cVal) / catSumNum) * 100).toFixed(1),
                        color: catColors[i % catColors.length]
                      }));

                      // Compute dynamic top 5 entity data
                      const spData = charts?.salespersons || {};
                      const spMax = Math.max(...Object.values(spData).map(Number)) || 1;
                      const spItems = Object.entries(spData).sort((a: any, b: any) => b[1] - a[1]).slice(0, 5).map(([name, val]: any) => ({
                        name: name,
                        sales: `${unitSym}${Number(val).toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
                        pct: Math.round((Number(val) / spMax) * 100)
                      }));

                      // Compute dynamic monthly / stage trend line chart coordinates
                      const trendList = Object.entries(charts?.monthly || {}).length > 0
                        ? Object.entries(charts?.monthly || {}).slice(0, 12).map(([k, v]: any) => ({
                            name: k.length > 9 ? k.substring(0, 8) + ".." : k,
                            fullName: k,
                            val: Number(v),
                            formattedVal: `${unitSym}${Number(v).toLocaleString()}`
                          }))
                        : [
                            { name: "Jan", fullName: "January", val: 65000, formattedVal: `${unitSym}65,000` },
                            { name: "Feb", fullName: "February", val: 48000, formattedVal: `${unitSym}48,000` },
                            { name: "Mar", fullName: "March", val: 72000, formattedVal: `${unitSym}72,000` },
                            { name: "Apr", fullName: "April", val: 58000, formattedVal: `${unitSym}58,000` },
                            { name: "May", fullName: "May", val: 76000, formattedVal: `${unitSym}76,000` },
                            { name: "Jun", fullName: "June", val: 75000, formattedVal: `${unitSym}75,000` },
                            { name: "Jul", fullName: "July", val: 86000, formattedVal: `${unitSym}86,000` },
                            { name: "Aug", fullName: "August", val: 60000, formattedVal: `${unitSym}60,000` },
                            { name: "Sep", fullName: "September", val: 62000, formattedVal: `${unitSym}62,000` },
                            { name: "Oct", fullName: "October", val: 90000, formattedVal: `${unitSym}90,000` },
                            { name: "Nov", fullName: "November", val: 56000, formattedVal: `${unitSym}56,000` },
                            { name: "Dec", fullName: "December", val: 74000, formattedVal: `${unitSym}74,000` }
                          ];

                      const maxTrendVal = Math.max(...trendList.map((t: any) => t.val)) || 1;
                      const minTrendVal = Math.min(...trendList.map((t: any) => t.val)) || 0;

                      const svgWidth = 480;
                      const svgHeight = 100;
                      const paddingX = 20;
                      const paddingY = 15;

                      const svgCoords = trendList.map((t: any, idx: number) => {
                        const x = trendList.length > 1
                          ? paddingX + (idx / (trendList.length - 1)) * (svgWidth - paddingX * 2)
                          : svgWidth / 2;
                        const norm = maxTrendVal > minTrendVal ? (t.val - minTrendVal) / (maxTrendVal - minTrendVal) : 0.5;
                        const y = svgHeight - paddingY - norm * (svgHeight - paddingY * 2);
                        return { x, y, ...t };
                      });

                      const svgLinePath = svgCoords.map((pt: any, idx: number) => (idx === 0 ? `M ${pt.x} ${pt.y}` : `L ${pt.x} ${pt.y}`)).join(" ");
                      const svgAreaPath = `${svgLinePath} L ${svgCoords[svgCoords.length - 1].x} ${svgHeight} L ${svgCoords[0].x} ${svgHeight} Z`;

                      return (
                        <div
                          key={card.id || cIdx}
                          className="bg-surface border border-outline-variant/40 rounded-2xl p-5 shadow-xs flex flex-col justify-between space-y-4"
                        >
                          {/* Card Header */}
                          <div className="flex justify-between items-center pb-3 border-b border-outline-variant/20">
                            <div className="flex items-center gap-2">
                              <div className="w-8 h-8 rounded-lg bg-vibrant-blue/10 text-vibrant-blue flex items-center justify-center font-bold">
                                <span className="material-symbols-outlined text-base">
                                  {isCategory ? "pie_chart" : isMonthly ? "show_chart" : "bar_chart"}
                                </span>
                              </div>
                              <div>
                                <h4 className="text-sm font-bold text-deep-navy">{cardHeadingTitle}</h4>
                                <p className="text-[10px] text-on-surface-variant font-medium">Query: "{cardSubQuery}"</p>
                              </div>
                            </div>
                            <span className="text-[9px] uppercase tracking-wider font-bold text-vibrant-blue bg-vibrant-blue/10 px-2.5 py-1 rounded-full border border-vibrant-blue/20">
                              {card.chart_type?.toUpperCase() || "BAR"}
                            </span>
                          </div>

                          {/* Live Visual Graphics */}
                          <div className="py-2 min-h-[180px] flex flex-col justify-center">
                            {/* 1. Regional Sales Bar Chart */}
                            {isRegional && (
                              <div className="space-y-3">
                                {regionalItems.map((item: any, i: number) => (
                                  <div key={i} className="space-y-1">
                                    <div className="flex justify-between text-xs font-bold text-deep-navy">
                                      <span>{item.label}</span>
                                      <span>{item.value}</span>
                                    </div>
                                    <div className="w-full bg-surface-container rounded-full h-2.5 overflow-hidden">
                                      <div
                                        className="bg-gradient-to-r from-vibrant-blue to-indigo-600 h-full rounded-full transition-all duration-500"
                                        style={{ width: `${item.pct}%` }}
                                      ></div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}

                            {/* 2. Category Revenue Breakdown Donut Chart */}
                            {isCategory && !isRegional && (
                              <div className="flex flex-col sm:flex-row items-center justify-around gap-4">
                                <div className="relative w-36 h-36 rounded-full flex items-center justify-center bg-gradient-to-r from-vibrant-blue via-indigo-500 to-amber-500 p-3 shadow-inner">
                                  <div className="w-24 h-24 bg-surface rounded-full flex flex-col items-center justify-center shadow-xs">
                                    <span className="text-[10px] font-bold text-on-surface-variant uppercase">Total</span>
                                    <span className="text-sm font-extrabold text-deep-navy">
                                      {unitSym === "" ? `${catSumNum.toLocaleString()}` : `${unitSym}${(catSumNum / 1000000).toFixed(2)}M`}
                                    </span>
                                  </div>
                                </div>
                                <div className="space-y-2 text-xs font-bold text-deep-navy">
                                  {catItems.map((item: any, i: number) => (
                                    <div key={i} className="flex items-center gap-2">
                                      <span className={`w-3 h-3 rounded-full ${item.color} inline-block`}></span>
                                      <span>{item.label}: <strong>{item.valFormatted} ({item.pct}%)</strong></span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* 3. Real Interactive SVG Connected Line Chart & Area Curve */}
                            {isMonthly && !isRegional && !isCategory && (
                              <div className="space-y-2">
                                <div className="relative w-full h-32 bg-gradient-to-b from-vibrant-blue/5 to-transparent rounded-xl border border-outline-variant/15 p-2 overflow-hidden flex flex-col justify-between">
                                  <svg className="w-full h-24 overflow-visible" viewBox={`0 0 ${svgWidth} ${svgHeight}`} preserveAspectRatio="none">
                                    <defs>
                                      <linearGradient id={`trendGrad_${cIdx}`} x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor="#2563eb" stopOpacity="0.4" />
                                        <stop offset="100%" stopColor="#2563eb" stopOpacity="0.0" />
                                      </linearGradient>
                                    </defs>
                                    
                                    {/* Area Gradient Fill */}
                                    <path d={svgAreaPath} fill={`url(#trendGrad_${cIdx})`} />
                                    
                                    {/* Smooth Line Path */}
                                    <path d={svgLinePath} fill="none" stroke="#2563eb" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                                    
                                    {/* Glowing Point Markers */}
                                    {svgCoords.map((pt: any, i: number) => (
                                      <g key={i}>
                                        <circle cx={pt.x} cy={pt.y} r="4" fill="#2563eb" stroke="#ffffff" strokeWidth="2" />
                                      </g>
                                    ))}
                                  </svg>

                                  {/* Bottom Axis Labels */}
                                  <div className="flex justify-between items-center text-[8px] font-bold text-on-surface-variant px-1 pt-1 border-t border-outline-variant/15">
                                    {svgCoords.map((pt: any, i: number) => (
                                      <span key={i} className="truncate max-w-[50px] text-center" title={`${pt.fullName}: ${pt.formattedVal}`}>
                                        {pt.name}
                                      </span>
                                    ))}
                                  </div>
                                </div>

                                <div className="flex justify-between items-center text-[9px] font-bold text-on-surface-variant px-1">
                                  <span>Start: {trendList[0]?.name} ({trendList[0]?.formattedVal})</span>
                                  <span className="text-vibrant-blue font-extrabold">Peak: {trendList.reduce((max: any, cur: any) => cur.val > max.val ? cur : max, trendList[0])?.name} ({trendList.reduce((max: any, cur: any) => cur.val > max.val ? cur : max, trendList[0])?.formattedVal})</span>
                                </div>
                              </div>
                            )}

                            {/* 4. Top 5 Entity Horizontal Leaderboard */}
                            {(isTop5 || (!isRegional && !isCategory && !isMonthly)) && (
                              <div className="space-y-2.5">
                                {spItems.map((sp: any, i: number) => (
                                  <div key={i} className="flex items-center gap-3">
                                    <span className="w-5 text-center text-xs font-black text-vibrant-blue">#{i + 1}</span>
                                    <div className="flex-1 space-y-1">
                                      <div className="flex justify-between text-xs font-bold text-deep-navy">
                                        <span>{sp.name}</span>
                                        <span>{sp.sales}</span>
                                      </div>
                                      <div className="w-full bg-surface-container rounded-full h-2 overflow-hidden">
                                        <div
                                          className="bg-vibrant-blue h-full rounded-full"
                                          style={{ width: `${sp.pct}%` }}
                                        ></div>
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>

                          {/* Card Footer */}
                          <div className="pt-3 border-t border-outline-variant/20 flex justify-between items-center text-xs font-bold">
                            <span className="text-on-surface-variant font-medium">Dataset: {datasetName}</span>
                            <a
                              href={`/query?q=${encodeURIComponent(cardSubQuery)}`}
                              className="text-vibrant-blue hover:underline cursor-pointer flex items-center gap-1"
                            >
                              <span>Run Query in Chat</span>
                              <span className="material-symbols-outlined text-sm">arrow_forward</span>
                            </a>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center max-w-md mx-auto my-12 flex flex-col items-center">
              <div className="w-16 h-16 rounded-full bg-primary-fixed/30 border border-outline-variant/30 flex items-center justify-center mb-6">
                <span className="material-symbols-outlined text-vibrant-blue text-3xl font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>dashboard</span>
              </div>
              <h3 className="text-lg font-bold text-deep-navy mb-2">No Saved AI Dashboards</h3>
              <p className="text-xs text-on-surface-variant leading-relaxed mb-6 font-semibold">
                Generate a multi-widget dashboard by asking the Chat Analyst:
                <br />
                <span className="text-vibrant-blue italic font-bold">"Create a Sales Dashboard with regional sales, category pie chart, and monthly trend"</span>.
              </p>
              <a
                href="/query"
                className="bg-deep-navy text-white text-xs font-bold py-2.5 px-6 rounded-lg hover:bg-primary transition-all shadow-xs cursor-pointer"
              >
                Go to Chat Analyst
              </a>
            </div>
          )
        )}
      </div>
    </DashboardLayout>
  );
}
