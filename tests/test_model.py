"""Tests for temporal train/test separation and model training."""
from __future__ import annotations

import pandas as pd
import pytest

from backend.scripts.train_model import temporal_split, train_horizon


def test_temporal_split_is_time_ordered():
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=100, freq="h"),
            "x": range(100),
            "y": range(100),
        }
    )
    train, test = temporal_split(frame, train_fraction=0.7)
    assert train["timestamp"].max() < test["timestamp"].min()
    assert len(train) > 0 and len(test) > 0
    assert set(train["timestamp"]) & set(test["timestamp"]) == set()



def test_temporal_split_keeps_equal_timestamps_together():
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=20, freq="h").repeat(8),
            "patient_id": [f"P{i}" for _ in range(20) for i in range(8)],
            "y": range(160),
        }
    )
    train, test = temporal_split(frame, train_fraction=0.7)
    assert train["timestamp"].max() < test["timestamp"].min()
    assert set(train["timestamp"]).isdisjoint(set(test["timestamp"]))


def test_temporal_split_fraction():
    frame = pd.DataFrame({"timestamp": pd.date_range("2026-01-01", periods=100, freq="h"), "x": 1})
    train, test = temporal_split(frame, train_fraction=0.8)
    assert len(train) == 80
    assert len(test) == 20


def test_train_horizon_on_real_dataset(project_ready):
    from backend.app import config
    import pandas as pd

    sensor = pd.read_csv(config.DATA_DIR / "sensor_readings.csv", parse_dates=["timestamp"])
    profiles = pd.read_csv(config.DATA_DIR / "patient_profiles.csv")
    summaries = pd.read_csv(config.DATA_DIR / "glucose_summaries.csv")

    artifact, summary = train_horizon(sensor, profiles, summaries, horizon_minutes=60)
    assert artifact["model"] is not None
    assert artifact["model_type"] in {"ridge_regression", "gradient_boosting"}
    assert "glucose_lag_1" in artifact["feature_columns"]
    assert list(sorted(summary["baselines"].keys())) == [
        "gradient_boosting",
        "persistence",
        "ridge_regression",
    ]
    mae = summary["metrics"]["mae"]
    rmse = summary["metrics"]["rmse"]
    pers_mae = summary["baselines"]["persistence"]["mae"]
    assert mae > 0 and rmse > 0
    assert mae < pers_mae, (
        "selected model should beat the persistence baseline; "
        f"selected MAE={mae}, persistence MAE={pers_mae}"
    )


def test_train_all_writes_artifacts(tmp_path, project_ready):
    from backend.app import config
    from backend.scripts.train_model import train_all
    import pandas as pd
    import json
    import joblib
    from pathlib import Path

    out = tmp_path / "models"
    train_all(data_dir=config.DATA_DIR, out_dir=out, horizons=(30, 60))
    assert (out / "model_h30.joblib").exists()
    assert (out / "model_h60.joblib").exists()
    assert (out / "metrics.json").exists()

    art = joblib.load(out / "model_h60.joblib")
    assert art["model_version"]
    assert art["horizon_minutes"] == 60
    assert all(k in art["metrics"]["selected"] for k in ("mae", "rmse"))

    metrics = json.loads((out / "metrics.json").read_text())
    assert set(metrics["horizons"]) == {"30", "60"}
    assert "disclaimer" in metrics


def test_metrics_reproducible_seed():
    from tests.conftest import make_tiny_sensor

    tiny = make_tiny_sensor(n_hours=48)
    artifact_a, _ = train_horizon(
        tiny["sensor"], tiny["profiles"], tiny["summaries"], horizon_minutes=30, seed=99
    )
    artifact_b, _ = train_horizon(
        tiny["sensor"], tiny["profiles"], tiny["summaries"], horizon_minutes=30, seed=99
    )
    assert artifact_a["metrics"]["selected"] == artifact_b["metrics"]["selected"]