# QueryIQ Production Release Benchmark Report

**Generated Date**: 2026-07-20T12:50:56.979155

## Release Quality Gates Status

| Gate | Status | Execution Time |
| :--- | :--- | :--- |
| **Schema Evolution** | ✅ PASSED | 879.2ms |
| **API Contract & SSE** | ✅ PASSED | 2735.9ms |
| **Deterministic Stability** | ✅ PASSED | 2848.5ms |
| **Query Replay (266 logs)** | ✅ PASSED | 2858.0ms |

## Production Performance Metrics

- **Accuracy**: 100.00%
- **Average Warm Start Latency**: 1.10ms
- **Cold Start Initial Latency**: 672.15ms
- **Incorrect-Answer Rate**: 0.00% (Target: 0%)
- **Memory Peak RSS Overhead**: 0.20MB (Target: <= 50MB)
