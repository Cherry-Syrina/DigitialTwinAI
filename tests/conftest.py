"""Shared fixtures. Ensures synthetic data + trained models exist before tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.main import create_app


def pytest_configure(config):
    """Use a project-local tmp folder (system temp is ACL-blocked on this machine)."""
    root = Path(__file__).resolve().parent.parent
    base = root / ".pytest_tmp"
    base.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(base)
    # Isolate the SQLite overlay: tests never touch real doctor data and start
    # from a clean database each session. Kept OUTSIDE .pytest_tmp because the
    # tmp_path fixture wipes --basetemp lazily (which would hit our open DB).
    db_dir = root / ".pytest_db"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_file = db_dir / "test_glucotwin.db"
    for stale in db_dir.glob("*.db*"):
        try:
            stale.unlink()
        except OSError:
            pass
    os.environ["GLUCOTWIN_DB_PATH"] = str(db_file)


def ensure_artifacts() -> None:
    from backend.scripts.generate_data import generate
    from backend.scripts.train_model import train_all

    if not config.DATA_DIR.joinpath("sensor_readings.csv").exists():
        generate(out_dir=config.DATA_DIR)
    if not config.MODELS_DIR.joinpath("metrics.json").exists():
        train_all()


@pytest.fixture(scope="session", autouse=True)
def project_ready():
    ensure_artifacts()
    yield


@pytest.fixture(scope="session")
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def fresh_client() -> TestClient:
    """A client with a freshly-initialised twin engine (isolated state)."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def auth_client(monkeypatch) -> TestClient:
    """Client with authentication ENABLED, on its own SQLite database.

    Env is set before ``create_app`` so the app builds against the auth DB; the
    shared admin key lets tests create the clinician accounts they need.
    """
    root = Path(__file__).resolve().parent
    db_file = root / ".pytest_db" / "auth_test.db"
    monkeypatch.setenv("GLUCOTWIN_DB_PATH", str(db_file))
    monkeypatch.setenv("GLUCOTWIN_AUTH_ENABLED", "1")
    monkeypatch.setenv("GLUCOTWIN_ADMIN_KEY", "test-admin-key")
    app = create_app()
    with TestClient(app) as c:
        yield c


def make_tiny_sensor(patient_id: str = "T-01", n_hours: int = 48) -> dict:
    """Small deterministic sensor frame (no missing values) for fast unit tests."""
    import numpy as np
    import pandas as pd

    start = pd.Timestamp("2026-01-01 00:00")
    ts = pd.date_range(start, periods=n_hours * 12, freq="5min")
    rng = np.random.default_rng(7)
    base = 120.0 + 8 * np.sin(2 * np.pi * np.arange(len(ts)) / 288)
    glucose = base + rng.normal(0, 1.5, len(ts))
    sensor = pd.DataFrame(
        {
            "patient_id": patient_id,
            "timestamp": ts,
            "glucose_mg_dl": np.round(glucose, 1),
            "heart_rate_bpm": np.round(70 + 3 * np.sin(2 * np.pi * np.arange(len(ts)) / 288) + rng.normal(0, 2, len(ts)), 1),
            "steps_5min": 0,
            "sleep_minutes": np.where(np.arange(len(ts)) % 288 < 96, 5.0, 0.0),
            "meal_event": 0,
            "minutes_since_meal": 120.0,
        }
    )
    sensor.loc[sensor.index % 288 == 90, "meal_event"] = 1
    profiles = pd.DataFrame(
        [{"patient_id": patient_id, "age": 50, "bmi": 26.0, "years_since_diagnosis": 5}]
    )
    summaries = pd.DataFrame(
        [{"patient_id": patient_id, "hba1c_pct": 7.0, "summary_end_date": "2025-12-01"}]
    )
    return {"sensor": sensor, "profiles": profiles, "summaries": summaries}