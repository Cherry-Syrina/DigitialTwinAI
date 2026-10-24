"""Tests for feature construction and leakage prevention."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.app import config
from backend.app.ml import features as F
from tests.conftest import make_tiny_sensor


def test_build_supervised_frame_schema():
    tiny = make_tiny_sensor(n_hours=48)
    built = F.build_supervised_frame(
        tiny["sensor"], tiny["profiles"], tiny["summaries"], horizon_minutes=30
    )
    frame = built.features
    for col in F.FEATURE_COLUMNS:
        assert col in frame.columns, f"missing {col}"
    assert built.label_column in frame.columns
    assert "patient_id" not in F.FEATURE_COLUMNS
    assert "timestamp" not in F.FEATURE_COLUMNS
    assert frame[F.FEATURE_COLUMNS].isna().sum().sum() == 0
    assert len(frame) > 0


def test_no_future_leak_in_lags():
    """glucose_lag_1 at row t must equal glucose at the same t, not the label."""
    tiny = make_tiny_sensor(n_hours=24)
    built = F.build_supervised_frame(
        tiny["sensor"], tiny["profiles"], tiny["summaries"], horizon_minutes=60
    )
    frame = built.features
    merged = frame.merge(
        tiny["sensor"][["patient_id", "timestamp", "glucose_mg_dl"]],
        on=["patient_id", "timestamp"],
        how="left",
    )
    assert np.allclose(merged["glucose_lag_1"], merged["glucose_mg_dl"], atol=0.5)


def test_label_is_future_value():
    tiny = make_tiny_sensor(n_hours=24)
    built = F.build_supervised_frame(
        tiny["sensor"], tiny["profiles"], tiny["summaries"], horizon_minutes=60
    )
    frame = built.features
    sensor = tiny["sensor"].sort_values("timestamp").reset_index(drop=True)
    lookup = dict(zip(sensor["timestamp"], sensor["glucose_mg_dl"]))
    diffs = []
    for _, row in frame.iterrows():
        future_ts = row["timestamp"] + pd.Timedelta(minutes=60)
        if future_ts in lookup:
            diffs.append(abs(row[built.label_column] - lookup[future_ts]))
    assert len(diffs) > 0
    assert np.median(diffs) < 0.6, "label does not match glucose at t + horizon"



def test_hba1c_summary_is_not_used_before_its_end_date():
    tiny = make_tiny_sensor(n_hours=72)
    summaries = pd.DataFrame(
        [
            {"patient_id": "T-01", "summary_end_date": "2026-01-01", "hba1c_pct": 6.1},
            {"patient_id": "T-01", "summary_end_date": "2026-01-02", "hba1c_pct": 7.2},
        ]
    )
    built = F.build_supervised_frame(
        tiny["sensor"], tiny["profiles"], summaries, horizon_minutes=30
    )
    before_first_available = built.features["timestamp"] < pd.Timestamp("2026-01-02")
    after_first_available = built.features["timestamp"] < pd.Timestamp("2026-01-03")
    assert not before_first_available.any()
    assert set(built.features.loc[after_first_available, "hba1c_pct"]) == {6.1}
    assert set(built.features.loc[~after_first_available, "hba1c_pct"]) == {7.2}


def test_inference_frame_single_row():
    tiny = make_tiny_sensor(n_hours=24)
    sensor = tiny["sensor"].sort_values("timestamp").reset_index(drop=True)
    window = sensor.iloc[-12:]
    static = {"age": 50.0, "bmi": 26.0, "years_since_diagnosis": 5.0, "hba1c_pct": 7.0}
    frame = F.build_inference_frame(window, static, list(F.FEATURE_COLUMNS))
    assert len(frame) == 1
    assert frame.isna().sum().sum() == 0
    assert frame["glucose_lag_1"].iloc[0] == window["glucose_mg_dl"].iloc[-1]


def test_inference_frame_rejects_missing_glucose():
    tiny = make_tiny_sensor(n_hours=24)
    sensor = tiny["sensor"].sort_values("timestamp").reset_index(drop=True)
    window = sensor.iloc[-12:].copy()
    window.loc[window.index[-1], "glucose_mg_dl"] = np.nan
    static = {"age": 50.0, "bmi": 26.0, "years_since_diagnosis": 5.0, "hba1c_pct": 7.0}
    with pytest.raises(ValueError):
        F.build_inference_frame(window, static, list(F.FEATURE_COLUMNS))


def test_inference_frame_no_future_sleep():
    """sleep_hours_24h must be computed from the supplied context only."""
    tiny = make_tiny_sensor(n_hours=24)
    sensor = tiny["sensor"].sort_values("timestamp").reset_index(drop=True)
    window = sensor.iloc[-12:]
    static = {"age": 50.0, "bmi": 26.0, "years_since_diagnosis": 5.0, "hba1c_pct": 7.0}
    sleep_rows = sensor.iloc[-288:]
    frame = F.build_inference_frame(window, static, list(F.FEATURE_COLUMNS), sleep_rows=sleep_rows)
    sleep_hours = frame["sleep_hours_24h"].iloc[0]
    expected = sleep_rows["sleep_minutes"].sum() / 60.0
    assert abs(sleep_hours - expected) < 1e-6


def test_build_rejects_bad_horizon():
    tiny = make_tiny_sensor(n_hours=24)
    with pytest.raises(ValueError):
        F.build_supervised_frame(
            tiny["sensor"], tiny["profiles"], tiny["summaries"], horizon_minutes=37
        )