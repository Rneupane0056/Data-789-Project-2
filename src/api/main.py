"""
FastAPI serving app.

PROVIDED: app setup, model/feature-store load at startup, /health, /model/info,
and the request/response schemas (so input validation -> HTTP 422 works for free).
IMPLEMENTED: /predict and /predict_batch, plus a GET /features/{customer_id}
helper route used in the demo.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional

import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.api.fraud_detector import FraudDetector
from src.streaming.feature_store import FeatureStore

app = FastAPI(title="TrustBank Fraud Detection API")

# uvicorn already prints this logger's INFO lines, so per-request latency
# shows up in the console and in `docker compose logs api`.
logger = logging.getLogger("uvicorn.error")

# Loaded once at startup (do NOT load the model per-request).
detector = FraudDetector()
store = FeatureStore()

# Used when a customer has no stored features (new customer, expired key,
# or Redis unreachable), so every transaction can still be scored.
DEFAULT_FEATURES = {"transaction_count": 0, "avg_amount": 0.0}


class Transaction(BaseModel):
    customer_id: str
    amount: float
    merchant_category: str
    is_online: bool
    timestamp: str
    transaction_id: Optional[str] = None


class FraudPrediction(BaseModel):
    transaction_id: Optional[str] = None
    fraud_probability: float
    is_fraud: int
    model_version: str
    latency_ms: float


# ---------- helpers ----------

def _lookup_features(customer_id: str) -> Optional[dict]:
    """One customer's features from Redis, or None if missing / Redis is down."""
    try:
        return store.get_customer_features(customer_id)
    except redis.RedisError as exc:
        logger.warning("feature store unavailable (%s); using defaults", exc)
        return None


def _lookup_features_batch(customer_ids: list[str]) -> dict:
    """Features for many customers in ONE round-trip (MGET); {} if Redis is down."""
    try:
        return store.get_customer_features_batch(customer_ids)
    except redis.RedisError as exc:
        logger.warning("feature store unavailable (%s); using defaults", exc)
        return {}


def _merge(txn: Transaction, features: Optional[dict]) -> dict:
    """Transaction fields + stored window features -> one dict for the model.
    Supplies all four model inputs: amount, is_online, avg_amount, transaction_count."""
    merged = txn.model_dump()
    merged.update(DEFAULT_FEATURES)
    if features:
        merged.update(features)
    return merged


# ---------- routes ----------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/model/info")
async def model_info():
    return {"model_version": detector.model_version}


@app.get("/features/{customer_id}")
async def get_features(customer_id: str):
    """Demo helper: show what the feature store currently holds for a customer."""
    features = _lookup_features(customer_id)
    if features is None:
        raise HTTPException(status_code=404, detail=f"no features stored for {customer_id}")
    return {"customer_id": customer_id, "features": features}


@app.post("/predict", response_model=FraudPrediction)
async def predict_fraud(txn: Transaction):
    """Score one transaction: Redis features + transaction -> model."""
    start = time.perf_counter()
    features = _lookup_features(txn.customer_id)
    result = detector.predict(_merge(txn, features))
    latency_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "predict customer=%s features=%s fraud_probability=%.4f latency_ms=%.3f",
        txn.customer_id, features, result["fraud_probability"], latency_ms,
    )
    return FraudPrediction(
        transaction_id=txn.transaction_id,
        latency_ms=round(latency_ms, 3),
        **result,
    )


@app.post("/predict_batch", response_model=List[FraudPrediction])
async def predict_fraud_batch(txns: List[Transaction]):
    """Score many transactions; features for all customers come from one MGET."""
    start = time.perf_counter()
    unique_ids = list(dict.fromkeys(t.customer_id for t in txns))  # dedupe, keep order
    features_by_id = _lookup_features_batch(unique_ids)
    results = [detector.predict(_merge(t, features_by_id.get(t.customer_id))) for t in txns]
    latency_ms = (time.perf_counter() - start) * 1000.0
    logger.info("predict_batch size=%d latency_ms=%.3f", len(txns), latency_ms)
    # Each item reports the latency of the whole batch call.
    return [
        FraudPrediction(transaction_id=t.transaction_id, latency_ms=round(latency_ms, 3), **r)
        for t, r in zip(txns, results)
    ]