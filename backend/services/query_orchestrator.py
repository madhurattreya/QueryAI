"""
backend/services/query_orchestrator.py
───────────────────────────────────────
Core query execution orchestrator.
Manages the pipeline of:
  Request → Intent Parsing → Schema Retrieval → Cache Check → Prompt Generation
  → Code Generation → Sandbox Execution → Self-Healing → Formatting → Telemetry.

Yields SSE progress blocks and final success/error responses.
Moves the 1200+ lines of inline execution logic out of routers/query.py.
"""
from __future__ import annotations
import os
import re
import time
import json
import uuid
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator
import pandas as pd
from sqlalchemy import inspect
import concurrent.futures

import backend.config as config
from backend.models.schemas import QueryRequest
from backend.models.context import ExecutionContext
import backend.services.security as security
import backend.services.engine as engine
import backend.services.router as router_service
import backend.services.formatter as formatter
from backend.services.llm import LLMManager
import backend.services.history_db as db
import backend.services.schema_cache as schema_cache
import backend.services.prompt_builder as prompt_builder
import backend.services.logger as logger_service
import backend.services.kpi_engine as kpi_engine


# ─── Directories ─────────────────────────────────────────────────────────────

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHARTS_DIR = os.path.join(WORKSPACE_ROOT, "data", "charts")
RESULTS_DIR = os.path.join(WORKSPACE_ROOT, "data", "results")


# ─── Helper Functions ─────────────────────────────────────────────────────────

def estimate_tokens(prompt: str) -> int:
    words = len(prompt.split())
    chars = len(prompt)
    return int(words * 1.2 + (chars - words * 5) * 0.25)


def get_active_dataset_details() -> Tuple[str, str, str]:
    active_name = "unknown"
    active_hash = "no_data"
    
    if config.current_source_type == "file" and config.datasets:
        active_name = list(config.datasets.keys())[0]
        active_hash = "|".join([f"{k}:{engine.get_df_hash(v)}" for k, v in sorted(config.datasets.items())])
    elif config.current_source_type == "sql" and config.database_engine:
        active_name = config.db_flavor or "sql"
        active_hash = str(config.database_engine.url)
        
    ds_id = db.get_or_create_dataset(active_name)
    return active_name, active_hash, ds_id


def generate_smart_suggestions(question: str, parsed_query=None) -> List[str]:
    suggestions = []
    cat_cols = []
    num_cols = []
    date_cols = []

    if config.datasets:
        df_name = list(config.datasets.keys())[0]
        df = config.datasets[df_name]
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                num_cols.append(col)
            elif pd.api.types.is_datetime64_any_dtype(df[col]) or "date" in col.lower():
                date_cols.append(col)
            else:
                cat_cols.append(col)

    groupby = getattr(parsed_query, "groupby", []) if parsed_query else []
    aggregations = getattr(parsed_query, "aggregations", []) if parsed_query else []
    measure = aggregations[0]["column"] if aggregations else (num_cols[0] if num_cols else "total")

    if groupby:
        gb_col = groupby[0]
        suggestions.append(f"Show top 5 {gb_col} by {measure}")
        if len(num_cols) > 1:
            other_num = [c for c in num_cols if c.lower() != measure.lower()]
            if other_num:
                suggestions.append(f"Compare {other_num[0]} across all {gb_col}")

    if cat_cols:
        suggestions.append(f"Show breakdown by {cat_cols[0]}")
        if len(cat_cols) > 1:
            suggestions.append(f"What are the top categories in {cat_cols[1]}?")

    if num_cols:
        suggestions.append(f"What is the average {num_cols[0]}?")
        if len(num_cols) > 1:
            suggestions.append(f"Show sum of {num_cols[1]}")

    if date_cols:
        suggestions.append(f"Show monthly trend of {measure}")

    # Fallback to schema-based options if still under 3
    if len(suggestions) < 3:
        if cat_cols and num_cols:
            suggestions.append(f"Show total {num_cols[0]} by {cat_cols[0]}")
        if num_cols:
            suggestions.append(f"Show maximum and minimum {num_cols[0]}")
        suggestions.append("Show overall summary of dataset")

    # Remove duplicates and match user query
    seen = set()
    cleaned = []
    q_clean = question.lower().strip()
    for s in suggestions:
        s_clean = s.strip()
        if s_clean.lower() not in seen and s_clean.lower() != q_clean:
            seen.add(s_clean.lower())
            cleaned.append(s_clean)

    return cleaned[:4]


def generate_local_explanation(question: str, result, parsed_query) -> Optional[str]:
    if isinstance(result, pd.DataFrame):
        if result.empty:
            filters_info = f": {parsed_query.filters}" if parsed_query and getattr(parsed_query, "filters", None) else "."
            return f"The analysis returned 0 matching records for your filter criteria{filters_info}"

        # Value count / unique breakdown result
        if "COUNT" in result.columns or "count" in result.columns:
            main_col = result.columns[0]
            total_unique = len(result)
            count_col = "COUNT" if "COUNT" in result.columns else "count"
            top_vals = [f"**{row[main_col]}** ({row[count_col]:,})" for _, row in result.head(5).iterrows()]
            top_str = ", ".join(top_vals)
            return (
                f"Found **{total_unique} unique values** for **{main_col}**.\n\n"
                f"Top entries: {top_str}" + (f", and {total_unique - 5} more." if total_unique > 5 else ".")
            )

        if result.shape == (1, 1):
            val = result.iloc[0, 0]
            val_str = f"{val:,.2f}" if isinstance(val, float) else f"{val:,}" if isinstance(val, int) else str(val)
            col_name = result.columns[0]
            return f"The calculated **{col_name}** is **{val_str}**."

        if result.shape[0] == 1:
            row_dict = result.iloc[0].to_dict()
            desc = ", ".join([f"**{k}**: {v:,.2f}" if isinstance(v, float) else f"**{k}**: {v:,}" if isinstance(v, int) else f"**{k}**: {v}" for k, v in row_dict.items() if pd.notnull(v)])
            return f"Analysis returned 1 record:\n{desc}"

        row_count = len(result)
        cols_str = ", ".join([f"**{c}**" for c in result.columns[:4]])
        return f"Found **{row_count:,} records** matching your query (columns: {cols_str})."

    elif isinstance(result, (int, float, str, bool)):
        val_str = f"{result:,.2f}" if isinstance(result, float) else f"{result:,}" if isinstance(result, int) else str(result)
        measure_name = parsed_query.execution_plan.get("measure") if parsed_query and hasattr(parsed_query, "execution_plan") else "Result"
        return f"The calculated **{measure_name}** is **{val_str}**."

    return None


def compile_badges_and_explanation(total_start: float, dataset_name: str, engine_type: str, llm_used: bool, parsed_query) -> Tuple[dict, dict]:
    badge_level = "Deterministic"
    badge_desc = "No AI Generation"
    badge_score = round((parsed_query.confidence or 0.95) * 100) if parsed_query else 95
    
    if engine_type == "hybrid":
        badge_level = "Hybrid"
        badge_desc = "Planner Assisted"
        badge_score = round((parsed_query.confidence or 0.80) * 100) if parsed_query else 80
    elif llm_used or engine_type in ["llm", "prediction"]:
        badge_level = "AI Generated"
        badge_desc = "LLM Assisted"
        badge_score = round((parsed_query.confidence or 0.50) * 100) if parsed_query else 50
        
    confidence_badge = {
        "level": badge_level,
        "score": badge_score,
        "description": badge_desc
    }

    query_explanation = {
        "dataset": dataset_name,
        "measure": parsed_query.execution_plan.get("measure") or (parsed_query.aggregations[0]["column"] if parsed_query and parsed_query.aggregations else "None"),
        "aggregation": parsed_query.aggregations[0]["operator"].upper() if parsed_query and parsed_query.aggregations else "None",
        "groupby": parsed_query.execution_plan.get("groupby") if parsed_query else [],
        "sorting": parsed_query.execution_plan.get("sorting") if parsed_query else [],
        "limit": parsed_query.execution_plan.get("limit") if parsed_query else "None",
        "engine": "Deterministic Engine" if badge_level == "Deterministic" else "Hybrid Planner" if badge_level == "Hybrid" else "LLM Generation Engine",
        "execution_time": f"{round((time.time() - total_start) * 1000)} ms"
    }
    
    return confidence_badge, query_explanation


def background_tasks_worker(
    conv_id: str,
    user_msg_id: str,
    assistant_msg_id: str,
    question: str,
    code: str,
    result_preview_str: str,
    result_file_path: str,
    chart_id: str,
    explanation: str,
    time_taken: float,
    dataset_rows: int,
    prompt_size: int,
    engine_used: str,
    debug_info_str: str,
    chart_png_path: str,
    chart_html_path: str,
    chart_meta_path: str,
    dataset_id: str
):
    db.add_message(conv_id=conv_id, role="user", content=question)
    db.add_message(
        conv_id=conv_id,
        role="assistant",
        content=explanation or "Result processed.",
        generated_code=code,
        result_preview=result_preview_str,
        result_file=result_file_path,
        chart_id=chart_id,
        execution_time=time_taken,
        rows=dataset_rows,
        prompt_size=prompt_size,
        engine_used=engine_used,
        debug_info=debug_info_str
    )

    if chart_id and os.path.exists(chart_html_path):
        os.makedirs(CHARTS_DIR, exist_ok=True)
        with open(chart_meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "id": chart_id,
                "conversation_id": conv_id,
                "question": question,
                "created_at": datetime.now().isoformat(),
                "dataset_id": dataset_id,
                "rows": dataset_rows
            }, f)
        db.add_chart(chart_id, conv_id, assistant_msg_id, dataset_id, question, "plotly", chart_html_path, chart_png_path)

    all_messages = db.get_messages(conv_id, limit=None)
    if len(all_messages) >= 10 and len(all_messages) % 5 == 0:
        history_text = ""
        for m in all_messages:
            history_text += f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:100]}\n"
        summary_prompt = prompt_builder.build_prompt("summary", history_text=history_text)
        try:
            model = config.settings.get("model", config.app_settings.default_model)
            manager = LLMManager()
            summary, _, _llm_metrics = manager.call_llm_with_fallback(summary_prompt, model)
            db.update_conversation_summary(conv_id, summary.strip())
        except Exception:
            pass

    try:
        debug_info = json.loads(debug_info_str) if debug_info_str else {}
        logger_service.log_telemetry({
            "status": "success",
            "conversation_id": conv_id,
            "engine_used": engine_used,
            "execution_time": time_taken,
            "rows_returned": dataset_rows,
            "prompt_size": prompt_size,
            "model_used": debug_info.get("model", "unknown"),
            "timings": debug_info.get("timings", {})
        })
    except Exception:
        pass

    try:
        db.cleanup_charts(max_age_days=7, max_charts=1000)
    except Exception:
        pass
        
    try:
        engine.persist_cache_to_disk()
    except Exception:
        pass


# ─── Query Orchestrator ───────────────────────────────────────────────────────

class QueryOrchestrator:
    """
    Orchestrates the entire query execution life-cycle.
    Provides async streaming generator yielding SSE chunks.
    """

    async def execute_query_stream(
        self, req: QueryRequest, background_tasks: Any, workspace_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        total_start = time.time()
        llm_metrics_accumulator = []
        request_id = str(uuid.uuid4())
        
        yield json.dumps({"type": "progress", "step": "Receiving Request"}) + "\n"
        
        question = req.question
        conversation_id = req.conversation_id
        assistant_msg_id = str(uuid.uuid4())
        
        timings = {
            "Routing": 0.0, "Cache lookup": 0.0, "Schema lookup": 0.0,
            "Dataset loading": 0.0, "Prompt creation": 0.0, "Planner": 0.0,
            "Generator": 0.0, "Execution": 0.0, "Chart generation": 0.0,
            "Formatting": 0.0, "Serialization": 0.0, "Response": 0.0
        }
        
        # Load/Create Conversation details
        t_start = time.time()
        if not conversation_id or not db.get_conversation(conversation_id):
            conversation_id = db.create_conversation(title=question[:50], workspace_id=workspace_id)
        conv_details = db.get_conversation(conversation_id)
        timings["Routing"] += time.time() - t_start

        # Load active dataset
        yield json.dumps({"type": "progress", "step": "Loading Active Dataset"}) + "\n"
        t_start_ds = time.time()
        dataset_name, dataset_hash, dataset_id = get_active_dataset_details()
        timings["Dataset loading"] = time.time() - t_start_ds
        
        # KPI dashboard precomputation
        active_df = None
        if config.current_source_type == "file" and config.datasets:
            active_df_name = list(config.datasets.keys())[0]
            active_df = config.datasets[active_df_name]
            if active_df is not None and dataset_hash not in kpi_engine.kpi_cache:
                kpi_engine.compute_and_cache_kpis(active_df_name, active_df, dataset_hash)
        
        # Guard: No datasets loaded
        if (config.current_source_type == "file" and not config.datasets) or (config.current_source_type == "sql" and not config.database_engine):
            source_label = "database" if config.current_source_type == "sql" else "file dataset"
            yield json.dumps({
                "type": "error", "status": "error",
                "error": f"No active {source_label} is currently loaded. Please go to the Datasets tab and load one.",
                "time_taken": round(time.time() - total_start, 3)
            }) + "\n"
            return

        # Guard: Live database ping
        if config.current_source_type == "sql" and config.database_engine:
            try:
                from sqlalchemy import text
                with config.database_engine.connect() as test_conn:
                    test_conn.execute(text("SELECT 1"))
            except Exception as conn_err:
                yield json.dumps({
                    "type": "error", "status": "error",
                    "error": f"Cannot connect to the database: {str(conn_err)[:200]}",
                    "time_taken": round(time.time() - total_start, 3)
                }) + "\n"
                return

        # Dataset switched context reset
        if conv_details and conv_details.get("dataset_id") != dataset_id:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            cursor.execute("UPDATE conversations SET dataset_id = ?, summary = NULL WHERE id = ?", (dataset_id, conversation_id))
            conn.commit()
            conn.close()
            conv_details["summary"] = None

        # ─── Step 1: Routing & Classification ─────────────────────────────────
        yield json.dumps({"type": "progress", "step": "Routing Query"}) + "\n"
        t_start_route = time.time()
        
        prev_plan = None
        try:
            recent_messages = db.get_messages(conversation_id, limit=2)
            if recent_messages:
                for m in reversed(recent_messages):
                    if m["role"] == "assistant" and m.get("debug_info"):
                        info = json.loads(m["debug_info"])
                        if info.get("execution_plan"):
                            prev_plan = info["execution_plan"]
                            break
        except Exception:
            pass

        router_res = router_service.classify_query_engine_detailed(question, prev_plan=prev_plan, conversation_id=conversation_id)
        engine_type = router_res["engine"]
        complexity = router_service.detect_complexity(question)
        llm_used = router_res.get("llm_used", False)
        parsed_query = router_res.pop("parsed_query", None)
        timings["Routing"] += time.time() - t_start_route

        # ─── Step 2: Schema Building ───────────────────────────────────────────
        yield json.dumps({"type": "progress", "step": "Building Cached Schema"}) + "\n"
        t_start_schema = time.time()
        
        available_sources = list(config.datasets.keys()) if config.current_source_type == "file" else []
        if config.current_source_type == "sql" and config.database_engine:
            try:
                available_sources = inspect(config.database_engine).get_table_names()
            except Exception:
                pass
                
        relevant_sources = router_service.select_relevant_sources(question, available_sources)
        selected_schema_desc = ""
        selected_profile_desc = ""
        for name in relevant_sources:
            selected_schema_desc += schema_cache.get_table_schema(name) + "\n"
            selected_profile_desc += schema_cache.get_table_profile(name) + "\n"
        timings["Schema lookup"] = time.time() - t_start_schema

        # ─── Step 2.5: Hybrid Planner ──────────────────────────────────────────
        if engine_type == "hybrid" and parsed_query:
            yield json.dumps({"type": "progress", "step": "Generating Hybrid Execution Plan"}) + "\n"
            t_start_hybrid = time.time()
            hybrid_prompt = prompt_builder.build_prompt(
                "hybrid_planner",
                schema_desc=selected_schema_desc,
                profile_desc=selected_profile_desc,
                question=question
            )
            try:
                model = config.settings.get("model", config.app_settings.default_model)
                manager = LLMManager()
                raw_plan_json, _, _llm_metrics = manager.call_llm_with_fallback(hybrid_prompt, model, 0.0)
                if _llm_metrics:
                    llm_metrics_accumulator.append(_llm_metrics)
                
                clean_str = raw_plan_json.strip().strip("`").replace("json\n", "").strip()
                if clean_str.startswith("```"):
                    clean_str = clean_str.split("```")[1].strip()
                
                plan_data = json.loads(clean_str)
                parsed_query.intent = plan_data.get("intent", parsed_query.intent)
                parsed_query.filters = plan_data.get("filters", parsed_query.filters)
                parsed_query.aggregations = plan_data.get("aggregations", parsed_query.aggregations)
                parsed_query.execution_plan["groupby"] = plan_data.get("groupby", parsed_query.execution_plan.get("groupby", []))
                parsed_query.sorting = plan_data.get("sorting", parsed_query.sorting)
                if plan_data.get("limit"):
                    parsed_query.execution_plan["limit"] = plan_data.get("limit")
                
                from backend.services.query_parser import compile_to_dsl
                parsed_query.execution_plan["dsl"] = compile_to_dsl(parsed_query.execution_plan)
            except Exception:
                pass
            timings["Planner"] = time.time() - t_start_hybrid

        # ─── Step 3: Cache Verification ────────────────────────────────────────
        t_start_cache = time.time()
        model = config.settings.get("model", config.app_settings.default_model)
        temperature = 0.0
        
        template_text = prompt_builder.get_template(engine_type or "pandas")
        prompt_template_hash = hashlib.sha256(template_text.encode("utf-8")).hexdigest()
        summary = conv_details.get("summary") if conv_details else ""
        conversation_context_hash = hashlib.sha256((summary or "").encode("utf-8")).hexdigest()
        
        cache_key = engine.get_sha256_cache_key(
            dataset_hash=dataset_hash,
            question=question,
            conversation_id=conversation_id,
            selected_model=model,
            temperature=temperature,
            dataset_version=dataset_id,
            router_type=engine_type,
            prompt_template_hash=prompt_template_hash,
            conversation_context_hash=conversation_context_hash
        )
        cached_val = engine.get_cached_result(cache_key)
        timings["Cache lookup"] = time.time() - t_start_cache
        
        if cached_val:
            yield json.dumps({"type": "progress", "step": "Cache hit! Returning cached result..."}) + "\n"
            timings["Response"] = time.time() - total_start
            
            max_val = -1.0
            slowest = "None"
            for stage, val in timings.items():
                if stage != "Response" and val > max_val:
                    max_val = val
                    slowest = stage
            
            cached_val["cached"] = True
            cached_val["conversation_id"] = conversation_id
            cached_val["execution_time"] = round(timings["Response"], 3)
            cached_val["type"] = "success"
            cached_val["debug_info"]["timings"] = {k: round(v, 4) for k, v in timings.items()}
            cached_val["debug_info"]["cache_hit"] = True
            cached_val["debug_info"]["slowest_stage"] = f"{slowest} ({max_val * 1000:.1f}ms)"
            yield json.dumps(cached_val) + "\n"
            return

        context = ExecutionContext(
            conversation_id=conversation_id,
            dataset_id=dataset_id,
            dataset_version=dataset_id,
            engine=engine_type,
            schema_desc=selected_schema_desc,
            profile_desc=selected_profile_desc,
            model=model,
            question=question,
            complexity=complexity,
            chart_requested=engine_type == "visualization"
        )

        # ─── Step 4: LLM Planner Step ─────────────────────────────────────────
        plan_block = ""
        if complexity == "complex" and engine_type in ["aggregation", "filter", "visualization", "prediction"]:
            yield json.dumps({"type": "progress", "step": "Generating query execution plan..."}) + "\n"
            t_start = time.time()
            plan_prompt = prompt_builder.build_prompt(
                "planner",
                schema_desc=selected_schema_desc,
                profile_desc=selected_profile_desc,
                question=question
            )
            try:
                manager = LLMManager()
                plan, _, _llm_metrics = manager.call_llm_with_fallback(plan_prompt, model, temperature)
                if _llm_metrics:
                    llm_metrics_accumulator.append(_llm_metrics)
                context.execution_plan = plan.strip()
                plan_block = f"Planned Steps:\n{context.execution_plan}\n"
            except Exception:
                pass
            timings["Planner"] = time.time() - t_start

        # History context
        recent_messages = db.get_messages(conversation_id, limit=5)
        history_block = ""
        if recent_messages:
            history_block = "\nRecent Conversation History:\n"
            for m in recent_messages:
                role_label = "User" if m["role"] == "user" else "Assistant"
                content_clean = re.sub(r"```.*?```", "[Code]", m["content"], flags=re.DOTALL)
                history_block += f"{role_label}: {content_clean[:120].strip()}\n"
        summary_block = f"Conversation Summary: {conv_details.get('summary')}\n" if conv_details and conv_details.get("summary") else ""
        
        chart_uuid = str(uuid.uuid4())
        chart_html_path = os.path.join(CHARTS_DIR, f"{chart_uuid}.html")
        chart_png_path = os.path.join(CHARTS_DIR, f"{chart_uuid}.png")
        chart_meta_path = os.path.join(CHARTS_DIR, f"{chart_uuid}_metadata.json")
        os.makedirs(CHARTS_DIR, exist_ok=True)

        result = None
        dataset_rows = 0
        active_chart_id = None

        # ─── Step 5: Deterministic Execution Path ──────────────────────────────
        if not llm_used:
            yield json.dumps({"type": "progress", "step": "Executing Plan (Deterministic Engine)"}) + "\n"
            
            if engine_type == "visualization":
                t_start_chart = time.time()
                chart_type = parsed_query.chart_type
                known_cols = []
                active_df_name = ""
                active_df = None  # Initialize before conditional assignment

                # ── Source resolution: file OR SQL ────────────────────────────
                if config.datasets:
                    # File-based dataset already in memory
                    active_df_name = list(config.datasets.keys())[0]
                    active_df = config.datasets[active_df_name]
                    known_cols = active_df.columns.tolist()

                elif config.current_source_type == "sql" and config.database_engine:
                    # SQL connection — pull a sample from the most relevant table
                    yield json.dumps({"type": "progress", "step": "Fetching SQL data for chart..."}) + "\n"
                    try:
                        from sqlalchemy import inspect as sa_inspect, text as sa_text
                        inspector = sa_inspect(config.database_engine)
                        tables = inspector.get_table_names()
                        if tables:
                            # Try to pick the table most relevant to the question
                            q_lower = question.lower()
                            best_table = tables[0]
                            for tbl in tables:
                                if tbl.lower() in q_lower:
                                    best_table = tbl
                                    break
                            active_df_name = best_table
                            with config.database_engine.connect() as _conn:
                                active_df = pd.read_sql(
                                    sa_text(f"SELECT * FROM {best_table} LIMIT 5000"),
                                    _conn
                                )
                            known_cols = active_df.columns.tolist()
                    except Exception as _sql_err:
                        yield json.dumps({
                            "type": "error", "status": "error",
                            "error": f"Could not fetch SQL data for chart: {str(_sql_err)}",
                            "time_taken": round(time.time() - total_start, 3)
                        }) + "\n"
                        return

                if active_df is None:
                    err_msg = (
                        "No dataset is currently loaded. Please upload or activate a dataset "
                        "from the Datasets panel before creating charts."
                    )
                    yield json.dumps({"type": "error", "status": "error", "error": err_msg, "time_taken": round(time.time() - total_start, 3)}) + "\n"
                    return
                if active_df.empty:
                    err_msg = (
                        f"The active dataset '{active_df_name}' has no rows. "
                        "Please re-upload the file or switch to a dataset that contains data."
                    )
                    yield json.dumps({"type": "error", "status": "error", "error": err_msg, "time_taken": round(time.time() - total_start, 3)}) + "\n"
                    return

                # ── Apply parsed query filters to chart dataset ──────────────────
                chart_df = active_df.copy()
                filter_descs = []
                if parsed_query and getattr(parsed_query, "filters", None):
                    for f in parsed_query.filters:
                        col = f.get("column")
                        op = f.get("operator", "==")
                        val = f.get("value")
                        if col in chart_df.columns and val is not None:
                            if op in ("==", "equal", "="):
                                chart_df = chart_df[chart_df[col].astype(str).str.lower() == str(val).lower()]
                                filter_descs.append(f"{col} = '{val}'")
                            elif op == "!=":
                                chart_df = chart_df[chart_df[col].astype(str).str.lower() != str(val).lower()]
                            elif op == ">":
                                chart_df = chart_df[pd.to_numeric(chart_df[col], errors='coerce') > float(val)]
                            elif op == "<":
                                chart_df = chart_df[pd.to_numeric(chart_df[col], errors='coerce') < float(val)]
                            elif op == ">=":
                                chart_df = chart_df[pd.to_numeric(chart_df[col], errors='coerce') >= float(val)]
                            elif op == "<=":
                                chart_df = chart_df[pd.to_numeric(chart_df[col], errors='coerce') <= float(val)]

                if chart_df.empty:
                    chart_df = active_df.copy()
                    filter_descs = []

                # ── Column resolution with schema validation ──────────────────
                cols_from_parser = parsed_query.entities.get("matched_columns", [])
                valid_cols = [c for c in cols_from_parser if c in known_cols]
                
                if not valid_cols and known_cols:
                    q_words = set(question.lower().split())
                    for col in known_cols:
                        col_words = set(col.lower().replace("_", " ").split())
                        if col_words & q_words:
                            valid_cols.append(col)
                        if len(valid_cols) >= 3:
                            break

                # Separate valid columns into numeric vs categorical
                numeric_cols = [c for c in valid_cols if pd.api.types.is_numeric_dtype(active_df[c])]
                cat_cols = [c for c in valid_cols if not pd.api.types.is_numeric_dtype(active_df[c])]

                if not numeric_cols:
                    all_num = [c for c in known_cols if pd.api.types.is_numeric_dtype(active_df[c])]
                    if all_num:
                        rev_cols = [c for c in all_num if "revenue" in c.lower() or "sales" in c.lower() or "profit" in c.lower()]
                        numeric_cols.append(rev_cols[0] if rev_cols else all_num[0])

                if not cat_cols:
                    filtered_cols = [f.get("column") for f in (parsed_query.filters if parsed_query and getattr(parsed_query, "filters", None) else [])]
                    all_cat = [c for c in known_cols if not pd.api.types.is_numeric_dtype(active_df[c]) and c not in filtered_cols]
                    if not all_cat:
                        all_cat = [c for c in known_cols if not pd.api.types.is_numeric_dtype(active_df[c])]
                    if all_cat:
                        cat_cols.append(all_cat[0])

                col_x = cat_cols[0] if cat_cols else (valid_cols[0] if valid_cols else (known_cols[0] if known_cols else None))
                col_y = numeric_cols[0] if numeric_cols else (valid_cols[1] if len(valid_cols) > 1 else None)

                if col_x is None:
                    yield json.dumps({
                        "type": "error", "status": "error",
                        "error": f"Could not identify chart columns. Available columns: {', '.join(known_cols[:10])}",
                        "time_taken": round(time.time() - total_start, 3)
                    }) + "\n"
                    return

                # Aggregation for bar/line/pie charts
                if not chart_type:
                    chart_type = "bar"

                if chart_type in ("bar", "line", "pie", "area") and col_x and col_y and col_x in chart_df.columns and col_y in chart_df.columns:
                    chart_df = chart_df.groupby(col_x, as_index=False)[col_y].sum()
                    chart_df = chart_df.sort_values(by=col_y, ascending=False).head(20)

                import backend.services.chart_factory as cf
                filter_suffix = f" ({', '.join(filter_descs)})" if filter_descs else ""
                title = f"{chart_type.title()} of {col_y or col_x}" + (f" by {col_x}" if col_y else "") + filter_suffix

                if chart_type == "bar":
                    fig = cf.build_bar_chart(chart_df, col_x, col_y, title)
                elif chart_type == "line":
                    fig = cf.build_line_chart(chart_df, col_x, col_y, title)
                elif chart_type == "box":
                    fig = cf.build_box_plot(chart_df, col_x, col_y, title)
                elif chart_type == "histogram":
                    fig = cf.build_histogram(chart_df, col_x, title)
                elif chart_type == "pie":
                    fig = cf.build_pie_chart(chart_df, col_x, col_y, title)
                elif chart_type == "heatmap":
                    fig = cf.build_heatmap(chart_df, title=title)
                elif chart_type == "area":
                    fig = cf.build_area_chart(chart_df, col_x, col_y, title)
                elif chart_type == "treemap":
                    fig = cf.build_treemap(chart_df, [col_x], col_y, title)
                else:
                    fig = cf.build_scatter_chart(chart_df, col_x, col_y or col_x, title)

                cf.create_chart_assets(fig, CHARTS_DIR, chart_uuid)
                result = "Chart saved to chart.png and chart.html"
                code = f"fig = px.{chart_type or 'bar'}(df, x='{col_x}'" + (f", y='{col_y}'" if col_y else "") + f", title='{title}')\ncf.create_chart_assets(fig, CHARTS_DIR, '{chart_uuid}')"
                context.code = code
                context.raw_result = pd.DataFrame([{"Result": result}])
                context.explanation = f"Generated a predefined {chart_type or 'bar'} chart for {col_y or col_x}" + (f" by {col_x}" if col_y else "") + (f" filtered on {', '.join(filter_descs)}." if filter_descs else ".")
                active_chart_id = chart_uuid
                timings["Chart generation"] = time.time() - t_start_chart

            elif engine_type == "insight":
                t_start_insight = time.time()
                from backend.services.insight_engine import generate_dataset_insights
                df_name = ""
                df = None
                if config.datasets:
                    df_name = list(config.datasets.keys())[0]
                    df = config.datasets[df_name]
                insights_text = generate_dataset_insights(df_name, df)
                context.explanation = insights_text
                context.raw_result = pd.DataFrame([{"Insights": insights_text}])
                code = "# Programmatic Insight Engine (no code executed)"
                context.code = code
                timings["Execution"] = time.time() - t_start_insight

            elif engine_type == "kpi_dashboard":
                t_start_kpi = time.time()
                kpis = kpi_engine.kpi_cache.get(dataset_hash)
                if not kpis and active_df is not None:
                    kpis = kpi_engine.compute_and_cache_kpis(dataset_name, active_df, dataset_hash)
                if kpis:
                    result = pd.DataFrame([{"KPI": k.upper(), "Value": str(v)} for k, v in kpis.items() if not isinstance(v, list)])
                    context.raw_result = result
                    code = "# Precomputed KPI Dashboard Overview"
                    context.code = code
                    context.explanation = (
                        f"Business Dashboard Overview for **{dataset_name}**:\n"
                        f"- **Total Revenue**: ${kpis.get('revenue', 0):,.2f}\n"
                        f"- **Total Profit**: ${kpis.get('profit', 0):,.2f} (Margin: {kpis.get('margin', 0)}%)\n"
                        f"- **Total Orders**: {kpis.get('orders', 0):,} from {kpis.get('customers', 0):,} customers\n"
                        f"- **Average Order Value**: ${kpis.get('aov', 0):,.2f}"
                    )
                else:
                    context.raw_result = pd.DataFrame()
                    code = "# Precomputed KPI Dashboard"
                    context.code = code
                    context.explanation = "No KPI dashboard is currently cached."
                timings["Execution"] = time.time() - t_start_kpi

            elif engine_type == "metadata":
                t_start_meta = time.time()
                tables = list(config.datasets.keys()) if config.current_source_type == "file" else []
                if config.current_source_type == "sql" and config.database_engine:
                    try:
                        tables = inspect(config.database_engine).get_table_names()
                    except Exception:
                        pass
                tables_str = ", ".join(tables)
                context.explanation = f"Metadata summary: Currently loaded tables: {tables_str}"
                context.raw_result = pd.DataFrame([{"Tables": tables}])
                code = "# Preloaded Metadata check"
                context.code = code
                timings["Execution"] = time.time() - t_start_meta

            elif engine_type == "general_chat":
                t_start_chat = time.time()
                context.explanation = "Hello! I am QueryIQ, your enterprise AI data analyst. How can I help you explore your data today?"
                context.raw_result = pd.DataFrame([{"Message": context.explanation}])
                code = "# Direct chat response"
                context.code = code
                timings["Execution"] = time.time() - t_start_chat

            elif engine_type == "ambiguity":
                t_start_amb = time.time()
                reason = parsed_query.execution_plan.get("match_reason") if parsed_query else "Ambiguous columns detected."
                context.explanation = f"Ambiguity detected: {reason}\nCould you please clarify your request?"
                context.raw_result = pd.DataFrame([{"Status": "Ambiguous", "Reason": reason}])
                code = "# Ambiguity Resolution Required"
                context.code = code
                timings["Execution"] = time.time() - t_start_amb

            else:
                # ─── Aggregations, filters, sortings ─────────────────────────────
                t_start_exec = time.time()
                from backend.services.query_engine import execute_parsed_query
                from backend.services.join_planner import JoinPlanner
                
                planner = JoinPlanner()
                merged_df, join_code, matched_tables = planner.plan_and_join_datasets(parsed_query)
                
                if matched_tables and len(matched_tables) > 1:
                    df = merged_df
                    df_name = f"merged_{'_'.join(matched_tables)}"
                    result, query_code = execute_parsed_query(parsed_query, df, df_name=df_name)
                    code_expr = f"{join_code}\nresult = {query_code}"
                else:
                    df_name = matched_tables[0] if matched_tables else (list(config.datasets.keys())[0] if config.datasets else "df")
                    df = config.datasets.get(df_name)
                    result, query_code = execute_parsed_query(parsed_query, df, df_name=df_name)
                    code_expr = query_code
                    
                context.raw_result = result
                code = f"result = {code_expr}"
                context.code = code
                
                local_exp = generate_local_explanation(question, result, parsed_query)
                if local_exp:
                    context.explanation = local_exp
                elif parsed_query and parsed_query.intent == "id_lookup" and not result.empty:
                    row_dict = result.iloc[0].to_dict()
                    kv_desc = ", ".join([f"{k}: {v}" for k, v in row_dict.items() if pd.notnull(v)])
                    context.explanation = f"I found the record for {parsed_query.execution_plan.get('id_column')} {parsed_query.execution_plan.get('id_value')}:\n{kv_desc}"
                elif isinstance(result, (pd.DataFrame, pd.Series)):
                    context.explanation = f"Found {len(result)} records matching your query."
                else:
                    context.explanation = f"Calculated result: {result}"
                timings["Execution"] = time.time() - t_start_exec

            # Formatting
            t_start_fmt = time.time()
            result = context.raw_result
            show_all = any(x in question.lower() for x in ["show all", "all rows", "all records", "everything"])
            limit_rows = config.app_settings.preview_rows
            
            if isinstance(result, pd.DataFrame):
                for col in result.columns:
                    if pd.api.types.is_datetime64_any_dtype(result[col]):
                        result[col] = result[col].astype(str)
                import numpy as np
                result = result.replace({np.nan: None, pd.NaT: None})
                dataset_rows = len(result)
                
                result_preview = result.head(limit_rows) if (not show_all and dataset_rows > limit_rows) else result
                result_preview_str = json.dumps(result_preview.to_dict(orient="records"))
                
                if dataset_rows > 100:
                    os.makedirs(RESULTS_DIR, exist_ok=True)
                    parquet_filename = f"{str(uuid.uuid4())}.parquet"
                    result_file_path = os.path.join(RESULTS_DIR, parquet_filename)
                    result.to_parquet(result_file_path)
                else:
                    result_file_path = ""
            elif isinstance(result, pd.Series):
                if pd.api.types.is_datetime64_any_dtype(result):
                    result = result.astype(str)
                if pd.api.types.is_datetime64_any_dtype(result.index):
                    result.index = result.index.astype(str)
                import numpy as np
                result = result.replace({np.nan: None, pd.NaT: None})
                dataset_rows = len(result)
                
                result_preview = result.head(limit_rows) if (not show_all and len(result) > limit_rows) else result
                series_dict = [{"Index": str(k), "Value": str(v)} for k, v in result_preview.items()]
                result_preview_str = json.dumps(series_dict)
                result_file_path = ""
            else:
                dataset_rows = 1
                result_preview_str = json.dumps([{"Result": str(result)}])
                result_file_path = ""
            timings["Formatting"] = time.time() - t_start_fmt
            
            t_start_ser = time.time()
            total_taken = time.time() - total_start
            timings["Response"] = total_taken
            
            max_val = -1.0
            slowest = "None"
            for stage, val in timings.items():
                if stage != "Response" and val > max_val:
                    max_val = val
                    slowest = stage
                    
            confidence_badge, query_explanation = compile_badges_and_explanation(
                total_start, dataset_name, engine_type, llm_used, parsed_query
            )

            heuristics_data = {}
            try:
                from backend.services.insight_engine import run_result_heuristics
                if isinstance(result, pd.DataFrame):
                    heuristics_data = run_result_heuristics(result)
            except Exception:
                pass

            from backend.services.schema_index import SchemaIndexRegistry
            
            res_col = parsed_query.aggregations[0]["column"] if (parsed_query and parsed_query.aggregations) else "None"
            df_nm = df_name if 'df_name' in locals() else dataset_name
            sem_tp = "Unknown"
            if res_col != "None" and df_nm:
                idx = SchemaIndexRegistry.get(df_nm)
                if idx:
                    sem_tp = idx.get_column_semantic_type(res_col)
            
            debug_info = {
                "timings": {k: round(v, 4) for k, v in timings.items()},
                "complexity": complexity,
                "engine_used": engine_type,
                "prompt_size": 0,
                "model": "deterministic_query_engine",
                "cache_hit": False,
                "auto_retry_count": 0,
                "router_decision": router_res.get("engine", "deterministic") if isinstance(router_res, dict) else str(router_res),
                "slowest_stage": f"{slowest} ({max_val * 1000:.1f}ms)",
                "cache_used": False,
                "llm_used": False,
                "parser_used": True,
                "question": question,
                "parsed_intent": parsed_query.intent if parsed_query else "unknown",
                "execution_plan": parsed_query.execution_plan if parsed_query else {},
                "matched_dataset": df_nm,
                "matched_columns": parsed_query.entities.get("matched_columns", []) if parsed_query else [],
                "applied_pandas_code": code,
                "rows_before": len(df) if ('df' in locals() and df is not None) else 0,
                "rows_after": dataset_rows,
                "execution_time": timings.get("Execution", 0.0),
                "returned_result": result_preview_str,
                "confidence_badge": confidence_badge,
                "query_explanation": query_explanation,
                "heuristics": heuristics_data,
                "request_id": request_id,
                "intent": parsed_query.intent if parsed_query else "unknown",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "generation_time_ms": 0.0,
                "execution_time_ms": timings.get("Execution", 0.0) * 1000,
                "validation_result": None,
                "recovery_steps": [],
                "column_resolution_steps": [],
                "confidence_score": parsed_query.confidence if parsed_query else 0.0,
                
                # New semantic telemetry fields
                "detected_metric": parsed_query.entities.get("detected_metric", "Unknown") if parsed_query else "Unknown",
                "resolved_column": res_col,
                "semantic_type": str(sem_tp),
                "confidence": parsed_query.confidence if parsed_query else 0.0,
                "aggregation": parsed_query.aggregations[0]["operator"] if (parsed_query and parsed_query.aggregations) else "None",
                "reason": (
                    parsed_query.execution_plan.get("match_reason") or 
                    (router_res.get("fallback_reason") if isinstance(router_res, dict) else None) or 
                    ""
                ) if parsed_query else "",
                "fallback_used": router_res.get("fallback_used", False) if isinstance(router_res, dict) else False,
            }
            
            suggestions_list = generate_smart_suggestions(question, parsed_query)
                
            explanation_level = config.settings.get("explain_level", "Normal")
            if explanation_level == "Technical":
                technical_appendix = (
                    f"\n\n---\n"
                    f"### Technical Appendix\n"
                    f"- **Execution Engine**: {engine_type.upper()} Engine\n"
                    f"- **Formulas / Query Code**:\n```python\n{context.code}\n```\n"
                    f"- **Slowest Stage**: {slowest}\n"
                    f"- **Dataset Rows Processed**: {dataset_rows}\n"
                )
                context.explanation += technical_appendix

            debug_info_str = json.dumps(debug_info)
            timings["Serialization"] = time.time() - t_start_ser
            
            # Save cache
            cached_payload = {
                "status": "success", "dataset_id": dataset_id,
                "model": "deterministic_query_engine", "rows": dataset_rows,
                "chart_id": active_chart_id, "result": json.loads(result_preview_str),
                "code": code, "explanation": context.explanation,
                "prompt_size": 0, "engine_used": engine_type,
                "debug_info": debug_info, "confidence_badge": confidence_badge,
                "query_explanation": query_explanation, "suggestions": suggestions_list
            }
            engine.set_cached_result(cache_key, cached_payload)
            
            background_tasks.add_task(
                background_tasks_worker,
                conv_id=conversation_id, user_msg_id=str(uuid.uuid4()), assistant_msg_id=assistant_msg_id,
                question=question, code=code, result_preview_str=result_preview_str, result_file_path=result_file_path,
                chart_id=active_chart_id, explanation=context.explanation, time_taken=total_taken,
                dataset_rows=dataset_rows, prompt_size=0, engine_used=engine_type,
                debug_info_str=debug_info_str, chart_png_path=chart_png_path, chart_html_path=chart_html_path,
                chart_meta_path=chart_meta_path, dataset_id=dataset_id
            )
            
            final_payload = {
                "type": "success", "status": "success",
                "conversation_id": conversation_id, "dataset_id": dataset_id,
                "model": "deterministic_query_engine", "execution_time": round(total_taken, 3),
                "rows": dataset_rows, "chart_id": active_chart_id,
                "result": json.loads(result_preview_str), "code": code,
                "explanation": context.explanation, "prompt_size": 0,
                "engine_used": engine_type, "debug_info": debug_info,
                "confidence_badge": confidence_badge, "query_explanation": query_explanation
            }
            yield json.dumps(final_payload) + "\n"
            return

        # ─── Step 6: LLM Code Generation Path ──────────────────────────────────
        yield json.dumps({"type": "progress", "step": "Generating SQL/Pandas Code"}) + "\n"
        
        t_start_prompt = time.time()
        t_start_gen = time.time()
        code = None
        prompt = ""
        
        if engine_type == "metadata":
            prompt = prompt_builder.build_prompt("insight", schema_desc=selected_schema_desc, profile_desc=selected_profile_desc, summary_block=summary_block, history_block=history_block, question=question)
        elif engine_type == "general_chat":
            prompt = f"System: {prompt_builder.get_template('system')}\nUser: {question}"
        elif engine_type == "insight":
            prompt = "# Programmatic Insight Engine (no prompt needed)"
        elif engine_type == "visualization":
            prompt = prompt_builder.build_prompt("chart", schema_desc=selected_schema_desc, profile_desc=selected_profile_desc, summary_block=summary_block, history_block=history_block, chart_png_path=chart_png_path.replace(os.sep, '/'), chart_html_path=chart_html_path.replace(os.sep, '/'), question=question)
        elif config.current_source_type == "sql" and config.database_engine:
            prompt = prompt_builder.build_prompt("sql", schema_desc=selected_schema_desc, profile_desc=selected_profile_desc, summary_block=summary_block, history_block=history_block, plan_block=plan_block, db_flavor=config.db_flavor or "SQLite", question=question)
        else:
            prompt = prompt_builder.build_prompt("pandas", schema_desc=selected_schema_desc, profile_desc=selected_profile_desc, summary_block=summary_block, history_block=history_block, plan_block=plan_block, question=question)
            
        context.prompt_size = estimate_tokens(prompt)
        context.prompt = prompt
        timings["Prompt creation"] = time.time() - t_start_prompt
        
        manager = LLMManager()
        t_start_gen = time.time()
        
        if engine_type not in ["metadata", "general_chat", "insight", "dashboard_gen"]:
            try:
                raw_content, final_model, _llm_metrics = manager.call_llm_with_fallback(prompt, model, temperature)
                if _llm_metrics:
                    llm_metrics_accumulator.append(_llm_metrics)
                context.model = final_model
                
                block_type = "sql" if (config.current_source_type == "sql" and config.database_engine and engine_type != "visualization") else "python"
                code_match = re.search(fr"```{block_type}\s*(.*?)\s*```", raw_content, re.DOTALL | re.IGNORECASE)
                if code_match:
                    code = code_match.group(1).strip()
                else:
                    code_match2 = re.search(r"```\s*(.*?)\s*```", raw_content, re.DOTALL)
                    code = code_match2.group(1).strip() if code_match2 else raw_content.strip()
                    
                if block_type == "python":
                    code_lines = []
                    for line in code.split("\n"):
                        trimmed = line.strip()
                        if not trimmed.startswith("import ") and not trimmed.startswith("from "):
                            code_lines.append(line)
                    code = "\n".join(code_lines)
                    code = re.sub(r'\bfig\.show\([^)]*\)', '', code)
                    code = re.sub(r'\bshow\([^)]*\)', '', code)
                    
                    lines = [l for l in code.split("\n") if l.strip()]
                    if lines and not any(re.match(r"^\s*result\s*=", l) for l in lines):
                        last_line = lines[-1].strip()
                        print_match = re.match(r"^print\((.*)\)$", last_line)
                        if print_match:
                            lines[-1] = f"result = {print_match.group(1)}"
                        else:
                            lines[-1] = f"result = {last_line}"
                        code = "\n".join(lines)
                context.code = code
            except Exception as e:
                context.error = f"Failed to generate query code: {str(e)}"
                yield json.dumps({"type": "error", "status": "error", "error": context.error, "time_taken": round(time.time() - total_start, 3)}) + "\n"
                return
        elif engine_type == "insight":
            try:
                from backend.services.insight_engine import generate_dataset_insights
                df_name = list(config.datasets.keys())[0] if config.datasets else ""
                df = config.datasets[df_name] if df_name else None
                insights_text = generate_dataset_insights(df_name, df)
                context.explanation = insights_text
                context.raw_result = pd.DataFrame([{"Insights": insights_text}])
                code = "# Programmatic Insight Engine (no code executed)"
                context.code = code
            except Exception as e:
                context.error = f"Failed in Insight Engine: {str(e)}"
                yield json.dumps({"type": "error", "status": "error", "error": context.error, "time_taken": round(time.time() - total_start, 3)}) + "\n"
                return
        elif engine_type == "dashboard_gen":
            try:
                from backend.services.ai_dashboard import AIDashboardService
                service = AIDashboardService()
                layout = service.generate_dashboard(question, selected_schema_desc)
                context.explanation = (
                    f"### Executive Summary\nI have successfully created the **{layout.get('title')}** dashboard based on your request.\n\n"
                    f"### Business Meaning\nThis dashboard contains {len(layout.get('cards', []))} metric widgets designed to track key indicators for this dataset.\n\n"
                    f"### Why This Happened\nThe BI Architect mapped the request to the available columns and constructed relevant visualization cards.\n\n"
                    f"### Key Drivers\nDashboard widgets: {', '.join([c.get('title') for c in layout.get('cards', [])])}.\n\n"
                    f"### Potential Risks\nEnsure the queries for each widget align with the expected transaction scopes.\n\n"
                    f"### Recommendations\nOpen the dashboards workspace to customize or edit layout placements.\n\n"
                    f"### Suggested Next Questions\n1. Open the created dashboard\n2. Add a line chart for monthly trends to this dashboard\n3. Export dashboard as PDF"
                )
                context.raw_result = pd.DataFrame([{"Dashboard ID": layout.get("id"), "Title": layout.get("title")}])
                result = context.raw_result
                code = f"# AI Dashboard Generation\n# Generated Dashboard ID: {layout.get('id')}\n# Layout:\n" + json.dumps(layout, indent=2)
                context.code = code
            except Exception as e:
                context.error = f"Failed to generate dashboard: {str(e)}"
                yield json.dumps({"type": "error", "status": "error", "error": context.error, "time_taken": round(time.time() - total_start, 3)}) + "\n"
                return
        else:
            try:
                raw_content, final_model, _llm_metrics = manager.call_llm_with_fallback(prompt, model, temperature)
                if _llm_metrics:
                    llm_metrics_accumulator.append(_llm_metrics)
                context.model = final_model
                context.explanation = raw_content.strip()
                context.raw_result = pd.DataFrame([{"Result": context.explanation}])
                code = "# Direct LLM response (no code executed)"
                context.code = code
            except Exception as e:
                context.error = f"Failed to generate LLM response: {str(e)}"
                yield json.dumps({"type": "error", "status": "error", "error": context.error, "time_taken": round(time.time() - total_start, 3)}) + "\n"
                return
                
        timings["Generator"] = time.time() - t_start_gen

        # ─── Step 7: Sandbox Execution & Self-Healing ──────────────────────────
        auto_retry_count = 0
        if engine_type not in ["metadata", "general_chat", "insight", "dashboard_gen"]:
            yield json.dumps({"type": "progress", "step": "Executing Sandbox"}) + "\n"
            t_start = time.time()
            
            all_columns = []
            if config.current_source_type == "file":
                for df_item in config.datasets.values():
                    all_columns.extend(df_item.columns.tolist())
            elif config.current_source_type == "sql" and config.database_engine:
                try:
                    inspector = inspect(config.database_engine)
                    for t in available_sources:
                        all_columns.extend([col['name'].lstrip('\ufeff') for col in inspector.get_columns(t)])
                except Exception:
                    pass
                    
            def run_sandbox():
                nonlocal result
                if config.current_source_type == "sql" and config.database_engine and engine_type != "visualization":
                    security.validate_sql(code)
                    def run_sql():
                        return pd.read_sql(code, config.database_engine)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as sql_executor:
                        sql_future = sql_executor.submit(run_sql)
                        result = sql_future.result(timeout=config.app_settings.sandbox_timeout_seconds)
                else:
                    security.validate_code(code)
                    safe_builtins = {
                        'len': len, 'str': str, 'int': int, 'float': float, 'sum': sum,
                        'max': max, 'min': min, 'abs': abs, 'any': any, 'all': all,
                        'zip': zip, 'enumerate': enumerate, 'range': range, 'list': list,
                        'dict': dict, 'set': set, 'tuple': tuple, 'bool': bool, 'round': round
                    }
                    local_vars = {name: df_item for name, df_item in config.datasets.items()}
                    if config.datasets:
                        active_name = list(config.datasets.keys())[0]
                        active_df = config.datasets[active_name]
                        local_vars["df"] = active_df
                        local_vars.update(engine.build_safe_column_aliases(active_df))
                    local_vars["result"] = None
                    local_vars["pd"] = pd
                    if engine.HAS_PLOTLY:
                        local_vars["go"] = engine.go
                        local_vars["px"] = engine.px
                        
                    engine.run_query_with_timeout(code, {"__builtins__": safe_builtins}, local_vars, timeout=config.app_settings.sandbox_timeout_seconds)
                    result = local_vars.get("result")
                    if result is None:
                        raise ValueError("The generated code did not assign any value to 'result'.")

            try:
                run_sandbox()
            except Exception as primary_err:
                auto_retry_count = 1
                yield json.dumps({"type": "progress", "step": "Query error: Attempting automatic fuzzy column correction..."}) + "\n"
                corrected = engine.attempt_fast_correction(code, primary_err, all_columns)
                
                if corrected:
                    try:
                        code = corrected
                        context.code = code
                        run_sandbox()
                    except Exception:
                        corrected = None
                        
                if not corrected:
                    yield json.dumps({"type": "progress", "step": "Fuzzy correction failed. Attempting LLM self-healing regeneration..."}) + "\n"
                    t_llm_start = time.time()
                    retry_prompt = prompt_builder.build_prompt("correction", error_msg=str(primary_err), failed_code=code, schema_desc=selected_schema_desc, profile_desc=selected_profile_desc)
                    try:
                        raw_content, final_model, _llm_metrics = manager.call_llm_with_fallback(retry_prompt, model, temperature)
                        if _llm_metrics:
                            llm_metrics_accumulator.append(_llm_metrics)
                        context.model = final_model
                        
                        block_type = "sql" if (config.current_source_type == "sql" and config.database_engine and engine_type != "visualization") else "python"
                        code_match = re.search(fr"```{block_type}\s*(.*?)\s*```", raw_content, re.DOTALL | re.IGNORECASE)
                        if code_match:
                            code = code_match.group(1).strip()
                        else:
                            code_match2 = re.search(r"```\s*(.*?)\s*```", raw_content, re.DOTALL)
                            code = code_match2.group(1).strip() if code_match2 else raw_content.strip()
                        
                        if block_type == "python":
                            code_lines = []
                            for line in code.split("\n"):
                                trimmed = line.strip()
                                if not trimmed.startswith("import ") and not trimmed.startswith("from "):
                                    code_lines.append(line)
                            code = "\n".join(code_lines)
                            code = re.sub(r'\bfig\.show\([^)]*\)', '', code)
                            code = re.sub(r'\bshow\([^)]*\)', '', code)
                            
                        context.code = code
                        run_sandbox()
                    except Exception as final_err:
                        context.error = f"Column reference error: {str(primary_err)}. Retry correction failed: {str(final_err)}"
                        yield json.dumps({"type": "error", "status": "error", "error": "The generated query referenced a column that does not exist.", "time_taken": round(time.time() - total_start, 3)}) + "\n"
                        logger_service.log_telemetry({"status": "error", "conversation_id": conversation_id, "engine_used": engine_type, "execution_time": time.time() - total_start, "error": context.error})
                        return
                    timings["Generator"] += (time.time() - t_llm_start)

            timings["Execution"] = time.time() - t_start
            context.raw_result = result
        else:
            result = context.raw_result

        dataset_rows = len(result) if isinstance(result, (pd.DataFrame, pd.Series)) else 1
        context.rows = dataset_rows
        
        yield json.dumps({"type": "progress", "step": "Formatting Results"}) + "\n"
        
        # Explanation
        explanation = context.explanation
        wants_explain = engine_type not in ["metadata", "general_chat"]
        explanation_level = config.settings.get("explain_level", "Normal")
        
        if "ceo" in question.lower() or "executive" in question.lower():
            explanation_level = "Executive"
        elif "technically" in question.lower() or "technical" in question.lower() or "code" in question.lower():
            explanation_level = "Technical"
        elif "briefly" in question.lower() or "quick" in question.lower() or "short" in question.lower():
            explanation_level = "Quick"
        elif "detailed" in question.lower() or "detail" in question.lower():
            explanation_level = "Detailed"
            
        if wants_explain and not explanation:
            local_exp = generate_local_explanation(question, result, parsed_query)
            if local_exp:
                explanation = local_exp
                context.explanation = explanation
            else:
                yield json.dumps({"type": "progress", "step": "Generating Explanation"}) + "\n"
                t_start = time.time()
                result_preview = result.to_string() if isinstance(result, (pd.DataFrame, pd.Series)) else str(result)
                if len(result_preview) > 1500:
                    result_preview = result_preview[:1500] + "\n[INFO] Truncated for token optimization..."
                    
                summary_prompt = prompt_builder.build_prompt("explanation", question=question, result_str=result_preview, explanation_level=explanation_level)
                try:
                    explanation, _, _llm_metrics = manager.call_llm_with_fallback(summary_prompt, model, temperature)
                    if _llm_metrics:
                        llm_metrics_accumulator.append(_llm_metrics)
                    context.explanation = explanation.strip()
                except Exception:
                    context.explanation = "Data processed successfully."
                timings["Generator"] += (time.time() - t_start)
        elif not explanation:
            context.explanation = "Result processed."

        # Format Final Preview
        t_start_fmt = time.time()
        result_preview_str = ""
        result_file_path = None
        has_chart = os.path.exists(chart_html_path)
        active_chart_id = chart_uuid if has_chart else None
        
        show_all = any(x in question.lower() for x in ["show all", "all rows", "all records", "everything"])
        limit_rows = config.app_settings.preview_rows
        
        if isinstance(result, pd.DataFrame):
            if dataset_rows > config.app_settings.max_result_rows:
                result = result.head(config.app_settings.max_result_rows)
                dataset_rows = config.app_settings.max_result_rows
                
            for col in result.columns:
                if pd.api.types.is_datetime64_any_dtype(result[col]):
                    result[col] = result[col].astype(str)
                    
            import numpy as np
            result = result.replace({np.nan: None, pd.NaT: None})
            result_preview = result.head(limit_rows) if (not show_all and dataset_rows > limit_rows) else result
            result_preview_str = json.dumps(result_preview.to_dict(orient="records"))
            
            if dataset_rows > 100:
                os.makedirs(RESULTS_DIR, exist_ok=True)
                parquet_filename = f"{str(uuid.uuid4())}.parquet"
                result_file_path = os.path.join(RESULTS_DIR, parquet_filename)
                result.to_parquet(result_file_path)
            else:
                result_file_path = ""
        elif isinstance(result, pd.Series):
            import numpy as np
            result = result.replace({np.nan: None, pd.NaT: None})
            result_preview = result.head(limit_rows) if (not show_all and len(result) > limit_rows) else result
            series_dict = [{"Index": str(k), "Value": str(v)} for k, v in result_preview.items()]
            result_preview_str = json.dumps(series_dict)
            result_file_path = ""
        else:
            result_preview_str = json.dumps([{"Result": str(result)}])

        timings["Formatting"] = time.time() - t_start_fmt
        
        t_start_ser = time.time()
        total_taken = time.time() - total_start
        timings["Response"] = total_taken
        
        max_val = -1.0
        slowest = "None"
        for stage, val in timings.items():
            if stage != "Response" and val > max_val:
                max_val = val
                slowest = stage
                
        confidence_badge, query_explanation = compile_badges_and_explanation(
            total_start, dataset_name, engine_type, llm_used, parsed_query
        )

        heuristics_data = {}
        try:
            from backend.services.insight_engine import run_result_heuristics
            if isinstance(result, pd.DataFrame):
                heuristics_data = run_result_heuristics(result)
        except Exception:
            pass

        # Compile debug breakdown
        prompt_tokens = sum(m.prompt_tokens for m in llm_metrics_accumulator if m)
        completion_tokens = sum(m.completion_tokens for m in llm_metrics_accumulator if m)
        generation_time_ms = sum(m.generation_time_ms for m in llm_metrics_accumulator if m)
        llm_retry_count = sum(m.retry_count for m in llm_metrics_accumulator if m)
        llm_timed_out = any(m.timed_out for m in llm_metrics_accumulator if m)

        debug_info = {
            "timings": {k: round(v, 4) for k, v in timings.items()},
            "complexity": complexity,
            "engine_used": engine_type,
            "prompt_size": context.prompt_size,
            "model": context.model,
            "cache_hit": False,
            "auto_retry_count": auto_retry_count,
            "router_decision": router_res.get("engine", "deterministic") if isinstance(router_res, dict) else str(router_res),
            "slowest_stage": f"{slowest} ({max_val * 1000:.1f}ms)",
            "cache_used": False,
            "llm_used": True,
            "parser_used": False,
            "confidence_badge": confidence_badge,
            "query_explanation": query_explanation,
            "heuristics": heuristics_data,
            "request_id": request_id,
            "intent": parsed_query.intent if parsed_query else "unknown",
            "matched_columns": parsed_query.entities.get("matched_columns", []) if parsed_query else [],
            "matched_values": router_res.get("matched_values", []) if isinstance(router_res, dict) else [],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "generation_time_ms": generation_time_ms,
            "execution_time_ms": timings.get("Execution", 0.0) * 1000,
            "validation_result": None,
            "recovery_steps": [],
            "column_resolution_steps": [],
            "confidence_score": parsed_query.confidence if parsed_query else 0.0,
            "llm_timed_out": llm_timed_out,
            "llm_retry_count": llm_retry_count,
        }
        
        suggestions_list = generate_smart_suggestions(question, parsed_query)
            
        if explanation_level == "Technical":
            technical_appendix = (
                f"\n\n---\n"
                f"### Technical Appendix\n"
                f"- **Execution Engine**: {engine_type.upper()} Engine\n"
                f"- **Formulas / Query Code**:\n```python\n{context.code}\n```\n"
                f"- **Slowest Stage**: {slowest}\n"
                f"- **Dataset Rows Processed**: {dataset_rows}\n"
            )
            context.explanation += technical_appendix

        debug_info_str = json.dumps(debug_info)
        timings["Serialization"] = time.time() - t_start_ser
        
        # Save cache
        cached_payload = {
            "status": "success", "dataset_id": dataset_id,
            "model": context.model, "rows": dataset_rows,
            "chart_id": active_chart_id, "result": json.loads(result_preview_str),
            "code": code, "explanation": context.explanation,
            "prompt_size": context.prompt_size, "engine_used": engine_type,
            "debug_info": debug_info, "confidence_badge": confidence_badge,
            "query_explanation": query_explanation, "suggestions": suggestions_list
        }
        engine.set_cached_result(cache_key, cached_payload)
        
        background_tasks.add_task(
            background_tasks_worker,
            conv_id=conversation_id, user_msg_id=str(uuid.uuid4()), assistant_msg_id=assistant_msg_id,
            question=question, code=code, result_preview_str=result_preview_str, result_file_path=result_file_path,
            chart_id=active_chart_id, explanation=context.explanation, time_taken=total_taken,
            dataset_rows=dataset_rows, prompt_size=context.prompt_size, engine_used=engine_type,
            debug_info_str=debug_info_str, chart_png_path=chart_png_path, chart_html_path=chart_html_path,
            chart_meta_path=chart_meta_path, dataset_id=dataset_id
        )

        final_payload = {
            "type": "success", "status": "success",
            "conversation_id": conversation_id, "dataset_id": dataset_id,
            "model": context.model, "execution_time": round(total_taken, 3),
            "rows": dataset_rows, "chart_id": active_chart_id,
            "result": json.loads(result_preview_str), "code": code,
            "explanation": context.explanation, "prompt_size": context.prompt_size,
            "engine_used": engine_type, "debug_info": debug_info,
            "confidence_badge": confidence_badge, "query_explanation": query_explanation
        }
        yield json.dumps(final_payload) + "\n"
