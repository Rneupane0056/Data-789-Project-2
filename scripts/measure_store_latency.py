"""Measure feature-store retrieval latency. Requires Redis + populated features.

    python scripts\\measure_store_latency.py
"""
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.streaming.feature_store import FeatureStore


def percentile(values, pct):
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[index]


def main():
    store = FeatureStore()
    ids = [f"CUST{n:04d}" for n in range(200)]

    # Warm up: the first call pays for the TCP connect, which would otherwise
    # land in the sample and inflate the maximum.
    store.get_customer_features(ids[0])

    # --- single-key GET ---
    single = []
    for _ in range(1000):
        customer_id = random.choice(ids)
        start = time.perf_counter()
        store.get_customer_features(customer_id)
        single.append((time.perf_counter() - start) * 1000.0)

    # --- batch MGET of 50 keys ---
    batch = []
    for _ in range(100):
        sample = random.sample(ids, 50)
        start = time.perf_counter()
        store.get_customer_features_batch(sample)
        batch.append((time.perf_counter() - start) * 1000.0)

    print("single-key GET (n=1000), milliseconds")
    print(f"  p50 {percentile(single, 50):.3f}   p95 {percentile(single, 95):.3f}"
          f"   p99 {percentile(single, 99):.3f}   max {max(single):.3f}")
    print(f"  mean {statistics.mean(single):.3f}")
    print()
    print("batch MGET of 50 keys (n=100), milliseconds")
    print(f"  p50 {percentile(batch, 50):.3f}   p95 {percentile(batch, 95):.3f}")
    print(f"  per key at p50: {percentile(batch, 50) / 50:.4f}")


if __name__ == "__main__":
    main()