"""
ml/train.py — XGBoost fraud classifier training with MLflow tracking.

Reads gold.features (Supabase), trains XGBoost (scale_pos_weight handles the
~578:1 imbalance), logs params/metrics/model to MLflow, and saves a joblib
artifact (ml/artifacts/xgb_fraud.pkl) consumed by predict.py.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import joblib
import mlflow
import mlflow.xgboost
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from ml.features import (
    ML_FEATURES,
    ML_TARGET,
    load_training_frame,
    prepare_matrix,
)

log = logging.getLogger(__name__)
MODEL_PATH = settings.MODELS_DIR / "xgb_fraud.pkl"


def _init_mlflow():
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(settings.MLFLOW_EXPERIMENT)


def train_model():
    """Train XGBoost, log to MLflow, save artifact, return artifact dict."""
    _init_mlflow()

    df = load_training_frame()
    n_fraud = int(df[ML_TARGET].sum())
    log.info("Loaded %s rows, %s fraud (%.3f%%)",
             f"{len(df):,}", f"{n_fraud:,}", df[ML_TARGET].mean() * 100)

    X = prepare_matrix(df)
    y = df[ML_TARGET].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=settings.TEST_SIZE,
        random_state=settings.RANDOM_STATE, stratify=y,
    )
    log.info("Train: %s | Test: %s", f"{len(X_train):,}", f"{len(X_test):,}")

    # Compute class imbalance from actual training data (overrides hardcoded value)
    n_legit_train = int((y_train == 0).sum())
    n_fraud_train = int((y_train == 1).sum())
    spw = max(1, n_legit_train // max(n_fraud_train, 1))
    log.info("scale_pos_weight = %d (legit=%s, fraud=%s)",
             spw, f"{n_legit_train:,}", f"{n_fraud_train:,}")
    xgb_params = {**settings.XGBOOST_PARAMS, "scale_pos_weight": spw}

    with mlflow.start_run(run_name="xgb_fraud") as run:
        mlflow.set_tags({
            "stage": "train",
            "dataset": "sparkov_combined",
            "n_features": len(ML_FEATURES),
        })
        mlflow.log_params(xgb_params)
        mlflow.log_params({
            "test_size": settings.TEST_SIZE,
            "n_train": len(X_train),
            "n_test": len(X_test),
            "train_fraud": n_fraud_train,
        })

        log.info("Training XGBoost ...")
        model = XGBClassifier(**xgb_params)
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=50)

        y_prob = model.predict_proba(X_test)[:, 1]
        y_pred = (y_prob >= settings.FRAUD_THRESHOLD).astype(int)

        roc_auc = roc_auc_score(y_test, y_prob)
        pr_auc = average_precision_score(y_test, y_prob)
        report = classification_report(
            y_test, y_pred, target_names=["Legit", "Fraud"],
            output_dict=True, zero_division=0,
        )
        fraud = report["Fraud"]

        metrics = {
            "roc_auc": roc_auc,
            "pr_auc": pr_auc,
            "precision_fraud": fraud["precision"],
            "recall_fraud": fraud["recall"],
            "f1_fraud": fraud["f1-score"],
            "accuracy": report["accuracy"],
        }
        mlflow.log_metrics(metrics)
        for k, v in metrics.items():
            log.info("%-16s %.4f", k, v)

        # Log model to MLflow + feature importances
        mlflow.xgboost.log_model(model, artifact_path="model")
        importances = dict(zip(ML_FEATURES, model.feature_importances_.tolist()))
        mlflow.log_dict(importances, "feature_importances.json")

        artifact = {
            "model": model,
            "feature_cols": ML_FEATURES,
            "metrics": metrics,
            "threshold": settings.FRAUD_THRESHOLD,
            "mlflow_run_id": run.info.run_id,
        }
        joblib.dump(artifact, MODEL_PATH)
        log.info("Model saved → %s (MLflow run %s)", MODEL_PATH, run.info.run_id)

    return artifact


def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}. Run train first.")
    return joblib.load(MODEL_PATH)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    train_model()
