"""Data access layer: synthetic CSV dataset (read-only) + SQLite overlay.

Reads merge the read-only synthetic CSVs with doctor-entered records stored
in SQLite (``services/db.py``), so new patients/readings survive restarts
while the demo dataset stays untouched. Writes go to SQLite only and refresh
the in-memory merge under a lock.

Data validation failures raise :class:`DataValidationError` which the API maps
to an explicit 500 error - the app never silently substitutes fabricated
data. Unknown patients raise :class:`PatientNotFoundError` (404) and duplicate
registration attempts raise :class:`DuplicatePatientError` (409).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from .. import config
from .db import Database

READINGS_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class DataValidationError(RuntimeError):
    """Raised when the dataset is missing, malformed, or incomplete."""


class PatientNotFoundError(LookupError):
    """Raised when a requested patient id does not exist."""


class DuplicatePatientError(LookupError):
    """Raised when a registration would collide with an existing patient id."""


REQUIRED_SENSOR_COLUMNS = [
    "patient_id",
    "timestamp",
    "glucose_mg_dl",
    "heart_rate_bpm",
    "steps_5min",
    "sleep_minutes",
    "meal_event",
    "minutes_since_meal",
]

REQUIRED_PROFILE_COLUMNS = [
    "patient_id",
    "name",
    "age",
    "sex",
    "diabetes_type",
    "years_since_diagnosis",
    "bmi",
    "medical_history",
    "current_medications",
]

PROFILE_TEXT_COLUMNS = [
    "name", "sex", "diabetes_type", "medical_history",
    "current_medications", "family_history", "smoking_status",
    "activity_level", "data_label",
]

PIPE_COLUMNS = ["medical_history", "current_medications"]


def _join_pipe(value) -> str:
    """Normalise list-or-string field values to the pipe format used by CSVs."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "|".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


class DataRepository:
    """Loads CSVs once, validates them, and serves in-memory merged slices."""

    def __init__(self, data_dir: Path | str | None = None, db: Database | None = None):
        self.data_dir = Path(data_dir or config.DATA_DIR)
        self.db = db if db is not None else Database()
        self._lock = threading.RLock()
        self.profiles: pd.DataFrame | None = None
        self.ehr: pd.DataFrame | None = None
        self.summaries: pd.DataFrame | None = None
        self.sensor: pd.DataFrame | None = None
        self.manifest: dict | None = None
        self.loaded_at: str | None = None
        self._csv: dict[str, pd.DataFrame] = {}
        self._load_csv()
        self._reload_overlay()

    # ------------------------------------------------------------------ load
    def _load_csv(self) -> None:
        required_files = [
            "patient_profiles.csv",
            "ehr_records.csv",
            "glucose_summaries.csv",
            "sensor_readings.csv",
        ]
        missing = [f for f in required_files if not (self.data_dir / f).exists()]
        if missing:
            raise DataValidationError(
                f"Synthetic dataset incomplete in {self.data_dir}: missing {missing}. "
                "Run `python -m backend.scripts.generate_data` from the project root."
            )

        try:
            profiles = pd.read_csv(self.data_dir / "patient_profiles.csv")
            ehr = pd.read_csv(self.data_dir / "ehr_records.csv")
            summaries = pd.read_csv(self.data_dir / "glucose_summaries.csv")
            sensor = pd.read_csv(self.data_dir / "sensor_readings.csv", parse_dates=["timestamp"])
        except Exception as exc:
            raise DataValidationError(f"Failed to parse synthetic dataset: {exc}") from exc

        missing_cols = [c for c in REQUIRED_PROFILE_COLUMNS if c not in profiles.columns]
        if missing_cols:
            raise DataValidationError(f"patient_profiles.csv missing columns: {missing_cols}")
        missing_cols = [c for c in REQUIRED_SENSOR_COLUMNS if c not in sensor.columns]
        if missing_cols:
            raise DataValidationError(f"sensor_readings.csv missing columns: {missing_cols}")
        if len(profiles) == 0 or len(sensor) == 0:
            raise DataValidationError("Synthetic dataset contains no rows")
        if sensor.duplicated(subset=["patient_id", "timestamp"]).any():
            raise DataValidationError("sensor_readings.csv contains duplicate patient/timestamp rows")
        if not set(profiles["patient_id"]).issubset(set(sensor["patient_id"])):
            raise DataValidationError("sensor_readings.csv is missing patients from profiles")

        sensor = sensor.sort_values(["patient_id", "timestamp"]).reset_index(drop=True)
        profiles = profiles.copy()
        profiles["bmi"] = pd.to_numeric(profiles["bmi"], errors="coerce")
        for col in PROFILE_TEXT_COLUMNS:
            if col in profiles.columns:
                profiles[col] = (
                    profiles[col].fillna("Not recorded").astype(str)
                )
        if "diabetes_type" in profiles.columns:
            profiles["diabetes_type"] = profiles["diabetes_type"].replace(
                {"None": "No diabetes", "nan": "Not recorded"}
            )

        manifest_path = self.data_dir / "manifest.json"
        manifest = {}
        if manifest_path.exists():
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)

        with self._lock:
            self._csv = {
                "profiles": profiles,
                "ehr": ehr,
                "summaries": summaries,
                "sensor": sensor,
            }
            self.manifest = manifest

    def _reload_overlay(self) -> None:
        """Re-merge the read-only CSVs with the current SQLite contents."""
        csv_profiles = self._csv["profiles"]
        csv_ehr = self._csv["ehr"]
        csv_summaries = self._csv["summaries"]
        csv_sensor = self._csv["sensor"]

        db_profiles = self.db.load_patients_frame()
        db_ehr = self.db.load_ehr_frame()
        db_summaries = self.db.load_summaries_frame()
        db_sensor = self.db.load_sensor_frame()

        profiles = pd.concat([csv_profiles, db_profiles], ignore_index=True, sort=False)
        profiles = profiles.drop_duplicates(subset=["patient_id"], keep="first")
        profiles["bmi"] = pd.to_numeric(profiles["bmi"], errors="coerce")
        for col in PROFILE_TEXT_COLUMNS:
            if col in profiles.columns:
                profiles[col] = profiles[col].fillna("Not recorded").astype(str)
        if "diabetes_type" in profiles.columns:
            profiles["diabetes_type"] = profiles["diabetes_type"].replace(
                {"None": "No diabetes", "nan": "Not recorded"}
            )

        ehr = pd.concat([csv_ehr, db_ehr], ignore_index=True, sort=False)
        summaries = pd.concat([csv_summaries, db_summaries], ignore_index=True, sort=False)

        csv_sensor = csv_sensor.copy()
        csv_sensor["_is_imported"] = False
        db_sensor = db_sensor.copy()
        db_sensor["_is_imported"] = True
        sensor = pd.concat([csv_sensor, db_sensor], ignore_index=True, sort=False)
        sensor = sensor.sort_values(
            ["patient_id", "timestamp"], kind="stable", na_position="last"
        ).reset_index(drop=True)
        # Safety net: the import pipeline rejects duplicates before insert;
        # if one ever slips through, the synthetic row wins.
        sensor = sensor.drop_duplicates(subset=["patient_id", "timestamp"], keep="first")
        sensor["synthetic_pos"] = -1
        not_imported = ~sensor["_is_imported"]
        sensor.loc[not_imported, "synthetic_pos"] = (
            sensor.loc[not_imported].groupby("patient_id").cumcount()
        )

        with self._lock:
            self.profiles = profiles
            self.ehr = ehr
            self.summaries = summaries
            self.sensor = sensor
            self.loaded_at = pd.Timestamp.now().isoformat(timespec="seconds")

    # ---------------------------------------------------------------- helpers
    def patient_ids(self) -> list[str]:
        assert self.profiles is not None
        return self.profiles["patient_id"].tolist()

    def get_profile(self, patient_id: str) -> pd.DataFrame:
        assert self.profiles is not None
        row = self.profiles[self.profiles["patient_id"] == patient_id]
        if row.empty:
            raise PatientNotFoundError(f"Patient '{patient_id}' not found")
        return row

    def get_ehr(self, patient_id: str) -> pd.DataFrame:
        assert self.ehr is not None
        self.get_profile(patient_id)
        rows = self.ehr[self.ehr["patient_id"] == patient_id]
        return rows.sort_values("record_date", ascending=False).reset_index(drop=True)

    def get_summaries(self, patient_id: str) -> pd.DataFrame:
        assert self.summaries is not None
        self.get_profile(patient_id)
        rows = self.summaries[self.summaries["patient_id"] == patient_id]
        return rows.sort_values("summary_end_date", ascending=False).reset_index(drop=True)

    def get_sensor(self, patient_id: str) -> pd.DataFrame:
        assert self.sensor is not None
        self.get_profile(patient_id)
        return self.sensor[self.sensor["patient_id"] == patient_id].reset_index(drop=True)

    def existing_reading_timestamps(self, patient_id: str) -> set[str]:
        """Canonical timestamps already recorded for this patient (CSV + DB)."""
        sensor = self.get_sensor(patient_id)
        if sensor.empty:
            return set()
        return {
            ts.strftime(READINGS_TIMESTAMP_FORMAT)
            for ts in sensor["timestamp"].dropna()
        }

    def latest_summary_row(self, patient_id: str) -> dict:
        summaries = self.get_summaries(patient_id)
        if summaries.empty:
            raise DataValidationError(f"No glucose summary rows for patient {patient_id}")
        return summaries.iloc[0].to_dict()

    def static_features_row(self, patient_id: str) -> dict:
        """Static feature values used by the model (no identifiers)."""
        profile = self.get_profile(patient_id).iloc[0].to_dict()
        summary = self.latest_summary_row(patient_id)
        return {
            "age": float(profile["age"]),
            "bmi": float(profile["bmi"]),
            "years_since_diagnosis": float(profile["years_since_diagnosis"]),
            "hba1c_pct": float(summary["hba1c_pct"]),
        }

    def patient_list(self) -> list[dict]:
        assert self.profiles is not None and self.sensor is not None
        out = []
        for _, row in self.profiles.iterrows():
            pid = row["patient_id"]
            sensor = self.sensor[self.sensor["patient_id"] == pid]
            valid = sensor["glucose_mg_dl"].dropna()
            out.append(
                {
                    "patient_id": pid,
                    "name": row["name"],
                    "age": int(row["age"]),
                    "sex": row["sex"],
                    "diabetes_type": row["diabetes_type"],
                    "latest_glucose_mg_dl": round(float(valid.iloc[-1]), 1) if len(valid) else None,
                    "latest_reading_time": str(sensor["timestamp"].max()) if len(sensor) else None,
                    "sensor_rows": int(len(sensor)),
                    "data_label": str(row.get("data_label") or config.DATA_LABEL_SYNTHETIC),
                }
            )
        return out

    # ---------------------------------------------------------------- writes
    def patient_owner(self, patient_id: str) -> str | None:
        """Owning clinician id, or ``None`` for shared/synthetic patients.

        Raises ``PatientNotFoundError`` for unknown ids so ownership checks fail
        closed (404 before any data is returned).
        """
        self.get_profile(patient_id)
        row = self.db.get_patient(patient_id)
        return (row or {}).get("owner_id")

    def _ensure_id_free(self, patient_id: str) -> None:
        assert self.profiles is not None
        if patient_id in set(self.profiles["patient_id"]):
            raise DuplicatePatientError(
                f"Patient ID '{patient_id}' already exists. Choose a different, unique ID."
            )

    def create_patient(self, payload: dict, owner_id: str | None = None) -> dict:
        """Persist a new doctor-registered patient (profile + initial HbA1c row).

        ``owner_id`` records the clinician account that created the patient so
        that, when authentication is enabled, other accounts cannot see it.
        """
        patient_id = payload["patient_id"]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        row = {
            "patient_id": patient_id,
            "name": payload["name"],
            "age": int(payload["age"]),
            "sex": payload["sex"],
            "diabetes_type": payload["diabetes_type"],
            "years_since_diagnosis": int(payload.get("years_since_diagnosis", 0)),
            "height_cm": float(payload["height_cm"]),
            "weight_kg": float(payload["weight_kg"]),
            "bmi": float(payload["bmi"]),
            "medical_history": _join_pipe(payload.get("medical_history")),
            "current_medications": _join_pipe(payload.get("current_medications")),
            "family_history": payload.get("family_history") or "Not recorded",
            "smoking_status": payload.get("smoking_status") or "Not recorded",
            "activity_level": payload.get("activity_level") or "Not recorded",
            "data_label": config.DATA_LABEL_ENTERED,
            "created_at": now,
            "updated_at": now,
        }
        if owner_id is not None:
            row["owner_id"] = owner_id
        with self._lock:
            self._ensure_id_free(patient_id)
            self.db.insert_patient(row)
            # The doctor-entered HbA1c is stored as an explicit registration
            # summary so the forecasting model has its required static feature.
            self.db.insert_summary(
                {
                    "patient_id": patient_id,
                    "summary_period": "at_registration",
                    "summary_end_date": date.today().isoformat(),
                    "mean_glucose_mg_dl": None,
                    "std_glucose_mg_dl": None,
                    "time_in_range_pct": None,
                    "time_above_range_pct": None,
                    "time_below_range_pct": None,
                    "readings_count": None,
                    "hba1c_pct": float(payload["hba1c_pct"]),
                    "data_label": config.DATA_LABEL_ENTERED,
                }
            )
            self._reload_overlay()
        return self.get_profile(patient_id).iloc[0].to_dict()

    def update_patient(self, patient_id: str, fields: dict) -> dict:
        """Update an existing patient's profile (PUT). Never changes the ID."""
        self.get_profile(patient_id)  # raises PatientNotFoundError
        allowed = {
            "name", "age", "sex", "diabetes_type", "years_since_diagnosis",
            "height_cm", "weight_kg", "bmi", "medical_history",
            "current_medications", "family_history", "smoking_status",
            "activity_level",
        }
        updates: dict = {}
        for key, value in fields.items():
            if key in ("patient_id", "data_label", "hba1c_pct") or key not in allowed:
                continue
            if key in PIPE_COLUMNS:
                updates[key] = _join_pipe(value)
            elif isinstance(value, (int, float)) and key in ("age", "years_since_diagnosis"):
                updates[key] = int(value)
            else:
                updates[key] = value
        hba1c = fields.get("hba1c_pct")

        with self._lock:
            if updates:
                self.db.update_patient(patient_id, updates)
            if hba1c is not None:
                # Append a new dated summary row rather than rewriting history.
                self.db.insert_summary(
                    {
                        "patient_id": patient_id,
                        "summary_period": "doctor_updated",
                        "summary_end_date": date.today().isoformat(),
                        "mean_glucose_mg_dl": None,
                        "std_glucose_mg_dl": None,
                        "time_in_range_pct": None,
                        "time_above_range_pct": None,
                        "time_below_range_pct": None,
                        "readings_count": None,
                        "hba1c_pct": float(hba1c),
                        "data_label": config.DATA_LABEL_ENTERED,
                    }
                )
            self._reload_overlay()
        return self.get_profile(patient_id).iloc[0].to_dict()

    def add_ehr(self, patient_id: str, payload: dict) -> dict:
        """Append an EHR-style record for an existing patient."""
        self.get_profile(patient_id)  # raises PatientNotFoundError
        row = {
            "record_id": f"EHR-DB-{uuid4().hex[:10].upper()}",
            "patient_id": patient_id,
            "record_date": payload["record_date"],
            "record_type": payload["record_type"],
            "hba1c_pct": payload.get("hba1c_pct"),
            "systolic_bp": payload.get("systolic_bp"),
            "diastolic_bp": payload.get("diastolic_bp"),
            "ldl_mg_dl": payload.get("ldl_mg_dl"),
            "medications": _join_pipe(payload.get("medications")) or None,
            "clinician_note": payload.get("clinician_note"),
            "data_label": config.DATA_LABEL_ENTERED,
        }
        with self._lock:
            self.db.insert_ehr(row)
            self._reload_overlay()
        return row

    def add_readings(
        self,
        patient_id: str,
        entries: list[dict],
        entry_method: str = "manual_entry",
        dry_run: bool = False,
    ) -> dict:
        """Validate duplicates and (unless dry-run) persist normalised readings.

        ``entries`` are already validated/normalised (see ``services/importing``).
        Returns accepted/rejected rows plus counts - rejected rows never raise,
        so bulk imports can partially succeed with explicit feedback.
        """
        self.get_profile(patient_id)  # raises PatientNotFoundError
        with self._lock:
            existing = self.existing_reading_timestamps(patient_id)
            seen_batch: set[str] = set()
            rows_out: list[dict] = []
            accepted: list[dict] = []
            duplicates = 0

            for entry in entries:
                ts = entry["timestamp"]
                if ts in existing:
                    duplicates += 1
                    rows_out.append(
                        {
                            "row_index": entry["row_index"],
                            "timestamp": ts,
                            "status": "rejected",
                            "reason": "duplicate timestamp (already recorded for this patient)",
                        }
                    )
                    continue
                if ts in seen_batch:
                    duplicates += 1
                    rows_out.append(
                        {
                            "row_index": entry["row_index"],
                            "timestamp": ts,
                            "status": "rejected",
                            "reason": "duplicate timestamp within this batch",
                        }
                    )
                    continue
                seen_batch.add(ts)
                stored = {
                    **entry,
                    "patient_id": patient_id,
                    "data_label": config.DATA_LABEL_ENTERED,
                    "entry_method": entry_method,
                }
                accepted.append(stored)
                rows_out.append({**entry, "status": "accepted", "reason": None})

            rows_out.sort(key=lambda r: r["row_index"])
            persisted = False
            if accepted and not dry_run:
                try:
                    self.db.insert_readings(accepted)
                except sqlite3.IntegrityError as exc:
                    raise DataValidationError(
                        "Reading insert collided with a concurrent write; please retry."
                    ) from exc
                self._reload_overlay()
                persisted = True

        return {
            "patient_id": patient_id,
            "rows": rows_out,
            "accepted_count": len(accepted),
            "rejected_count": len(rows_out) - len(accepted),
            "duplicate_count": duplicates,
            "persisted": persisted,
            "dry_run": bool(dry_run),
        }
