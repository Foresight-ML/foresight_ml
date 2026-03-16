"""Class imbalance handling for financial distress prediction.

Provides SMOTE oversampling (training split only), class weight
computation for XGBoost, and split summary report generation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE

from src.data.split import NON_NUMERIC_COLS, TARGET_COL, _upload_to_gcs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SMOTE oversampling
# ---------------------------------------------------------------------------


def apply_smote(
    train_df: pd.DataFrame,
    target_col: str = TARGET_COL,
    random_state: int = 42,
) -> pd.DataFrame:
    """Apply SMOTE oversampling to the training split only.

    Only numeric feature columns are used for SMOTE synthesis.
    Non-numeric columns (identifiers, categoricals) are carried
    forward from the original rows and filled with the nearest
    neighbour's value for synthetic rows.

    Args:
        train_df: Training DataFrame (pre-split, never val/test).
        target_col: Name of the binary target column.
        random_state: Random seed for reproducibility.

    Returns:
        Oversampled training DataFrame with balanced classes.
    """
    before_counts = train_df[target_col].value_counts().to_dict()
    log.info("SMOTE — class distribution before: %s", before_counts)

    # Separate numeric features for SMOTE
    numeric_cols = [
        c
        for c in train_df.select_dtypes(include=np.number).columns
        if c != target_col and c not in NON_NUMERIC_COLS
    ]

    X = train_df[numeric_cols].values
    y = train_df[target_col].values

    # Replace NaN/inf with 0 for SMOTE (already handled by scaler in pipeline,
    # but SMOTE may run before scaling)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    smote = SMOTE(random_state=random_state)
    X_resampled, y_resampled = smote.fit_resample(X, y)

    # Build resampled DataFrame
    resampled_df = pd.DataFrame(X_resampled, columns=numeric_cols)
    resampled_df[target_col] = y_resampled

    # Carry forward non-numeric columns for original rows
    non_numeric = [c for c in train_df.columns if c not in numeric_cols and c != target_col]
    n_original = len(train_df)
    for col in non_numeric:
        original_values = train_df[col].values
        # Synthetic rows get NaN for non-numeric columns
        padded = np.empty(len(resampled_df), dtype=object)
        padded[:n_original] = original_values
        padded[n_original:] = np.nan
        resampled_df[col] = padded

    # Reorder columns to match original
    resampled_df = resampled_df[[c for c in train_df.columns if c in resampled_df.columns]]

    after_counts = resampled_df[target_col].value_counts().to_dict()
    log.info("SMOTE — class distribution after: %s", after_counts)
    log.info("SMOTE — rows: %d -> %d", n_original, len(resampled_df))

    return resampled_df


# ---------------------------------------------------------------------------
# Class weights
# ---------------------------------------------------------------------------


def compute_class_weights(
    train_df: pd.DataFrame,
    target_col: str = TARGET_COL,
) -> dict[str, Any]:
    """Compute class weights for XGBoost scale_pos_weight.

    ``scale_pos_weight = count(negative) / count(positive)``

    Args:
        train_df: Training DataFrame.
        target_col: Name of the binary target column.

    Returns:
        Dict with ``scale_pos_weight``, ``n_positive``, ``n_negative``.
    """
    counts = train_df[target_col].value_counts()
    n_pos = int(counts.get(1, 0))
    n_neg = int(counts.get(0, 0))
    scale_pos_weight = n_neg / n_pos if n_pos > 0 else 1.0

    result = {
        "scale_pos_weight": round(scale_pos_weight, 4),
        "n_positive": n_pos,
        "n_negative": n_neg,
    }
    log.info("Class weights: %s", result)
    return result


def save_class_weights(
    weights: dict[str, Any],
    out_dir: Path,
    bucket: str | None = None,
    gcs_path: str | None = None,
) -> Path:
    """Save class weights as JSON.

    Args:
        weights: Dict from ``compute_class_weights``.
        out_dir: Local output directory.
        bucket: GCS bucket name (optional).
        gcs_path: GCS object path (optional).

    Returns:
        Local path to the saved JSON.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    local_path = out_dir / "class_weights.json"
    with open(local_path, "w") as f:
        json.dump(weights, f, indent=2)
    log.info("Saved class weights: %s", local_path)
    if bucket and gcs_path:
        _upload_to_gcs(local_path, bucket, gcs_path)
    return local_path


# ---------------------------------------------------------------------------
# Split summary report
# ---------------------------------------------------------------------------


def _safe_value_counts(df: pd.DataFrame, col: str) -> dict[str, int]:
    """Return value_counts as a dict with native Python keys and values.

    Converts numpy.int64 keys to ``str`` so the result is JSON-serializable.
    """
    return {str(k): int(v) for k, v in df[col].value_counts().items()}


def _distress_rate(df: pd.DataFrame, target_col: str = TARGET_COL) -> float:
    """Compute distress rate (fraction of positive class)."""
    if len(df) == 0:
        return 0.0
    return float(df[target_col].mean())


def generate_split_report(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    train_smote: pd.DataFrame | None = None,
    class_weights: dict[str, Any] | None = None,
    out_dir: Path | None = None,
    bucket: str | None = None,
    gcs_path: str | None = None,
) -> dict[str, Any]:
    """Generate a summary report of the data splits.

    Args:
        train: Training split (pre-SMOTE).
        val: Validation split.
        test: Test split.
        train_smote: Training split after SMOTE (optional).
        class_weights: Dict from ``compute_class_weights`` (optional).
        out_dir: Local directory to save report JSON (optional).
        bucket: GCS bucket name (optional).
        gcs_path: GCS object path (optional).

    Returns:
        Report dict with row counts, distress rates, and class distributions.
    """
    report: dict[str, Any] = {
        "splits": {
            "train": {
                "rows": len(train),
                "distress_rate": round(_distress_rate(train), 6),
                "class_distribution": _safe_value_counts(train, TARGET_COL),
            },
            "val": {
                "rows": len(val),
                "distress_rate": round(_distress_rate(val), 6),
                "class_distribution": _safe_value_counts(val, TARGET_COL),
            },
            "test": {
                "rows": len(test),
                "distress_rate": round(_distress_rate(test), 6),
                "class_distribution": _safe_value_counts(test, TARGET_COL),
            },
        },
    }

    if train_smote is not None:
        report["smote"] = {
            "rows_before": len(train),
            "rows_after": len(train_smote),
            "class_distribution_after": _safe_value_counts(train_smote, TARGET_COL),
        }

    if class_weights is not None:
        report["class_weights"] = class_weights

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        local_path = out_dir / "split_report.json"
        with open(local_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        log.info("Saved split report: %s", local_path)
        if bucket and gcs_path:
            _upload_to_gcs(local_path, bucket, gcs_path)

    return report
