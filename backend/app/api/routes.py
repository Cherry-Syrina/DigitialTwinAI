"""API route definitions for GlucoTwin AI.

Endpoints access services through ``request.app.state`` (an :class:`AppState`
instance defined in ``main.py``). Structural failures surface through global
exception handlers: 404 unknown patient, 503 missing model artifacts, 500
malformed/missing dataset.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pandas import isna

from .. import config
from ..ml.infer import MetricsNotAvailableError, ModelNotAvailableError
from ..schemas import api as schemas
from ..services import importing
from ..services.repository import (
    DataValidationError,
    DuplicatePatientError,
    PatientNotFoundError,
)
from ..services.risk import load_thresholds

router = APIRouter(prefix="/api")

SYNTHETIC_DISCLAIMER = (
    "All data and predictions in this API come from explicitly synthetic data and an "
    "unvalidated research prototype. Not a medical device. Not for clinical use."
)


# ------------------------------------------------------------- access control
# When GLUCOTWIN_AUTH_ENABLED is off these helpers are no-ops, so the local demo
# and the whole existing test-suite keep working unchanged. When it is on they
# enforce a real bearer token plus per-patient ownership (see services/auth.py).


def require_clinician(request: Request) -> dict | None:
    """Return the authenticated clinician, or ``None`` when auth is disabled."""
    if not config.auth_enabled():
        return None
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Authentication required: send an 'Authorization: Bearer <token>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    clinician = request.app.state.auth.resolve(token.strip())
    if clinician is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return clinician


def patient_access(
    patient_id: str,
    request: Request,
    clinician: dict | None = Depends(require_clinician),
) -> None:
    """Reject unauthenticated requests and cross-clinician patient access.

    Shared synthetic patients (``owner_id`` NULL) stay available to any signed-in
    clinician; doctor-created patients are visible only to their owner. Unknown
    ids raise ``PatientNotFoundError`` (404) so nothing leaks before the check.
    """
    if clinician is None:
        return
    owner = request.app.state.repo.patient_owner(patient_id)
    if owner is not None and owner != clinician["clinician_id"]:
        raise HTTPException(
            status_code=403,
            detail="You are not authorised to access this patient's record.",
        )


def _split_pipe(value, default):
    if not value or (isinstance(value, float) and isna(value)):
        return default
    return [x.strip() for x in str(value).split("|") if x.strip()]


def _records(frame) -> list[dict]:
    """DataFrame -> list of dicts with NaN converted to null (never NaN JSON)."""
    if frame is None or len(frame) == 0:
        return []
    return json.loads(frame.to_json(orient="records"))


def profile_response(repo, patient_id: str) -> dict:
    """Assemble the PatientProfileResponse payload for GET/POST/PUT replies."""
    profile = _records(repo.get_profile(patient_id))[0]
    ehr = _records(repo.get_ehr(patient_id))
    summaries = _records(repo.get_summaries(patient_id))
    return {
        "patient_id": profile["patient_id"],
        "name": profile["name"],
        "age": int(profile["age"]),
        "sex": profile["sex"],
        "diabetes_type": profile["diabetes_type"],
        "years_since_diagnosis": int(profile["years_since_diagnosis"]),
        "height_cm": float(profile["height_cm"]),
        "weight_kg": float(profile["weight_kg"]),
        "bmi": float(profile["bmi"]),
        "medical_history": _split_pipe(profile.get("medical_history"), []),
        "current_medications": _split_pipe(profile.get("current_medications"), []),
        "family_history": str(profile.get("family_history") or "n/a"),
        "smoking_status": str(profile.get("smoking_status") or "n/a"),
        "activity_level": str(profile.get("activity_level") or "n/a"),
        "ehr_records": ehr,
        "glucose_summaries": summaries,
        "data_label": str(profile.get("data_label") or config.DATA_LABEL_SYNTHETIC),
        "disclaimer": SYNTHETIC_DISCLAIMER,
    }


def _run_import(
    request: Request,
    patient_id: str,
    raw_rows: list[dict],
    pre_rejected: list[dict],
    entry_method: str,
    dry_run: bool,
    note: str = "",
    filename: str | None = None,
) -> dict:
    """Validate rows, persist (unless dry-run), refresh the twin, shape reply."""
    state = request.app.state
    entries: list[dict] = []
    rejected = list(pre_rejected)
    for raw in raw_rows:
        row_index = int(raw.get("row_index", 0))
        if raw.get("_csv_error"):
            rejected.append(
                {
                    "row_index": row_index,
                    "timestamp": str(raw.get("timestamp") or ""),
                    "status": "rejected",
                    "reason": raw["_csv_error"],
                }
            )
            continue
        entry, rejection = importing.validate_reading(
            raw, row_index, expected_patient_id=patient_id
        )
        if entry is not None:
            entries.append(entry)
        else:
            rejected.append(rejection)

    result = state.repo.add_readings(
        patient_id, entries, entry_method=entry_method, dry_run=dry_run
    )
    rows = sorted(rejected + result["rows"], key=lambda r: r["row_index"])
    accepted_count = result["accepted_count"]
    rejected_count = len(rows) - accepted_count
    duplicate_count = result["duplicate_count"]

    if dry_run:
        message = (
            f"Dry run: {accepted_count} row(s) would be stored, "
            f"{rejected_count} would be rejected ({duplicate_count} duplicate)."
        )
    elif accepted_count:
        message = (
            f"{accepted_count} reading(s) stored, {rejected_count} rejected "
            f"({duplicate_count} duplicate)."
        )
    else:
        message = f"No readings stored: all {rejected_count} row(s) were rejected."
    if note:
        message = f"{message} {note}"

    if result["persisted"] and accepted_count:
        state.twin.notify_data_changed(patient_id)

    return {
        "patient_id": patient_id,
        "rows": rows,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "duplicate_count": duplicate_count,
        "persisted": result["persisted"],
        "dry_run": dry_run,
        "message": message,
        "filename": filename,
    }


@router.get("/health", response_model=schemas.HealthResponse, tags=["system"])
def health(request: Request):
    state = request.app.state
    model_ready = state.forecaster.is_ready()
    patients = None
    boot_errors = []
    try:
        repo = state.repo
        patients = len(repo.patient_ids())
    except Exception as exc:
        boot_errors.append(str(exc))
    if model_ready and not boot_errors:
        return schemas.HealthResponse(
            status="ok",
            service=config.API_TITLE,
            api_version=config.API_VERSION,
            model_loaded=True,
            model_horizons_minutes=state.forecaster.available_horizons(),
            dataset_patients=patients,
            data_source="synthetic dataset (data/synthetic)",
            disclaimer=SYNTHETIC_DISCLAIMER,
        )
    return schemas.HealthResponse(
        status="degraded",
        service=config.API_TITLE,
        api_version=config.API_VERSION,
        model_loaded=model_ready,
        model_horizons_minutes=state.forecaster.available_horizons(),
        dataset_patients=patients,
        data_source="synthetic dataset (data/synthetic)",
        disclaimer=SYNTHETIC_DISCLAIMER,
    )


@router.get("/patients", response_model=list[schemas.PatientSummary], tags=["patients"])
def list_patients(request: Request, clinician: dict | None = Depends(require_clinician)):
    repo = request.app.state.repo
    rows = repo.patient_list()
    if clinician is None:
        return rows
    # Hide patients owned by other clinicians; shared synthetic patients (owner
    # NULL) remain visible.
    return [
        row
        for row in rows
        if repo.patient_owner(row["patient_id"]) in (None, clinician["clinician_id"])
    ]


@router.get(
    "/patients/{patient_id}",
    response_model=schemas.PatientProfileResponse,
    tags=["patients"],
    dependencies=[Depends(patient_access)],
)
def get_patient(patient_id: str, request: Request):
    return profile_response(request.app.state.repo, patient_id)


@router.post(
    "/patients",
    response_model=schemas.PatientProfileResponse,
    status_code=201,
    tags=["patients"],
    responses={409: {"description": "patient_id already exists"}},
)
def create_patient(
    body: schemas.PatientCreate,
    request: Request,
    clinician: dict | None = Depends(require_clinician),
):
    """Register a new demonstration patient (persisted in SQLite)."""
    owner_id = clinician["clinician_id"] if clinician else None
    request.app.state.repo.create_patient(body.model_dump(), owner_id=owner_id)
    return profile_response(request.app.state.repo, body.patient_id)


@router.put(
    "/patients/{patient_id}",
    response_model=schemas.PatientProfileResponse,
    tags=["patients"],
    responses={404: {"description": "Unknown patient"}},
    dependencies=[Depends(patient_access)],
)
def update_patient(patient_id: str, body: schemas.PatientUpdate, request: Request):
    """Edit an existing patient's profile; optional hba1c_pct appends a new summary."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=422, detail="Update body is empty - provide at least one field")
    request.app.state.repo.update_patient(patient_id, fields)
    return profile_response(request.app.state.repo, patient_id)


@router.post(
    "/patients/{patient_id}/ehr",
    status_code=201,
    tags=["doctor"],
    responses={404: {"description": "Unknown patient"}},
    dependencies=[Depends(patient_access)],
)
def add_ehr(patient_id: str, body: schemas.EhrEntryIn, request: Request):
    """Append one doctor-entered EHR-style record (never overwrites history)."""
    raw = body.model_dump()
    canonical, err = importing.parse_timestamp(f"{raw['record_date']} 00:00:00")
    if err:
        raise HTTPException(status_code=422, detail=f"record_date: {err}")
    raw["record_date"] = canonical[:10]
    record = request.app.state.repo.add_ehr(patient_id, raw)
    return record


@router.post(
    "/patients/{patient_id}/readings",
    response_model=schemas.ImportResult,
    tags=["doctor"],
    responses={
        404: {"description": "Unknown patient"},
        422: {"description": "Batch empty / out-of-range values"},
    },
    dependencies=[Depends(patient_access)],
)
def import_readings(
    patient_id: str, body: schemas.ReadingsImportRequest, request: Request
):
    """Manual/batch entry of timestamped readings.

    With ``dry_run=true`` the rows are validated and a preview returned
    without persisting anything. Range validation happens in the request
    schema (422); timestamp/duplicate problems are reported per row so a
    batch can partially succeed.
    """
    raw_rows = []
    pre_rejected = []
    for i, reading in enumerate(body.readings):
        raw_rows.append({"row_index": i, **reading.model_dump()})
    return _run_import(
        request, patient_id, raw_rows, pre_rejected,
        entry_method="manual_entry", dry_run=body.dry_run,
    )


@router.post(
    "/patients/{patient_id}/readings/csv",
    response_model=schemas.ImportResult,
    tags=["doctor"],
    responses={
        404: {"description": "Unknown patient"},
        422: {"description": "Structurally invalid CSV (empty, bad header, too large)"},
    },
    dependencies=[Depends(patient_access)],
)
def import_readings_csv(
    patient_id: str, body: schemas.CsvImportRequest, request: Request
):
    """Upload raw CSV text (server-side parsing and sanitisation).

    Required column: ``timestamp``. Optional: glucose_mg_dl, heart_rate_bpm,
    steps_5min, sleep_minutes, meal_event, minutes_since_meal, patient_id.
    Unknown columns are ignored and reported. Use ``dry_run=true`` for a
    preview before committing.
    """
    request.app.state.repo.get_profile(patient_id)  # 404 before parsing
    try:
        raw_rows, ignored = importing.parse_csv_text(body.csv_text)
    except importing.CsvFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    note = ""
    if ignored:
        note = f"Ignored unknown column(s): {', '.join(ignored)}."
    return _run_import(
        request, patient_id, raw_rows, [],
        entry_method="csv_import", dry_run=body.dry_run, note=note,
    )


@router.post(
    "/patients/{patient_id}/readings/csv/upload",
    response_model=schemas.ImportResult,
    tags=["doctor"],
    responses={
        404: {"description": "Unknown patient"},
        422: {"description": "Missing/empty file or structurally invalid CSV (empty, bad header, too large)"},
    },
    dependencies=[Depends(patient_access)],
)
def import_readings_csv_upload(
    patient_id: str,
    request: Request,
    file: UploadFile = File(..., description="Sensor CSV file (multipart/form-data)"),
    dry_run: bool = Form(default=False, description="Preview only; persist nothing"),
):
    """Upload a CSV file (``multipart/form-data``) for server-side validation.

    Companion to the JSON ``csv_text`` endpoint for browser file uploads. The
    file is read with the configured size cap, decoded, and validated with the
    same per-row rules: required ``timestamp`` column, numeric ranges, missing
    values kept NULL (never imputed) and duplicate timestamps rejected. Use
    ``dry_run=true`` for a preview before committing.
    """
    request.app.state.repo.get_profile(patient_id)  # 404 before consuming the upload
    filename = importing.sanitise_filename(file.filename)
    data = file.file.read(config.MAX_CSV_TEXT_BYTES + 1)
    if len(data) > config.MAX_CSV_TEXT_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"CSV exceeds the {config.MAX_CSV_TEXT_BYTES // (1024 * 1024)} MiB upload limit"
            ),
        )
    try:
        raw_rows, ignored = importing.parse_csv_bytes(data)
    except importing.CsvFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    bits = []
    if filename:
        bits.append(f"File: {filename}.")
    if ignored:
        bits.append(f"Ignored unknown column(s): {', '.join(ignored)}.")
    return _run_import(
        request, patient_id, raw_rows, [],
        entry_method="csv_upload", dry_run=dry_run, note=" ".join(bits), filename=filename or None,
    )


@router.get(
    "/patients/{patient_id}/history",
    response_model=schemas.HistoryResponse,
    tags=["patients"],
    dependencies=[Depends(patient_access)],
)
def patient_history(
    patient_id: str,
    request: Request,
    hours: float | None = Query(default=None, gt=0, le=24 * 7),
    limit: int | None = Query(default=None, ge=1, le=5000),
    include_future: bool = Query(
        default=False,
        description="Include rows beyond the twin's replay cursor (already-generated future data).",
    ),
):
    twin = request.app.state.twin
    readings = twin.history(patient_id, hours=hours, limit=limit, include_future=include_future)
    return {
        "patient_id": patient_id,
        "unit": "mg/dL",
        "readings": readings,
        "sample_interval_minutes": config.SAMPLE_INTERVAL_MINUTES,
        "data_label": "synthetic",
        "disclaimer": SYNTHETIC_DISCLAIMER,
    }


@router.get(
    "/patients/{patient_id}/digital-twin",
    response_model=schemas.TwinResponse,
    tags=["twin"],
    dependencies=[Depends(patient_access)],
)
def digital_twin(patient_id: str, request: Request):
    return request.app.state.twin.state(patient_id)


@router.post(
    "/patients/{patient_id}/predict",
    tags=["twin"],
    responses={
        422: {"description": "Horizon not trained / bad inputs"},
        503: {"description": "Model artifacts unavailable"},
    },
    dependencies=[Depends(patient_access)],
)
def predict(patient_id: str, body: schemas.PredictRequest, request: Request):
    twin = request.app.state.twin
    horizon = body.horizon_minutes or config.DEFAULT_HORIZON
    try:
        return twin.predict(patient_id, horizon_minutes=horizon, explain=body.explain)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DataValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/patients/{patient_id}/what-if",
    tags=["twin"],
    responses={422: {"description": "Horizon not trained / bad overrides"}, 503: {"description": "Model unavailable"}},
    dependencies=[Depends(patient_access)],
)
def what_if(patient_id: str, body: schemas.WhatIfRequest, request: Request):
    twin = request.app.state.twin
    horizon = body.horizon_minutes or config.DEFAULT_HORIZON
    if not body.overrides:
        raise HTTPException(status_code=422, detail="overrides must not be empty for a what-if scenario")
    try:
        return twin.what_if(patient_id, horizon_minutes=horizon, overrides=body.overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DataValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/demo/advance", response_model=schemas.AdvanceResponse, tags=["demo"])
def demo_advance(body: schemas.AdvanceRequest, request: Request):
    """Replay the next synthetic sensor readings for one or all patients."""
    twin = request.app.state.twin
    targets = [body.patient_id] if body.patient_id else twin.engine_patient_ids()
    results = []
    for pid in targets:
        try:
            results.append(twin.advance(pid, steps=body.steps))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "advanced": results,
        "run_ts": {"now": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    }


@router.get("/model/metrics", tags=["model"])
def model_metrics(request: Request):
    """Return the full evaluation metrics (including uncertainty) from metrics.json."""
    return request.app.state.forecaster.load_metrics()


@router.get("/model/thresholds", tags=["model"])
def threshold_config(request: Request):
    return load_thresholds().as_dict()


@router.get(
    "/patients/{patient_id}/report",
    response_model=schemas.ReportResponse,
    tags=["doctor"],
    dependencies=[Depends(patient_access)],
)
def patient_report(patient_id: str, request: Request):
    from ..services.report import render_markdown

    state = request.app.state
    repo = state.repo
    twin = state.twin
    profile = repo.get_profile(patient_id)  # raises -> 404 handler if unknown
    twin_state = twin.state(patient_id, include_trajectory=True)
    recent_readings = twin.history(patient_id, limit=14)
    try:
        metrics = state.forecaster.load_metrics()
    except MetricsNotAvailableError:
        metrics = None  # report states that metrics are unavailable
    data_label = str(_records(profile)[0].get("data_label") or config.DATA_LABEL_SYNTHETIC)
    return {
        "patient_id": patient_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content_markdown": render_markdown(
            repo,
            patient_id,
            twin_state,
            recent_readings=recent_readings,
            thresholds=state.thresholds,
            metrics=metrics,
        ),
        "data_label": data_label,
    }


@router.get(
    "/patients/{patient_id}/report.pdf",
    tags=["doctor"],
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF consult report"},
        404: {"description": "Unknown patient"},
    },
    dependencies=[Depends(patient_access)],
)
def patient_report_pdf(patient_id: str, request: Request):
    """Server-side PDF version of the patient report (download)."""
    from ..services.pdf_report import render_pdf

    state = request.app.state
    repo = state.repo
    repo.get_profile(patient_id)  # raises -> 404 handler if unknown
    twin_state = state.twin.state(patient_id, include_trajectory=True)
    recent_readings = state.twin.history(patient_id, limit=14)
    try:
        metrics = state.forecaster.load_metrics()
    except MetricsNotAvailableError:
        metrics = None
    pdf_bytes = render_pdf(
        repo,
        patient_id,
        twin_state,
        recent_readings=recent_readings,
        thresholds=state.thresholds,
        metrics=metrics,
    )
    safe_id = importing.sanitise_filename(patient_id) or "patient"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="glucotwin-report-{safe_id}.pdf"',
            "X-Report-Kind": "synthetic-demonstration-prototype",
        },
    )