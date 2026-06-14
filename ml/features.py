"""
ml/features.py — feature definitions + loaders shared by train/predict/evaluate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import ML_FEATURES, ML_TARGET  # noqa: F401  (re-exported)
from config import db

# Columns the model never trains on but we carry for joining/scoring
ID_COLUMNS = ["trans_id", "trans_num"]


def load_training_frame(limit: int | None = None) -> pd.DataFrame:
    """Load gold.features (features + target) for training/evaluation."""
    cols = ", ".join(ML_FEATURES + [ML_TARGET])
    sql = f"SELECT {cols} FROM gold.features"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return db.read_sql(sql)


def load_scoring_frame(limit: int, offset: int) -> pd.DataFrame:
    """Load a batch of gold.features (ids + features) for batch scoring."""
    cols = ", ".join(ID_COLUMNS + ML_FEATURES)
    sql = (
        f"SELECT {cols} FROM gold.features "
        f"ORDER BY trans_id LIMIT {int(limit)} OFFSET {int(offset)}"
    )
    return db.read_sql(sql)


def prepare_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Return a float feature matrix with nulls filled (geo_distance etc.)."""
    X = df[ML_FEATURES].copy()
    for col in ML_FEATURES:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    return X.fillna(0.0).astype(float)
