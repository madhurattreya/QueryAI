# QueryIQ Enterprise Architecture Documentation

This document describes the production-grade architecture of the QueryIQ Enterprise Edition BI platform.

---

## 1. System Architecture

```mermaid
graph TD
    User([Business User]) -->|Natural Language Query| API[FastAPI Web API]
    API -->|Route Classification| Router[Cost-Based Router]
    
    subgraph Execution Routing
        Router -->|1. Metadata| Meta[Metadata Engine]
        Router -->|2. Deterministic| QueryEng[Query Engine]
        Router -->|3. Analytics Lib| AnalyticsLib[Analytics Library]
        Router -->|4. Visualization| Viz[Visualization Engine]
        Router -->|5. SQL| SQL[SQL Connector]
        Router -->|6. LLM Fallback| LLM[LLM Planner]
    end
    
    QueryEng -->|Preprocess Custom Formulas| FormulaEngine[Formula Engine]
    QueryEng -->|Coordinate Multi-Table Joins| JoinPlanner[Join Planner]
    JoinPlanner -->|Lookup Connections| RelEngine[Relationship Engine]
    
    RelEngine -->|Read/Write Graph| SQLite[(studio_metadata.db)]
    FormulaEngine -->|Load Dimensions/Measures| SQLite
    
    API -->|Write Log| Telemetry[Telemetry Service]
    Telemetry -->|Store Stats| SQLite
```

---

## 2. Component Reference

### A. Relationship Discovery Engine
- **Module**: `backend.services.relationship_engine`
- **Functionality**: Automatically discovers PK/FK pairs by matching column naming patterns and calculating overlapping value distributions.
- **API**:
  - `GET /api/relationships`: Lists all registered relationships.
  - `GET /api/relationships/graph`: Returns the complete adjacency graph.
  - `POST /api/relationships/discover`: Triggers background relationship discovery.

### B. Automatic Join Planner
- **Module**: `backend.services.join_planner`
- **Functionality**: Uses BFS/DFS pathfinding on the relationship graph to resolve the shortest join path between tables and builds merged DataFrames on the fly.

### C. DAX-like Formula Engine
- **Module**: `backend.services.formula_engine`
- **Functionality**: A lightweight parser and compiler that translates DAX expressions (e.g. `DIVIDE(SUM(Profit), SUM(Sales))`, `RUNNING_TOTAL(Sales)`) into vectorized Pandas executions.

### D. Observability & Telemetry
- **Module**: `backend.services.telemetry`
- **Functionality**: Monitored stats covering CPU usage, process memory footprint, query execution latencies, and success distributions.
