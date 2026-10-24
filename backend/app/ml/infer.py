"""Model artifact loading and inference for GlucoTwin AI.

Raises :class:`ModelNotAvailableError` when artifacts are missing so the API
can return an explicit error instead of fabricating predictions.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .. import config


class ModelNotAvailableError(RuntimeError):
    """Raised when a trained model artifact cannot be loaded."""


class MetricsNotAvailableError(RuntimeError):
    """Raised when trained metrics metadata cannot be loaded."""


class Forecaster:
    """Thread-safe lazy loader/executor for trained horizon models."""

    def __init__(self, models_dir: Path | str | None = None):
        self.models_dir = Path(models_dir or config.MODELS_DIR)
        self._cache: dict[int, dict] = {}
        self._lock = threading.Lock()

    def artifact_path(self, horizon_minutes: int) -> Path:
        return self.models_dir / f"model_h{horizon_minutes}.joblib"

    def available_horizons(self) -> list[int]:
        found = []
        for h in config.FORECAST_HORIZONS:
            if self.artifact_path(h).exists():
                found.append(h)
        return sorted(found)

    def is_ready(self) -> bool:
        return len(self.available_horizons()) > 0 and (self.models_dir / "metrics.json").exists()

    def load(self, horizon_minutes: int) -> dict:
        if horizon_minutes in self._cache:
            return self._cache[horizon_minutes]
        path = self.artifact_path(horizon_minutes)
        if not path.exists():
            raise ModelNotAvailableError(
                f"No trained model for horizon {horizon_minutes}m at {path}. "
                "Run `python -m backend.scripts.train_model` from the project root first."
            )
        try:
            artifact = joblib.load(path)
        except Exception as exc:  # pragma: no cover - corrupt artifact path
            raise ModelNotAvailableError(f"Failed to load model artifact {path}: {exc}") from exc
        for key in ("model", "feature_columns", "model_version"):
            if key not in artifact:
                raise ModelNotAvailableError(f"Model artifact {path} is missing '{key}'")
        with self._lock:
            self._cache[horizon_minutes] = artifact
        return artifact

    def predict_frame(self, horizon_minutes: int, frame: pd.DataFrame) -> float:
        artifact = self.load(horizon_minutes)
        model = artifact["model"]
        expected = artifact["feature_columns"]
        missing = [c for c in expected if c not in frame.columns]
        if missing:
            raise ValueError(f"Feature frame is missing columns: {missing}")
        value = float(model.predict(frame[expected])[0])
        if not np.isfinite(value):
            raise ModelNotAvailableError("Model produced a non-finite prediction")
        return round(value, 1)

    def prediction_interval(self, horizon_minutes: int, value: float) -> dict | None:
        """Prediction interval for a point forecast, or ``None`` if not calibrated.

        Returns ``None`` (never a fabricated band) when the artifact has no
        stored interval, so the UI can simply omit it on older models.
        """
        artifact = self.load(horizon_minutes)
        info = artifact.get("interval") or {}
        half_width = info.get("half_width_mg_dl")
        if half_width is None:
            return None
        half_width = float(half_width)
        return {
            "level": float(info.get("level", 0.9)),
            "lower_mg_dl": round(value - half_width, 1),
            "upper_mg_dl": round(value + half_width, 1),
            "half_width_mg_dl": round(half_width, 1),
            "method": info.get("method"),
            "coverage_pct": info.get("coverage_pct"),
            "n_calibration": info.get("n_calibration"),
            "n_eval": info.get("n_eval"),
            "source": "model_interval",
            "disclaimer": (
                "Uncertainty estimate calibrated on held-out synthetic data; not a "
                "clinically validated confidence interval."
            ),
        }

    def explain_frame(self, horizon_minutes: int, frame: pd.DataFrame, top_n: int = 6) -> list[dict]:
        """Local approximate contribution per feature (ablation vs training median).

        Contribution = f(x) - f(x with feature replaced by its training median).
        Positive means the feature raised the prediction relative to its
        typical value. This is a model-derived sensitivity, not a clinical
        explanation.
        """
        artifact = self.load(horizon_minutes)
        expected = artifact["feature_columns"]
        medians = artifact["feature_medians"]
        base_value = self.predict_frame(horizon_minutes, frame)
        contributions = []
        for col in expected:
            probe = frame.copy()
            probe.loc[:, col] = medians.get(col, float(probe[col].iloc[0]))
            try:
                probe_value = self.predict_frame(horizon_minutes, probe)
            except ModelNotAvailableError:
                continue
            delta = round(base_value - probe_value, 2)
            contributions.append({"feature": col, "contribution": delta})
        contributions.sort(key=lambda c: abs(c["contribution"]), reverse=True)
        top = contributions[:top_n]
        total = sum(abs(c["contribution"]) for c in contributions) or 1.0
        for item in top:
            item["relative_share_pct"] = round(100.0 * abs(item["contribution"]) / total, 1)
        return top

    def load_metrics(self) -> dict:
        path = self.models_dir / "metrics.json"
        if not path.exists():
            raise MetricsNotAvailableError(
                f"Metrics file not found at {path}. "
                "Run `python -m backend.scripts.train_model` from the project root first."
            )
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
