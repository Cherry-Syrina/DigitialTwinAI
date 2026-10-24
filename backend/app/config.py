"""GlucoTwin AI application configuration and path resolution."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Project root: <glucotwin-ai>/  (backend/app/config.py -> parents[2])
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.getenv("GLUCOTWIN_DATA_DIR", PROJECT_ROOT / "data" / "synthetic"))
MODELS_DIR = Path(os.getenv("GLUCOTWIN_MODELS_DIR", PROJECT_ROOT / "models"))

PROFILES_CSV = DATA_DIR / "patient_profiles.csv"
EHR_CSV = DATA_DIR / "ehr_records.csv"
SUMMARIES_CSV = DATA_DIR / "glucose_summaries.csv"
SENSOR_CSV = DATA_DIR / "sensor_readings.csv"
MANIFEST_JSON = DATA_DIR / "manifest.json"

THRESHOLDS_JSON = Path(
    os.getenv("GLUCOTWIN_THRESHOLDS_FILE", PROJECT_ROOT / "backend" / "app" / "data" / "thresholds.json")
)

METRICS_JSON = MODELS_DIR / "metrics.json"

# --- Doctor-entered data persistence (SQLite) --------------------------------
# New patients / readings recorded through the API live here. The synthetic
# CSV dataset stays read-only. Override with GLUCOTWIN_DB_PATH (used by tests).
DATA_LABEL_SYNTHETIC = "synthetic"
DATA_LABEL_ENTERED = "doctor_entered"

# Import limits (defence in depth; Pydantic enforces the same bounds).
MAX_IMPORT_ROWS = 5000
MAX_CSV_TEXT_BYTES = 2 * 1024 * 1024  # 2 MiB of raw CSV text per upload
MAX_FIELD_LENGTH = 500

# --- Modelling configuration -------------------------------------------------
SAMPLE_INTERVAL_MINUTES = 5
LOOKBACK_ROWS = 12  # 60 minutes of history used to build features
FORECAST_HORIZONS = (30, 60, 90, 120)  # minutes ahead
DEFAULT_HORIZON = 60
# Set so the replay window starts 2026-09-07 07:00 (dawn/breakfast rise) - an
# interesting demo window where the forecast for poorer-control patients
# triggers a hyperglycemia flag.
DEFAULT_DEMO_BUFFER_ROWS = 204

RANDOM_SEED = 42

# --- API configuration -------------------------------------------------------
API_TITLE = "GlucoTwin AI API"
API_VERSION = "1.0.0"
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

# --- Authentication (opt-in) -------------------------------------------------
# The API is open by default so the local demo runs without setup. Setting
# GLUCOTWIN_AUTH_ENABLED=1 turns on real bearer-token authentication with
# patient-level ownership isolation (see services/auth.py and api/auth_routes.py).
AUTH_TOKEN_TTL_HOURS = 12
MIN_PASSWORD_LENGTH = 10


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def auth_enabled() -> bool:
    """Read on every call (not cached) so tests can toggle it per app."""
    return _flag("GLUCOTWIN_AUTH_ENABLED", False)


def auth_token_ttl_hours() -> int:
    try:
        value = int(os.getenv("GLUCOTWIN_TOKEN_TTL_HOURS", str(AUTH_TOKEN_TTL_HOURS)))
    except (TypeError, ValueError):
        return AUTH_TOKEN_TTL_HOURS
    return max(1, min(value, 24 * 30))


def admin_key() -> str:
    """Shared secret required to create clinician accounts (never a default)."""
    return os.getenv("GLUCOTWIN_ADMIN_KEY", "").strip()


@lru_cache(maxsize=1)
def cors_origins() -> list[str]:
    raw = os.getenv("GLUCOTWIN_CORS_ORIGINS")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(DEFAULT_CORS_ORIGINS)


def db_path() -> Path:
    """SQLite database file for doctor-entered records.

    Read from the environment on every call (not cached) so tests can point
    the app at an isolated database before constructing it.
    """
    raw = os.getenv("GLUCOTWIN_DB_PATH")
    if raw:
        return Path(raw)
    return PROJECT_ROOT / "data" / "glucotwin.db"
