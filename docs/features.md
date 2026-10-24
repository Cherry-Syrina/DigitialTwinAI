# Feature engineering — GlucoTwin AI

Features are built identically for training and inference to avoid train/serve skew (the same
`build_inference_frame`/`build_features` code path is used, with a `sleep_rows` parameter to keep
the feature window inside either the test split or the twin's replay cursor).

## Observation window

- `SAMPLE_INTERVAL_MINUTES = 5`, `LOOKBACK_ROWS = 12` → a 60-minute lookback window feeds each
  prediction.

## Feature list (30)

### Glucose dynamics (from the CGM series)
| Feature | Meaning |
|---|---|
| `glucose_lag_1 … glucose_lag_12` | last 12 values (most recent first), 5-min spaced |
| `glucose_roll_mean_30m` | mean of last 6 readings |
| `glucose_roll_std_30m` | std of last 6 readings |
| `glucose_roll_mean_60m` | mean of last 12 readings |
| `glucose_slope_60m` | least-squares slope over the window |
| `glucose_delta_15m` | value now minus value 15 minutes ago |

### Contextual / wearable
| Feature | Meaning |
|---|---|
| `steps_last_60m` | summed step count in the window |
| `heart_rate_last_60m` | last heart-rate value |
| `sleep_hours_24h` | hours of sleep in the preceding 24 h (longitudinal) |
| `minutes_since_meal` | time since the last registered meal event |
| `meal_event_recent` | binary — meal event inside the window |

### Time cycles (cyclical, not raw)
| Feature | Meaning |
|---|---|
| `hour_sin`, `hour_cos` | time-of-day encoded onto the unit circle |
| `day_sin`, `day_cos` | day-of-week encoded cyclically |

### Static profile
| Feature | Meaning |
|---|---|
| `age`, `bmi`, `years_since_diagnosis`, `hba1c_pct` | per-patient constants |

## Exclusions

- `patient_id` and `timestamp` are **not** predictive features (namespace / key columns only).
- No feature uses any row at or after the prediction timestamp → **no leakage**.
- Missing glucose/heart-rate values are carried as NaN; the `Forecaster` and the training script
  drop rows with insufficient history rather than forward-filling across gaps.

## Verification

`tests/test_features.py` asserts:
- exactly the expected feature set is produced and in canonical order,
- features require ≥ `LOOKBACK_ROWS` prior rows; insufficient history yields an empty frame,
- no future row leaks into a feature window (`sleep_rows` respected in tests),
- NaN appears only from genuinely missing raw values, never from lookahead.