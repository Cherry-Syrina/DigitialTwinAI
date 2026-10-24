"""Digital Twin Engine for GlucoTwin AI.

Maintains an in-memory virtual state per synthetic patient:
  * a cursor over the generated sensor time-series (observed vs still-unknown rows)
  * the last update time
  * the most recent model predictions with full provenance (model version,
    input window, timestamps)

``advance`` replays the next synthetic sensor readings ("simulated feed"),
updates the twin state, and can re-run the forecasting model. Observed
readings and model predictions are always returned with an explicit
``source`` field so callers can never confuse measurements with forecasts.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .. import config
from ..ml import features as F
from ..ml.infer import Forecaster, ModelNotAvailableError
from .repository import DataRepository, PatientNotFoundError, DataValidationError
from .risk import Thresholds, assess, load_thresholds


@dataclass
class PredictionRecord:
    generated_at: str
    horizon_minutes: int
    predicted_glucose: float
    model_version: str
    model_type: str
    window_start: str
    window_end: str
    window_rows: int
    source: str = "model_prediction"

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class TwinState:
    patient_id: str
    cursor: int                 # number of SYNTHETIC rows observed (0..synthetic_total)
    synthetic_total: int        # total synthetic rows available to replay
    total_rows: int             # merged total at init (synthetic + imported)
    last_updated: str
    predictions: list[PredictionRecord] = field(default_factory=list)


class DigitalTwinEngine:
    def __init__(
        self,
        repo: DataRepository,
        forecaster: Forecaster,
        buffer_rows: int | None = None,
        thresholds: Thresholds | None = None,
    ):
        self.repo = repo
        self.forecaster = forecaster
        self.thresholds = thresholds or load_thresholds()
        self.buffer_rows = buffer_rows if buffer_rows is not None else config.DEFAULT_DEMO_BUFFER_ROWS
        self._lock = threading.RLock()
        self._states: dict[str, TwinState] = {}
        self._init_states()

    def _init_states(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for pid in self.repo.patient_ids():
            self._states[pid] = self._new_state(pid, now)

    def _new_state(self, patient_id: str, now: str) -> TwinState:
        """Build twin state for one patient.

        The replay cursor only counts synthetic rows: doctor-imported readings
        are always observed regardless of cursor position.
        """
        sensor = self.repo.get_sensor(patient_id)
        synthetic_total = int((~sensor["_is_imported"]).sum())
        if synthetic_total == 0:
            cursor = 0  # doctor-entered patient: nothing to replay
        else:
            min_keep = config.LOOKBACK_ROWS + max(config.FORECAST_HORIZONS) // config.SAMPLE_INTERVAL_MINUTES
            cursor = min(max(min_keep + 1, synthetic_total - self.buffer_rows), synthetic_total)
        return TwinState(
            patient_id=patient_id,
            cursor=cursor,
            synthetic_total=synthetic_total,
            total_rows=int(len(sensor)),
            last_updated=now,
        )

    # ------------------------------------------------------------- helpers
    def engine_patient_ids(self) -> list[str]:
        return self.repo.patient_ids()

    def _state(self, patient_id: str) -> TwinState:
        if patient_id not in self._states:
            # Patient may have been registered after the engine initialised
            # (DataRepository.get_profile raises -> 404 for truly unknown ids).
            sensor = self.repo.get_sensor(patient_id)  # raises PatientNotFoundError
            with self._lock:
                if patient_id not in self._states:
                    state = self._new_state(patient_id, datetime.now(timezone.utc).isoformat(timespec="seconds"))
                    state.total_rows = int(len(sensor))
                    self._states[patient_id] = state
        return self._states[patient_id]

    def full_sensor(self, patient_id: str) -> pd.DataFrame:
        return self.repo.get_sensor(patient_id)

    def observed(self, patient_id: str) -> pd.DataFrame:
        """Synthetic rows up to the replay cursor PLUS every imported reading.

        Imported (doctor-entered) readings are real new observations and are
        always part of the observed state; synthetic rows beyond the cursor
        remain hidden replay data.
        """
        state = self._state(patient_id)
        frame = self.full_sensor(patient_id)
        mask = frame["_is_imported"] | (frame["synthetic_pos"] < state.cursor)
        return frame.loc[mask].reset_index(drop=True)

    def observation_window(self, patient_id: str) -> pd.DataFrame:
        """Last LOOKBACK observed rows with glucose forward-filled."""
        obs = self.observed(patient_id).tail(config.LOOKBACK_ROWS).copy()
        if len(obs) < config.LOOKBACK_ROWS:
            raise DataValidationError(
                f"Not enough observed readings for patient {patient_id} "
                f"(need {config.LOOKBACK_ROWS}, have {len(obs)})"
            )
        obs["glucose_mg_dl"] = obs["glucose_mg_dl"].ffill()
        if obs["glucose_mg_dl"].isna().any():
            raise DataValidationError(
                f"Observation window for {patient_id} contains unresolved missing glucose values"
            )
        return obs

    def context_rows(self, patient_id: str) -> pd.DataFrame:
        """Up to 24h of observed readings (for sleep/aggregate features)."""
        rows_needed = 288
        obs = self.observed(patient_id).tail(rows_needed).copy()
        obs["glucose_mg_dl"] = obs["glucose_mg_dl"].ffill()
        obs["heart_rate_bpm"] = obs["heart_rate_bpm"].ffill()
        return obs

    # ------------------------------------------------------------- reading
    @staticmethod
    def _row_source(row) -> str:
        """Observed rows are labelled honestly: synthetic feed vs entered."""
        if str(row.get("data_label", config.DATA_LABEL_SYNTHETIC)) == config.DATA_LABEL_SYNTHETIC:
            return "synthetic_sensor_feed"
        return "doctor_entered_reading"

    def latest_reading(self, patient_id: str) -> dict | None:
        obs = self.observed(patient_id)
        if obs.empty:
            return None
        row = obs.iloc[-1]
        glucose = row["glucose_mg_dl"]
        return {
            "timestamp": str(row["timestamp"]),
            "glucose_mg_dl": None if pd.isna(glucose) else round(float(glucose), 1),
            "heart_rate_bpm": None if pd.isna(row["heart_rate_bpm"]) else round(float(row["heart_rate_bpm"]), 1),
            "steps_5min": int(row["steps_5min"]) if not pd.isna(row["steps_5min"]) else None,
            "meal_event": int(row["meal_event"]) if not pd.isna(row["meal_event"]) else 0,
            "minutes_since_meal": round(float(row["minutes_since_meal"]), 0)
            if not pd.isna(row["minutes_since_meal"])
            else None,
            "source": self._row_source(row),
            "data_label": str(row.get("data_label", config.DATA_LABEL_SYNTHETIC)),
        }

    def history(
        self,
        patient_id: str,
        hours: float | None = None,
        limit: int | None = None,
        include_future: bool = False,
    ) -> list[dict]:
        frame = self.full_sensor(patient_id) if include_future else self.observed(patient_id)
        if hours is not None:
            cutoff = frame["timestamp"].max() - pd.Timedelta(hours=hours)
            frame = frame[frame["timestamp"] >= cutoff]
        if limit is not None:
            frame = frame.tail(limit)
        out = []
        for _, row in frame.iterrows():
            glucose = row["glucose_mg_dl"]
            hr = row["heart_rate_bpm"]
            out.append(
                {
                    "timestamp": str(row["timestamp"]),
                    "glucose_mg_dl": None if pd.isna(glucose) else round(float(glucose), 1),
                    "heart_rate_bpm": None if pd.isna(hr) else round(float(hr), 1),
                    "steps_5min": int(row["steps_5min"]) if not pd.isna(row["steps_5min"]) else None,
                    "sleep_minutes": float(row["sleep_minutes"])
                    if not pd.isna(row["sleep_minutes"])
                    else None,
                    "meal_event": int(row["meal_event"]) if not pd.isna(row["meal_event"]) else 0,
                    "minutes_since_meal": round(float(row["minutes_since_meal"]), 0)
                    if not pd.isna(row["minutes_since_meal"])
                    else None,
                    "source": self._row_source(row),
                }
            )
        return out

    # ------------------------------------------------------------- advance
    def advance(self, patient_id: str, steps: int = 12) -> dict:
        """Replay the next `steps` synthetic readings into the twin state."""
        if steps < 1:
            raise ValueError("steps must be >= 1")
        with self._lock:
            state = self._state(patient_id)
            added = min(steps, state.synthetic_total - state.cursor)
            full = self.full_sensor(patient_id)
            if added <= 0:
                synthetic = full.loc[~full["_is_imported"]]
                last_ts = str(synthetic.iloc[state.cursor - 1]["timestamp"]) if state.cursor > 0 else None
                if state.synthetic_total == 0:
                    message = "No synthetic sensor feed for this patient (doctor-entered readings only)"
                else:
                    message = "No further synthetic readings available to replay"
                return {
                    "patient_id": patient_id,
                    "added_rows": 0,
                    "message": message,
                    "simulated_time": last_ts,
                }
            state.cursor += added
            state.last_updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
            latest = self.latest_reading(patient_id)
            synthetic = full.loc[~full["_is_imported"]]
            observed_full = self.observed(patient_id)
            return {
                "patient_id": patient_id,
                "added_rows": added,
                "new_cursor": state.cursor,
                "buffer_rows_remaining": int(len(full) - len(observed_full)),
                "simulated_time": str(synthetic.iloc[state.cursor - 1]["timestamp"]),
                "latest_reading": latest,
                "last_updated": state.last_updated,
                "feed_type": "simulated_replay_of_synthetic_sensor_data",
            }

    def notify_data_changed(self, patient_id: str) -> None:
        """Stamp the twin after new readings were persisted (import/manual)."""
        state = self._state(patient_id)
        state.last_updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        state.total_rows = int(len(self.full_sensor(patient_id)))

    # ------------------------------------------------------------ predict
    def _feature_frame(self, patient_id: str, overrides: dict | None = None) -> tuple[pd.DataFrame, dict]:
        static_row = self.repo.static_features_row(patient_id)
        window = self.observation_window(patient_id)
        context = self.context_rows(patient_id)
        feature_columns = list(F.FEATURE_COLUMNS)
        frame = F.build_inference_frame(window, static_row, feature_columns, sleep_rows=context)
        if overrides:
            apply_overrides(frame, overrides)
            if frame.isna().any().any():
                bad = frame.columns[frame.isna().any()].tolist()
                raise ValueError(f"Overrides produced invalid features: {bad}")
        meta = {
            "window_start": str(window["timestamp"].iloc[0]),
            "window_end": str(window["timestamp"].iloc[-1]),
            "window_rows": int(len(window)),
            "static_features": static_row,
            "context_hours_available": round(len(context) * config.SAMPLE_INTERVAL_MINUTES / 60.0, 2),
        }
        return frame, meta

    def predict(
        self,
        patient_id: str,
        horizon_minutes: int | None = None,
        overrides: dict | None = None,
        record: bool = True,
        explain: bool = False,
    ) -> dict:
        """Run the trained model(s) on the twin's latest observed window."""
        state = self._state(patient_id)
        available = self.forecaster.available_horizons()
        if not available:
            raise ModelNotAvailableError(
                "No trained model artifacts found. Run "
                "`python -m backend.scripts.train_model` from the project root."
            )
        horizon = horizon_minutes or config.DEFAULT_HORIZON
        if horizon not in available:
            raise ValueError(
                f"horizon_minutes={horizon} is not trained. Available horizons: {available}"
            )

        frame, window_meta = self._feature_frame(patient_id, overrides)
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        trajectory = []
        primary_prediction = None
        for h in available:
            value = self.forecaster.predict_frame(h, frame)
            ts = pd.Timestamp(window_meta["window_end"]) + pd.Timedelta(minutes=h)
            point = {
                "timestamp": ts.isoformat(),
                "predicted_glucose_mg_dl": value,
                "horizon_minutes": h,
                "source": "model_prediction",
                "interval": self.forecaster.prediction_interval(h, value),
            }
            trajectory.append(point)
            if h == horizon:
                primary_prediction = point

        trajectory.sort(key=lambda p: p["horizon_minutes"])
        current = self.latest_reading(patient_id)
        current_glucose = current["glucose_mg_dl"] if current and current["glucose_mg_dl"] else None
        risk = assess(
            [
                {"predicted_glucose": p["predicted_glucose_mg_dl"], "timestamp": p["timestamp"]}
                for p in trajectory
            ],
            thresholds=self.thresholds,
            current_glucose=current_glucose,
        )

        artifact = self.forecaster.load(horizon)
        record_obj = PredictionRecord(
            generated_at=generated_at,
            horizon_minutes=horizon,
            predicted_glucose=primary_prediction["predicted_glucose_mg_dl"],
            model_version=artifact["model_version"],
            model_type=artifact["model_type"],
            window_start=window_meta["window_start"],
            window_end=window_meta["window_end"],
            window_rows=window_meta["window_rows"],
        )
        if record:
            state.predictions.append(record_obj)
            state.predictions = state.predictions[-20:]
            state.last_updated = generated_at

        result = {
            "patient_id": patient_id,
            "data_label": "synthetic",
            "generated_at": generated_at,
            "horizon_minutes": horizon,
            "predicted_glucose_mg_dl": primary_prediction["predicted_glucose_mg_dl"],
            "prediction_timestamp": primary_prediction["timestamp"],
            "current_glucose_mg_dl": current_glucose,
            "trajectory": trajectory,
            "interval": primary_prediction.get("interval"),
            "risk": risk,
            "model": {
                "version": artifact["model_version"],
                "type": artifact["model_type"],
                "framework": "scikit-learn",
                "input_window": window_meta,
                "available_horizons_minutes": available,
            },
            "source": "model_prediction",
            "simulated_time": window_meta["window_end"],
            "disclaimer": (
                "Prediction generated from synthetic data by an unvalidated research "
                "prototype. Not a medical device. Not for clinical decision-making."
            ),
        }
        if explain:
            try:
                result["feature_contributions"] = self.forecaster.explain_frame(horizon, frame)
            except ModelNotAvailableError:
                result["feature_contributions"] = []
        return result

    def state(self, patient_id: str, include_trajectory: bool = True) -> dict:
        twin_state = self._state(patient_id)
        full = self.full_sensor(patient_id)
        obs = self.observed(patient_id)
        latest = self.latest_reading(patient_id)
        # Display window: last LOOKBACK observed rows (never raises - the
        # forecast below reports "not enough history" explicitly instead).
        window = obs.tail(config.LOOKBACK_ROWS)
        prediction = None
        risk = None
        model_info = None
        error = None
        if include_trajectory:
            try:
                prediction = self.predict(patient_id, record=False, explain=False)
                risk = prediction["risk"]
                model_info = prediction["model"]
            except ModelNotAvailableError as exc:
                error = str(exc)
            except (ValueError, DataValidationError) as exc:
                error = str(exc)

        profile_row = self.repo.get_profile(patient_id).iloc[0]
        data_label = str(profile_row.get("data_label", config.DATA_LABEL_SYNTHETIC))
        observed_rows = int(len(obs))
        total_rows = int(len(full))
        has_synthetic = twin_state.synthetic_total > 0

        return {
            "patient_id": patient_id,
            "data_label": data_label,
            "last_updated": twin_state.last_updated,
            "simulated_time": str(obs["timestamp"].iloc[-1]) if len(obs) else None,
            "observed_rows": observed_rows,
            "total_rows": total_rows,
            "buffer_rows_remaining": int(total_rows - observed_rows),
            "latest_reading": latest,
            "sensor_feed": {
                "type": "synthetic_replay" if has_synthetic else "doctor_entered_readings",
                "last_reading_timestamp": str(obs["timestamp"].iloc[-1]) if len(obs) else None,
                "minutes_between_readings": config.SAMPLE_INTERVAL_MINUTES,
                "freshness": "updated_on_simulated_advance_or_new_reading",
                "synthetic_rows_remaining": int(twin_state.synthetic_total - twin_state.cursor),
            },
            "window_used": {
                "start": str(window["timestamp"].iloc[0]) if len(window) else None,
                "end": str(window["timestamp"].iloc[-1]) if len(window) else None,
                "rows": int(len(window)),
                "columns": ["timestamp", "glucose_mg_dl", "heart_rate_bpm", "steps_5min",
                            "sleep_minutes", "meal_event", "minutes_since_meal"],
            },
            "prediction": None if prediction is None else {
                k: prediction[k]
                for k in (
                    "generated_at",
                    "horizon_minutes",
                    "predicted_glucose_mg_dl",
                    "prediction_timestamp",
                    "trajectory",
                    "interval",
                    "model",
                    "source",
                    "simulated_time",
                    "disclaimer",
                )
                if k in prediction
            },
            "risk": risk,
            "model_error": error,
            "prediction_history": [p.as_dict() for p in twin_state.predictions[-10:]],
        }

    def what_if(self, patient_id: str, horizon_minutes: int, overrides: dict) -> dict:
        """Recompute a prediction under hypothetical input overrides."""
        result = self.predict(
            patient_id,
            horizon_minutes=horizon_minutes,
            overrides=overrides,
            record=False,
            explain=True,
        )
        result["scenario"] = {
            "overrides": overrides,
            "label": "Simulated what-if scenario (hypothetical, not a recommendation)",
            "note": (
                "Overrides are applied to model inputs only. Results are hypothetical "
                "model outputs on synthetic data and must not be interpreted as "
                "treatment advice."
            ),
        }
        return result


WHAT_IF_VALIDATORS = {
    "glucose_offset_mg_dl": (-60.0, 60.0),
    "steps_last_60m": (0.0, 6000.0),
    "heart_rate_last_60m": (40.0, 190.0),
    "sleep_hours_24h": (0.0, 14.0),
    "minutes_since_meal": (0.0, 480.0),
    "meal_event_recent": (0.0, 1.0),
}


def apply_overrides(frame: pd.DataFrame, overrides: dict) -> pd.DataFrame:
    """Apply validated what-if overrides to a single-row feature frame."""
    for key, value in overrides.items():
        if key not in WHAT_IF_VALIDATORS:
            raise ValueError(
                f"Unsupported what-if input '{key}'. Supported: {sorted(WHAT_IF_VALIDATORS)}"
            )
        lo, hi = WHAT_IF_VALIDATORS[key]
        if not (lo <= float(value) <= hi):
            raise ValueError(f"'{key}' must be between {lo} and {hi} (got {value})")

    if "glucose_offset_mg_dl" in overrides:
        offset = float(overrides["glucose_offset_mg_dl"])
        for col in frame.columns:
            if col.startswith("glucose_lag_") or col.startswith("glucose_roll_"):
                frame.loc[:, col] = frame[col].astype(float) + offset
    for key in ("steps_last_60m", "heart_rate_last_60m", "sleep_hours_24h",
                "minutes_since_meal", "meal_event_recent"):
        if key in overrides:
            frame.loc[:, key] = float(overrides[key])
    return frame
