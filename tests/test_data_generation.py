"""Tests for the deterministic synthetic data generator."""
from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from backend.scripts import generate_data


@pytest.fixture()
def tmp_data(tmp_path):
    return generate_data.generate(out_dir=tmp_path, seed=42, days=3)


def test_generates_all_expected_files(tmp_path):
    generate_data.generate(out_dir=tmp_path, seed=1, days=3)
    for name in [
        "patient_profiles.csv",
        "ehr_records.csv",
        "glucose_summaries.csv",
        "sensor_readings.csv",
        "manifest.json",
    ]:
        assert (tmp_path / name).exists(), f"missing {name}"


def test_deterministic_same_seed(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    generate_data.generate(out_dir=a, seed=2026, days=3)
    generate_data.generate(out_dir=b, seed=2026, days=3)
    for name in ["patient_profiles.csv", "sensor_readings.csv"]:
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_different_seeds_differ(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    generate_data.generate(out_dir=a, seed=1, days=3)
    generate_data.generate(out_dir=b, seed=2, days=3)
    assert (a / "sensor_readings.csv").read_bytes() != (b / "sensor_readings.csv").read_bytes()


def test_schema_and_content(tmp_data, tmp_path):
    sensor = pd.read_csv(tmp_path / "sensor_readings.csv", parse_dates=["timestamp"])
    profiles = pd.read_csv(tmp_path / "patient_profiles.csv")
    summaries = pd.read_csv(tmp_path / "glucose_summaries.csv")

    required = [
        "patient_id", "timestamp", "glucose_mg_dl", "heart_rate_bpm",
        "steps_5min", "sleep_minutes", "meal_event", "minutes_since_meal",
    ]
    assert request_columns(sensor, required)
    assert set(profiles["patient_id"]) <= set(sensor["patient_id"])
    assert not sensor.duplicated(subset=["patient_id", "timestamp"]).any()
    assert "seed" in tmp_data and tmp_data["seed"] == 42


def test_missing_values_present(tmp_data, tmp_path):
    sensor = pd.read_csv(tmp_path / "sensor_readings.csv")
    assert sensor["glucose_mg_dl"].isna().sum() > 0
    assert sensor["heart_rate_bpm"].isna().sum() > 0


def test_patient_id_not_blank(tmp_data, tmp_path):
    sensor = pd.read_csv(tmp_path / "sensor_readings.csv")
    assert (sensor["patient_id"].astype(str).str.strip() != "").all()


def request_columns(frame, columns):
    return all(c in frame.columns for c in columns)