# Changelog - QueryIQ Enterprise Edition

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.0.0] - 2026-07-15
### Added
- **Authentication**: JWT access and refresh token authentication, `bcrypt` password hashing, token expiration, password resets, and mock OAuth endpoints.
- **Role-Based Access Control (RBAC)**: Fine-grained security matrix for roles: Super Admin, Admin, Manager, Analyst, and Viewer. Enforced permission-driven decorator scopes on all REST APIs.
- **Multi-Workspace Isolation**: Fully partitioned all dashboards, datasets, reports, saved queries, chat history, and API keys under independent workspaces.
- **Dashboard Versioning**: Dashboard layout version history tracking version numbers, authors, change descriptions, timestamps, and draft/published statuses. Supports restore and layout diff comparison.
- **Scheduler History**: Execution logs (duration, status, started/completed timestamps, error messages, and retry logs) in SQLite.
- **Alert Engine**: Evaluates metrics conditions (e.g. `Profit < 0`) periodically and generates in-app notifications.
- **Observability Dashboard API**: Exposes CPU, RAM, active users/workspaces/datasets, running jobs, scheduler queue size, database query latencies, and dataset memory footprints.
- **Developer API Key Manager**: Allows developer keys generation and revocation.
- **Hardening Benchmarks**: Modular stress-testing suite (`backend/tests/run_enterprise_benchmarks.py`) validating all 10 target benchmark scopes.

---

## [2.0.0] - 2026-07-15
### Added
- **Natural Language Dashboard Editing**: A 100% deterministic layout modifier parsing requests (stacking, deleting, moving, duplicating, renaming cards) without LLM latency.
- **Global Command Palette**: Floating command palette overlay triggered via `Ctrl+K` returning unified results across datasets, dashboards, bookmarks, and chat history.
- **Smart Suggestions**: Programmatically derives interactive clickable chips from the query execution plan.
- **Dataset Health Check**: Exposes diagnostics (missing %, duplicates, IQR outliers, skewness, Pearson correlation, and recommended fixes) inside a beautiful Connect page modal.
- **Smart Auto Insights**: Programmatic facts extractor querying Pareto concentration and MoM growth, using LLM strictly for copywriting polishing.
- **Aesthetic PDF & Excel Exporting**: Multi-sheet spreadsheets and printable CSS layouts.

---

## [1.0.0] - 2026-07-14
### Added
- Initial release supporting CSV, Excel, and SQL connectors, Conversational analytics, Plotly visualizations, semantic models, alerting, and DuckDB analytics.
