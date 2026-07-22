"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import DashboardLayout from "@/components/DashboardLayout";
import { ApiClient } from "@/lib/apiClient";

export default function WelcomePage() {
  const [history, setHistory] = useState<any[]>([]);
  const [status, setStatus] = useState<any>({});

  useEffect(() => {
    const fetchData = async () => {
      try {
        const histRes = await ApiClient.request("/api/conversations");
        if (histRes.ok) {
          const histData = await histRes.json();
          setHistory(histData.slice(-3).reverse()); // Show last 3
        }
        
        const statRes = await ApiClient.request("/api/status");
        if (statRes.ok) {
          const statData = await statRes.json();
          setStatus(statData);
        }
      } catch (err) {
        console.error("Error loading welcome data", err);
      }
    };
    fetchData();
  }, []);

  return (
    <DashboardLayout fullScreen={false}>
      {/* Scrollable Content Canvas */}
      <div className="flex-grow overflow-y-auto pb-12">
        {/* Hero Section */}
        <section className="mb-12 relative w-full h-[400px] rounded-xl overflow-hidden bg-tertiary border border-outline-variant flex items-center shadow-xs">
          {/* Abstract design elements */}
          <div className="absolute right-0 top-0 h-full w-1/2 opacity-20 pointer-events-none z-0 flex items-center justify-center">
            <span className="material-symbols-outlined text-[300px] text-vibrant-blue">psychology</span>
          </div>

          <div className="relative z-10 px-12 max-w-2xl">
            <div className="inline-flex items-center gap-2 bg-secondary-container/10 border border-secondary-container/30 px-3 py-1 rounded-full mb-6">
              <span className="material-symbols-outlined text-secondary-container text-sm font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>
                auto_awesome
              </span>
              <span className="font-label-caps text-label-caps text-secondary-container uppercase">Intelligence Engine Active</span>
            </div>
            <h2 className="font-display-lg text-display-lg text-white mb-4 tracking-tight leading-tight">
              QueryIQ - Enterprise AI Data Analyst
            </h2>
            <p className="font-body-lg text-body-lg text-on-tertiary-container mb-8 leading-relaxed max-w-xl">
              Unify your data silos and execute complex multi-layer analysis using natural language. QueryIQ transforms raw clusters into executive-level insights in milliseconds.
            </p>
            <div className="flex items-center gap-4">
              <Link href="/query">
                <button className="bg-secondary-container text-primary px-8 py-3 rounded-lg font-headline-sm hover:bg-secondary-fixed-dim transition-all cursor-pointer">
                  Start Exploring
                </button>
              </Link>
              <Link href="/connect">
                <button className="border border-outline-variant text-white px-8 py-3 rounded-lg font-headline-sm hover:bg-white/5 transition-all cursor-pointer">
                  Connect Data
                </button>
              </Link>
            </div>
          </div>

          {/* Code Editor Preview inside Hero */}
          <div className="absolute right-12 bottom-12 w-[480px] h-[320px] rounded-lg border border-outline-variant/30 bg-surface/5 backdrop-blur-md p-6 overflow-hidden hidden xl:block z-10">
            <div className="flex items-center justify-between mb-4 border-b border-outline-variant/20 pb-2">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 bg-error rounded-full"></div>
                <div className="w-3 h-3 bg-secondary-fixed rounded-full"></div>
                <div className="w-3 h-3 bg-secondary-container rounded-full"></div>
              </div>
              <span className="font-code-block text-code-block text-on-tertiary-container">ai_engine_v3.sql</span>
            </div>
            <div className="font-code-block text-code-block text-secondary-container/80 space-y-2 leading-relaxed">
              <p><span className="text-on-tertiary-container">SELECT</span> region, <span className="text-on-tertiary-container">SUM</span>(revenue) <span className="text-on-tertiary-container">AS</span> total_sales</p>
              <p><span className="text-on-tertiary-container">FROM</span> global_sales_data_2024</p>
              <p><span className="text-on-tertiary-container">WHERE</span> status = <span className="text-secondary-fixed">'completed'</span></p>
              <p><span className="text-on-tertiary-container">GROUP BY</span> region</p>
              <p><span className="text-on-tertiary-container">ORDER BY</span> total_sales <span className="text-on-tertiary-container">DESC</span>;</p>
              <div className="pt-4 mt-4 border-t border-outline-variant/20">
                <p className="text-on-tertiary-container italic opacity-60">-- Analyzing 1.2M rows...</p>
                <p className="text-secondary-container flex items-center gap-2 mt-2">
                  <span className="material-symbols-outlined text-sm ai-pulse">check_circle</span>
                  Success: Optimization detected for North America.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Quick Action Cards */}
        <section className="mb-12">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Link href="/connect" className="bg-surface-primary border border-border-subtle p-6 rounded-xl hover:shadow-lg transition-all group cursor-pointer">
              <div className="w-12 h-12 rounded-lg bg-surface-container-high flex items-center justify-center mb-6 transition-colors group-hover:bg-primary-container">
                <span className="material-symbols-outlined text-primary group-hover:text-secondary-container text-2xl">upload_file</span>
              </div>
              <h3 className="font-headline-sm text-headline-sm mb-2 text-on-surface">Upload Datasets</h3>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-6 leading-relaxed">Drop CSV, Parquet, or JSON files to begin instant analysis.</p>
              <div className="flex items-center text-secondary font-label-caps text-label-caps gap-2 group-hover:text-vibrant-blue transition-colors">
                DRAG & DROP <span className="material-symbols-outlined text-sm">arrow_forward</span>
              </div>
            </Link>

            <Link href="/connect" className="bg-surface-primary border border-border-subtle p-6 rounded-xl hover:shadow-lg transition-all group cursor-pointer">
              <div className="w-12 h-12 rounded-lg bg-surface-container-high flex items-center justify-center mb-6 transition-colors group-hover:bg-primary-container">
                <span className="material-symbols-outlined text-primary group-hover:text-secondary-container text-2xl">database</span>
              </div>
              <h3 className="font-headline-sm text-headline-sm mb-2 text-on-surface">Connect SQL</h3>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-6 leading-relaxed">Connect Snowflake, PostgreSQL, or BigQuery directly.</p>
              <div className="flex items-center text-secondary font-label-caps text-label-caps gap-2 group-hover:text-vibrant-blue transition-colors">
                CONFIG SOURCE <span className="material-symbols-outlined text-sm">arrow_forward</span>
              </div>
            </Link>

            <Link href="/connect" className="bg-surface-primary border border-border-subtle p-6 rounded-xl hover:shadow-lg transition-all group cursor-pointer">
              <div className="w-12 h-12 rounded-lg bg-surface-container-high flex items-center justify-center mb-6 transition-colors group-hover:bg-primary-container">
                <span className="material-symbols-outlined text-primary group-hover:text-secondary-container text-2xl">folder_managed</span>
              </div>
              <h3 className="font-headline-sm text-headline-sm mb-2 text-on-surface">Import Folders</h3>
              <p className="font-body-sm text-body-sm text-on-surface-variant mb-6 leading-relaxed">Sync entire S3 buckets or local data repositories.</p>
              <div className="flex items-center text-secondary font-label-caps text-label-caps gap-2 group-hover:text-vibrant-blue transition-colors">
                SYNC DIRECTORY <span className="material-symbols-outlined text-sm">arrow_forward</span>
              </div>
            </Link>
          </div>
        </section>

        {/* Projects & Datasets Grid */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Recent Projects */}
          <div className="lg:col-span-8">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-headline-md text-headline-md text-on-surface">Recent Projects</h2>
              <Link href="/query">
                <button className="text-secondary font-label-caps text-label-caps hover:underline cursor-pointer">
                  VIEW ALL PROJECTS
                </button>
              </Link>
            </div>
            
            <div className="space-y-3">
              {history.length > 0 ? (
                history.map((item, idx) => {
                  // Select different illustrations for each history card
                  const images = [
                    "https://lh3.googleusercontent.com/aida-public/AB6AXuCBS6JDAgii5HfiGDBj9q0F0djbfAIlxp_8rrgEJwepqSHEBsJ1F7XL1jhlpbtjoneK7Q25oVw0VJNP05y69r33tU0AQ9eZkrv049y43HHfCEwUAGVo1LchbBw5ClPJmV9Eh5QX2ogL658nuK47HJcdw30Jbmis3symkYEI9ZyBx8V91_eX4GAj2bU0S5956kd8FrdkMG7KRU_hNdQDNTGcCKSLMpuUnTNWAStcyt-B7z7lAXmnj1rO",
                    "https://lh3.googleusercontent.com/aida-public/AB6AXuDX-EChUDa7YMHYJNNCU0HXYQUdPKjKGYgmtm9_Ebd78faDRKq1Cg-XM4tkvq7KVoxwgI_6kezyhvrIFUGuhVvAcWzQam7PWIPxqNUYUePSEF23DF88K2NCJnn6vnRA6P20WP_XX4BlLvkiTKtWxymLEhqdAoGy9t1OKDJnL5BCoTgPGCLygU0vBXNfLeEX0ewYq06_vuu2HaWuiZGeiF4F4spOBYHnzfy7Vpk6F_xrR7XfzkJngdD_",
                    "https://lh3.googleusercontent.com/aida-public/AB6AXuAo2egu9_l8Eqv_sjQ5lPTbcBAqXRBf_crby3Ht4eiHGTUia2zO6xGEyiFQL57rUit09x-RVTMz_KodhS9-Cn0a3GAkHulSspX8dO3tpHTSL2npHbPNItAYp61eZICozDMGnfveLn-WzABFCEcOc4bOe4PegjI8JtJX-VU18cwELP9a0jWYnTh2kE70h2LLzaraIPBs6atln9hFJ3e4dz0rxVp3tOKlia0JT5hAloh3-55cXRo5ZxGE"
                  ];
                  return (
                    <Link
                      key={idx}
                      href="/query"
                      className="bg-surface-primary border border-border-subtle p-4 rounded-lg flex items-center gap-6 hover:bg-surface-container-low transition-colors group cursor-pointer"
                    >
                      <div className="w-14 h-14 bg-surface-container rounded border border-outline-variant overflow-hidden flex-shrink-0">
                        <img
                          alt="Viz Thumbnail"
                          className="w-full h-full object-cover grayscale group-hover:grayscale-0 transition-all"
                          src={images[idx % images.length]}
                        />
                      </div>
                      <div className="flex-1">
                        <h4 className="font-headline-sm text-headline-sm mb-1 text-on-surface line-clamp-1">{item.Question}</h4>
                        <div className="flex items-center gap-4">
                          <span className="flex items-center gap-1 font-body-sm text-body-sm text-on-surface-variant">
                            <span className="material-symbols-outlined text-sm">schedule</span> {item.Timestamp}
                          </span>
                          <span className="flex items-center gap-1 font-body-sm text-body-sm text-on-surface-variant">
                            <span className="material-symbols-outlined text-sm">speed</span> {item["Time Taken (sec)"]}s latency
                          </span>
                        </div>
                      </div>
                      <div className="text-right flex flex-col items-end gap-2 flex-shrink-0">
                        <div className="bg-secondary-fixed/30 text-on-secondary-container px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">
                          {item["Rows Returned"]} rows
                        </div>
                        <span className="font-body-sm text-body-sm text-outline">v1.0.{idx}</span>
                      </div>
                    </Link>
                  );
                })
              ) : (
                <>
                  {/* Mock Projects when history is empty */}
                  <div className="bg-surface-primary border border-border-subtle p-4 rounded-lg flex items-center gap-6 hover:bg-surface-container-low transition-colors group cursor-pointer">
                    <div className="w-14 h-14 bg-surface-container rounded border border-outline-variant overflow-hidden flex-shrink-0">
                      <img
                        alt="Viz Thumbnail"
                        className="w-full h-full object-cover grayscale group-hover:grayscale-0 transition-all"
                        src="https://lh3.googleusercontent.com/aida-public/AB6AXuCBS6JDAgii5HfiGDBj9q0F0djbfAIlxp_8rrgEJwepqSHEBsJ1F7XL1jhlpbtjoneK7Q25oVw0VJNP05y69r33tU0AQ9eZkrv049y43HHfCEwUAGVo1LchbBw5ClPJmV9Eh5QX2ogL658nuK47HJcdw30Jbmis3symkYEI9ZyBx8V91_eX4GAj2bU0S5956kd8FrdkMG7KRU_hNdQDNTGcCKSLMpuUnTNWAStcyt-B7z7lAXmnj1rO"
                      />
                    </div>
                    <div className="flex-grow">
                      <h4 className="font-headline-sm text-headline-sm mb-1 text-on-surface">Q4 Revenue Optimization Analysis</h4>
                      <div className="flex items-center gap-4">
                        <span className="flex items-center gap-1 font-body-sm text-body-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-sm">schedule</span> 2h ago
                        </span>
                        <span className="flex items-center gap-1 font-body-sm text-body-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-sm">group</span> Shared with 12 others
                        </span>
                      </div>
                    </div>
                    <div className="text-right flex flex-col items-end gap-2 flex-shrink-0">
                      <div className="bg-secondary-fixed/30 text-on-secondary-container px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">
                        Analysis Active
                      </div>
                      <span className="font-body-sm text-body-sm text-outline">v2.4.1</span>
                    </div>
                  </div>

                  <div className="bg-surface-primary border border-border-subtle p-4 rounded-lg flex items-center gap-6 hover:bg-surface-container-low transition-colors group cursor-pointer">
                    <div className="w-14 h-14 bg-surface-container rounded border border-outline-variant overflow-hidden flex-shrink-0">
                      <img
                        alt="Viz Thumbnail"
                        className="w-full h-full object-cover grayscale group-hover:grayscale-0 transition-all"
                        src="https://lh3.googleusercontent.com/aida-public/AB6AXuDX-EChUDa7YMHYJNNCU0HXYQUdPKjKGYgmtm9_Ebd78faDRKq1Cg-XM4tkvq7KVoxwgI_6kezyhvrIFUGuhVvAcWzQam7PWIPxqNUYUePSEF23DF88K2NCJnn6vnRA6P20WP_XX4BlLvkiTKtWxymLEhqdAoGy9t1OKDJnL5BCoTgPGCLygU0vBXNfLeEX0ewYq06_vuu2HaWuiZGeiF4F4spOBYHnzfy7Vpk6F_xrR7XfzkJngdD_"
                      />
                    </div>
                    <div className="flex-grow">
                      <h4 className="font-headline-sm text-headline-sm mb-1 text-on-surface">User Retention - Mobile Cohort A</h4>
                      <div className="flex items-center gap-4">
                        <span className="flex items-center gap-1 font-body-sm text-body-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-sm">schedule</span> Yesterday
                        </span>
                        <span className="flex items-center gap-1 font-body-sm text-body-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-sm">person</span> Private
                        </span>
                      </div>
                    </div>
                    <div className="text-right flex flex-col items-end gap-2 flex-shrink-0">
                      <div className="bg-surface-container-highest text-on-surface-variant px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">
                        Draft
                      </div>
                      <span className="font-body-sm text-body-sm text-outline">v1.0.0</span>
                    </div>
                  </div>

                  <div className="bg-surface-primary border border-border-subtle p-4 rounded-lg flex items-center gap-6 hover:bg-surface-container-low transition-colors group group-hover:translate-y-[-2px] cursor-pointer">
                    <div className="w-14 h-14 bg-surface-container rounded border border-outline-variant overflow-hidden flex-shrink-0">
                      <img
                        alt="Viz Thumbnail"
                        className="w-full h-full object-cover grayscale group-hover:grayscale-0 transition-all"
                        src="https://lh3.googleusercontent.com/aida-public/AB6AXuAo2egu9_l8Eqv_sjQ5lPTbcBAqXRBf_crby3Ht4eiHGTUia2zO6xGEyiFQL57rUit09x-RVTMz_KodhS9-Cn0a3GAkHulSspX8dO3tpHTSL2npHbPNItAYp61eZICozDMGnfveLn-WzABFCEcOc4bOe4PegjI8JtJX-VU18cwELP9a0jWYnTh2kE70h2LLzaraIPBs6atln9hFJ3e4dz0rxVp3tOKlia0JT5hAloh3-55cXRo5ZxGE"
                      />
                    </div>
                    <div className="flex-grow">
                      <h4 className="font-headline-sm text-headline-sm mb-1 text-on-surface">Global Inventory Forecasting</h4>
                      <div className="flex items-center gap-4">
                        <span className="flex items-center gap-1 font-body-sm text-body-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-sm">schedule</span> 3 days ago
                        </span>
                        <span className="flex items-center gap-1 font-body-sm text-body-sm text-on-surface-variant">
                          <span className="material-symbols-outlined text-sm">cloud</span> AWS S3 Source
                        </span>
                      </div>
                    </div>
                    <div className="text-right flex flex-col items-end gap-2 flex-shrink-0">
                      <div className="bg-error/10 text-error px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider">
                        Review Required
                      </div>
                      <span className="font-body-sm text-body-sm text-outline">v4.0.0</span>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Favorite Datasets */}
          <div className="lg:col-span-4">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-headline-md text-headline-md text-on-surface">Favorite Datasets</h2>
              <button className="text-secondary font-label-caps text-label-caps hover:underline cursor-pointer">
                EDIT
              </button>
            </div>

            <div className="bg-surface-primary border border-border-subtle rounded-xl divide-y divide-border-subtle overflow-hidden shadow-xs">
              {status.loaded_files && status.loaded_files.length > 0 ? (
                status.loaded_files.map((file: string, idx: number) => (
                  <div key={idx} className="p-4 hover:bg-surface-container-low transition-colors group cursor-pointer flex items-center gap-4">
                    <span className="material-symbols-outlined text-secondary-container font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>star</span>
                    <div className="flex-1">
                      <h5 className="font-body-md font-bold text-primary">{file}</h5>
                      <p className="text-[10px] font-label-caps text-outline tracking-widest uppercase">ACTIVE FILE • DATASET SOURCE</p>
                    </div>
                    <Link href="/explorer">
                      <span className="material-symbols-outlined text-outline group-hover:text-primary transition-colors">open_in_new</span>
                    </Link>
                  </div>
                ))
              ) : (
                <>
                  <div className="p-4 hover:bg-surface-container-low transition-colors group cursor-pointer flex items-center gap-4">
                    <span className="material-symbols-outlined text-secondary-container font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>star</span>
                    <div className="flex-1">
                      <h5 className="font-body-md font-bold text-primary">Master_Customer_DB</h5>
                      <p className="text-[10px] font-label-caps text-outline tracking-widest uppercase">1.4 GB • 850K ROWS</p>
                    </div>
                    <span className="material-symbols-outlined text-outline group-hover:text-primary transition-colors">open_in_new</span>
                  </div>
                  <div className="p-4 hover:bg-surface-container-low transition-colors group cursor-pointer flex items-center gap-4">
                    <span className="material-symbols-outlined text-secondary-container font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>star</span>
                    <div className="flex-1">
                      <h5 className="font-body-md font-bold text-primary">Sales_Transactions_FY24</h5>
                      <p className="text-[10px] font-label-caps text-outline tracking-widest uppercase">540 MB • 2.1M ROWS</p>
                    </div>
                    <span className="material-symbols-outlined text-outline group-hover:text-primary transition-colors">open_in_new</span>
                  </div>
                  <div className="p-4 hover:bg-surface-container-low transition-colors group cursor-pointer flex items-center gap-4">
                    <span className="material-symbols-outlined text-secondary-container font-variation-settings-fill" style={{ fontVariationSettings: "'FILL' 1" }}>star</span>
                    <div className="flex-1">
                      <h5 className="font-body-md font-bold text-primary">Marketing_Attribution_Final</h5>
                      <p className="text-[10px] font-label-caps text-outline tracking-widest uppercase">88 MB • 12K ROWS</p>
                    </div>
                    <span className="material-symbols-outlined text-outline group-hover:text-primary transition-colors">open_in_new</span>
                  </div>
                </>
              )}
            </div>

            <div className="mt-6 p-6 rounded-xl bg-tertiary text-white relative overflow-hidden shadow-xs">
              <div className="absolute right-0 bottom-0 opacity-10 pointer-events-none translate-x-4 translate-y-4">
                <span className="material-symbols-outlined text-[100px] text-white">dataset</span>
              </div>
              <div className="relative z-10">
                <h4 className="font-headline-sm text-headline-sm mb-2 font-bold">Need a Custom View?</h4>
                <p className="font-body-sm text-body-sm text-on-tertiary-container mb-4 font-semibold">Our AI can generate a synthetic dataset for testing your models.</p>
                <Link href="/connect">
                  <button className="bg-secondary-container text-primary font-label-caps text-label-caps px-4 py-2.5 rounded font-bold hover:bg-secondary-fixed transition-all cursor-pointer">
                    GENERATE NOW
                  </button>
                </Link>
              </div>
            </div>
          </div>
        </section>
      </div>
    </DashboardLayout>
  );
}
