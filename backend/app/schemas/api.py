"""Pydantic schemas for the GlucoTwin AI API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import config


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    api_version: str
    model_loaded: bool
    model_horizons_minutes: list[int]
    dataset_patients: Optional[int] = None
    data_source: str
    disclaimer: str


class PatientSummary(BaseModel):
    patient_id: str
    name: str
    age: int
    sex: str
    diabetes_type: str
    latest_glucose_mg_dl: Optional[float] = None
    latest_reading_time: Optional[str] = None
    sensor_rows: int
    data_label: str


class ReadingOut(BaseModel):
    timestamp: str
    glucose_mg_dl: Optional[float] = None
    heart_rate_bpm: Optional[float] = None
    steps_5min: Optional[int] = None
    sleep_minutes: Optional[float] = None
    meal_event: int = 0
    minutes_since_meal: Optional[float] = None
    source: str


class HistoryResponse(BaseModel):
    patient_id: str
    unit: str
    readings: list[ReadingOut]
    sample_interval_minutes: int
    data_label: str
    disclaimer: str


class PatientProfileResponse(BaseModel):
    patient_id: str
    name: str
    age: int
    sex: str
    diabetes_type: str
    years_since_diagnosis: int
    height_cm: float
    weight_kg: float
    bmi: float
    medical_history: list[str]
    current_medications: list[str]
    family_history: str
    smoking_status: str
    activity_level: str
    ehr_records: list[dict[str, Any]]
    glucose_summaries: list[dict[str, Any]]
    data_label: str
    disclaimer: str


class PredictRequest(BaseModel):
    horizon_minutes: Optional[int] = Field(
        default=None, ge=5, le=240, description="Forecast horizon in minutes"
    )
    explain: bool = Field(default=False, description="Include local feature contributions")


class WhatIfRequest(BaseModel):
    horizon_minutes: Optional[int] = Field(default=None, ge=5, le=240)
    overrides: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Hypothetical inputs: glucose_offset_mg_dl, steps_last_60m, "
            "heart_rate_last_60m, sleep_hours_24h, minutes_since_meal, "
            "meal_event_recent"
        ),
    )


class AdvanceRequest(BaseModel):
    patient_id: Optional[str] = Field(
        default=None, description="Patient to advance; if omitted, all patients advance"
    )
    steps: int = Field(default=12, ge=1, le=288)


class AdvanceResponse(BaseModel):
    advanced: list[dict[str, Any]]
    run_ts: dict[str, Any]


class TwinResponse(BaseModel):
    patient_id: str
    data_label: str
    last_updated: str
    simulated_time: Optional[str] = None
    observed_rows: int
    total_rows: int
    buffer_rows_remaining: int
    latest_reading: Optional[dict[str, Any]] = None
    sensor_feed: dict[str, Any]
    window_used: dict[str, Any]
    prediction: Optional[dict[str, Any]] = None
    risk: Optional[dict[str, Any]] = None
    model_error: Optional[str] = None
    prediction_history: list[dict[str, Any]]


class ModelMetricsResponse(BaseModel):
    model_version: str
    task: str
    framework: str
    split_method: str
    features: list[str]
    training_data_source: str
    horizons: dict[str, Any]
    disclaimer: str


class ReportResponse(BaseModel):
    patient_id: str
    generated_at: str
    content_markdown: str
    data_label: str


# ---------------------------------------------------------------- doctor writes


def _clean_entries(value: Optional[list[str]], field_name: str) -> list[str]:
    if value is None:
        return []
    cleaned = []
    for item in value:
        text = str(item).strip()
        if not text:
            continue
        if len(text) > 120:
            raise ValueError(f"each {field_name} entry must be at most 120 characters")
        cleaned.append(text)
    if len(cleaned) > 25:
        raise ValueError(f"at most 25 {field_name} entries are allowed")
    return cleaned


class PatientCreate(BaseModel):
    """Registration payload for a new demonstration patient.

    Ranges are deliberately generous (this is a demo dataset, not clinical
    validation) but every required field is checked so an incomplete patient
    can never reach the store.
    """

    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(
        min_length=2,
        max_length=32,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Unique ID, e.g. DOC-001 (letters, digits, - and _)",
    )
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=0, le=120)
    sex: str = Field(min_length=1, max_length=40)
    diabetes_type: str = Field(min_length=1, max_length=40)
    years_since_diagnosis: int = Field(ge=0, le=100)
    height_cm: float = Field(gt=40, le=260)
    weight_kg: float = Field(gt=20, le=600)
    bmi: float = Field(gt=5, le=120)
    hba1c_pct: float = Field(
        gt=2, le=25, description="Doctor-entered HbA1c (%) used as the model's static feature"
    )
    medical_history: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
    family_history: str = Field(default="", max_length=300)
    smoking_status: str = Field(default="", max_length=60)
    activity_level: str = Field(default="", max_length=60)

    @field_validator("medical_history", "current_medications")
    @classmethod
    def _entries(cls, v, info):
        return _clean_entries(v, info.field_name)

    @field_validator("name", "sex", "diabetes_type")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("must not be blank")
        return text


class PatientUpdate(BaseModel):
    """Partial update of an existing patient (PUT). The ID never changes."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    age: Optional[int] = Field(default=None, ge=0, le=120)
    sex: Optional[str] = Field(default=None, min_length=1, max_length=40)
    diabetes_type: Optional[str] = Field(default=None, min_length=1, max_length=40)
    years_since_diagnosis: Optional[int] = Field(default=None, ge=0, le=100)
    height_cm: Optional[float] = Field(default=None, gt=40, le=260)
    weight_kg: Optional[float] = Field(default=None, gt=20, le=600)
    bmi: Optional[float] = Field(default=None, gt=5, le=120)
    hba1c_pct: Optional[float] = Field(default=None, gt=2, le=25)
    medical_history: Optional[list[str]] = None
    current_medications: Optional[list[str]] = None
    family_history: Optional[str] = Field(default=None, max_length=300)
    smoking_status: Optional[str] = Field(default=None, max_length=60)
    activity_level: Optional[str] = Field(default=None, max_length=60)

    @field_validator("medical_history", "current_medications")
    @classmethod
    def _entries(cls, v, info):
        if v is None:
            return None
        return _clean_entries(v, info.field_name)


class EhrEntryIn(BaseModel):
    """One doctor-entered EHR-style record (appended, never overwritten)."""

    model_config = ConfigDict(extra="forbid")

    record_date: str = Field(min_length=4, max_length=32, description="YYYY-MM-DD")
    record_type: str = Field(min_length=1, max_length=80)
    hba1c_pct: Optional[float] = Field(default=None, gt=2, le=25)
    systolic_bp: Optional[int] = Field(default=None, ge=50, le=300)
    diastolic_bp: Optional[int] = Field(default=None, ge=30, le=220)
    ldl_mg_dl: Optional[float] = Field(default=None, ge=1, le=500)
    medications: Optional[list[str]] = None
    clinician_note: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("medications")
    @classmethod
    def _entries(cls, v, info):
        return _clean_entries(v, info.field_name)


class ReadingIn(BaseModel):
    """One timestamped sensor/medical reading. Missing measurements stay null."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(min_length=1, max_length=64)
    glucose_mg_dl: Optional[float] = Field(default=None, ge=10, le=1000)
    heart_rate_bpm: Optional[float] = Field(default=None, ge=20, le=300)
    steps_5min: Optional[int] = Field(default=None, ge=0, le=100000)
    sleep_minutes: Optional[float] = Field(default=None, ge=0, le=1440)
    meal_event: int = Field(default=0, ge=0, le=1)
    minutes_since_meal: Optional[float] = Field(default=None, ge=0, le=10080)


class ReadingsImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    readings: list[ReadingIn] = Field(min_length=1, max_length=config.MAX_IMPORT_ROWS)
    dry_run: bool = Field(default=False, description="Validate only; persist nothing")


class CsvImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv_text: str = Field(
        min_length=1,
        max_length=config.MAX_CSV_TEXT_BYTES,
        description="Raw CSV text; server parses and sanitises it",
    )
    dry_run: bool = Field(default=False, description="Preview only; persist nothing")


class ImportRow(BaseModel):
    row_index: int
    timestamp: Optional[str] = None
    status: Literal["accepted", "rejected"]
    reason: Optional[str] = None
    glucose_mg_dl: Optional[float] = None
    heart_rate_bpm: Optional[float] = None
    steps_5min: Optional[int] = None
    sleep_minutes: Optional[float] = None
    meal_event: Optional[int] = None
    minutes_since_meal: Optional[float] = None
    missing: list[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    patient_id: str
    rows: list[ImportRow]
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    persisted: bool
    dry_run: bool
    message: str
    filename: Optional[str] = Field(
        default=None, description="Base name of the uploaded file (multipart uploads only)"
    )


# ------------------------------------------------------------------- auth


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=config.MIN_PASSWORD_LENGTH, max_length=256)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ClinicianOut(BaseModel):
    clinician_id: str
    username: str
    role: str


class TokenResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: str
    clinician: ClinicianOut


class RevokeResponse(BaseModel):
    revoked: bool