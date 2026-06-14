"""
etl/gold/features.py — GOLD layer: ML feature engineering (pandas)

Reads clean.transactions, engineers the 19 model features (temporal, geo,
velocity windows, encodings, historical fraud rates), and writes gold.features
to Supabase — the feature store consumed by ml/train.py.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import settings, db

log = logging.getLogger(__name__)

CATEGORY_ENCODING = {
    "grocery_pos": 0, "grocery_net": 1, "shopping_pos": 2, "shopping_net": 3,
    "food_dining": 4, "gas_transport": 5, "entertainment": 6, "travel": 7,
    "health_fitness": 8, "home": 9, "kids_pets": 10, "personal_care": 11,
    "misc_pos": 12, "misc_net": 13,
}
ONLINE_CATEGORIES = {"grocery_net", "shopping_net", "misc_net"}

FEATURE_COLUMNS = [
    "trans_id", "trans_num", "trans_at", "amt", "is_fraud",
    "hour_of_day", "day_of_week", "is_weekend", "month",
    "geo_distance_km", "city_pop_log", "is_rural",
    "tx_count_1h", "tx_count_24h", "tx_amount_1h", "tx_amount_24h", "amt_zscore",
    "category_encoded", "is_online",
    "gender_encoded", "age_group_encoded",
    "merchant_fraud_rate", "category_fraud_rate",
]


def _haversine(lat1: np.ndarray, lon1: np.ndarray,
               lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (np.sin(dlat / 2) ** 2
         + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2))
         * np.sin(dlon / 2) ** 2)
    return R * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _velocity_windows(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling 1h and 24h count/sum per customer proxy key, excluding current row."""
    df = df.sort_values("trans_at").copy()
    df["cust_key"] = (df["city"].fillna("") + "_"
                      + df["state"].fillna("") + "_"
                      + df["gender"].fillna(""))

    vel_parts = []
    log.info("  Computing velocity windows (%s customer keys) ...",
             f"{df['cust_key'].nunique():,}")

    for key, grp in df.groupby("cust_key", sort=False):
        g = grp.sort_values("trans_at").set_index("trans_at")
        amt = g["amt"]
        r1h  = amt.rolling("1h",  closed="both")
        r24h = amt.rolling("24h", closed="both")
        vel_parts.append(pd.DataFrame({
            "tx_count_1h":   (r1h.count()  - 1).clip(lower=0).astype(int).values,
            "tx_count_24h":  (r24h.count() - 1).clip(lower=0).astype(int).values,
            "tx_amount_1h":  (r1h.sum()  - amt).clip(lower=0).values,
            "tx_amount_24h": (r24h.sum() - amt).clip(lower=0).values,
        }, index=grp.sort_values("trans_at").index))

    vel_df = pd.concat(vel_parts)
    return df.join(vel_df)


def run_feature_engineering() -> int:
    log.info("Reading clean.transactions ...")
    df = db.read_sql("SELECT * FROM clean.transactions")
    n = len(df)
    log.info("  rows: %s", f"{n:,}")

    df["trans_at"] = pd.to_datetime(df["trans_at"], utc=True)

    # ── Temporal ──────────────────────────────────────────────────────────
    df["hour_of_day"] = df["trans_at"].dt.hour.astype("int16")
    df["day_of_week"] = df["trans_at"].dt.dayofweek.astype("int16")  # 0=Mon..6=Sun
    df["is_weekend"]  = df["day_of_week"].isin([5, 6])
    df["month"]       = df["trans_at"].dt.month.astype("int16")

    # ── Geographic ────────────────────────────────────────────────────────
    has_geo = df["cust_lat"].notna() & df["merch_lat"].notna()
    df["geo_distance_km"] = np.nan
    df.loc[has_geo, "geo_distance_km"] = _haversine(
        df.loc[has_geo, "cust_lat"].to_numpy(),
        df.loc[has_geo, "cust_long"].to_numpy(),
        df.loc[has_geo, "merch_lat"].to_numpy(),
        df.loc[has_geo, "merch_long"].to_numpy(),
    )
    pop = pd.to_numeric(df["city_pop"], errors="coerce").fillna(1).clip(lower=1)
    df["city_pop_log"] = np.log(pop)
    df["is_rural"]     = pop < 50_000

    # ── Velocity windows ──────────────────────────────────────────────────
    log.info("Computing velocity windows ...")
    df = _velocity_windows(df)

    # ── Amount z-score per customer key ──────────────────────────────────
    grp_amt = df.groupby("cust_key")["amt"]
    df["amt_zscore"] = (
        (df["amt"] - grp_amt.transform("mean"))
        / grp_amt.transform("std").replace(0, np.nan)
    ).fillna(0.0)

    # ── Category encoding ─────────────────────────────────────────────────
    df["category_encoded"] = (df["category"].map(CATEGORY_ENCODING)
                                .fillna(12).astype("int16"))
    df["is_online"] = df["category"].isin(ONLINE_CATEGORIES)

    # ── Customer encoding ─────────────────────────────────────────────────
    df["gender_encoded"] = df["gender"].map({"F": 0, "M": 1}).fillna(-1).astype("int16")
    age_enc = {"18-25": 0, "26-35": 1, "36-50": 2, "51-65": 3, "66+": 4}
    df["age_group_encoded"] = df["age_group"].map(age_enc).fillna(2).astype("int16")

    # ── Historical fraud rates ────────────────────────────────────────────
    fraud_int = df["is_fraud"].astype(int)
    df["merchant_fraud_rate"] = (
        fraud_int.groupby(df["merchant"]).transform("mean")
    )
    df["category_fraud_rate"] = (
        fraud_int.groupby(df["category"]).transform("mean")
    )

    # ── Write gold.features ───────────────────────────────────────────────
    out = df[FEATURE_COLUMNS].copy()
    log.info("Truncating gold.features and writing %s rows ...", f"{n:,}")
    db.execute("TRUNCATE TABLE gold.features RESTART IDENTITY CASCADE")

    batch_size = 100_000
    for i in range(0, n, batch_size):
        batch = out.iloc[i: i + batch_size]
        db.bulk_insert(batch, "features", schema="gold", chunksize=5000)
        log.info("  wrote %s / %s", f"{min(i + batch_size, n):,}", f"{n:,}")

    log.info("Gold features complete: %s rows", f"{n:,}")
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    run_feature_engineering()
