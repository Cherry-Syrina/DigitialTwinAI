"""Feature construction for glucose forecasting.

Every feature at time ``t`` is derived only from data available at or before
``t`` (observations and static patient attributes). Labels are values at
``t + horizon``. Patient identifiers are never used as predictive features.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import config

STATIC_FEATURES = [
    "age",
    "bmi",
    "years_since_diagnosis",
    "hba1c_pct",
]

CONTEXT_FEATURES = [
    "steps_last_60m",
    "heart_rate_last_60m",
    "sleep_hours_24h",
    "minutes_since_meal",
    "meal_event_recent",
]

TEMPORAL_FEATURES = ["hour_sin", "hour_cos", "day_sin", "day_cos"]

GLUCOSE_HISTORY_FEATURES = (
    [f"glucose_lag_{i}" for i in range(1, config.LOOKBACK_ROWS + 1)]
    + [
        "glucose_roll_mean_30m",
        "glucose_roll_std_30m",
        "glucose_roll_mean_60m",
        "glucose_slope_60m",
        "glucose_delta_15m",
    ]
)

FEATURE_COLUMNS = (
    GLUCOSE_HISTORY_FEATURES + CONTEXT_FEATURES + TEMPORAL_FEATURES + STATIC_FEATURES
)


def label_column(horizon_minutes: int) -> str:
    return f"glucose_t_plus_{horizon_minutes}m"


@dataclass
class DatasetConfig:
    lookback_rows: int = config.LOOKBACK_ROWS
    horizons: tuple[int, ...] = config.FORECAST_HORIZONS
    sample_interval_minutes: int = config.SAMPLE_INTERVAL_MINUTES


@dataclass
class BuiltDataset:
    features: pd.DataFrame
    label_column: str
    horizon_minutes: int
    feature_columns: list[str] = field(default_factory=lambda: list(FEATURE_COLUMNS))
    dropped_rows: int = 0


def add_static_features(frame: pd.DataFrame, profiles: pd.DataFrame, summaries: pd.DataFrame) -> pd.DataFrame:
    """Add profile attributes and the latest summary available at each timestamp."""
    profile_cols = ["patient_id", "age", "bmi", "years_since_diagnosis"]
    merged = frame.merge(profiles[profile_cols], on="patient_id", how="left")

    summary_rows = summaries[["patient_id", "summary_end_date", "hba1c_pct"]].copy()
    # Summary dates are date-only and describe a period through that whole day.
    # Make the value available from the following midnight to avoid leaking it
    # into any sensor observation covered by the summary itself.
    summary_rows["available_from"] = (
        pd.to_datetime(summary_rows["summary_end_date"], errors="coerce").dt.normalize()
        + pd.Timedelta(days=1)
    )
    summary_rows = summary_rows.dropna(subset=["available_from"])[
        ["patient_id", "available_from", "hba1c_pct"]
    ]
    observations = merged.copy()
    observations["timestamp"] = pd.to_datetime(observations["timestamp"], errors="coerce")
    observations = observations.sort_values(["timestamp", "patient_id"], kind="mergesort")
    summary_rows = summary_rows.sort_values(["available_from", "patient_id"], kind="mergesort")
    return pd.merge_asof(
        observations,
        summary_rows,
        left_on="timestamp",
        right_on="available_from",
        by="patient_id",
        direction="backward",
    )


def add_temporal_features(frame: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(frame["timestamp"], utc=False)
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek.astype(float)
    frame = frame.copy()
    frame["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    frame["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    frame["day_sin"] = np.sin(2 * np.pi * dow / 7.0)
    frame["day_cos"] = np.cos(2 * np.pi * dow / 7.0)
    return frame


def _slope(values: np.ndarray) -> float:
    """Least-squares slope (mg/dL per sample) over a window; NaN-safe."""
    v = np.asarray(values, dtype=float)
    mask = ~np.isnan(v)
    if mask.sum() < 3:
        return float("nan")
    x = np.arange(len(v), dtype=float)[mask]
    y = v[mask]
    denom = ((x - x.mean()) ** 2).sum()
    if denom == 0:
        return 0.0
    return float(((x - x.mean()) * (y - y.mean())).sum() / denom)


def build_supervised_frame(
    sensor: pd.DataFrame,
    profiles: pd.DataFrame,
    summaries: pd.DataFrame,
    horizon_minutes: int,
    cfg: DatasetConfig | None = None,
) -> BuiltDataset:
    """Build a leakage-free supervised learning frame for one forecast horizon.

    For every patient row ``t`` the features use only observations up to ``t``
    and the label is glucose at ``t + horizon``. Rows whose observation
    window or label is missing are dropped (complete-case), interior gaps of
    up to two samples are forward-filled within the patient first.
    """
    cfg = cfg or DatasetConfig()
    if horizon_minutes % cfg.sample_interval_minutes != 0:
        raise ValueError("horizon_minutes must be a multiple of the sample interval")
    horizon_rows = horizon_minutes // cfg.sample_interval_minutes
    lb = cfg.lookback_rows

    df = sensor.sort_values(["patient_id", "timestamp"]).reset_index(drop=True)
    df = df.drop_duplicates(subset=["patient_id", "timestamp"], keep="first")
    df = add_static_features(df, profiles, summaries)
    df = add_temporal_features(df)
    df["glucose_mg_dl"] = df.groupby("patient_id")["glucose_mg_dl"].ffill()
    df["heart_rate_bpm"] = df.groupby("patient_id")["heart_rate_bpm"].ffill()

    label = label_column(horizon_minutes)
    out_frames: list[pd.DataFrame] = []
    dropped = 0

    for _, g in df.groupby("patient_id", sort=False):
        glucose = g["glucose_mg_dl"].to_numpy(dtype=float)
        n = len(g)
        start = lb - 1            # first row with a complete history window
        end = n - horizon_rows    # first row without a label (exclusive)
        if end <= start:
            dropped += n
            continue

        win = np.lib.stride_tricks.sliding_window_view(glucose, lb)  # win[k] ends at k+lb-1
        win_start = start - lb + 1  # == 0
        win_sub = win[win_start : end - lb + 1]  # one window per row in [start, end)
        window_ok = ~np.isnan(win_sub).any(axis=1)

        labels = np.full(end - start, np.nan)
        labels[:] = glucose[start + horizon_rows : end + horizon_rows]

        sub = g.iloc[start:end].copy()
        valid = window_ok & ~np.isnan(labels)
        valid &= ~np.isnan(sub["minutes_since_meal"].to_numpy(dtype=float))

        sub["glucose_lag_1"] = win_sub[:, -1]
        for i in range(2, lb + 1):
            sub[f"glucose_lag_{i}"] = win_sub[:, -i]

        gs = pd.Series(glucose)
        sub["glucose_roll_mean_30m"] = gs.rolling(7, min_periods=7).mean().to_numpy()[start:end]
        sub["glucose_roll_std_30m"] = gs.rolling(7, min_periods=7).std().to_numpy()[start:end]
        sub["glucose_roll_mean_60m"] = gs.rolling(13, min_periods=13).mean().to_numpy()[start:end]

        slopes = np.full(n, np.nan)
        for i in range(lb - 1, n):
            slopes[i] = _slope(glucose[i - lb + 1 : i + 1])
        sub["glucose_slope_60m"] = slopes[start:end]

        delta = np.full(n, np.nan)
        delta[3:] = glucose[3:] - glucose[:-3]
        sub["glucose_delta_15m"] = delta[start:end]

        sub["steps_last_60m"] = pd.Series(
            g["steps_5min"].fillna(0).to_numpy(dtype=float)
        ).rolling(12, min_periods=1).sum().to_numpy()[start:end]
        sub["heart_rate_last_60m"] = pd.Series(
            g["heart_rate_bpm"].to_numpy(dtype=float)
        ).rolling(12, min_periods=1).mean().to_numpy()[start:end]
        sub["sleep_hours_24h"] = (
            pd.Series(g["sleep_minutes"].fillna(0).to_numpy(dtype=float))
            .rolling(288, min_periods=1)
            .sum()
            .to_numpy()[start:end]
            / 60.0
        )
        sub["minutes_since_meal"] = sub["minutes_since_meal"].astype(float)
        sub["meal_event_recent"] = (
            pd.Series(g["meal_event"].fillna(0).to_numpy(dtype=float))
            .rolling(6, min_periods=1)
            .max()
            .to_numpy()[start:end]
        )

        sub[label] = labels
        sub = sub.loc[valid].copy()
        if len(sub):
            out_frames.append(sub)

    if not out_frames:
        raise ValueError("No usable rows could be built from the sensor data")

    combined = pd.concat(out_frames, ignore_index=True)
    missing = [c for c in FEATURE_COLUMNS if c not in combined.columns]
    if missing:
        raise ValueError(f"Feature construction failed, missing columns: {missing}")

    keep = FEATURE_COLUMNS + [label, "patient_id", "timestamp"]
    features = combined[keep].dropna(subset=FEATURE_COLUMNS + [label]).reset_index(drop=True)
    dropped += len(combined) - len(features)
    return BuiltDataset(
        features=features,
        label_column=label,
        horizon_minutes=horizon_minutes,
        feature_columns=list(FEATURE_COLUMNS),
        dropped_rows=int(dropped),
    )


def build_inference_frame(
    window_rows: pd.DataFrame,
    static_row: dict,
    feature_columns: list[str],
    sleep_rows: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a single-row feature frame from a recent observation window.

    ``window_rows`` must contain the most recent readings ordered oldest to
    newest with sensor columns (glucose_mg_dl, steps_5min, heart_rate_bpm,
    sleep_minutes, meal_event, minutes_since_meal, timestamp). ``sleep_rows``
    optionally provides up to 24h of history for the sleep feature (matching
    the training-time rolling window). Only values at or before the last
    window row are used - no future information.
    """
    rows = window_rows.sort_values("timestamp").copy()
    if len(rows) == 0:
        raise ValueError("Cannot build inference features from an empty window")

    ts = pd.to_datetime(rows["timestamp"])
    glucose = rows["glucose_mg_dl"].astype(float).to_numpy()
    if np.isnan(glucose).any():
        raise ValueError("Observation window contains missing glucose values")

    lookback = len(glucose)
    g = pd.Series(glucose)
    out: dict[str, float] = {}

    out["glucose_lag_1"] = float(glucose[-1])
    for i in range(2, lookback + 1):
        out[f"glucose_lag_{i}"] = float(glucose[-i])

    out["glucose_roll_mean_30m"] = float(g.rolling(7, min_periods=1).mean().iloc[-1])
    std_val = g.rolling(7, min_periods=2).std().iloc[-1]
    out["glucose_roll_std_30m"] = float(0.0 if np.isnan(std_val) else std_val)
    out["glucose_roll_mean_60m"] = float(g.rolling(13, min_periods=1).mean().iloc[-1])
    out["glucose_slope_60m"] = float(_slope(glucose))
    out["glucose_delta_15m"] = float(glucose[-1] - glucose[-4]) if lookback >= 4 else 0.0

    steps = rows["steps_5min"].fillna(0).astype(float).to_numpy()
    hr = rows["heart_rate_bpm"].ffill().astype(float).to_numpy()
    meal = rows["meal_event"].fillna(0).astype(float).to_numpy()

    sleep_source = sleep_rows if sleep_rows is not None else rows
    sleep = sleep_source["sleep_minutes"].fillna(0).astype(float).to_numpy()

    out["steps_last_60m"] = float(
        steps.sum() * (60.0 / max(len(rows) * config.SAMPLE_INTERVAL_MINUTES, 1))
    )
    hr_valid = hr[~np.isnan(hr)]
    out["heart_rate_last_60m"] = float(hr_valid.mean()) if len(hr_valid) else float("nan")
    out["sleep_hours_24h"] = float(sleep.sum() / 60.0)
    out["minutes_since_meal"] = float(rows["minutes_since_meal"].iloc[-1])
    out["meal_event_recent"] = float(meal.max())

    last_ts = ts.iloc[-1]
    hour = last_ts.hour + last_ts.minute / 60.0
    dow = float(last_ts.dayofweek)
    out["hour_sin"] = float(np.sin(2 * np.pi * hour / 24.0))
    out["hour_cos"] = float(np.cos(2 * np.pi * hour / 24.0))
    out["day_sin"] = float(np.sin(2 * np.pi * dow / 7.0))
    out["day_cos"] = float(np.cos(2 * np.pi * dow / 7.0))

    for key in STATIC_FEATURES:
        if key not in static_row:
            raise ValueError(f"Static feature missing from patient profile: {key}")
        out[key] = float(static_row[key])

    frame = pd.DataFrame([{c: out.get(c, float("nan")) for c in feature_columns}])
    if frame.isna().any().any():
        bad = frame.columns[frame.isna().any()].tolist()
        raise ValueError(f"Feature vector contains missing values: {bad}")
    return frame
