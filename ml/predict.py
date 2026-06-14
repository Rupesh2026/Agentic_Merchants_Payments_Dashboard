"""
ml/predict.py — batch scoring → gold.risk_scores (with SHAP explanations).

Loads the trained XGBoost model, scores every row in gold.features, computes the
top-3 SHAP features per transaction (the JSONB the RAG agent later reads), and
upserts gold.risk_scores in batches via psycopg2 execute_values.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import shap
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from config import db
from ml.features import ML_FEATURES, load_scoring_frame, prepare_matrix

log = logging.getLogger(__name__)

BATCH = settings.SILVER_BATCH

RISK_TIERS = [(90, "critical"), (70, "high"), (30, "medium"), (0, "low")]

SHAP_FEATURE_DESCRIPTIONS = {
    "amt":                 "Transaction amount of ${value:.2f}",
    "hour_of_day":         "Transaction at {value:.0f}:00",
    "day_of_week":         "Occurred on {day_name}",
    "is_weekend":          "Weekend transaction",
    "geo_distance_km":     "Transaction {value:.0f}km from home city",
    "city_pop_log":        "City population ~{pop:,}",
    "is_rural":            "Rural area transaction",
    "tx_count_1h":         "{value:.0f} transactions in the last hour",
    "tx_count_24h":        "{value:.0f} transactions in the last 24h",
    "tx_amount_1h":        "${value:.2f} spent in the last hour",
    "tx_amount_24h":       "${value:.2f} spent in the last 24h",
    "amt_zscore":          "Amount {value:.1f} std-devs from this customer's norm",
    "category_encoded":    "Merchant category signal",
    "is_online":           "Online (card-not-present) transaction",
    "gender_encoded":      "Cardholder demographic signal",
    "age_group_encoded":   "Cardholder age-group signal",
    "merchant_fraud_rate": "Merchant historical fraud rate {value:.2%}",
    "category_fraud_rate": "Category historical fraud rate {value:.2%}",
    "month":               "Seasonal (month) signal",
}
DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

UPSERT_SQL = """
    INSERT INTO gold.risk_scores
        (trans_id, trans_num, risk_score, fraud_probability, risk_tier, top_shap_features)
    VALUES %s
    ON CONFLICT (trans_id) DO UPDATE SET
        risk_score        = EXCLUDED.risk_score,
        fraud_probability = EXCLUDED.fraud_probability,
        risk_tier         = EXCLUDED.risk_tier,
        top_shap_features = EXCLUDED.top_shap_features,
        scored_at         = NOW()
"""
UPSERT_TEMPLATE = "(%s, %s, %s, %s, %s, %s::jsonb)"


def score_to_tier(score: int) -> str:
    for threshold, tier in RISK_TIERS:
        if score >= threshold:
            return tier
    return "low"


def format_shap_feature(feature: str, value: float) -> str:
    template = SHAP_FEATURE_DESCRIPTIONS.get(feature, f"{feature} = {{value}}")
    try:
        if feature == "day_of_week":
            return template.format(day_name=DAY_NAMES[int(value) % 7])
        if feature == "city_pop_log":
            return template.format(pop=int(np.exp(value)))
        return template.format(value=value)
    except Exception:
        return f"{feature}: {value:.3f}"


def compute_top_shap(shap_row, feat_row, feature_names, top_n=3) -> list:
    abs_shap = np.abs(shap_row)
    top_idx = np.argsort(abs_shap)[::-1][:top_n]
    out = []
    for idx in top_idx:
        feat = feature_names[idx]
        val = float(feat_row[idx])
        out.append({
            "feature": feat,
            "value": round(val, 4),
            "shap_value": round(float(shap_row[idx]), 4),
            "explanation": format_shap_feature(feat, val),
        })
    return out


def batch_score(artifact=None, force: bool = False) -> int:
    """Score all gold.features rows → gold.risk_scores."""
    existing = db.read_sql("SELECT COUNT(*) AS c FROM gold.risk_scores").iloc[0]["c"]
    if existing and not force:
        log.info("Risk scores already present (%s). Use force=True to rescore.", f"{existing:,}")
        return int(existing)

    if artifact is None:
        artifact = joblib.load(settings.MODELS_DIR / "xgb_fraud.pkl")
    model = artifact["model"]
    features = artifact["feature_cols"]

    log.info("Initializing SHAP TreeExplainer ...")
    explainer = shap.TreeExplainer(model)

    total = int(db.read_sql("SELECT COUNT(*) AS c FROM gold.features").iloc[0]["c"])
    log.info("Scoring %s transactions ...", f"{total:,}")

    conn = db.get_connection()
    processed, offset = 0, 0
    try:
        while offset < total:
            df = load_scoring_frame(BATCH, offset)
            if df.empty:
                break

            X = prepare_matrix(df)
            Xv = X.values
            probs = model.predict_proba(Xv)[:, 1]
            scores = np.clip((probs * 100).astype(int), 0, 100)

            shap_vals = explainer.shap_values(Xv)
            if isinstance(shap_vals, list):       # older SHAP returns per-class list
                shap_vals = shap_vals[1] if len(shap_vals) > 1 else shap_vals[0]

            rows = []
            tids = df["trans_id"].tolist()
            tnums = df["trans_num"].tolist()
            for i in range(len(df)):
                score = int(scores[i])
                top = compute_top_shap(shap_vals[i], Xv[i], features)
                rows.append((
                    int(tids[i]), str(tnums[i]), score,
                    float(probs[i]), score_to_tier(score), json.dumps(top),
                ))

            with conn.cursor() as cur:
                execute_values(cur, UPSERT_SQL, rows, template=UPSERT_TEMPLATE, page_size=5000)

            processed += len(df)
            offset += BATCH
            log.info("  scored %s / %s", f"{processed:,}", f"{total:,}")
    finally:
        conn.close()

    log.info("Batch scoring complete: %s transactions", f"{processed:,}")
    return processed


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    batch_score(force=True)
