"""Synthetic patient report generator (for the Doctor View / Reports export).

The report only ever includes information that actually exists: observed
readings, stored summaries/EHR rows, and model outputs. Missing pieces are
shown as "n/a" or an explicit "unavailable" note - nothing is invented.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .. import config
from .repository import DataRepository, PatientNotFoundError


def _records(frame) -> list[dict]:
    if frame is None or len(frame) == 0:
        return []
    return json.loads(frame.to_json(orient="records"))


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    try:
        if value != value:  # NaN
            return "n/a"
    except (TypeError, ValueError):
        pass
    return str(value)


def render_markdown(
    repo: DataRepository,
    patient_id: str,
    twin_state: dict | None = None,
    recent_readings: list[dict] | None = None,
    thresholds: dict | None = None,
    metrics: dict | None = None,
) -> str:
    """Render a markdown patient report.

    ``twin_state``: digital twin snapshot (prediction/risk may be null).
    ``recent_readings``: latest observed readings (observed vs entered labelled).
    ``thresholds``: configured risk threshold dictionary.
    ``metrics``: trained-model evaluation metadata (None -> stated as unavailable).
    """
    if thresholds is not None and hasattr(thresholds, "as_dict"):
        thresholds = thresholds.as_dict()  # accept Thresholds or plain dict
    profile_df = repo.get_profile(patient_id)
    profile = _records(profile_df)[0]
    ehr = repo.get_ehr(patient_id)
    summaries = repo.get_summaries(patient_id)
    twin = twin_state or {}
    prediction = twin.get("prediction") or {}
    risk = twin.get("risk") or {}
    data_label = str(profile.get("data_label") or config.DATA_LABEL_SYNTHETIC)
    is_synthetic = data_label == config.DATA_LABEL_SYNTHETIC
    title_kind = "Synthetic Patient Report" if is_synthetic else "Demonstration Patient Report"

    lines: list[str] = []
    lines.append(f"# {title_kind} - {profile['name']} ({patient_id})")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("> **DATA LABEL:** This report is built entirely from **synthetic** and")
    lines.append("> **doctor-entered demonstration** data. It MUST NOT be used for medical")
    lines.append("> decisions and does not replace professional medical judgment.")
    lines.append("")

    # ---------------------------------------------------------------- provenance
    lines.append("## 1. Data source and provenance")
    lines.append("")
    sensor = repo.get_sensor(patient_id)
    if len(sensor):
        imported = int(sensor["_is_imported"].sum())
        synthetic_n = int(len(sensor) - imported)
    else:
        imported, synthetic_n = 0, 0
    lines.append(f"- Profile label: **{data_label}**")
    lines.append(f"- Observed sensor readings: {synthetic_n} from the synthetic dataset, {imported} doctor-entered")
    lines.append("- Synthetic rows are generated demonstration data; entered rows were added through this app")
    lines.append("")
    lines.append("## 2. Demographics")
    lines.append("")
    lines.append(f"- Age: {_fmt(profile['age'])}")
    lines.append(f"- Sex: {_fmt(profile['sex'])}")
    lines.append(f"- Diabetes type: {_fmt(profile['diabetes_type'])}")
    lines.append(f"- Years since diagnosis: {_fmt(profile['years_since_diagnosis'])}")
    lines.append(f"- Height / Weight: {_fmt(profile['height_cm'])} cm / {_fmt(profile['weight_kg'])} kg")
    lines.append(f"- BMI: {_fmt(profile['bmi'])}")
    lines.append(f"- Activity level: {_fmt(profile.get('activity_level'))}")
    lines.append(f"- Smoking status: {_fmt(profile.get('smoking_status'))}")
    lines.append("")
    lines.append("## 3. Relevant medical history (EHR)")
    lines.append("")
    history = [c.strip() for c in str(profile.get("medical_history") or "").split("|") if c.strip()]
    if history:
        for condition in history:
            lines.append(f"- {condition}")
    else:
        lines.append("- No medical history recorded.")
    lines.append("")
    lines.append("## 4. Current medications")
    lines.append("")
    medications = [c.strip() for c in str(profile.get("current_medications") or "").split("|") if c.strip()]
    if medications:
        for med in medications:
            lines.append(f"- {med}")
    else:
        lines.append("- No medications recorded.")
    lines.append("")
    lines.append("## 5. Previous glucose summaries")
    lines.append("")
    lines.append("| Period | End date | Mean (mg/dL) | TIR (%) | Above (%) | Below (%) | HbA1c (%) | Label |")
    lines.append("|--------|----------|--------------|---------|-----------|-----------|-----------|-------|")
    for _, row in summaries.iterrows():
        lines.append(
            f"| {_fmt(row['summary_period'])} | {_fmt(row['summary_end_date'])} | "
            f"{_fmt(row['mean_glucose_mg_dl'])} | {_fmt(row['time_in_range_pct'])} | "
            f"{_fmt(row['time_above_range_pct'])} | {_fmt(row['time_below_range_pct'])} | "
            f"{_fmt(row['hba1c_pct'])} | {_fmt(row.get('data_label'))} |"
        )
    lines.append("")
    lines.append("## 6. Recent EHR-like records")
    lines.append("")
    if len(ehr) == 0:
        lines.append("- No EHR records recorded.")
    else:
        lines.append("| Date | Type | HbA1c (%) | BP (sys/dia) | LDL (mg/dL) | Label |")
        lines.append("|------|------|-----------|--------------|-------------|-------|")
        for _, row in ehr.head(12).iterrows():
            lines.append(
                f"| {_fmt(row['record_date'])} | {_fmt(row['record_type'])} | {_fmt(row['hba1c_pct'])} | "
                f"{_fmt(row['systolic_bp'])}/{_fmt(row['diastolic_bp'])} | {_fmt(row['ldl_mg_dl'])} | "
                f"{_fmt(row.get('data_label'))} |"
            )
    lines.append("")
    lines.append("## 7. Recent observed sensor readings")
    lines.append("")
    if not recent_readings:
        lines.append("- No observed readings yet. Add readings via *Medical Data* before a")
        lines.append("  chart or forecast can be produced.")
    else:
        lines.append("| Timestamp | Glucose (mg/dL) | HR (bpm) | Steps | Meal? | Source |")
        lines.append("|-----------|-----------------|----------|-------|-------|--------|")
        for r in recent_readings:
            lines.append(
                f"| {_fmt(r.get('timestamp'))} | {_fmt(r.get('glucose_mg_dl'))} | "
                f"{_fmt(r.get('heart_rate_bpm'))} | {_fmt(r.get('steps_5min'))} | "
                f"{'yes' if r.get('meal_event') else 'no'} | {_fmt(r.get('source'))} |"
            )
    lines.append("")
    lines.append("## 8. Digital twin state")
    lines.append("")
    lines.append(f"- Simulated/observed time: {_fmt(twin.get('simulated_time'))}")
    lines.append(f"- Observed rows: {_fmt(twin.get('observed_rows'))} / {_fmt(twin.get('total_rows'))}")
    lines.append(f"- Replay buffer remaining: {_fmt(twin.get('buffer_rows_remaining'))} readings")
    latest = twin.get("latest_reading") or {}
    lines.append(
        f"- Latest reading: {_fmt(latest.get('timestamp'))}, "
        f"glucose={_fmt(latest.get('glucose_mg_dl'))} mg/dL "
        f"(source: {_fmt(latest.get('source'))})"
    )
    lines.append("")
    lines.append("## 9. Forecast and risk (research prototype)")
    lines.append("")
    if twin.get("model_error"):
        lines.append(f"- **No forecast available:** {twin['model_error']}")
    elif prediction:
        lines.append(
            f"- Model: {prediction.get('model', {}).get('type')} "
            f"v{prediction.get('model', {}).get('version')}"
        )
        lines.append(f"- Horizon: {prediction.get('horizon_minutes')} min")
        lines.append(f"- Predicted glucose: {prediction.get('predicted_glucose_mg_dl')} mg/dL")
        lines.append(f"- Prediction timestamp: {prediction.get('prediction_timestamp')}")
        interval = prediction.get("interval") or {}
        if interval:
            lower = interval.get("lower_mg_dl")
            upper = interval.get("upper_mg_dl")
            if lower is not None and upper is not None:
                lines.append(
                    f"- Uncertainty (80% interval): {lower} - {upper} mg/dL "
                    f"({interval.get('method')})"
                )
                cov = interval.get("coverage_pct")
                if cov is not None:
                    lines.append(
                        f"  - Empirical coverage (held-out synthetic test): {cov}%"
                    )
            note = interval.get("disclaimer")
            if note:
                lines.append(f"  - Note: {note}")
        lines.append("- Trajectory (MODEL PREDICTIONS, not measurements):")
        for point in prediction.get("trajectory", []):
            lines.append(
                f"  - +{point['horizon_minutes']}m -> {point['predicted_glucose_mg_dl']} mg/dL "
                f"at {point['timestamp']}"
            )
    else:
        lines.append("- No prediction available at export time.")
    lines.append("")
    if risk:
        lines.append(f"- Risk level: **{risk.get('level')}** - {risk.get('label')}")
        for flag in risk.get("flags", []):
            lines.append(
                f"  - [{flag['severity']}] {flag.get('message')} "
                f"(threshold {flag.get('threshold')} {flag.get('unit')}, at {flag.get('at_timestamp', 'n/a')})"
            )
        if not risk.get("flags"):
            lines.append("  - No configured threshold violations predicted.")
    lines.append("")
    if thresholds:
        lines.append("### Configured risk thresholds (configurable, not clinically validated)")
        lines.append("")
        lines.append("| Threshold | Value |")
        lines.append("|-----------|-------|")
        lines.append(f"| Hypo low | {_fmt(thresholds.get('hypo_low_mg_dl'))} {thresholds.get('unit', '')} |")
        lines.append(f"| Hypo critical | {_fmt(thresholds.get('hypo_critical_mg_dl'))} {thresholds.get('unit', '')} |")
        lines.append(f"| Hyper high | {_fmt(thresholds.get('hyper_high_mg_dl'))} {thresholds.get('unit', '')} |")
        lines.append(f"| Hyper critical | {_fmt(thresholds.get('hyper_critical_mg_dl'))} {thresholds.get('unit', '')} |")
        lines.append("")
        if thresholds.get("disclaimer"):
            lines.append(f"- {thresholds['disclaimer']}")
            lines.append("")
    lines.append("## 10. Model and evaluation metrics")
    lines.append("")
    if metrics:
        lines.append(f"- Model version: {_fmt(metrics.get('model_version'))}")
        lines.append(f"- Framework: {_fmt(metrics.get('framework'))}")
        lines.append(f"- Task: {_fmt(metrics.get('task'))} ({_fmt(metrics.get('split_method'))})")
        lines.append(f"- Training data source: {_fmt(metrics.get('training_data_source'))}")
        lines.append("")
        lines.append("| Horizon | Selected model | MAE | RMSE | Persistence MAE | Test rows | Interval (90%) | 90% coverage (held-out) |")
        lines.append("|---------|----------------|-----|------|-----------------|-----------|----------------|-------------------------|")
        for key in sorted((metrics.get("horizons") or {}).keys(), key=lambda k: int(k)):
            h = metrics["horizons"][key]
            m = h.get("metrics") or {}
            baseline = ((h.get("baselines") or {}).get("persistence") or {})
            unc = h.get("uncertainty") or {}
            cov = unc.get("coverage_pct")
            cov_cell = f"{cov}%" if cov is not None else "n/a"
            width = unc.get("half_width_mg_dl")
            width_cell = f"+/-{width}" if width is not None else "n/a"
            lines.append(
                f"| {key} min | {_fmt(h.get('selected_model'))} | {_fmt(m.get('mae'))} | "
                f"{_fmt(m.get('rmse'))} | {_fmt(baseline.get('mae'))} | {_fmt(h.get('rows_test'))} | "
                f"{width_cell} | {cov_cell} |"
            )
        lines.append("")
        lines.append(
            f"- {metrics.get('disclaimer') or 'Metrics are held-out test results on synthetic data only.'}"
        )
        if metrics.get("uncertainty_note"):
            lines.append(f"- {metrics['uncertainty_note']}")
    else:
        lines.append("- Model evaluation metrics unavailable (models not trained on this machine).")
        lines.append("- Run `python -m backend.scripts.train_model` from the project root to train.")
    lines.append("")
    lines.append("## 11. Limitations and statement")
    lines.append("")
    lines.append(
        "This prototype dashboard does not replace professional medical judgment. "
        "Predictions are produced by an unvalidated machine-learning model from "
        "synthetic demonstration data and have no established clinical accuracy. "
        "Authentication, authorization, security hardening and clinical validation "
        "are required before any real clinical deployment."
    )
    return "\n".join(lines)
