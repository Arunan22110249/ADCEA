"""Feature engineering utilities for ADCEA."""

from __future__ import annotations

from typing import Tuple, Dict

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestRegressor


def engineer_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Create a simple, generic feature matrix and feature importance scores.

    This is intentionally opinionated but robust:
    - pairwise products of numeric columns
    - date parts for datetime-like columns
    - basic TF–IDF features for the first text column
    - optional RandomForest-based importance scores when 'target' is present
    """
    df = df.copy()
    features = pd.DataFrame(index=df.index)

    # Numeric interactions
    num_cols = df.select_dtypes(include=["number"]).columns.tolist()
    for i in range(len(num_cols)):
        for j in range(i + 1, len(num_cols)):
            a, b = num_cols[i], num_cols[j]
            features[f"{a}__mul__{b}"] = df[a] * df[b]

    # Datetime features
    for col in df.columns:
        if np.issubdtype(df[col].dtype, np.datetime64):
            features[f"{col}__month"] = df[col].dt.month
            features[f"{col}__weekday"] = df[col].dt.weekday

    # Text features – first object column
    text_cols = df.select_dtypes(include=["object", "string"]).columns.tolist()
    if text_cols:
        tv = TfidfVectorizer(max_features=50)
        tfidf = tv.fit_transform(df[text_cols[0]].fillna(""))  # type: ignore[arg-type]
        tfidf_df = pd.DataFrame(
            tfidf.toarray(),
            index=df.index,
            columns=[f"tfidf_{i}" for i in range(tfidf.shape[1])],
        )
        features = pd.concat([features, tfidf_df], axis=1)

    scores: Dict[str, float] = {}
    if "target" in df.columns and not features.empty:
        try:
            rf = RandomForestRegressor(
                n_estimators=50,
                random_state=42,
                n_jobs=-1,
            )
            rf.fit(features.fillna(0), df["target"])
            scores = dict(zip(features.columns, rf.feature_importances_))
        except Exception:
            scores = {c: 0.0 for c in features.columns}

    return features, scores
