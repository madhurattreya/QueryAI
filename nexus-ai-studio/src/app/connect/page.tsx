"use client";

import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { ApiClient } from "@/lib/apiClient";

interface Dataset {
  id: string;
  name: string;
  filename: string;
  source: string;
  type: string;
  rows: number;
  columns: number;
  size_bytes: number;
  is_active: number;
  status: string;
  upload_time: string;
  last_used_time: string;
  total_queries: number;
  avg_query_time: number;
  cache_hit_rate: number;
}

export default function ConnectPage() {
  const [sourceType, setSourceType] = useState<"file" | "sql" | "folder">("file");
  const [dbType, setDbType] = useState<"sqlite" | "mysql" | "postgresql">("sqlite");

  // File Upload State
  const [file, setFile] = useState<File | null>(null);
  const [uploadBehavior, setUploadBehavior] = useState<"keep" | "replace">("keep");
  const [uploadStatus, setUploadStatus] = useState<{ type: "idle" | "loading" | "success" | "error"; message: string }>({
    type: "idle",
    message: ""
  });

  // Folder Import State
  const [folderPath, setFolderPath] = useState("");
  const [folderBehavior, setFolderBehavior] = useState<"keep" | "replace">("keep");
  const [folderStatus, setFolderStatus] = useState<{ type: "idle" | "loading" | "success" | "error"; message: string }>({
    type: "idle",
    message: ""
  });

  // SQL State
  const [sqlRequest, setSqlRequest] = useState({
    sqlite_path: "",
    host: "localhost",
    port: "",
    db_name: "",
    username: "",
    password: ""
  });
  const [sqlStatus, setSqlStatus] = useState<{ type: "idle" | "loading" | "success" | "error"; message: string }>({
    type: "idle",
    message: ""
  });


  // Datasets Registry State
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  // Preview & Schema Modals State
  const [previewDataset, setPreviewDataset] = useState<Dataset | null>(null);
  const [previewData, setPreviewData] = useState<any[]>([]);
  const [schemaDataset, setSchemaDataset] = useState<Dataset | null>(null);
  const [schemaCols, setSchemaCols] = useState<any[]>([]);
  
  // Renaming State
  const [renamingDataset, setRenamingDataset] = useState<Dataset | null>(null);
  const [renamingName, setRenamingName] = useState("");

  // Delete Confirmation State
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);

  // Health report state
  const [healthDataset, setHealthDataset] = useState<Dataset | null>(null);
  const [healthData, setHealthData] = useState<any>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const viewHealth = async (ds: Dataset) => {
    setActiveMenuId(null);
    setHealthDataset(ds);
    setHealthLoading(true);
    setHealthData(null);
    try {
      const res = await ApiClient.request(`/api/datasets/health/${ds.id}`);
      if (res.ok) {
        const data = await res.json();
        setHealthData(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setHealthLoading(false);
    }
  };

  const fetchDatasets = async () => {
    try {
      const res = await ApiClient.request("/api/datasets");
      if (res.ok) {
        const data = await res.json();
        setDatasets(data);
      }
    } catch (err) {
      console.error("Failed to fetch datasets", err);
    }
  };

  useEffect(() => {
    fetchDatasets();
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const requestedTab = params.get("tab");
      if (requestedTab === "sql") {
        setSourceType("sql");
      } else if (requestedTab === "file") {
        setSourceType("file");
      } else if (requestedTab === "folder" || requestedTab === "folders") {
        setSourceType("folder");
      }
    }
  }, []);

  const handleFolderImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!folderPath.trim()) return;

    setFolderStatus({ type: "loading", message: "Scanning folder and batch-registering datasets..." });
    try {
      const res = await ApiClient.request("/api/upload/folder", {
        method: "POST",
        body: JSON.stringify({
          folder_path: folderPath.trim(),
          behavior: folderBehavior
        })
      });
      const data = await res.json();
      if (res.ok && data.status === "success") {
        setFolderStatus({
          type: "success",
          message: `Successfully batch-imported ${data.registered_count} dataset(s) from directory!`
        });
        await fetchDatasets();
      } else {
        setFolderStatus({
          type: "error",
          message: data.detail || data.message || "Failed to import folder directory."
        });
      }
    } catch (err: any) {
      setFolderStatus({ type: "error", message: err.message || "Network error occurred." });
    }
  };



  const handleFileUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setUploadStatus({ type: "loading", message: "Uploading and registering dataset..." });
    const formData = new FormData();
    formData.append("file", file);

    try {
      const headers: Record<string, string> = { Accept: "application/json" };
      const token = ApiClient.getToken();
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch(ApiClient.getUrl(`/api/upload?behavior=${uploadBehavior}`), {
        method: "POST",
        headers,
        body: formData
      });
      const data = await res.json();
      if (res.ok && data.status === "success") {
        setUploadStatus({ type: "success", message: `Successfully registered ${file.name}!` });
        setFile(null);
        fetchDatasets();
      } else {
        let errorMsg = "Failed to upload file.";
        if (typeof data.detail === "string") {
          errorMsg = data.detail;
        } else if (Array.isArray(data.detail)) {
          errorMsg = data.detail.map((d: any) => (typeof d === "object" && d !== null ? d.msg || JSON.stringify(d) : String(d))).join("; ");
        } else if (typeof data.detail === "object" && data.detail !== null) {
          errorMsg = JSON.stringify(data.detail);
        } else if (data.message) {
          errorMsg = typeof data.message === "string" ? data.message : JSON.stringify(data.message);
        }
        setUploadStatus({ type: "error", message: errorMsg });
      }
    } catch (err: any) {
      setUploadStatus({ type: "error", message: String(err.message || err || "Network error occurred.") });
    }
  };

  const handleSqlConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    setSqlStatus({ type: "loading", message: "Establishing cryptographic database connection..." });

    try {
      const res = await ApiClient.request("/api/connect-sql", {
        method: "POST",
        body: JSON.stringify({
          db_type: dbType,
          sqlite_path: sqlRequest.sqlite_path,
          host: sqlRequest.host,
          port: sqlRequest.port || null,
          db_name: sqlRequest.db_name,
          username: sqlRequest.username,
          password: sqlRequest.password
        })
      });
      const data = await res.json();
      if (res.ok && data.status === "success") {
        setSqlStatus({
          type: "success",
          message: "Database registered successfully!"
        });
        fetchDatasets();
      } else {
        let errorMsg = "Failed to connect to database.";
        if (typeof data.detail === "string") {
          errorMsg = data.detail;
        } else if (Array.isArray(data.detail)) {
          errorMsg = data.detail.map((d: any) => (typeof d === "object" && d !== null ? d.msg || JSON.stringify(d) : String(d))).join("; ");
        } else if (data.message) {
          errorMsg = typeof data.message === "string" ? data.message : JSON.stringify(data.message);
        }
        setSqlStatus({ type: "error", message: errorMsg });
      }
    } catch (err: any) {
      setSqlStatus({ type: "error", message: String(err.message || err || "Network connection failed.") });
    }
  };

  const setDatasetActive = async (id: string) => {
    setActiveMenuId(null);
    try {
      const res = await ApiClient.request("/api/datasets/active", {
        method: "POST",
        body: JSON.stringify({ id })
      });
      if (res.ok) {
        fetchDatasets();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const deleteDataset = async (id: string) => {
    setActiveMenuId(null);
    setConfirmDeleteId(id);
  };

  const confirmDelete = async () => {
    if (!confirmDeleteId) return;
    const targetId = confirmDeleteId;
    setConfirmDeleteId(null);
    try {
      setDatasets((prev) => prev.filter((d) => d.id !== targetId));
      const res = await ApiClient.request(`/api/datasets/${targetId}`, {
        method: "DELETE"
      });
      if (res.ok) {
        await fetchDatasets();
      }
    } catch (err) {
      console.error(err);
      fetchDatasets();
    }
  };

  const deleteAllDatasets = async () => {
    setConfirmDeleteAll(true);
  };

  const confirmDeleteAllExec = async () => {
    setConfirmDeleteAll(false);
    try {
      setDatasets([]);
      const res = await ApiClient.request("/api/datasets", {
        method: "DELETE"
      });
      if (res.ok) {
        await fetchDatasets();
      }
    } catch (err) {
      console.error(err);
      fetchDatasets();
    }
  };

  const triggerRename = (ds: Dataset) => {
    setActiveMenuId(null);
    setRenamingDataset(ds);
    setRenamingName(ds.name);
  };

  const saveRename = async () => {
    if (!renamingDataset || !renamingName.trim()) return;
    try {
      const res = await ApiClient.request("/api/datasets/rename", {
        method: "POST",
        body: JSON.stringify({ id: renamingDataset.id, name: renamingName })
      });
      if (res.ok) {
        setRenamingDataset(null);
        fetchDatasets();
      }
    } catch (err) {
      console.error(err);
    }
  };

  const viewPreview = async (ds: Dataset) => {
    setActiveMenuId(null);
    try {
      const res = await ApiClient.request(`/api/datasets/preview/${ds.id}`);
      if (res.ok) {
        const data = await res.json();
        setPreviewData(data.result || []);
        setPreviewDataset(ds);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const viewSchema = async (ds: Dataset) => {
    setActiveMenuId(null);
    try {
      const res = await ApiClient.request(`/api/datasets/schema/${ds.id}`);
      if (res.ok) {
        const data = await res.json();
        setSchemaCols(data.columns || []);
        setSchemaDataset(ds);
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-deep-navy tracking-tight">Data Connections</h1>
        <p className="text-sm text-on-surface-variant mt-1">
          Register new datasets, connect SQL databases, and choose which dataset is active for queries.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Panel: Upload spreadsheet or SQL Form */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          
          {/* Selector tab */}
          <div className="flex gap-2 p-1 bg-surface-container border border-outline-variant/30 rounded-xl">
            <button
              onClick={() => setSourceType("file")}
              className={`flex-1 py-2 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                sourceType === "file" 
                  ? "bg-deep-navy text-white shadow-sm" 
                  : "text-on-surface-variant hover:text-deep-navy"
              }`}
            >
              <span className="material-symbols-outlined text-sm">upload_file</span>
              Import Spreadsheets
            </button>
            <button
              onClick={() => setSourceType("sql")}
              className={`flex-1 py-2 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                sourceType === "sql" 
                  ? "bg-deep-navy text-white shadow-sm" 
                  : "text-on-surface-variant hover:text-deep-navy"
              }`}
            >
              <span className="material-symbols-outlined text-sm">database</span>
              SQL Connections
            </button>
            <button
              onClick={() => setSourceType("folder")}
              className={`flex-1 py-2 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all cursor-pointer ${
                sourceType === "folder" 
                  ? "bg-deep-navy text-white shadow-sm" 
                  : "text-on-surface-variant hover:text-deep-navy"
              }`}
            >
              <span className="material-symbols-outlined text-sm">folder_managed</span>
              Import Folders
            </button>
          </div>


          <div className="bg-surface-white border border-outline-variant/35 rounded-xl p-8 shadow-sm">
            {sourceType === "file" ? (
              <form onSubmit={handleFileUpload} className="space-y-6">
                <div className="border-2 border-dashed border-outline-variant rounded-xl p-8 flex flex-col items-center justify-center bg-surface-container-low/50 hover:bg-surface-container-low transition-colors">
                  <span className="material-symbols-outlined text-4xl text-vibrant-blue mb-4">
                    cloud_upload
                  </span>
                  <label className="bg-deep-navy text-white text-xs font-bold py-2.5 px-5 rounded-lg cursor-pointer hover:bg-primary-container transition-all mb-2 shadow-sm">
                    Select CSV / Excel File
                    <input
                      type="file"
                      accept=".csv, .xlsx, .xls"
                      className="hidden"
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                    />
                  </label>
                  <p className="text-xs text-on-surface-variant mt-1 text-center font-semibold">
                    {file ? `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)` : "Supports CSV, XLSX, XLS up to 25MB"}
                  </p>
                </div>

                {/* Upload behavior selector */}
                <div className="bg-surface-container-low p-4 rounded-lg border border-outline-variant/50 space-y-3">
                  <p className="text-xs font-bold text-deep-navy">Upload Option:</p>
                  <div className="flex gap-6">
                    <label className="flex items-center gap-2 text-xs text-on-surface-variant font-semibold cursor-pointer">
                      <input
                        type="radio"
                        name="behavior"
                        checked={uploadBehavior === "keep"}
                        onChange={() => setUploadBehavior("keep")}
                        className="text-vibrant-blue focus:ring-0 cursor-pointer"
                      />
                      <span>Keep existing datasets</span>
                    </label>
                    <label className="flex items-center gap-2 text-xs text-on-surface-variant font-semibold cursor-pointer">
                      <input
                        type="radio"
                        name="behavior"
                        checked={uploadBehavior === "replace"}
                        onChange={() => setUploadBehavior("replace")}
                        className="text-vibrant-blue focus:ring-0 cursor-pointer"
                      />
                      <span>Replace current active dataset</span>
                    </label>
                  </div>
                </div>

                {uploadStatus.message && (
                  <div
                    className={`p-4 rounded-lg text-xs font-semibold ${
                      uploadStatus.type === "success"
                        ? "bg-success/15 text-success border border-success/20"
                        : uploadStatus.type === "error"
                        ? "bg-error/15 text-error border border-error/20"
                        : "bg-vibrant-blue/10 text-vibrant-blue border border-vibrant-blue/20"
                    }`}
                  >
                    {uploadStatus.message}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={!file || uploadStatus.type === "loading"}
                  className="w-full bg-vibrant-blue hover:bg-secondary-container text-white text-sm font-bold py-3 rounded-lg transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  {uploadStatus.type === "loading" ? "Registering Dataset..." : "Import File"}
                </button>
              </form>
            ) : sourceType === "sql" ? (
              <form onSubmit={handleSqlConnect} className="space-y-4">

                <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider mb-2">
                  Database Configurations
                </h3>
                
                <div className="flex gap-2">
                  {(["sqlite", "mysql", "postgresql"] as const).map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => setDbType(type)}
                      className={`flex-1 py-2 text-xs font-bold rounded-lg capitalize border transition-all cursor-pointer ${
                        dbType === type
                          ? "bg-secondary-fixed/50 border-vibrant-blue text-secondary font-extrabold"
                          : "bg-surface-container border-outline-variant/30 text-on-surface-variant hover:text-deep-navy"
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>

                {dbType === "sqlite" ? (
                  <div>
                    <label className="block text-xs font-bold text-on-surface-variant mb-2">SQLite File Path</label>
                    <input
                      type="text"
                      className="w-full bg-surface-container-lowest border border-outline-variant/60 rounded-lg px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-vibrant-blue focus:ring-1 focus:ring-vibrant-blue placeholder-on-surface-variant/40"
                      placeholder="e.g. data/my_database.db"
                      value={sqlRequest.sqlite_path}
                      onChange={(e) => setSqlRequest({ ...sqlRequest, sqlite_path: e.target.value })}
                      required
                    />
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-4">
                    <div className="col-span-2">
                      <label className="block text-xs font-bold text-on-surface-variant mb-2">Host Address</label>
                      <input
                        type="text"
                        className="w-full bg-surface-container-lowest border border-outline-variant/60 rounded-lg px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-vibrant-blue focus:ring-1 focus:ring-vibrant-blue"
                        value={sqlRequest.host}
                        onChange={(e) => setSqlRequest({ ...sqlRequest, host: e.target.value })}
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-on-surface-variant mb-2">Port Address (Optional)</label>
                      <input
                        type="text"
                        className="w-full bg-surface-container-lowest border border-outline-variant/60 rounded-lg px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-vibrant-blue focus:ring-1 focus:ring-vibrant-blue"
                        placeholder={dbType === "mysql" ? "3306" : "5432"}
                        value={sqlRequest.port}
                        onChange={(e) => setSqlRequest({ ...sqlRequest, port: e.target.value })}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-on-surface-variant mb-2">Database Name</label>
                      <input
                        type="text"
                        className="w-full bg-surface-container-lowest border border-outline-variant/60 rounded-lg px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-vibrant-blue focus:ring-1 focus:ring-vibrant-blue"
                        value={sqlRequest.db_name}
                        onChange={(e) => setSqlRequest({ ...sqlRequest, db_name: e.target.value })}
                        required
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-on-surface-variant mb-2">Username</label>
                      <input
                        type="text"
                        className="w-full bg-surface-container-lowest border border-outline-variant/60 rounded-lg px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-vibrant-blue focus:ring-1 focus:ring-vibrant-blue"
                        value={sqlRequest.username}
                        onChange={(e) => setSqlRequest({ ...sqlRequest, username: e.target.value })}
                        required
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="block text-xs font-bold text-on-surface-variant mb-2">Password</label>
                      <input
                        type="password"
                        className="w-full bg-surface-container-lowest border border-outline-variant/60 rounded-lg px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-vibrant-blue focus:ring-1 focus:ring-vibrant-blue"
                        value={sqlRequest.password}
                        onChange={(e) => setSqlRequest({ ...sqlRequest, password: e.target.value })}
                      />
                    </div>
                  </div>
                )}

                {sqlStatus.message && (
                  <div
                    className={`p-4 rounded-lg text-xs font-semibold ${
                      sqlStatus.type === "success"
                        ? "bg-success/15 text-success border border-success/20"
                        : "bg-error/15 text-error border border-error/20"
                    }`}
                  >
                    {sqlStatus.message}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={sqlStatus.type === "loading"}
                  className="w-full bg-vibrant-blue hover:bg-secondary-container text-white text-sm font-bold py-3 rounded-lg transition-colors shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {sqlStatus.type === "loading" ? "Registering Server..." : "Establish Connection"}
                </button>
              </form>
            ) : (
              <form onSubmit={handleFolderImport} className="space-y-6">
                <div>
                  <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider mb-2">
                    Batch Folder & Directory Sync
                  </h3>
                  <p className="text-xs text-on-surface-variant leading-relaxed font-semibold">
                    Enter a local directory path to scan and batch-register all contained CSV, Excel, Parquet, and JSON datasets.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-bold text-on-surface-variant mb-2">
                    Directory Path on Host Disk
                  </label>
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-3.5 top-3 text-on-surface-variant text-base">folder_open</span>
                    <input
                      type="text"
                      className="w-full bg-surface-container-lowest border border-outline-variant/60 rounded-lg pl-10 pr-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-vibrant-blue font-mono font-semibold"
                      placeholder="C:\Users\Public\Data\Sales_2024 or /var/data/analytics"
                      value={folderPath}
                      onChange={(e) => setFolderPath(e.target.value)}
                      required
                    />
                  </div>
                  <p className="text-[10px] text-on-surface-variant mt-1.5 font-semibold">
                    * Supports nested subdirectories. Automatically registers multiple files into QueryIQ catalog.
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="block text-xs font-bold text-on-surface-variant">Import Strategy</label>
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                      <input
                        type="radio"
                        name="folderBehavior"
                        value="keep"
                        checked={folderBehavior === "keep"}
                        onChange={() => setFolderBehavior("keep")}
                        className="text-vibrant-blue cursor-pointer"
                      />
                      <span>Keep Existing Datasets</span>
                    </label>
                    <label className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                      <input
                        type="radio"
                        name="folderBehavior"
                        value="replace"
                        checked={folderBehavior === "replace"}
                        onChange={() => setFolderBehavior("replace")}
                        className="text-vibrant-blue cursor-pointer"
                      />
                      <span>Replace Active Dataset</span>
                    </label>
                  </div>
                </div>

                {folderStatus.message && (
                  <div
                    className={`p-4 rounded-lg text-xs font-semibold ${
                      folderStatus.type === "success"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : folderStatus.type === "loading"
                        ? "bg-blue-50 text-vibrant-blue border border-blue-200"
                        : "bg-error-container/20 text-error border border-error/20"
                    }`}
                  >
                    {folderStatus.message}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={folderStatus.type === "loading" || !folderPath.trim()}
                  className="w-full bg-vibrant-blue hover:bg-secondary-container text-white text-sm font-bold py-3 rounded-lg transition-colors shadow-sm disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2"
                >
                  <span className="material-symbols-outlined text-sm">sync</span>
                  {folderStatus.type === "loading" ? "Scanning Directory..." : "Batch Sync & Register Folder"}
                </button>
              </form>
            )}

          </div>
        </div>

        {/* Right Panel: Dataset Management Panel */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          <div className="bg-surface-white border border-outline-variant/35 rounded-xl p-6 flex flex-col h-full min-h-[400px] shadow-sm">
            <div className="flex justify-between items-center mb-5">
              <h4 className="text-sm font-bold text-deep-navy uppercase tracking-wider">
                Loaded Datasets
              </h4>
              {datasets.length > 0 && (
                <button
                  onClick={deleteAllDatasets}
                  className="text-[10px] bg-error/10 hover:bg-error/20 text-error border border-error/20 px-2.5 py-1 rounded font-bold transition-colors cursor-pointer"
                >
                  Delete All
                </button>
              )}
            </div>

            <div className="flex-grow overflow-y-auto space-y-3">
              {datasets.map((ds) => {
                const isActive = ds.is_active === 1;
                return (
                  <div
                    key={ds.id}
                    className={`p-4 rounded-lg border flex flex-col relative transition-all ${
                      isActive 
                        ? "bg-primary-fixed/30 border-vibrant-blue" 
                        : "bg-surface-container-low border-outline-variant/30 hover:border-outline-variant/80"
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2 pr-6">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-vibrant-blue text-lg">
                          {ds.type === "file" ? "table_view" : "database"}
                        </span>
                        <div>
                          <p className="font-bold text-xs text-on-surface capitalize truncate max-w-[150px]">
                            {ds.name}
                          </p>
                          <p className="text-[9px] font-semibold text-on-surface-variant">
                            {ds.source} • {ds.type === "file" ? "File" : "SQL Server"}
                          </p>
                        </div>
                      </div>

                      {/* Active Status Badge */}
                      {isActive && (
                        <span className="px-2 py-0.5 bg-success/15 text-success border border-success/20 text-[9px] font-bold rounded-full flex items-center gap-1 shadow-sm shrink-0">
                          <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse"></span>
                          Active
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-3 gap-2 mt-2 pt-2 border-t border-outline-variant/35 text-[9px] font-bold text-on-surface-variant">
                      <div>Rows: <span className="text-on-surface font-extrabold font-mono">{ds.rows}</span></div>
                      <div>Cols: <span className="text-on-surface font-extrabold font-mono">{ds.columns}</span></div>
                      <div>Size: <span className="text-on-surface font-extrabold font-mono">{(ds.size_bytes / 1024).toFixed(1)} KB</span></div>
                    </div>

                    {/* Action button menu overlay trigger */}
                    <div className="absolute right-2 top-2">
                      <button
                        onClick={() => setActiveMenuId(activeMenuId === ds.id ? null : ds.id)}
                        className="p-1 hover:bg-surface-container rounded text-on-surface-variant hover:text-on-surface cursor-pointer"
                      >
                        <span className="material-symbols-outlined text-sm">more_vert</span>
                      </button>
                      
                      {activeMenuId === ds.id && (
                        <div className="absolute right-0 top-6 bg-surface-white border border-outline-variant/65 rounded-lg shadow-xl py-1 z-30 w-32 font-bold text-[10px]">
                          {!isActive && (
                            <button
                              onClick={() => setDatasetActive(ds.id)}
                              className="w-full text-left px-3 py-1.5 hover:bg-surface-container text-success flex items-center gap-1.5 cursor-pointer"
                            >
                              <span className="material-symbols-outlined text-sm">check_circle</span>
                              Set Active
                            </button>
                          )}
                          <button
                            onClick={() => viewPreview(ds)}
                            className="w-full text-left px-3 py-1.5 hover:bg-surface-container text-on-surface flex items-center gap-1.5 cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-sm">preview</span>
                            Preview
                          </button>
                           <button
                            onClick={() => viewSchema(ds)}
                            className="w-full text-left px-3 py-1.5 hover:bg-surface-container text-on-surface flex items-center gap-1.5 cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-sm">toc</span>
                            View Schema
                          </button>
                          <button
                            onClick={() => viewHealth(ds)}
                            className="w-full text-left px-3 py-1.5 hover:bg-surface-container text-on-surface flex items-center gap-1.5 cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-sm">health_and_safety</span>
                            Health Check
                          </button>
                          <button
                            onClick={() => triggerRename(ds)}
                            className="w-full text-left px-3 py-1.5 hover:bg-surface-container text-on-surface flex items-center gap-1.5 cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-sm">edit</span>
                            Rename
                          </button>
                          <button
                            onClick={() => deleteDataset(ds.id)}
                            className="w-full text-left px-3 py-1.5 hover:bg-surface-container text-error flex items-center gap-1.5 cursor-pointer"
                          >
                            <span className="material-symbols-outlined text-sm">delete</span>
                            Remove
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {datasets.length === 0 && (
                <p className="text-xs text-on-surface-variant text-center py-12 font-semibold">No active datasets registered.</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Preview Modal Overlay */}
      {previewDataset && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-surface-white border border-outline-variant rounded-xl p-6 w-full max-w-4xl max-h-[80vh] flex flex-col shadow-2xl">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider flex items-center gap-2">
                <span className="material-symbols-outlined text-vibrant-blue">preview</span>
                Preview Data: {previewDataset.name} (First 20 Rows)
              </h3>
              <button
                onClick={() => setPreviewDataset(null)}
                className="text-on-surface-variant hover:text-deep-navy cursor-pointer"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            
            <div className="flex-grow overflow-auto border border-outline-variant/50 rounded-lg bg-surface-container-lowest">
              {previewData.length > 0 ? (
                <table className="w-full text-left border-collapse text-[10px]">
                  <thead className="bg-surface-container sticky top-0">
                    <tr className="border-b border-outline-variant/55 text-deep-navy uppercase tracking-wider font-extrabold">
                      {Object.keys(previewData[0]).map((key) => (
                        <th key={key} className="p-2.5 bg-surface-container font-bold whitespace-nowrap">
                          {key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewData.map((row, idx) => (
                      <tr key={idx} className="hover:bg-surface-container border-b border-outline-variant/30">
                        {Object.values(row).map((val: any, cIdx) => (
                          <td key={cIdx} className="p-2.5 whitespace-nowrap text-on-surface font-semibold font-mono select-text">
                            {typeof val === "object" ? JSON.stringify(val) : String(val)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-xs text-on-surface-variant text-center py-12 font-semibold">No data returned for preview.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Schema Modal Overlay */}
      {schemaDataset && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-surface-white border border-outline-variant rounded-xl p-6 w-full max-w-md flex flex-col shadow-2xl">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider flex items-center gap-2">
                <span className="material-symbols-outlined text-vibrant-blue">toc</span>
                Schema Structure: {schemaDataset.name}
              </h3>
              <button
                onClick={() => setSchemaDataset(null)}
                className="text-on-surface-variant hover:text-deep-navy cursor-pointer"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            
            <div className="flex-grow overflow-auto max-h-[300px] border border-outline-variant/50 rounded-lg bg-surface-container-lowest p-2">
              <div className="divide-y divide-outline-variant/30">
                {schemaCols.map((col, idx) => (
                  <div key={idx} className="flex justify-between py-2 text-xs">
                    <span className="font-bold text-deep-navy font-mono">{col.name}</span>
                    <span className="px-2 py-0.5 bg-primary-fixed/50 border border-vibrant-blue/20 rounded text-[10px] text-secondary font-bold uppercase font-mono">
                      {col.type}
                    </span>
                  </div>
                ))}
                {schemaCols.length === 0 && (
                  <p className="text-xs text-on-surface-variant text-center py-6 font-semibold">Failed to load schema columns.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Dataset Health Modal Overlay */}
      {healthDataset && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-surface-white border border-outline-variant rounded-xl p-6 w-full max-w-2xl flex flex-col shadow-2xl max-h-[85vh]">
            <div className="flex justify-between items-center mb-4 border-b pb-3">
              <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider flex items-center gap-2">
                <span className="material-symbols-outlined text-vibrant-blue">health_and_safety</span>
                AI Dataset Health Report: {healthDataset.name}
              </h3>
              <button
                onClick={() => setHealthDataset(null)}
                className="text-on-surface-variant hover:text-deep-navy cursor-pointer"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            {healthLoading ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3">
                <div className="w-8 h-8 rounded-full border-4 border-vibrant-blue border-t-transparent animate-spin"></div>
                <p className="text-xs text-on-surface-variant font-bold">Analyzing dataset quality metrics...</p>
              </div>
            ) : healthData ? (
              <div className="flex-grow overflow-y-auto space-y-6 pr-1 text-xs text-on-surface-variant font-semibold">
                
                {/* Highlights Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-surface-container/30 p-4 rounded-xl border border-outline-variant/30">
                  <div className="bg-white p-3 rounded-lg shadow-xs">
                    <span className="text-[9px] uppercase tracking-wider text-outline block mb-0.5">Rows / Columns</span>
                    <span className="text-sm font-bold text-deep-navy">{healthData.total_rows} × {healthData.total_columns}</span>
                  </div>
                  <div className="bg-white p-3 rounded-lg shadow-xs">
                    <span className="text-[9px] uppercase tracking-wider text-outline block mb-0.5">Missing Cells %</span>
                    <span className={`text-sm font-bold ${healthData.overall_missing_pct > 15 ? 'text-amber-500' : 'text-emerald-500'}`}>
                      {healthData.overall_missing_pct}%
                    </span>
                  </div>
                  <div className="bg-white p-3 rounded-lg shadow-xs">
                    <span className="text-[9px] uppercase tracking-wider text-outline block mb-0.5">Duplicates</span>
                    <span className={`text-sm font-bold ${healthData.duplicates_count > 0 ? 'text-error' : 'text-emerald-500'}`}>
                      {healthData.duplicates_count} ({healthData.duplicates_pct}%)
                    </span>
                  </div>
                  <div className="bg-white p-3 rounded-lg shadow-xs">
                    <span className="text-[9px] uppercase tracking-wider text-outline block mb-0.5">Data Freshness</span>
                    <span className="text-xs font-bold text-deep-navy truncate block">{healthData.freshness}</span>
                  </div>
                </div>

                {/* Recommended Fixes */}
                <div className="space-y-2">
                  <h4 className="text-[10px] font-bold text-deep-navy uppercase tracking-wider">Recommended Fixes</h4>
                  <div className="space-y-2">
                    {healthData.recommended_fixes.map((fix: any, idx: number) => (
                      <div key={idx} className="p-3 bg-amber-500/5 border border-amber-500/20 rounded-lg flex items-start gap-2.5">
                        <span className="material-symbols-outlined text-amber-500 text-sm mt-0.5">build</span>
                        <div>
                          <p className="font-bold text-deep-navy">{fix.issue}</p>
                          <p className="text-[11px] text-outline mt-0.5">Recommended Action: {fix.fix}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Columns Detail */}
                <div className="space-y-2">
                  <h4 className="text-[10px] font-bold text-deep-navy uppercase tracking-wider">Column Metrics & Skewness</h4>
                  <div className="overflow-x-auto border border-outline-variant/30 rounded-lg bg-surface-container-lowest">
                    <table className="w-full text-left border-collapse text-[10px]">
                      <thead>
                        <tr className="bg-surface-container border-b border-outline-variant/40 text-deep-navy uppercase tracking-wider font-bold">
                          <th className="p-2">Column</th>
                          <th className="p-2">Missing %</th>
                          <th className="p-2">Skewness</th>
                          <th className="p-2">Outliers</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-outline-variant/30 font-mono">
                        {Object.entries(healthData.missing_pct_per_column).map(([col, pct]: any) => {
                          const skew = healthData.skewness[col] !== undefined ? healthData.skewness[col] : "N/A";
                          const outlier = healthData.outliers[col] ? `${healthData.outliers[col].count} (${healthData.outliers[col].percentage}%)` : "0";
                          return (
                            <tr key={col} className="hover:bg-surface-container/50">
                              <td className="p-2 font-bold text-deep-navy">{col}</td>
                              <td className={`p-2 font-bold ${pct > 20 ? 'text-amber-500' : 'text-on-surface'}`}>{pct}%</td>
                              <td className="p-2">{skew}</td>
                              <td className="p-2">{outlier}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Correlations */}
                {healthData.high_correlations.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-[10px] font-bold text-deep-navy uppercase tracking-wider">Strong Pearson Correlations</h4>
                    <div className="flex flex-wrap gap-2">
                      {healthData.high_correlations.map((c: any, idx: number) => (
                        <div key={idx} className="px-3 py-1.5 bg-vibrant-blue/5 border border-vibrant-blue/15 rounded-lg flex items-center gap-1">
                          <span className="font-mono text-deep-navy font-bold">{c.col1}</span>
                          <span className="text-outline">↔</span>
                          <span className="font-mono text-deep-navy font-bold">{c.col2}</span>
                          <span className="font-bold text-vibrant-blue bg-vibrant-blue/10 px-1.5 py-0.5 rounded ml-1">r = {c.r}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

              </div>
            ) : (
              <p className="text-xs text-on-surface-variant text-center py-10">Failed to analyze health diagnostics.</p>
            )}

            <div className="border-t pt-3 mt-4 flex justify-end">
              <button
                onClick={() => setHealthDataset(null)}
                className="bg-deep-navy text-white text-xs font-bold py-2 px-4 rounded-lg cursor-pointer hover:bg-primary-container transition-all"
              >
                Close Report
              </button>
            </div>

          </div>
        </div>
      )}

      {/* Rename Dialog Modal */}
      {renamingDataset && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-surface-white border border-outline-variant rounded-xl p-6 w-full max-w-sm shadow-2xl">
            <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider mb-4 flex items-center gap-2">
              <span className="material-symbols-outlined text-vibrant-blue">edit</span>
              Rename Dataset
            </h3>
            <div className="space-y-4">
              <input
                type="text"
                className="w-full bg-surface-container-lowest border border-outline-variant/60 rounded-lg px-4 py-2.5 text-xs text-on-surface focus:outline-none focus:border-vibrant-blue focus:ring-1 focus:ring-vibrant-blue"
                value={renamingName}
                onChange={(e) => setRenamingName(e.target.value)}
                required
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setRenamingDataset(null)}
                  className="bg-surface-container border border-outline-variant/30 hover:bg-surface-container-high px-4 py-2 rounded text-xs font-bold text-on-surface transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={saveRename}
                  className="bg-vibrant-blue hover:bg-secondary-container text-white px-4 py-2 rounded text-xs font-bold transition-colors cursor-pointer"
                >
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Single Dataset Confirmation Modal */}
      {confirmDeleteId && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-surface-white border border-outline-variant rounded-xl p-6 w-full max-w-sm shadow-2xl">
            <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider mb-2 flex items-center gap-2">
              <span className="material-symbols-outlined text-error">delete</span>
              Remove Dataset
            </h3>
            <p className="text-xs text-on-surface-variant mb-5">
              Are you sure you want to remove this dataset? Associated files will be permanently deleted.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmDeleteId(null)}
                className="bg-surface-container border border-outline-variant/30 hover:bg-surface-container-high px-4 py-2 rounded text-xs font-bold text-on-surface transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="bg-error hover:opacity-90 text-white px-4 py-2 rounded text-xs font-bold transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <span className="material-symbols-outlined text-sm">delete</span>
                Remove
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete All Datasets Confirmation Modal */}
      {confirmDeleteAll && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-surface-white border border-outline-variant rounded-xl p-6 w-full max-w-sm shadow-2xl">
            <h3 className="text-sm font-bold text-deep-navy uppercase tracking-wider mb-2 flex items-center gap-2">
              <span className="material-symbols-outlined text-error">delete_forever</span>
              Delete All Datasets
            </h3>
            <p className="text-xs text-on-surface-variant mb-5">
              Are you sure you want to delete <strong>ALL</strong> datasets? This clears everything and resets all conversation contexts. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmDeleteAll(false)}
                className="bg-surface-container border border-outline-variant/30 hover:bg-surface-container-high px-4 py-2 rounded text-xs font-bold text-on-surface transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteAllExec}
                className="bg-error hover:opacity-90 text-white px-4 py-2 rounded text-xs font-bold transition-colors cursor-pointer flex items-center gap-1.5"
              >
                <span className="material-symbols-outlined text-sm">delete_forever</span>
                Delete All
              </button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
