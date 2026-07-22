import os
import sys
import time
import subprocess
import json
import statistics
import psutil
from datetime import datetime

# Adjust sys path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

def run_suite_command(command_list, name):
    print(f"Running {name}...")
    t0 = time.time()
    res = subprocess.run(command_list, capture_output=True, text=True)
    elapsed = (time.time() - t0) * 1000
    
    if res.returncode != 0:
        print(f"[FAILED] {name} (Exit Code: {res.returncode})")
        print("--- STDERR ---")
        print(res.stderr)
        print("--- STDOUT ---")
        print(res.stdout)
        return False, elapsed, res.stdout
    else:
        print(f"[PASSED] {name} in {elapsed:.1f}ms")
        return True, elapsed, res.stdout

def main():
    print("="*60)
    print("            QUERYIQ CI REGRESSION & QUALITY GATE")
    print("="*60)
    
    process = psutil.Process()
    
    reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "reports"))
    os.makedirs(reports_dir, exist_ok=True)
    
    # 1. Measure Cold Start vs Warm Start Latency
    print("\nMeasuring Cold Start vs Warm Start Latency...")
    # Import parser to simulate first-load parser initialization
    t_cold_start = time.time()
    from backend.services.query_parser import parse_question
    import pandas as pd
    df_dummy = pd.DataFrame({"A": [1, 2]})
    # First parse (Cold start)
    p_cold = parse_question("Total A", df_dummy, "dummy_ds")
    cold_latency = (time.time() - t_cold_start) * 1000
    
    # Subsequent parses (Warm start)
    warm_latencies = []
    for _ in range(50):
        t_w = time.time()
        parse_question("Total A", df_dummy, "dummy_ds")
        warm_latencies.append((time.time() - t_w) * 1000)
    avg_warm_latency = statistics.mean(warm_latencies)
    
    print(f"  Cold Start Latency: {cold_latency:.2f}ms")
    print(f"  Avg Warm Start Latency: {avg_warm_latency:.2f}ms")
    
    # Measure baseline after warm-up imports are complete
    mem_baseline = process.memory_info().rss / (1024 * 1024)
    print(f"Baseline RSS Memory (Post-Warmup): {mem_baseline:.1f} MB")
    
    # 2. Run Test Suites
    suite_results = {}
    
    # Run Schema Evolution Test
    ok_evo, time_evo, out_evo = run_suite_command([sys.executable, "backend/tests/test_schema_evolution.py"], "Schema Evolution Gate")
    suite_results["schema_evolution"] = ok_evo
    
    # Run API Integration & SSE Contract Test
    ok_api, time_api, out_api = run_suite_command([sys.executable, "-m", "pytest", "backend/tests/test_api_integration.py"], "API Contract Gate")
    suite_results["api_contract"] = ok_api
    
    # Run Stability Gate
    ok_stab, time_stab, out_stab = run_suite_command([sys.executable, "backend/tests/test_stability.py"], "Stability Gate")
    suite_results["stability"] = ok_stab
    
    # Run 266 Query Replay Log & SLA Check
    ok_replay, time_replay, out_replay = run_suite_command([sys.executable, "backend/scripts/query_log_replay.py"], "Query Log Replay Suite")
    suite_results["query_replay"] = ok_replay
    
    # Parse Query Replay stats from output stdout
    replay_accuracy = 0.0
    correct_det_rate = 0.0
    incorrect_rate = 0.0
    
    for line in out_replay.splitlines():
        if "Accuracy" in line:
            replay_accuracy = float(line.split(":")[1].replace("%", "").strip())
        elif "Correct Deterministic Rate" in line:
            correct_det_rate = float(line.split(":")[1].replace("%", "").strip())
        elif "Incorrect Execution Rate" in line:
            incorrect_rate = float(line.split(":")[1].replace("%", "").strip())
            
    # Peak Memory Check
    mem_peak = process.memory_info().rss / (1024 * 1024)
    mem_delta = mem_peak - mem_baseline
    print(f"\nPeak Memory (RSS): {mem_peak:.1f} MB (Delta: {mem_delta:.1f} MB)")
    
    # 3. Read Previous Run from history.csv
    history_file = os.path.join(reports_dir, "history.csv")
    prev_accuracy = None
    prev_latency = None
    
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                lines = f.read().splitlines()
                if len(lines) > 1:
                    last_line = lines[-1].split(",")
                    prev_accuracy = float(last_line[1])
                    prev_latency = float(last_line[2])
        except Exception as e:
            print(f"[HISTORY WARN] Failed to read previous run history: {e}")
            
    # Calculate Deltas
    delta_acc_str = "N/A"
    delta_lat_str = "N/A"
    if prev_accuracy is not None:
        delta_acc = replay_accuracy - prev_accuracy
        delta_acc_str = f"{delta_acc:+.2f}%"
    if prev_latency is not None:
        delta_lat = avg_warm_latency - prev_latency
        delta_lat_str = f"{delta_lat:+.2f}ms"
        
    # Print Clean CLI Metrics Table
    print("\n" + "="*60)
    print("                    CI GATE METRICS REPORT")
    print("="*60)
    print(f"{'Metric':<25} | {'Current':<10} | {'Previous':<10} | {'Delta':<10}")
    print("-"*60)
    print(f"{'Replay Accuracy':<25} | {replay_accuracy:<10.2f}% | {f'{prev_accuracy:.2f}%' if prev_accuracy else 'N/A':<10} | {delta_acc_str:<10}")
    print(f"{'Warm Start Latency':<25} | {avg_warm_latency:<10.2f}ms | {f'{prev_latency:.2f}ms' if prev_latency else 'N/A':<10} | {delta_lat_str:<10}")
    print(f"{'Memory Delta (RSS)':<25} | {mem_delta:<10.2f}MB | {'N/A':<10} | {'N/A':<10}")
    print(f"{'Incorrect Answer Rate':<25} | {incorrect_rate:<10.2f}% | {'N/A':<10} | {'N/A':<10}")
    print("="*60 + "\n")
    
    # Write to History CSV
    history_exists = os.path.exists(history_file)
    with open(history_file, "a", encoding="utf-8") as f:
        if not history_exists:
            f.write("Date,Accuracy,Avg_Warm_Latency,Memory_Delta,Incorrect_Rate\n")
        f.write(f"{datetime.now().isoformat()},{replay_accuracy},{avg_warm_latency},{mem_delta},{incorrect_rate}\n")
        
    # Write Structured JSON Performance Report
    perf_report = {
        "timestamp": datetime.now().isoformat(),
        "metrics": {
            "accuracy": replay_accuracy,
            "warm_start_latency_ms": avg_warm_latency,
            "cold_start_latency_ms": cold_latency,
            "memory_delta_mb": mem_delta,
            "incorrect_rate": incorrect_rate
        },
        "gates": {
            "schema_evolution": "PASSED" if ok_evo else "FAILED",
            "api_contract": "PASSED" if ok_api else "FAILED",
            "stability": "PASSED" if ok_stab else "FAILED",
            "query_replay": "PASSED" if ok_replay else "FAILED"
        }
    }
    with open(os.path.join(reports_dir, "performance_report.json"), "w", encoding="utf-8") as f:
        json.dump(perf_report, f, indent=2)
        
    # Write Markdown Report
    with open(os.path.join(reports_dir, "benchmark_report.md"), "w", encoding="utf-8") as f:
        f.write(f"""# QueryIQ Production Release Benchmark Report

**Generated Date**: {datetime.now().isoformat()}

## Release Quality Gates Status

| Gate | Status | Execution Time |
| :--- | :--- | :--- |
| **Schema Evolution** | {"✅ PASSED" if ok_evo else "❌ FAILED"} | {time_evo:.1f}ms |
| **API Contract & SSE** | {"✅ PASSED" if ok_api else "❌ FAILED"} | {time_api:.1f}ms |
| **Deterministic Stability** | {"✅ PASSED" if ok_stab else "❌ FAILED"} | {time_stab:.1f}ms |
| **Query Replay (266 logs)** | {"✅ PASSED" if ok_replay else "❌ FAILED"} | {time_replay:.1f}ms |

## Production Performance Metrics

- **Accuracy**: {replay_accuracy:.2f}%
- **Average Warm Start Latency**: {avg_warm_latency:.2f}ms
- **Cold Start Initial Latency**: {cold_latency:.2f}ms
- **Incorrect-Answer Rate**: {incorrect_rate:.2f}% (Target: 0%)
- **Memory Peak RSS Overhead**: {mem_delta:.2f}MB (Target: <= 50MB)
""")

    # 4. Enforce Split SLA Gates
    all_passed = True
    
    if not ok_evo:
        print("[SLA BREACH] Schema Evolution Gate Failed!")
        all_passed = False
    if not ok_api:
        print("[SLA BREACH] API Contract / SSE Protocol Gate Failed!")
        all_passed = False
    if not ok_stab:
        print("[SLA BREACH] Deterministic Stability Gate Failed!")
        all_passed = False
    if replay_accuracy < 98.0:
        print(f"[SLA BREACH] Overall Replay Accuracy ({replay_accuracy:.2f}%) below threshold (98.0%)")
        all_passed = False
    if avg_warm_latency > 15.0:
        print(f"[SLA BREACH] Average Latency ({avg_warm_latency:.2f}ms) exceeds SLA limit (15.0ms)")
        all_passed = False
    if mem_delta > 50.0:
        print(f"[SLA BREACH] Memory RSS Delta ({mem_delta:.2f}MB) exceeds limits (50.0MB)")
        all_passed = False
    if incorrect_rate > 0.0:
        print(f"[SLA BREACH] Incorrect Execution Rate ({incorrect_rate:.2f}%) is above 0%")
        all_passed = False
        
    if all_passed:
        print(">>> ALL PRODUCTION RELIABILITY GATES PASSED SUCCESSFULLY! <<<")
        sys.exit(0)
    else:
        print("[SLA BREACH] GATES COMPLETED WITH PERFORMANCE OR ACCURACY SLA BREACH!")
        sys.exit(1)

if __name__ == "__main__":
    main()
