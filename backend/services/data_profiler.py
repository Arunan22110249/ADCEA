"""Lightweight data profiling for ADCEA."""

from __future__ import annotations

import pandas as pd
from typing import Dict, Any


def profile_df(df: pd.DataFrame) -> Dict[str, Any]:
    return {
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "missing": {c: int(df[c].isna().sum()) for c in df.columns},
        "preview": df.head(10).to_dict(orient="records"),
    }
