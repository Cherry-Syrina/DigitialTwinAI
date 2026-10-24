"""SQLite persistence for doctor-entered records (patients, readings, EHR).

The synthetic CSV dataset remains the read-only base layer; anything created
through the API (new patients, manual/CSV-imported readings, EHR entries)
is stored here so it survives backend restarts.

Only stdlib ``sqlite3`` is used - no new dependencies. The database file is
resolved from :func:`backend.app.config.db_path` (``GLUCOTWIN_DB_PATH`` env
override, default ``data/glucotwin.db``).
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .. import config

PATIENT_COLUMNS = [
    "patient_id", "name", "age", "sex", "diabetes_type",
    "years_since_diagnosis", "height_cm", "weight_kg", "bmi",
    "medical_history", "current_medications", "family_history",
    "smoking_status", "activity_level", "data_label",
]

EHR_COLUMNS = [
    "record_id", "patient_id", "record_date", "record_type", "hba1c_pct",
    "systolic_bp", "diastolic_bp", "ldl_mg_dl", "medications",
    "clinician_note", "data_label",
]

SUMMARY_COLUMNS = [
    "patient_id", "summary_period", "summary_end_date", "mean_glucose_mg_dl",
    "std_glucose_mg_dl", "time_in_range_pct", "time_above_range_pct",
    "time_below_range_pct", "readings_count", "hba1c_pct", "data_label",
]

SENSOR_COLUMNS = [
    "patient_id", "timestamp", "glucose_mg_dl", "heart_rate_bpm",
    "steps_5min", "sleep_minutes", "meal_event", "minutes_since_meal",
    "data_label",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    sex TEXT NOT NULL,
    diabetes_type TEXT NOT NULL,
    years_since_diagnosis INTEGER NOT NULL,
    height_cm REAL NOT NULL,
    weight_kg REAL NOT NULL,
    bmi REAL NOT NULL,
    medical_history TEXT NOT NULL DEFAULT '',
    current_medications TEXT NOT NULL DEFAULT '',
    family_history TEXT NOT NULL DEFAULT '',
    smoking_status TEXT NOT NULL DEFAULT 'Not recorded',
    activity_level TEXT NOT NULL DEFAULT 'Not recorded',
    data_label TEXT NOT NULL,
    owner_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS glucose_summaries (
    patient_id TEXT NOT NULL,
    summary_period TEXT NOT NULL,
    summary_end_date TEXT NOT NULL,
    mean_glucose_mg_dl REAL,
    std_glucose_mg_dl REAL,
    time_in_range_pct REAL,
    time_above_range_pct REAL,
    time_below_range_pct REAL,
    readings_count INTEGER,
    hba1c_pct REAL NOT NULL,
    data_label TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ehr_records (
    record_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    record_date TEXT NOT NULL,
    record_type TEXT NOT NULL,
    hba1c_pct REAL,
    systolic_bp INTEGER,
    diastolic_bp INTEGER,
    ldl_mg_dl REAL,
    medications TEXT,
    clinician_note TEXT,
    data_label TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    glucose_mg_dl REAL,
    heart_rate_bpm REAL,
    steps_5min INTEGER,
    sleep_minutes REAL,
    meal_event INTEGER NOT NULL DEFAULT 0,
    minutes_since_meal REAL,
    data_label TEXT NOT NULL,
    entry_method TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (patient_id, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_sensor_patient_ts
    ON sensor_readings (patient_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_ehr_patient ON ehr_records (patient_id);
CREATE INDEX IF NOT EXISTS idx_summaries_patient ON glucose_summaries (patient_id);

-- Authentication (only used when GLUCOTWIN_AUTH_ENABLED is on). Passwords are
-- stored as salted PBKDF2-SHA256 digests and session tokens as SHA-256 hashes,
-- so neither credential can be recovered from the database file.
CREATE TABLE IF NOT EXISTS clinicians (
    clinician_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'clinician',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    clinician_id TEXT NOT NULL REFERENCES clinicians (clinician_id) ON DELETE CASCADE,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_clinician ON auth_tokens (clinician_id);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Single-connection SQLite store guarded by a re-entrant lock.

    FastAPI runs sync endpoints on a threadpool, so every access is
    serialised through ``self._lock`` on one shared connection.
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else config.db_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Additive migrations for databases created by older versions."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(patients)")}
        if "owner_id" not in cols:
            self._conn.execute("ALTER TABLE patients ADD COLUMN owner_id TEXT")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------- patients
    def get_patient(self, patient_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM patients WHERE patient_id = ?", (patient_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_patient_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT patient_id FROM patients ORDER BY patient_id"
            ).fetchall()
        return [r["patient_id"] for r in rows]

    def insert_patient(self, row: dict) -> None:
        fields = [c for c in PATIENT_COLUMNS if c in row]
        values = [row[f] for f in fields]
        if "owner_id" in row:
            fields.append("owner_id")
            values.append(row["owner_id"])
        now = utc_now_iso()
        fields += ["created_at", "updated_at"]
        values += [now, now]
        placeholders = ", ".join("?" for _ in fields)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO patients ({', '.join(fields)}) VALUES ({placeholders})",
                values,
            )
            self._conn.commit()

    def update_patient(self, patient_id: str, fields: dict) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE patients SET {assignments}, updated_at = ? WHERE patient_id = ?",
                [*fields.values(), utc_now_iso(), patient_id],
            )
            self._conn.commit()

    # ------------------------------------------------------------ summaries
    def insert_summary(self, row: dict) -> None:
        fields = [c for c in SUMMARY_COLUMNS if c in row]
        placeholders = ", ".join("?" for _ in fields)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO glucose_summaries ({', '.join(fields)}) VALUES ({placeholders})",
                [row[f] for f in fields],
            )
            self._conn.commit()

    # ------------------------------------------------------------------ ehr
    def insert_ehr(self, row: dict) -> None:
        fields = [c for c in EHR_COLUMNS if c in row]
        placeholders = ", ".join("?" for _ in fields)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO ehr_records ({', '.join(fields)}) VALUES ({placeholders})",
                [row[f] for f in fields],
            )
            self._conn.commit()

    # ------------------------------------------------------------- readings
    def insert_readings(self, rows: list[dict]) -> int:
        """Persist normalised readings. Raises sqlite3.IntegrityError on a
        (patient_id, timestamp) collision - callers pre-check, this is the
        final race-safe guard."""
        if not rows:
            return 0
        fields = SENSOR_COLUMNS + ["entry_method", "created_at"]
        placeholders = ", ".join("?" for _ in fields)
        now = utc_now_iso()
        values = [
            [r.get(c) for c in SENSOR_COLUMNS]
            + [r.get("entry_method") or "manual_entry", now]
            for r in rows
        ]
        with self._lock:
            self._conn.executemany(
                f"INSERT INTO sensor_readings ({', '.join(fields)}) VALUES ({placeholders})",
                values,
            )
            self._conn.commit()
        return len(rows)

    # ------------------------------------------------------------- overlays
    def _frame(self, sql: str, columns: list[str]) -> pd.DataFrame:
        with self._lock:
            rows = self._conn.execute(sql).fetchall()
        data = {c: [] for c in columns}
        for row in rows:
            for c in columns:
                data[c].append(row[c])
        return pd.DataFrame(data, columns=columns)

    def load_patients_frame(self) -> pd.DataFrame:
        return self._frame(
            f"SELECT {', '.join(PATIENT_COLUMNS)} FROM patients ORDER BY patient_id",
            PATIENT_COLUMNS,
        )

    def load_ehr_frame(self) -> pd.DataFrame:
        return self._frame(
            f"SELECT {', '.join(EHR_COLUMNS)} FROM ehr_records ORDER BY record_date DESC",
            EHR_COLUMNS,
        )

    def load_summaries_frame(self) -> pd.DataFrame:
        return self._frame(
            f"SELECT {', '.join(SUMMARY_COLUMNS)} FROM glucose_summaries "
            "ORDER BY summary_end_date DESC",
            SUMMARY_COLUMNS,
        )

    def load_sensor_frame(self) -> pd.DataFrame:
        cols = SENSOR_COLUMNS + ["entry_method", "created_at"]
        frame = self._frame(
            f"SELECT {', '.join(cols)} FROM sensor_readings ORDER BY patient_id, timestamp",
            cols,
        )
        if not frame.empty:
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        return frame

    # --------------------------------------------------------- authentication
    def insert_clinician(self, row: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO clinicians (clinician_id, username, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    row["clinician_id"],
                    row["username"],
                    row["password_hash"],
                    row.get("role", "clinician"),
                    utc_now_iso(),
                ),
            )
            self._conn.commit()

    def get_clinician_by_username(self, username: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM clinicians WHERE username = ? COLLATE NOCASE", (username,)
            ).fetchone()
        return dict(row) if row else None

    def get_clinician(self, clinician_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM clinicians WHERE clinician_id = ?", (clinician_id,)
            ).fetchone()
        return dict(row) if row else None

    def count_clinicians(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) AS n FROM clinicians").fetchone()["n"])

    def insert_token(self, token_hash: str, clinician_id: str, issued_at: str, expires_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO auth_tokens (token_hash, clinician_id, issued_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (token_hash, clinician_id, issued_at, expires_at),
            )
            self._conn.commit()

    def get_token(self, token_hash: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM auth_tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
        return dict(row) if row else None

    def delete_token(self, token_hash: str) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (token_hash,))
            self._conn.commit()
            return cur.rowcount

    def purge_expired_tokens(self, now_iso: str) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM auth_tokens WHERE expires_at <= ?", (now_iso,))
            self._conn.commit()
            return cur.rowcount
