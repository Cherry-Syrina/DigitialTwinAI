"""Server-side PDF patient report (printer-friendly consult summary).

Renders a clean, professional PDF from the *same* underlying data the markdown
report uses (profile, observed readings, digital-twin state, thresholds, model
metrics). Observed measurements and model predictions are always visually
separated and explicitly labelled; nothing is invented and no clinical
recommendation is made.

Joins the constraints of the markdown report: an unvalidated research prototype
on synthetic/demonstration data, not a medical device.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .. import config
from .repository import DataRepository

# Core (Helvetica) fonts are latin-1; normalise common typography so rendering
# never fails on smart quotes / dashes / symbols coming from stored data.
_TRANSLATE = str.maketrans(
    {
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"', "\u2248": "~", "\u00b1": "+/-",
        "\u00b0": " deg", "\u2022": "-", "\u2192": "->", "\u2026": "...",
    }
)

GREEN = (13, 148, 136)
NAVY = (15, 42, 67)
GREY = (100, 116, 139)
LIGHT = (241, 245, 249)
RED_BG = (254, 242, 242)
RED_TX = (153, 27, 27)

PAGE_W = 210.0
MARGIN = 14.0
USABLE = PAGE_W - 2 * MARGIN  # 182 mm


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    try:
        if value != value:  # NaN
            return "n/a"
    except (TypeError, ValueError):
        pass
    return str(value)


def _t(value) -> str:
    return _fmt(value).translate(_TRANSLATE).encode("latin-1", "replace").decode("latin-1")


def _records(frame) -> list[dict]:
    if frame is None or len(frame) == 0:
        return []
    return json.loads(frame.to_json(orient="records"))


class _Report(FPDF):
    """FPDF with a compact running header/footer and a legal-size disclaimer."""

    def __init__(self, subtitle: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.subtitle = subtitle
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(MARGIN, 12, MARGIN)
        # Uncompressed content streams keep the report fully greppable/auditable
        # (and let tests assert on the rendered text). Reports are small.
        self.set_compression(False)

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*GREY)
        self.cell(118, 5, _t("GlucoTwin AI - demonstration prototype (synthetic data)"), align="L")
        self.cell(USABLE - 118, 5, _t(self.subtitle), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*LIGHT)
        y = self.get_y()
        self.line(MARGIN, y, PAGE_W - MARGIN, y)
        self.ln(3)

    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*GREY)
        self.cell(
            0, 5,
            _t("Not a medical device. Not for clinical decision-making. Page %d" % self.page_no()),
            align="C",
        )


def _section(pdf: _Report, title: str) -> None:
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 6, _t(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*GREEN)
    y = pdf.get_y()
    pdf.line(MARGIN, y, PAGE_W - MARGIN, y)
    pdf.ln(1.5)


def _para(pdf: _Report, text: str, size: float = 9.0) -> None:
    pdf.set_font("Helvetica", "", size)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 4.6, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _bullets(pdf: _Report, items: list[str], empty: str) -> None:
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(51, 65, 85)
    if not items:
        _para(pdf, empty)
        return
    for item in items:
        pdf.multi_cell(USABLE, 4.6, _t(f"- {item}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _kv(pdf: _Report, pairs: list[tuple[str, object]]) -> None:
    pdf.set_font("Helvetica", "", 9)
    for label, value in pairs:
        pdf.set_text_color(*GREY)
        pdf.cell(52, 4.8, _t(label))
        pdf.set_text_color(51, 65, 85)
        pdf.cell(0, 4.8, _t(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _table(pdf: _Report, headers: list[str], rows: list[list], widths: list[float]) -> None:
    assert abs(sum(widths) - USABLE) < 1.0, "table widths must fit the page"
    pdf.set_font("Helvetica", "B", 7.6)
    pdf.set_fill_color(*LIGHT)
    pdf.set_text_color(*NAVY)
    pdf.set_draw_color(203, 213, 225)
    for head, width in zip(headers, widths):
        pdf.cell(width, 5.4, _t(head), border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 7.6)
    pdf.set_text_color(51, 65, 85)
    if not rows:
        pdf.cell(USABLE, 5.4, _t("(none recorded)"), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return
    for row in rows:
        for cell, width in zip(row, widths):
            pdf.cell(width, 5.0, _t(cell), border=1)
        pdf.ln()


def render_pdf(
    repo: DataRepository,
    patient_id: str,
    twin_state: dict | None = None,
    recent_readings: list[dict] | None = None,
    thresholds: dict | None = None,
    metrics: dict | None = None,
) -> bytes:
    """Render a printable PDF consult report and return its bytes."""
    if thresholds is not None and hasattr(thresholds, "as_dict"):
        thresholds = thresholds.as_dict()  # accept Thresholds or plain dict

    profile = _records(repo.get_profile(patient_id))[0]
    ehr = repo.get_ehr(patient_id)
    summaries = repo.get_summaries(patient_id)
    sensor = repo.get_sensor(patient_id)
    twin = twin_state or {}
    prediction = twin.get("prediction") or {}
    risk = twin.get("risk") or {}
    trajectory = prediction.get("trajectory") or []
    interval = prediction.get("interval") or {}

    data_label = str(profile.get("data_label") or config.DATA_LABEL_SYNTHETIC)
    is_synthetic = data_label == config.DATA_LABEL_SYNTHETIC
    title_kind = "Synthetic Patient Report" if is_synthetic else "Demonstration Patient Report"
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")

    imported = int(sensor["_is_imported"].sum()) if len(sensor) else 0
    synthetic_n = 0 if not len(sensor) else int(len(sensor) - imported)

    pdf = _Report(subtitle=f"{patient_id} - {_fmt(profile['name'])}")
    pdf.add_page()

    # ---------------------------------------------------------------- heading
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, _t(title_kind), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10.5)
    pdf.set_text_color(51, 65, 85)
    pdf.cell(0, 5.5, _t(f"{_fmt(profile['name'])}  ({patient_id})"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GREY)
    pdf.cell(0, 4.6, _t(f"Generated: {generated}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 4.6, _t(f"Data label: {data_label}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # --------------------------------------------------------- disclaimer box
    pdf.set_fill_color(*RED_BG)
    pdf.set_draw_color(*RED_TX)
    pdf.set_text_color(*RED_TX)
    pdf.set_font("Helvetica", "B", 8.4)
    pdf.multi_cell(
        USABLE, 4.4,
        _t(
            "DATA LABEL: this report is built entirely from synthetic and "
            "doctor-entered demonstration data. It MUST NOT be used for medical "
            "decisions and does not replace professional medical judgment."
        ),
        border=1, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.set_text_color(51, 65, 85)

    # ------------------------------------------------- 1. patient information
    _section(pdf, "1. Patient information")
    _kv(pdf, [
        ("Age", _fmt(profile["age"])),
        ("Sex", _fmt(profile["sex"])),
        ("Diabetes type", _fmt(profile["diabetes_type"])),
        ("Years since diagnosis", _fmt(profile["years_since_diagnosis"])),
        ("Height / Weight", f"{_fmt(profile['height_cm'])} cm / {_fmt(profile['weight_kg'])} kg"),
        ("BMI", _fmt(profile["bmi"])),
        ("Activity level", _fmt(profile.get("activity_level"))),
        ("Smoking status", _fmt(profile.get("smoking_status"))),
        ("Family history", _fmt(profile.get("family_history"))),
    ])

    # ------------------------------------------------------------ 2. provenance
    _section(pdf, "2. Data source and provenance")
    _kv(pdf, [
        ("Profile label", data_label),
        ("Observed readings", f"{synthetic_n} synthetic, {imported} doctor-entered"),
    ])
    _para(
        pdf,
        "Synthetic rows are generated demonstration data. Doctor-entered rows were "
        "added through this application and are clearly labelled. Missing values are "
        "stored as unknown (NULL) and are never imputed.",
    )

    # --------------------------------------------- 3. history and medications
    history = [c.strip() for c in str(profile.get("medical_history") or "").split("|") if c.strip()]
    medications = [c.strip() for c in str(profile.get("current_medications") or "").split("|") if c.strip()]
    _section(pdf, "3. Medical history and current medications")
    _bullets(pdf, history, "No medical history recorded.")
    pdf.ln(1)
    _bullets(pdf, medications, "No medications recorded.")

    # ------------------------------------------------------ 4. glucose summaries
    _section(pdf, "4. Previous glucose summaries")
    _table(
        pdf,
        ["Period", "End date", "Mean", "TIR %", "Above %", "Below %", "HbA1c %", "Label"],
        [
            [
                _fmt(row["summary_period"]), _fmt(row["summary_end_date"]),
                _fmt(row["mean_glucose_mg_dl"]), _fmt(row["time_in_range_pct"]),
                _fmt(row["time_above_range_pct"]), _fmt(row["time_below_range_pct"]),
                _fmt(row["hba1c_pct"]), _fmt(row.get("data_label")),
            ]
            for _, row in summaries.iterrows()
        ],
        [26, 22, 18, 18, 20, 20, 22, 36],
    )

    # --------------------------------------------------------- 5. EHR records
    _section(pdf, "5. EHR-style records")
    _table(
        pdf,
        ["Date", "Type", "HbA1c %", "BP (sys/dia)", "LDL", "Label"],
        [
            [
                _fmt(row["record_date"]), _fmt(row["record_type"]), _fmt(row["hba1c_pct"]),
                f"{_fmt(row['systolic_bp'])}/{_fmt(row['diastolic_bp'])}",
                _fmt(row["ldl_mg_dl"]), _fmt(row.get("data_label")),
            ]
            for _, row in ehr.head(12).iterrows()
        ],
        [26, 46, 20, 26, 20, 44],
    )

    # ------------------------------------------- 6. historical observations
    _section(pdf, "6. Historical observations (observed measurements)")
    _para(pdf, "These are recorded measurements, not predictions.", 8.5)
    _table(
        pdf,
        ["Timestamp", "Glucose (mg/dL)", "HR (bpm)", "Steps", "Meal?", "Source"],
        [
            [
                _fmt(r.get("timestamp")), _fmt(r.get("glucose_mg_dl")),
                _fmt(r.get("heart_rate_bpm")), _fmt(r.get("steps_5min")),
                "yes" if r.get("meal_event") else "no", _fmt(r.get("source")),
            ]
            for r in (recent_readings or [])
        ],
        [44, 30, 24, 20, 16, 48],
    )

    # -------------------------------------------------------- 7. digital twin
    _section(pdf, "7. Digital twin state")
    latest = twin.get("latest_reading") or {}
    _kv(pdf, [
        ("Simulated/observed time", _fmt(twin.get("simulated_time"))),
        ("Observed rows", f"{_fmt(twin.get('observed_rows'))} / {_fmt(twin.get('total_rows'))}"),
        ("Replay buffer remaining", f"{_fmt(twin.get('buffer_rows_remaining'))} readings"),
        ("Latest reading", f"{_fmt(latest.get('timestamp'))}  glucose={_fmt(latest.get('glucose_mg_dl'))} mg/dL"),
        ("Latest source", _fmt(latest.get("source"))),
    ])

    # ----------------------------------------------------- 8. forecast and risk
    _section(pdf, "8. Forecast and risk (model predictions - not measurements)")
    if twin.get("model_error"):
        _para(pdf, f"No forecast available: {twin['model_error']}")
    elif prediction:
        model = prediction.get("model") or {}
        _kv(pdf, [
            ("Model", f"{_fmt(model.get('type'))} v{_fmt(model.get('version'))}"),
            ("Horizon", f"{_fmt(prediction.get('horizon_minutes'))} min"),
            ("Predicted glucose", f"{_fmt(prediction.get('predicted_glucose_mg_dl'))} mg/dL"),
            ("Prediction timestamp", _fmt(prediction.get("prediction_timestamp"))),
        ])
        if interval:
            _kv(pdf, [
                ("Level", f"{int((interval.get('level') or 0.9)*100)}%"),
                ("Interval", f"{_fmt(interval.get('lower_mg_dl'))} - {_fmt(interval.get('upper_mg_dl'))} mg/dL"),
                ("Half-width", f"{_fmt(interval.get('half_width_mg_dl'))} mg/dL"),
                ("Interval method", _fmt(interval.get("method"))),
                ("Empirical coverage", f"{_fmt(interval.get('coverage_pct'))}% (held-out synthetic test, split-calibrated)"),
                ("Calibrated/eval rows", f"{_fmt(interval.get('n_calibration'))} / {_fmt(interval.get('n_eval'))}"),
            ])
            _para(pdf, "Prediction intervals are research estimates from split-conformal residuals and are NOT clinically validated confidence intervals.", 8.0)
        _table(
            pdf,
            ["Horizon (min)", "Prediction timestamp", "Predicted (mg/dL)", "Lower", "Upper", "Kind"],
            [
                [
                    f"+{_fmt(p.get('horizon_minutes'))}",
                    _fmt(p.get("timestamp")),
                    _fmt(p.get("predicted_glucose_mg_dl")),
                    _fmt((p.get("interval") or {}).get("lower_mg_dl")),
                    _fmt((p.get("interval") or {}).get("upper_mg_dl")),
                    "model prediction",
                ]
                for p in trajectory
            ],
            [24, 48, 34, 24, 24, 28],
        )
    else:
        _para(pdf, "No prediction available at export time.")
    pdf.ln(1)
    if risk:
        _kv(pdf, [
            ("Risk level", f"{_fmt(risk.get('level'))} - {_fmt(risk.get('label'))}"),
            ("Predicted range", f"{_fmt(risk.get('predicted_min_mg_dl'))} - {_fmt(risk.get('predicted_max_mg_dl'))} mg/dL"),
        ])
        flags = risk.get("flags") or []
        _bullets(
            pdf,
            [
                f"[{f.get('severity')}] {f.get('message')} "
                f"(threshold {f.get('threshold')} {f.get('unit')}, at {f.get('at_timestamp', 'n/a')})"
                for f in flags
            ],
            "No configured threshold violations predicted.",
        )

    # ---------------------------------------------------- 9. risk thresholds
    if thresholds:
        _section(pdf, "9. Configured risk thresholds (not clinically validated)")
        unit = thresholds.get("unit", "") or ""
        _table(
            pdf,
            ["Threshold", "Value"],
            [
                ["Hypo low", f"{_fmt(thresholds.get('hypo_low_mg_dl'))} {unit}".strip()],
                ["Hypo critical", f"{_fmt(thresholds.get('hypo_critical_mg_dl'))} {unit}".strip()],
                ["Hyper high", f"{_fmt(thresholds.get('hyper_high_mg_dl'))} {unit}".strip()],
                ["Hyper critical", f"{_fmt(thresholds.get('hyper_critical_mg_dl'))} {unit}".strip()],
            ],
            [60, 122],
        )
        if thresholds.get("disclaimer"):
            _para(pdf, _fmt(thresholds["disclaimer"]), 8.0)

    # ------------------------------------------------ 10. model metrics
    _section(pdf, "10. Model and evaluation metrics")
    if metrics:
        _kv(pdf, [
            ("Model version", _fmt(metrics.get("model_version"))),
            ("Framework", _fmt(metrics.get("framework"))),
            ("Task", _fmt(metrics.get("task"))),
            ("Split method", _fmt(metrics.get("split_method"))),
            ("Training data source", _fmt(metrics.get("training_data_source"))),
        ])
        if metrics.get("uncertainty_note"):
            _para(pdf, _fmt(metrics.get("uncertainty_note")), 7.5)
        rows = []
        for key in sorted((metrics.get("horizons") or {}).keys(), key=lambda k: int(k)):
            h = metrics["horizons"][key]
            m = h.get("metrics") or {}
            baseline = ((h.get("baselines") or {}).get("persistence") or {})
            uncertainty = h.get("uncertainty") or {}
            cov = uncertainty.get("coverage_pct")
            cov_cell = f"{cov}%" if cov is not None else "n/a"
            width = uncertainty.get("half_width_mg_dl")
            width_cell = f"+/-{width} mg/dL" if width is not None else "n/a"
            rows.append([
                f"{key} min", _fmt(h.get("selected_model")), _fmt(m.get("mae")),
                _fmt(m.get("rmse")), _fmt(baseline.get("mae")), _fmt(h.get("rows_test")),
                width_cell, cov_cell,
            ])
        _table(
            pdf,
            ["Horizon", "Selected model", "MAE", "RMSE", "Persistence MAE", "Test rows", "Interval (90%)", "90% coverage (held-out)"],
            rows,
            [18, 34, 16, 16, 24, 20, 26, 28],
        )
        _para(
            pdf,
            _fmt(metrics.get("disclaimer"))
            or "Metrics are held-out test results on synthetic data only.",
            8.0,
        )
    else:
        _para(pdf, "Model evaluation metrics unavailable (models not trained on this machine).")
        _para(pdf, "Run `python -m backend.scripts.train_model` from the project root to train.", 8.0)

    # ------------------------------------------------- 11. limitations
    _section(pdf, "11. Limitations and statement")
    _para(
        pdf,
        "This prototype dashboard does not replace professional medical judgment. "
        "Predictions are produced by an unvalidated machine-learning model from "
        "synthetic demonstration data and have no established clinical accuracy. "
        "Authentication, authorization, security hardening and clinical validation "
        "are required before any real clinical deployment. No treatment advice is "
        "provided and none should be inferred.",
    )

    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()
