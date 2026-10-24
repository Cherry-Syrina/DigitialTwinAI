"""Tests for the digital twin engine behaviour."""
from __future__ import annotations

import pytest

from backend.app.ml.infer import Forecaster
from backend.app.services.repository import PatientNotFoundError
from backend.app.services.twin import DigitalTwinEngine
from tests.conftest import ensure_artifacts

ensure_artifacts()


@pytest.fixture(scope="module")
def engine():
    from backend.app.services.repository import DataRepository

    repo = DataRepository()
    forecaster = Forecaster()
    return DigitalTwinEngine(repo, forecaster)


def test_state_has_replay_buffer(engine):
    state = engine.state("GT-001")
    assert state["observed_rows"] < state["total_rows"]
    assert state["buffer_rows_remaining"] > 0
    assert state["latest_reading"]["source"] == "synthetic_sensor_feed"
    assert state["window_used"]["rows"] == 12
    assert state["prediction"]["model"]["version"]
    assert state["prediction_history"] == []


def test_advance_updates_state(engine):
    before = engine.state("GT-002")
    assert before["observed_rows"] == before["total_rows"] - before["buffer_rows_remaining"]
    result = engine.advance("GT-002", steps=12)
    assert result["added_rows"] == 12
    after = engine.state("GT-002")
    assert after["observed_rows"] == before["observed_rows"] + 12
    assert result["feed_type"] == "simulated_replay_of_synthetic_sensor_data"


def test_predict_records_provenance(engine):
    before = len(engine._states["GT-001"].predictions)
    pred = engine.predict("GT-001", horizon_minutes=60)
    after_records = engine._states["GT-001"].predictions
    assert len(after_records) == before + 1
    record = after_records[-1]
    assert record.model_version == pred["model"]["version"]
    assert record.horizon_minutes == 60
    assert record.window_rows == 12
    assert record.source == "model_prediction"
    assert pred["trajectory"] == sorted(pred["trajectory"], key=lambda p: p["horizon_minutes"])


def test_predict_rejects_untrained_horizon(engine):
    with pytest.raises(ValueError):
        engine.predict("GT-001", horizon_minutes=77)


def test_prediction_timestamps_are_future_of_window(engine):
    pred = engine.predict("GT-003", horizon_minutes=30)
    window_end = pred["model"]["input_window"]["window_end"]
    for point in pred["trajectory"]:
        assert point["timestamp"] > window_end


def test_what_if_returns_hypothetical(engine):
    base = engine.predict("GT-001", horizon_minutes=60, record=False)
    scenario = engine.what_if(
        "GT-001",
        horizon_minutes=60,
        overrides={"glucose_offset_mg_dl": 40.0, "steps_last_60m": 500},
    )
    assert scenario["scenario"]["label"].startswith("Simulated")
    assert scenario["predicted_glucose_mg_dl"] != base["predicted_glucose_mg_dl"]


def test_what_if_rejects_unknown_key(engine):
    with pytest.raises(ValueError):
        engine.what_if("GT-001", horizon_minutes=60, overrides={"bogus": 1})


def test_what_if_rejects_out_of_range(engine):
    with pytest.raises(ValueError):
        engine.what_if("GT-001", horizon_minutes=60, overrides={"heart_rate_last_60m": 500})


def test_unknown_patient_raises(engine):
    with pytest.raises(PatientNotFoundError):
        engine.state("GT-999")


def test_history_observations_marked(engine):
    readings = engine.history("GT-001", hours=1, limit=50)
    assert len(readings) <= 50
    assert all(r["source"] == "synthetic_sensor_feed" for r in readings)


def test_risk_is_returned_for_non_zero_trajectory(engine):
    pred = engine.predict("GT-003", horizon_minutes=60, record=False)
    risk = pred["risk"]
    assert risk["level"] in {"none", "medium", "high", "critical"}
    assert risk["thresholds"]["unit"] == "mg/dL"
    assert any(f["type"] == "hyperglycemia" for f in risk["flags"]) or risk["level"] == "none"