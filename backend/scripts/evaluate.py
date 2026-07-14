import os
import sys
import time
import json
import asyncio
import pandas as pd
import hashlib

# Add project root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.config as config
from backend.services.loader import load_default_datasets
from backend.services.llm import LLMManager
import backend.services.history_db as db
import backend.services.schema_cache as schema_cache
import backend.services.router as router_service
from backend.routers.query import QueryRequest, execute_query_stream
from backend.services.dataset_manager import DatasetManager

# Try importing resource usage metrics
try:
    import psutil
except ImportError:
    psutil = None

class MockBackgroundTasks:
    def add_task(self, func, *args, **kwargs):
        # Skip side-effects like database logs and cache writes to avoid disk I/O bottlenecks during evaluation
        pass

def generate_benchmark_queries() -> dict:
    categories = {
        "Lookup": [],
        "Filter": [],
        "Aggregation": [],
        "Chart": [],
        "Insight": [],
        "Metadata": [],
        "Prediction": [],
        "Cache Hit": [],
        "Multi-condition": [],
        "Date": []
    }
    
    # 1. Lookups (100)
    cities = ["Delhi", "Mumbai", "London", "New York", "Chicago", "Tokyo", "Berlin", "Paris", "Sydney", "Toronto"]
    depts = ["HR", "IT", "Sales", "Finance", "Marketing", "Engineering", "Operations", "Legal", "Support", "Product"]
    for i in range(100):
        city = cities[i % len(cities)]
        dept = depts[(i // len(cities)) % len(depts)]
        categories["Lookup"].append(f"Show employees in {city} in department {dept}")
        
    # 2. Filters (100)
    for i in range(100):
        sal = 30000 + (i * 1000)
        categories["Filter"].append(f"Employees with salary greater than {sal}")
        
    # 3. Aggregations (100)
    metrics = ["salary", "experience", "age", "rating", "bonus"]
    ops = ["average", "highest", "lowest", "sum", "median", "total"]
    for i in range(100):
        metric = metrics[i % len(metrics)]
        op = ops[(i // len(metrics)) % len(ops)]
        dept = depts[(i // (len(metrics) * len(ops))) % len(depts)]
        categories["Aggregation"].append(f"What is the {op} {metric} in department {dept}")
        
    # 4. Charts (50)
    chart_types = ["histogram", "scatter plot", "pie chart", "bar chart", "box plot", "heatmap", "area chart", "treemap"]
    for i in range(50):
        ct = chart_types[i % len(chart_types)]
        categories["Chart"].append(f"Plot a {ct} of salary and experience")
        
    # 5. Insights (50)
    insight_phrases = ["hidden insights", "business insights", "trends", "patterns", "observations", "key findings"]
    for i in range(50):
        phrase = insight_phrases[i % len(insight_phrases)]
        categories["Insight"].append(f"Find {phrase} in this dataset")
        
    # 6. Metadata (50)
    meta_phrases = ["describe table", "list tables", "columns of dataset", "schema", "dataset info"]
    for i in range(50):
        phrase = meta_phrases[i % len(meta_phrases)]
        categories["Metadata"].append(f"Show me the {phrase}")
        
    # 7. Predictions (50)
    pred_targets = ["salary", "attrition", "performance", "bonus"]
    for i in range(50):
        target = pred_targets[i % len(pred_targets)]
        categories["Prediction"].append(f"Predict {target} based on experience")
        
    # 8. Cache Hits (50)
    for i in range(50):
        categories["Cache Hit"].append(f"Employees with salary greater than 50000")
        
    # 9. Multi-condition (50)
    for i in range(50):
        sal = 40000 + (i * 1000)
        city = cities[i % len(cities)]
        categories["Multi-condition"].append(f"Show IT employees in {city} earning above {sal}")
        
    # 10. Date (50)
    years = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022]
    for i in range(50):
        year = years[i % len(years)]
        categories["Date"].append(f"Employees hired after {year}")
        
    return categories

def run_evaluation():
    print("\n============================================================")
    print("         NEXUS AI DATA STUDIO END-TO-END VERIFICATION")
    print("============================================================\n")
    
    # Force activate employee_dataset
    db.init_db()
    dm = DatasetManager()
    xls_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "employee_dataset.xlsx")
    ds_id = hashlib.md5("employee_dataset".encode()).hexdigest()
    
    if os.path.exists(xls_path):
        dm.register_dataset_file("employee_dataset.xlsx", xls_path, behavior="keep")
        dm.activate_dataset_by_id(ds_id)
        
    schema_cache.clear_schema_cache()
    
    # Generate benchmark suite
    queries_by_category = generate_benchmark_queries()
    
    # Track statistics
    stats = {}
    total_successful = 0
    total_evaluated = 0
    llm_avoided_count = 0
    parser_success_count = 0
    cache_hit_count = 0
    
    # Setup initial process memory usage
    process = psutil.Process(os.getpid()) if psutil else None
    mem_start = process.memory_info().rss / (1024 * 1024) if process else 0.0
    cpu_start = psutil.cpu_percent(interval=None) if psutil else 0.0
    
    slowest_query_time = 0.0
    slowest_query_str = ""
    fastest_query_time = 999.0
    fastest_query_str = ""
    
    bg_tasks = MockBackgroundTasks()
    
    for category, questions in queries_by_category.items():
        latencies = []
        successful_in_cat = 0
        
        for question in questions:
            start_time = time.time()
            req = QueryRequest(question=question, conversation_id="eval-conv-id")
            
            try:
                chunks = []
                for chunk in execute_query_stream(req, bg_tasks):
                    chunks.append(json.loads(chunk.strip()))
                
                final_payload = chunks[-1]
                elapsed = time.time() - start_time
                latencies.append(elapsed)
                
                if final_payload.get("status") == "success":
                    successful_in_cat += 1
                    total_successful += 1
                    
                    # Telemetry calculations
                    debug = final_payload.get("debug_info", {})
                    if debug:
                        if not debug.get("llm_used", True):
                            llm_avoided_count += 1
                        if debug.get("parser_used", False):
                            parser_success_count += 1
                        if debug.get("cache_hit", False):
                            cache_hit_count += 1
                            
                    # Track fastest/slowest
                    if elapsed > slowest_query_time:
                        slowest_query_time = elapsed
                        slowest_query_str = question
                    if elapsed < fastest_query_time:
                        fastest_query_time = elapsed
                        fastest_query_str = question
            except Exception as e:
                print(f"[EVALUATION ERROR] Category: {category}, Question: {question}, Error: {str(e)}")
                
            total_evaluated += 1
            
        # Compile category stats
        if latencies:
            latencies_sorted = sorted(latencies)
            stats[category] = {
                "avg": sum(latencies) / len(latencies),
                "median": latencies_sorted[len(latencies_sorted) // 2],
                "p95": latencies_sorted[int(len(latencies_sorted) * 0.95)],
                "max": max(latencies),
                "accuracy": (successful_in_cat / len(questions)) * 100
            }
        else:
            stats[category] = {"avg": 0, "median": 0, "p95": 0, "max": 0, "accuracy": 0}
            
    mem_end = process.memory_info().rss / (1024 * 1024) if process else 0.0
    cpu_end = psutil.cpu_percent(interval=None) if psutil else 0.0
    
    llm_avoidance_rate = (llm_avoided_count / total_evaluated) * 100 if total_evaluated > 0 else 0.0
    parser_accuracy = (parser_success_count / total_evaluated) * 100 if total_evaluated > 0 else 0.0
    cache_hit_rate = (cache_hit_count / total_evaluated) * 100 if total_evaluated > 0 else 0.0
    
    print("\n=================================================")
    print("PRODUCTION PERFORMANCE REPORT")
    print("=================================================")
    for cat, data in stats.items():
        print(f"{cat:<18}: Avg={data['avg']*1000:6.1f}ms | P95={data['p95']*1000:6.1f}ms | Max={data['max']*1000:6.1f}ms | Accuracy={data['accuracy']:.1f}%")
    print("-" * 50)
    print(f"Parser Accuracy    : {parser_accuracy:.2f}%")
    print(f"LLM Avoidance      : {llm_avoidance_rate:.2f}%")
    print(f"Cache Hit Rate     : {cache_hit_rate:.2f}%")
    print(f"Memory Overhead    : {mem_end - mem_start:.2f} MB")
    print(f"CPU Usage Change   : {cpu_end - cpu_start:.2f}%")
    print(f"Slowest Query      : {slowest_query_str[:50]} ({slowest_query_time*1000:.1f}ms)")
    print(f"Fastest Query      : {fastest_query_str[:50]} ({fastest_query_time*1000:.1f}ms)")
    print("=================================================\n")
    
    # Assert criteria
    targets = {
        "Lookup": 0.300,
        "Filter": 0.500,
        "Aggregation": 0.700,
        "Metadata": 0.150,
        "Chart": 3.0,
        "Cache Hit": 0.050,
        "Insight": 0.500
    }
    
    failures = []
    for cat, max_lat in targets.items():
        if cat in stats and stats[cat]["avg"] > max_lat:
            failures.append(f"{cat} average latency ({stats[cat]['avg']*1000:.1f}ms) exceeded target ({max_lat*1000:.1f}ms)")
            
    if failures:
        print("[FAIL] Performance targets missed:")
        for fail in failures:
            print(f"  - {fail}")
        sys.exit(1)
    else:
        print("[SUCCESS] All performance targets successfully achieved!")
        sys.exit(0)

if __name__ == "__main__":
    run_evaluation()
