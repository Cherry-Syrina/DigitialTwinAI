"""Reproducible training/evaluation pipeline for GlucoTwin AI.

Trains one forecasting model per horizon (30/60/90/120 min):
  * persistence baseline  (predict current glucose)
  * Ridge linear baseline
  * Gradient Boosting regressor (candidate production model)

Training, validation, and test periods are chronological; horizon-sized embargoes prevent label windows crossing split boundaries.
Artifacts (model + metadata) are written to ``models/`` and a consolidated
``metrics.json`` is produced for the API and dashboard.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import config  # noqa: E402
from backend.app.ml import features as F  # noqa: E402

MODEL_VERSION = "1.2.0"
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
CONFORMAL_LEVELS = (0.80, 0.90)
PRIMARY_INTERVAL_LEVEL = 0.90

DISCLAIMER = (
    "Metrics are computed on held-out synthetic test data only. They demonstrate "
    "that the pipeline works technically and DO NOT establish clinical accuracy. "
    "Clinical use requires validation on real, consented data and regulatory review."
)


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 3),
        "rmse": round(_rmse(y_true, y_pred), 3),
    }


def _conformal_half_width(abs_residuals: np.ndarray, level: float) -> float:
    """Finite-sample (split-conformal) quantile of absolute residuals."""
    n = len(abs_residuals)
    if n == 0:
        return float("nan")
    quantile = min(1.0, float(np.ceil((n + 1) * level)) / n)
    return float(np.quantile(abs_residuals, quantile, method="higher"))


def _interval_report(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    observation_times: pd.Series,
    target_times: pd.Series,
) -> dict:
    """Calibrate and score on disjoint chronological test periods.

    A horizon-sized embargo separates calibration observations from evaluation
    so calibration labels cannot extend into the coverage period.
    """
    residuals = np.abs(np.asarray(y_true, dtype=float) - np.asarray(y_pred, dtype=float))
    observed = pd.to_datetime(pd.Series(observation_times)).reset_index(drop=True)
    targets = pd.to_datetime(pd.Series(target_times)).reset_index(drop=True)
    n = len(residuals)
    unique_times = observed.sort_values().drop_duplicates().reset_index(drop=True)
    boundary = unique_times.iloc[len(unique_times) // 2] if len(unique_times) >= 2 else None
    if boundary is not None:
        calibration_mask = (observed < boundary) & (targets < boundary)
        evaluation_mask = observed >= boundary
        calibration = residuals[calibration_mask.to_numpy()]
        evaluation = residuals[evaluation_mask.to_numpy()]
        evaluated = len(calibration) >= 20 and len(evaluation) >= 20
    else:
        calibration, evaluation, evaluated = residuals, residuals[:0], False
    if not evaluated:
        calibration, evaluation = residuals, residuals[:0]
    n_embargoed = n - len(calibration) - len(evaluation)

    levels: dict[str, dict] = {}
    for level in CONFORMAL_LEVELS:
        half_width = _conformal_half_width(calibration, level)
        coverage = (
            round(100.0 * float(np.mean(evaluation <= half_width)), 1)
            if evaluated and len(evaluation)
            else None
        )
        levels[f"{level:.2f}"] = {
            "level": level,
            "half_width_mg_dl": round(half_width, 2) if np.isfinite(half_width) else None,
            "coverage_pct": coverage,
            "n_calibration": int(len(calibration)),
            "n_eval": int(len(evaluation)) if evaluated else 0,
            "n_embargoed": int(n_embargoed),
        }

    primary = levels[f"{PRIMARY_INTERVAL_LEVEL:.2f}"]
    return {
        "method": "split_conformal_residual_quantile",
        "level": PRIMARY_INTERVAL_LEVEL,
        "half_width_mg_dl": primary["half_width_mg_dl"],
        "coverage_pct": primary["coverage_pct"],
        "n_calibration": primary["n_calibration"],
        "n_eval": primary["n_eval"],
        "n_embargoed": primary["n_embargoed"],
        "levels": levels,
        "note": (
            "Interval = +/- empirical quantile of held-out residuals (split conformal, "
            "symmetric). Calibrated on the earlier test period; coverage measured on the "
            "later period after a horizon-sized embargo. A research estimate on synthetic "
            "data, NOT a clinically validated confidence interval."
        ),
    }

def temporal_split(
    frame: pd.DataFrame, train_fraction: float = TRAIN_FRACTION
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time-ordered split: earliest rows train, latest rows test."""
    ordered = frame.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    timestamps = pd.to_datetime(ordered["timestamp"]).drop_duplicates().sort_values().reset_index(drop=True)
    if len(timestamps) < 2:
        raise ValueError("At least two distinct timestamps are required for a temporal split")
    split_idx = int(len(timestamps) * train_fraction)
    split_idx = max(1, min(split_idx, len(timestamps) - 1))
    boundary = timestamps.iloc[split_idx]
    train = ordered.loc[pd.to_datetime(ordered["timestamp"]) < boundary].copy()
    test = ordered.loc[pd.to_datetime(ordered["timestamp"]) >= boundary].copy()
    return train, test


def train_horizon(
    sensor: pd.DataFrame,
    profiles: pd.DataFrame,
    summaries: pd.DataFrame,
    horizon_minutes: int,
    seed: int = config.RANDOM_SEED,
) -> tuple[dict, dict]:
    """Train and evaluate all candidate models for a single horizon."""
    built = F.build_supervised_frame(sensor, profiles, summaries, horizon_minutes)
    frame = built.features
    label = built.label_column

    modelled = frame[built.feature_columns + [label, "timestamp"]].copy()
    modelled["target_timestamp"] = (
        pd.to_datetime(modelled["timestamp"]) + pd.to_timedelta(horizon_minutes, unit="m")
    )
    split_train, remainder = temporal_split(modelled, train_fraction=TRAIN_FRACTION)
    validation_start = pd.to_datetime(remainder["timestamp"]).min()
    split_train = split_train.loc[split_train["target_timestamp"] < validation_start].copy()
    split_validation, split_test = temporal_split(remainder, train_fraction=0.5)
    test_start = pd.to_datetime(split_test["timestamp"]).min()
    split_validation = split_validation.loc[split_validation["target_timestamp"] < test_start].copy()

    y_tr = split_train[label].to_numpy(dtype=float)
    y_val = split_validation[label].to_numpy(dtype=float)
    y_te = split_test[label].to_numpy(dtype=float)
    train_X = split_train[built.feature_columns]
    validation_X = split_validation[built.feature_columns]
    test_X = split_test[built.feature_columns]

    if len(train_X) < 100 or len(validation_X) < 50 or len(test_X) < 50:
        raise ValueError(
            f"Not enough rows for horizon {horizon_minutes}m: "
            f"train={len(train_X)}, validation={len(validation_X)}, test={len(test_X)}"
        )

    persistence_pred = test_X["glucose_lag_1"].to_numpy(dtype=float)
    baseline_metrics = _metrics(y_te, persistence_pred)

    ridge_pipe = Pipeline(
        [("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))]
    )
    ridge_pipe.fit(train_X, y_tr)
    ridge_validation_metrics = _metrics(y_val, ridge_pipe.predict(validation_X))

    gbm_pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "model",
                GradientBoostingRegressor(
                    n_estimators=180,
                    learning_rate=0.08,
                    max_depth=3,
                    subsample=0.9,
                    random_state=seed,
                ),
            ),
        ]
    )
    gbm_pipe.fit(train_X, y_tr)
    gbm_validation_metrics = _metrics(y_val, gbm_pipe.predict(validation_X))

    validation_candidates = {
        "ridge_regression": ridge_validation_metrics,
        "gradient_boosting": gbm_validation_metrics,
    }
    selected_name = min(validation_candidates, key=lambda k: validation_candidates[k]["mae"])

    # Select using validation only, refit on all development rows, then evaluate
    # once on the later, untouched test segment.
    development = pd.concat([split_train, split_validation], ignore_index=True)
    development_X = development[built.feature_columns]
    development_y = development[label].to_numpy(dtype=float)
    ridge_pipe.fit(development_X, development_y)
    gbm_pipe.fit(development_X, development_y)
    selected_model = ridge_pipe if selected_name == "ridge_regression" else gbm_pipe
    ridge_metrics = _metrics(y_te, ridge_pipe.predict(test_X))
    gbm_metrics = _metrics(y_te, gbm_pipe.predict(test_X))
    selected_metrics = ridge_metrics if selected_name == "ridge_regression" else gbm_metrics

    selected_pred = selected_model.predict(test_X)
    interval = _interval_report(
        y_te,
        selected_pred,
        split_test["timestamp"],
        split_test["target_timestamp"],
    )

    improved_over_baseline = round(baseline_metrics["mae"] - selected_metrics["mae"], 3)

    artifact = {
        "model": selected_model,
        "model_type": selected_name,
        "model_version": MODEL_VERSION,
        "horizon_minutes": horizon_minutes,
        "lookback_rows": config.LOOKBACK_ROWS,
        "feature_columns": list(built.feature_columns),
        "feature_medians": {
            c: float(np.median(development_X[c].to_numpy(dtype=float))) for c in built.feature_columns
        },
        "metrics": {"selected": selected_metrics, "baselines": {"persistence": baseline_metrics}},
        "interval": interval,
        "all_metrics": {
            "persistence": baseline_metrics,
            "ridge_regression": ridge_metrics,
            "gradient_boosting": gbm_metrics,
        },
        "selected_model_name": selected_name,
        "training": {
            "rows_total": int(len(frame)),
            "rows_train": int(len(train_X)),
            "rows_validation": int(len(validation_X)),
            "rows_development": int(len(development_X)),
            "rows_test": int(len(test_X)),
            "split_method": "time_ordered_70_15_15",
            "train_end_timestamp": str(split_train["timestamp"].max()),
            "validation_end_timestamp": str(split_validation["timestamp"].max()),
            "test_start_timestamp": str(split_test["timestamp"].min()),
            "dropped_rows": built.dropped_rows,
            "seed": seed,
            "trained_at": datetime.now().isoformat(timespec="seconds"),
            "data_source": "synthetic dataset (data/synthetic) - not real clinical data",
        },
        "disclaimer": DISCLAIMER,
    }
    summary = {
        "horizon_minutes": horizon_minutes,
        "selected_model": selected_name,
        "metrics": selected_metrics,
        "baselines": {
            "persistence": baseline_metrics,
            "ridge_regression": ridge_metrics,
            "gradient_boosting": gbm_metrics,
        },
        "mae_improvement_over_persistence": improved_over_baseline,
        "uncertainty": {
            k: interval[k]
            for k in (
                "method", "level", "half_width_mg_dl", "coverage_pct",
                "n_calibration", "n_eval", "n_embargoed",
            )
        },
        "rows_train": int(len(train_X)),
        "rows_validation": int(len(validation_X)),
        "rows_test": int(len(test_X)),
        "split_method": "time_ordered_70_15_15",
        "validation_metrics": validation_candidates,
    }
    return artifact, summary


def train_all(
    data_dir: Path | str = config.DATA_DIR,
    out_dir: Path | str = config.MODELS_DIR,
    seed: int = config.RANDOM_SEED,
    horizons: tuple[int, ...] = config.FORECAST_HORIZONS,
) -> dict:
    data_dir = Path(data_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    profiles = pd.read_csv(data_dir / "patient_profiles.csv")
    summaries = pd.read_csv(data_dir / "glucose_summaries.csv")
    sensor = pd.read_csv(data_dir / "sensor_readings.csv", parse_dates=["timestamp"])

    results: dict[str, dict] = {}
    for horizon in horizons:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            artifact, summary = train_horizon(sensor, profiles, summaries, horizon, seed=seed)
        out_path = out_dir / f"model_h{horizon}.joblib"
        joblib.dump(artifact, out_path)
        results[str(horizon)] = summary
        print(
            f"[horizon {horizon:>3}m] selected={summary['selected_model']:<18} "
            f"MAE={summary['metrics']['mae']:<7} RMSE={summary['metrics']['rmse']:<7} "
            f"(persistence MAE={summary['baselines']['persistence']['mae']}) "
            f"+/-{summary['uncertainty']['half_width_mg_dl']}mg/dL "
            f"({summary['uncertainty']['coverage_pct']}% {int(summary['uncertainty']['level']*100)}% coverage)"
        )

    metrics = {
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "framework": "scikit-learn",
        "task": "regression: predict glucose (mg/dL) at a future horizon from a "
        "60-minute observation window + contextual + static features",
        "split_method": "time_ordered_70_15_15 (train/validation/test; no shuffling)",
        "features": list(F.FEATURE_COLUMNS),
        "feature_note": "patient_id and timestamp are excluded from predictive features",
        "training_data_source": "deterministic synthetic dataset generated by this repository",
        "uncertainty_note": (
            "Per-horizon intervals use absolute residuals from the final temporal test segment. "
            "The earlier half calibrates interval width and the later half measures coverage, "
            "with a horizon-sized embargo between them; model selection uses validation only. "
            "Research estimates on synthetic data only - not clinically validated."
        ),
        "uncertainty": {
            "method": "split_conformal_residual_quantile",
            "level": PRIMARY_INTERVAL_LEVEL,
            "note": "primary 90% interval summary available per horizon below",
        },
        "horizons": results,
        "disclaimer": DISCLAIMER,
    }
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    print(f"Wrote {out_dir / 'metrics.json'}")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train GlucoTwin AI forecasting models")
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    parser.add_argument("--data", type=str, default=str(config.DATA_DIR))
    parser.add_argument("--out", type=str, default=str(config.MODELS_DIR))
    parser.add_argument(
        "--horizons", type=int, nargs="+", default=list(config.FORECAST_HORIZONS)
    )
    args = parser.parse_args()
    train_all(
        data_dir=args.data,
        out_dir=args.out,
        seed=args.seed,
        horizons=tuple(args.horizons),
    )


if __name__ == "__main__":
    main()
