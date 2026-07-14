import sys
import os
import time
import random
import pandas as pd
import psutil

# Adjust sys path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.config as config
from backend.services.query_parser import parse_question
from backend.services.router import classify_query_engine_detailed
from backend.services.query_engine import execute_parsed_query

def run_stress_test():
    print("=============================================================")
    print("               RUNNING ENTERPRISE STRESS SUITE")
    print("=============================================================")
    
    # 1. Load large mock dataset
    cities = ["Delhi", "Mumbai", "Bangalore", "Chennai", "Kolkata", "Hyderabad", "Pune", "Ahmedabad"]
    categories = ["Furniture", "Technology", "Office Supplies", "Electronics", "Apparel"]
    
    # Generate 10,000 mock rows
    data = {
        "Order ID": [100000 + i for i in range(10000)],
        "City": [random.choice(cities) for _ in range(10000)],
        "Category": [random.choice(categories) for _ in range(10000)],
        "Sales": [random.randint(50, 5000) for _ in range(10000)],
        "Profit": [random.randint(-500, 1500) for _ in range(10000)]
    }
    mock_df = pd.DataFrame(data)
    config.datasets["SalesData"] = mock_df
    config.current_source_type = "file"
    
    print(f"[INIT] Loaded mock dataset 'SalesData' with {len(mock_df)} rows.")

    # 2. Generate 500 simulation queries
    templates = [
        "Show sales in {city}",
        "Show profit in {city}",
        "What is total sales of {category}",
        "What is average profit of {category}",
        "Show average sales in {city} for {category}",
        "City wise total sales",
        "Category wise average profit",
        "Order ID {order_id}"
    ]

    queries = []
    for _ in range(500):
        tmpl = random.choice(templates)
        q = tmpl.format(
            city=random.choice(cities),
            category=random.choice(categories),
            order_id=random.randint(100000, 109999)
        )
        queries.append(q)

    print(f"[SUITE] Generated {len(queries)} simulation queries.")
    print("Executing load simulation...")

    latencies = []
    failures = 0
    start_time = time.time()
    
    cpu_before = psutil.cpu_percent(interval=None)
    mem_before = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

    for idx, q in enumerate(queries):
        t_start = time.time()
        try:
            router_res = classify_query_engine_detailed(q)
            engine_type = router_res["engine"]
            parsed = router_res["parsed_query"]
            
            # Execute query
            res, _ = execute_parsed_query(parsed, mock_df, "SalesData")
            
            latency = (time.time() - t_start) * 1000 # ms
            latencies.append(latency)
        except Exception as e:
            failures += 1
            latencies.append((time.time() - t_start) * 1000)
            
        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1} / 500 queries...")

    total_duration = time.time() - start_time
    cpu_after = psutil.cpu_percent(interval=None)
    mem_after = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)

    # 3. Calculate metrics
    avg_latency = sum(latencies) / len(latencies)
    sorted_lats = sorted(latencies)
    p95_latency = sorted_lats[int(len(sorted_lats) * 0.95)]
    qps = len(queries) / total_duration
    success_rate = ((len(queries) - failures) / len(queries)) * 100

    print("=============================================================")
    print("                    STRESS TEST METRICS")
    print("=============================================================")
    print(f"Total Queries Executed: {len(queries)}")
    print(f"Success Rate          : {success_rate:.2f}%")
    print(f"Total Duration        : {total_duration:.2f} s")
    print(f"Queries Per Second    : {qps:.2f} QPS")
    print(f"Average Latency       : {avg_latency:.2f} ms")
    print(f"95th Percentile Lat    : {p95_latency:.2f} ms")
    print(f"CPU Utilization Spike : {cpu_after - cpu_before:.1f}%")
    print(f"Memory Growth         : {mem_after - mem_before:.2f} MB")
    print("=============================================================")

if __name__ == "__main__":
    run_stress_test()
