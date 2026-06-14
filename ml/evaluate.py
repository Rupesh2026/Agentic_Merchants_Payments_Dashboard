"""
ml/evaluate.py — model evaluation + explainability plots, logged to MLflow.

Produces ROC curve, precision-recall curve, confusion matrix and a SHAP summary
plot (saved to ml/artifacts/ and logged as MLflow artifacts).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")          # headless / no display
import matplotlib.pyplot as plt
import numpy as np
import shap
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    average_precision_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

import mlflow

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from ml.features import ML_FEATURES, ML_TARGET, load_training_frame, prepare_matrix

log = logging.getLogger(__name__)
EVAL_SAMPLE = 200_000
SHAP_SAMPLE = 5_000


def _save(fig_path: Path):
    plt.tight_layout()
    plt.savefig(fig_path, dpi=110, bbox_inches="tight")
    plt.close()
    log.info("saved %s", fig_path.name)


def evaluate_model(artifact) -> dict:
    model = artifact["model"]

    df = load_training_frame(limit=EVAL_SAMPLE)
    X = prepare_matrix(df)
    y = df[ML_TARGET].astype(int)

    probs = model.predict_proba(X.values)[:, 1]
    preds = (probs >= settings.FRAUD_THRESHOLD).astype(int)

    roc_auc = roc_auc_score(y, probs)
    pr_auc = average_precision_score(y, probs)
    log.info("Eval ROC-AUC %.4f | PR-AUC %.4f", roc_auc, pr_auc)
    log.info("\n%s", classification_report(y, preds, target_names=["Legit", "Fraud"],
                                            zero_division=0))

    # ROC curve
    fpr, tpr, _ = roc_curve(y, probs)
    plt.figure(figsize=(5, 5))
    plt.plot(fpr, tpr, color=settings.PRIMARY_COLOR, label=f"AUC = {roc_auc:.3f}")
    plt.plot([0, 1], [0, 1], "--", color="#bbb")
    plt.xlabel("False Positive Rate"); plt.ylabel("True Positive Rate")
    plt.title("ROC Curve"); plt.legend(loc="lower right")
    _save(settings.MODELS_DIR / "roc_curve.png")

    # Precision-Recall curve
    prec, rec, _ = precision_recall_curve(y, probs)
    plt.figure(figsize=(5, 5))
    plt.plot(rec, prec, color=settings.SUCCESS_COLOR, label=f"PR-AUC = {pr_auc:.3f}")
    plt.xlabel("Recall"); plt.ylabel("Precision")
    plt.title("Precision-Recall Curve"); plt.legend(loc="upper right")
    _save(settings.MODELS_DIR / "pr_curve.png")

    # Confusion matrix
    cm = confusion_matrix(y, preds)
    ConfusionMatrixDisplay(cm, display_labels=["Legit", "Fraud"]).plot(
        cmap="Purples", colorbar=False)
    plt.title("Confusion Matrix")
    _save(settings.MODELS_DIR / "confusion_matrix.png")

    # SHAP summary (sample for speed)
    log.info("Computing SHAP summary on %s sampled rows ...", f"{SHAP_SAMPLE:,}")
    Xs = X.sample(min(SHAP_SAMPLE, len(X)), random_state=settings.RANDOM_STATE)
    explainer = shap.TreeExplainer(model)
    shap_vals = explainer.shap_values(Xs.values)
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[1] if len(shap_vals) > 1 else shap_vals[0]
    shap.summary_plot(shap_vals, Xs, feature_names=ML_FEATURES, show=False)
    _save(settings.MODELS_DIR / "shap_summary.png")

    # Log to MLflow
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(settings.MLFLOW_EXPERIMENT)
    with mlflow.start_run(run_name="evaluate"):
        mlflow.set_tag("stage", "evaluate")
        mlflow.log_metrics({"eval_roc_auc": roc_auc, "eval_pr_auc": pr_auc})
        for png in ["roc_curve.png", "pr_curve.png", "confusion_matrix.png", "shap_summary.png"]:
            mlflow.log_artifact(str(settings.MODELS_DIR / png), artifact_path="plots")

    return {"roc_auc": roc_auc, "pr_auc": pr_auc}


if __name__ == "__main__":
    import joblib
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    art = joblib.load(settings.MODELS_DIR / "xgb_fraud.pkl")
    evaluate_model(art)
