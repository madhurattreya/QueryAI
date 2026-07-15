# Running QueryIQ Enterprise BI Platform

This guide provides step-by-step instructions to run the backend engine, frontend workspace, and the enterprise benchmark suite.

---

## 1. Backend Server Setup (FastAPI)

The backend uses a Python virtual environment located in the root directory.

### Step 1: Navigate to the Project Root
Ensure you are in the main workspace root directory:
```powershell
cd "c:\Users\Madhur\Desktop\AI data"
```

### Step 2: Start the Uvicorn Backend Server
Run the Uvicorn server using the Python executable inside the virtual environment:
```powershell
.\venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000
```

Once running, the backend APIs will be available at:
- **API Base**: `http://127.0.0.1:8000`
- **Swagger Documentation (OpenAPI)**: `http://127.0.0.1:8000/docs`
- **Redoc Documentation**: `http://127.0.0.1:8000/redoc`

---

## 2. Frontend Server Setup (Next.js)

The frontend is located in the `nexus-ai-studio` directory.

### Step 1: Navigate to the Frontend Directory
```powershell
cd "c:\Users\Madhur\Desktop\AI data\nexus-ai-studio"
```

### Step 2: Start the Development Server
Run the npm dev server:
```powershell
npm run dev
```

Once started, open your web browser and navigate to:
- **Studio Interface**: `http://localhost:3000`

---

## 3. Running Enterprise Benchmarks

To execute the 10 modular benchmark suites (Authentication, Workspace Isolation, Dashboard, Analytics, Visualization, Export, Scheduler, API, Load, and Failure Recovery tests):

### Run Command:
From the root workspace directory, run:
```powershell
.\venv\Scripts\python .\backend\tests\run_enterprise_benchmarks.py
```
This will print detailed execution statistics, P95/P99 latency calculations, cache hit efficiencies, and cold start recovery times directly in your terminal.
