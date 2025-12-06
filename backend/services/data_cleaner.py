"""Data cleaning utilities for ADCEA."""

from __future__ import annotations

from typing import Tuple, Dict, Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.ensemble import IsolationForest


def clean_df(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Perform simple, robust cleaning on a DataFrame.

    Steps:
    - Strip column names
    - Drop completely empty columns
    - Impute numeric columns with median
    - Impute object columns with most frequent
    - Optionally detect and drop extreme outliers via IsolationForest
    """
    original_shape = df.shape
    df = df.copy()

    # Normalize column labels
    df.columns = [str(c).strip() for c in df.columns]

    # Drop fully empty columns
    empty_cols = [c for c in df.columns if df[c].isna().all()]
    df = df.drop(columns=empty_cols) if empty_cols else df

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    # Numeric imputation
    if numeric_cols:
        num_imp = SimpleImputer(strategy="median")
        df[numeric_cols] = num_imp.fit_transform(df[numeric_cols])

    # Categorical imputation
    if cat_cols:
        cat_imp = SimpleImputer(strategy="most_frequent")
        df[cat_cols] = cat_imp.fit_transform(df[cat_cols])

    # Optional: basic anomaly filtering on numeric features
    removed_outliers = 0
    if numeric_cols and df.shape[0] > 20:
        iso = IsolationForest(
            n_estimators=100,
            contamination=0.02,
            random_state=42,
        )
        mask = iso.fit_predict(df[numeric_cols])
        keep_mask = mask == 1
        removed_outliers = int((~keep_mask).sum())
        df = df[keep_mask].reset_index(drop=True)

    summary: Dict[str, Any] = {
        "original_rows": int(original_shape[0]),
        "original_cols": int(original_shape[1]),
        "clean_rows": int(df.shape[0]),
        "clean_cols": int(df.shape[1]),
        "dropped_empty_cols": empty_cols,
        "removed_outliers": removed_outliers,
        "numeric_cols": numeric_cols,
        "categorical_cols": cat_cols,
    }
    return df, summary
