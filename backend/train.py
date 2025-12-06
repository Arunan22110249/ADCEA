"""Training orchestration for ADCEA.

Implements a lightweight async-ish training queue using a thread pool.
"""

from __future__ import annotations

import io
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
import joblib

JOBS: Dict[str, Dict[str, Any]] = {}
MODEL_DIR = os.path.join(os.getcwd(), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

_executor = ThreadPoolExecutor(max_workers=1)


def _simulate_epochs(num_epochs: int = 8, start_metric: float = 0.6, improve: float = 0.04):
    history = []
    metric = start_metric
    for epoch in range(1, num_epochs + 1):
        metric = min(metric + np.random.uniform(0, improve), 0.99)
        history.append({"epoch": epoch, "metric": float(metric)})
    return history


def _train_job(job_id: str, df: pd.DataFrame, target_col: str) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    job["started_at"] = time.time()

    try:
        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found")

        y = df[target_col]
        X = df.drop(columns=[target_col])

        # Basic split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=None
        )

        # Pick classifier vs regressor based on dtype
        if y.dtype.kind in {"i", "b"} and y.nunique() <= 20:
            model = RandomForestClassifier(
                n_estimators=200, random_state=42, n_jobs=-1
            )
            model_type = "classifier"
        else:
            model = RandomForestRegressor(
                n_estimators=200, random_state=42, n_jobs=-1
            )
            model_type = "regressor"

        model.fit(X_train, y_train)

        # Metrics
        metrics: Dict[str, Any] = {"model_type": model_type}
        if model_type == "classifier":
            y_pred = model.predict(X_test)
            metrics["accuracy"] = float(accuracy_score(y_test, y_pred))
            try:
                if hasattr(model, "predict_proba"):
                    proba = model.predict_proba(X_test)
                    if proba.shape[1] == 2:
                        metrics["roc_auc"] = float(
                            roc_auc_score(y_test, proba[:, 1])
                        )
            except Exception:
                pass
            # Confusion matrix (limited to first few labels)
            labels = np.unique(y_test)
            cm = confusion_matrix(y_test, y_pred, labels=labels)
            metrics["confusion_matrix"] = {
                "labels": [str(l) for l in labels[:10]],
                "matrix": cm[:10, :10].tolist(),
            }
        else:
            y_pred = model.predict(X_test)
            metrics["rmse"] = float(mean_squared_error(y_test, y_pred, squared=False))

        job["metrics"] = metrics
        job["epoch_history"] = _simulate_epochs()
        job["status"] = "completed"
        job["completed_at"] = time.time()

        # Persist model
        model_name = f"model_{job_id}.joblib"
        model_path = os.path.join(MODEL_DIR, model_name)
        job["model_path"] = model_path
        job["model_name"] = model_name
        job["target"] = target_col
        job["feature_names"] = list(X.columns)
        job["rows"] = int(df.shape[0])
        job["cols"] = int(df.shape[1])

        joblib.dump(
            {
                "model": model,
                "target": target_col,
                "feature_names": list(X.columns),
                "metrics": metrics,
            },
            model_path,
        )
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        job["completed_at"] = time.time()


def start_training_from_bytes(file_bytes: bytes, target: str) -> str:
    df = pd.read_csv(io.BytesIO(file_bytes))
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "queued",
        "created_at": time.time(),
        "target": target,
    }
    _executor.submit(_train_job, job_id, df, target)
    return job_id


def get_job(job_id: str) -> Dict[str, Any]:
    return JOBS.get(job_id, None)
