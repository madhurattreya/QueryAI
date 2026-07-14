"use client";

import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";

export default function ExplorerPage() {
  const [datasets, setDatasets] = useState<any[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<any>(null);
  const [previewRows, setPreviewRows] = useState<any[]>([]);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [columns, setColumns] = useState<any[]>([]);


  const fetchDatasets = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/datasets");
      if (res.ok) {
        const data = await res.json();
        setDatasets(data);
        if (data.length > 0 && !selectedDataset) {
          setSelectedDataset(data[0]);
        }
      }
    } catch (err) {
      console.error(err);
      setErrorMsg("Failed to load datasets. Is the backend server running?");
    }
  };

  const fetchPreview = async (datasetName: string) => {
    setLoadingPreview(true);
    try {
      const question = `Show first 10 rows of dataset ${datasetName}`;
      const res = await fetch("http://127.0.0.1:8000/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question })
      });
      const data = await res.json();
      if (res.ok && data.status === "success") {
        setPreviewRows(data.result || []);
      } else {
        setPreviewRows([]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingPreview(false);
    }
  };

  useEffect(() => {
    fetchDatasets();
  }, []);

  useEffect(() => {
    if (selectedDataset) {
      fetchPreview(selectedDataset.name);
      // Fetch columns schema dynamically
      const fetchSchema = async () => {
        try {
          const res = await fetch(`http://127.0.0.1:8000/api/datasets/schema/${selectedDataset.id}`);
          if (res.ok) {
            const data = await res.json();
            setColumns(data.columns || []);
          } else {
            setColumns([]);
          }
        } catch (err) {
          console.error("Failed to load schema", err);
          setColumns([]);
        }
      };
      fetchSchema();
    }
  }, [selectedDataset]);


  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-deep-navy tracking-tight">Dataset Explorer</h1>
        <p className="text-sm text-on-surface-variant mt-1">
          Explore schemas, data types, and preview tables loaded in your current workspace.
        </p>
      </div>

      {errorMsg && (
        <div className="p-4 bg-error-container/20 border border-error/20 text-error rounded-xl text-xs mb-6">
          {errorMsg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Side: Dataset List */}
        <div className="lg:col-span-4 flex flex-col gap-4">
          <div className="bg-surface-white border border-outline-variant/35 rounded-xl p-6 shadow-sm">
            <h3 className="text-xs font-bold uppercase tracking-wider text-deep-navy mb-4">
              Select Dataset
            </h3>
            <div className="space-y-2 max-h-[450px] overflow-y-auto pr-1">
              {datasets.map((dataset) => {
                const isSelected = selectedDataset?.name === dataset.name;
                return (
                  <button
                    key={dataset.name}
                    onClick={() => setSelectedDataset(dataset)}
                    className={`w-full text-left p-4 rounded-xl border flex items-center gap-3 transition-all cursor-pointer ${
                      isSelected
                        ? "bg-primary-fixed/30 border-vibrant-blue text-deep-navy font-bold shadow-xs"
                        : "bg-surface-container-low border-outline-variant/30 hover:border-outline-variant/80 text-on-surface"
                    }`}
                  >
                    <span className="material-symbols-outlined text-lg text-vibrant-blue">
                      {dataset.type === "SQL Table" ? "table_chart" : "table_view"}
                    </span>
                    <div>
                      <p className="text-xs font-bold leading-tight">{dataset.name}</p>
                      <p className="text-[10px] text-on-surface-variant font-semibold mt-0.5">
                        {dataset.rows > 0 ? `${dataset.rows} rows` : "SQL Table"} • {dataset.columns || 0} columns
                      </p>
                    </div>
                  </button>
                );
              })}
              {datasets.length === 0 && (
                <p className="text-xs text-on-surface-variant text-center py-6 font-semibold">No datasets loaded. Go to Datasets page.</p>
              )}
            </div>
          </div>
        </div>

        {/* Right Side: Schema Details & Preview */}
        <div className="lg:col-span-8 flex flex-col gap-6">
          {selectedDataset ? (
            <>
              {/* Columns Schema */}
              <div className="bg-surface-white border border-outline-variant/35 rounded-xl p-6 md:p-8 shadow-sm">
                <h3 className="text-base font-bold text-deep-navy mb-4">
                  Schema: {selectedDataset.name}
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-outline-variant/35 text-deep-navy uppercase tracking-wider font-extrabold">
                        <th className="pb-3 font-bold">Column Name</th>
                        <th className="pb-3 font-bold">Data Type</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-outline-variant/20">
                      {columns.map((col: any, idx: number) => (
                        <tr key={idx} className="hover:bg-surface-container-low/50">
                          <td className="py-2.5 font-bold text-on-surface">{col.name}</td>
                          <td className="py-2.5 font-mono text-secondary font-semibold uppercase">{col.type}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Data Preview */}
              <div className="bg-surface-white border border-outline-variant/35 rounded-xl p-6 md:p-8 shadow-sm">
                <h3 className="text-base font-bold text-deep-navy mb-4 flex justify-between items-center">
                  <span>Data Preview (First 10 Rows)</span>
                  {loadingPreview && <span className="text-xs text-vibrant-blue animate-pulse">Loading preview...</span>}
                </h3>

                <div className="overflow-x-auto max-h-[300px] border border-outline-variant/50 rounded-lg bg-surface-container-lowest">
                  {previewRows.length > 0 ? (
                    <table className="w-full text-left border-collapse text-xs">
                      <thead className="bg-surface-container sticky top-0 z-20">
                        <tr className="border-b border-outline-variant/55 text-deep-navy uppercase tracking-wider font-extrabold">
                          {Object.keys(previewRows[0]).map((key) => (
                            <th key={key} className="p-3 font-bold whitespace-nowrap">
                              {key}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-outline-variant/30">
                        {previewRows.map((row, rowIdx) => (
                          <tr key={rowIdx} className="hover:bg-surface-container">
                            {Object.values(row).map((val: any, valIdx) => (
                              <td key={valIdx} className="p-3 whitespace-nowrap text-on-surface font-semibold font-mono select-text">
                                {typeof val === "object" ? JSON.stringify(val) : String(val)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="text-center py-10 text-on-surface-variant font-semibold">
                      {loadingPreview ? "Loading data table..." : "No preview available for this dataset."}
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="bg-surface-white border border-outline-variant/35 rounded-xl p-12 text-center text-on-surface-variant shadow-sm flex flex-col items-center">
              <span className="material-symbols-outlined text-4xl mb-4 text-vibrant-blue">explore</span>
              <p className="text-sm font-semibold">Select a dataset from the sidebar to inspect its structure.</p>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
