"""Validation and sanitisation for doctor-entered sensor readings.

Single source of truth for:
  * timestamp parsing / bounds checking (dataset-compatible canonical form)
  * per-row field validation (delegates ranges to Pydantic ``ReadingIn``)
  * missing-value detection (missing values are kept empty, NEVER imputed)
  * CSV text sanitisation (size limits, header checks, malformed rows)

Raw CSV text is parsed server-side so upload sanitisation does not depend on
the browser. Structural problems raise :class:`CsvFormatError` (mapped to
422); row-level problems are reported per row so a bulk import can partially
succeed with an explicit rejection list.
"""
from __future__ import annotations

import csv as csvlib
import io
from datetime import datetime, timedelta

import pandas as pd
from pydantic import ValidationError

from .. import config
from ..schemas import api as schemas

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
EARLIEST_TIMESTAMP = datetime(2000, 1, 1)

OPTIONAL_FIELDS = (
    "glucose_mg_dl",
    "heart_rate_bpm",
    "steps_5min",
    "sleep_minutes",
    "meal_event",
    "minutes_since_meal",
)
MEASUREMENT_FIELDS = (
    "glucose_mg_dl",
    "heart_rate_bpm",
    "steps_5min",
    "sleep_minutes",
    "minutes_since_meal",
)
KNOWN_CSV_COLUMNS = ("timestamp", "patient_id", "data_label", *OPTIONAL_FIELDS)


class CsvFormatError(ValueError):
    """Fatal structural problem with an uploaded CSV (whole request rejected)."""


def parse_timestamp(value) -> tuple[str | None, str | None]:
    """Parse to canonical ``YYYY-MM-DD HH:MM:SS`` (tz converted to UTC).

    Returns ``(canonical, None)`` on success or ``(None, reason)``.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, "timestamp is required"
    raw = str(value).strip()
    try:
        ts = pd.to_datetime(raw, errors="raise")
    except (ValueError, TypeError):
        return None, "timestamp could not be parsed (use YYYY-MM-DD HH:MM:SS or ISO 8601)"
    if not isinstance(ts, pd.Timestamp) or pd.isna(ts):
        return None, "timestamp could not be parsed (use YYYY-MM-DD HH:MM:SS or ISO 8601)"
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    ts = ts.floor("s")
    if ts.to_pydatetime() < EARLIEST_TIMESTAMP:
        return None, "timestamp is before 2000-01-01"
    if ts.to_pydatetime() > datetime.now() + timedelta(minutes=5):
        return None, "timestamp is in the future (check date and time)"
    return ts.strftime(TIMESTAMP_FORMAT), None


def _clean_raw(raw: dict) -> dict:
    """Strip strings; map empty optional cells to None (no fabrication)."""
    out: dict = {}
    for key, value in raw.items():
        if key is None:
            continue
        key = str(key).strip()
        if isinstance(value, str):
            value = value.strip()
        if key in OPTIONAL_FIELDS and value == "":
            value = None
        out[key] = value
    return out


def validate_reading(
    raw: dict,
    row_index: int,
    expected_patient_id: str | None = None,
) -> tuple[dict | None, dict | None]:
    """Validate + normalise one raw reading.

    Returns ``(entry, None)`` for an accepted row or ``(None, rejection)``.
    ``entry`` contains canonical typed values plus ``missing`` (list of empty
    measurement fields - stored as NULL, never imputed).
    """
    raw = _clean_raw(raw)
    rejected = {
        "row_index": row_index,
        "timestamp": str(raw.get("timestamp") or ""),
        "status": "rejected",
        "reason": None,
    }

    patient_id_cell = str(raw.get("patient_id") or "").strip()
    if expected_patient_id and patient_id_cell and patient_id_cell != expected_patient_id:
        rejected["reason"] = (
            f"row is labelled for patient '{patient_id_cell}', not '{expected_patient_id}'"
        )
        return None, rejected

    canonical, ts_error = parse_timestamp(raw.get("timestamp"))
    if ts_error:
        rejected["reason"] = ts_error
        return None, rejected

    try:
        reading = schemas.ReadingIn(
            timestamp=canonical,
            **{
                f: raw[f]
                for f in OPTIONAL_FIELDS
                if f in raw and raw[f] is not None
            },
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first.get("loc", ())) or "value"
        rejected["reason"] = f"{field}: {first.get('msg', 'invalid value')}"
        return None, rejected

    values = reading.model_dump()
    missing = [f for f in MEASUREMENT_FIELDS if values.get(f) is None]
    if len(missing) == len(MEASUREMENT_FIELDS):
        rejected["reason"] = "row contains no measurement values (all measurement cells are empty)"
        return None, rejected

    entry = {
        "row_index": row_index,
        "timestamp": canonical,
        "glucose_mg_dl": values["glucose_mg_dl"],
        "heart_rate_bpm": values["heart_rate_bpm"],
        "steps_5min": values["steps_5min"],
        "sleep_minutes": values["sleep_minutes"],
        "meal_event": values["meal_event"],
        "minutes_since_meal": values["minutes_since_meal"],
        "missing": missing,
    }
    return entry, None


def sanitise_filename(name: str | None, max_length: int = 120) -> str:
    """Reduce an uploaded filename to a safe base name for display only.

    Strips any directory components (Windows and POSIX separators) so a hostile
    multipart filename can never influence a path, and truncates for storage.
    """
    if not name:
        return ""
    base = str(name).replace("\\", "/").split("/")[-1].strip()
    base = "".join(ch for ch in base if ch.isprintable()).strip()
    return base[:max_length]


def parse_csv_bytes(data: bytes) -> tuple[list[dict], list[str]]:
    """Parse uploaded CSV *bytes* (multipart upload path).

    Enforces the raw byte-size limit before decoding so an oversized body is
    rejected without holding a decoded copy. Decodes UTF-8 (BOM tolerated),
    falling back to latin-1 for older exports. Raises :class:`CsvFormatError`
    for structural problems.
    """
    if data is None or len(data) == 0:
        raise CsvFormatError("Uploaded CSV file is empty")
    if len(data) > config.MAX_CSV_TEXT_BYTES:
        raise CsvFormatError(
            f"CSV exceeds the {config.MAX_CSV_TEXT_BYTES // (1024 * 1024)} MiB upload limit"
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except UnicodeDecodeError as exc:  # pragma: no cover - latin-1 never fails
            raise CsvFormatError("CSV is not decodable text") from exc
    return parse_csv_text(text)


def parse_csv_text(text: str) -> tuple[list[dict], list[str]]:
    """Parse and sanitise raw CSV text.

    Returns ``(raw_rows, ignored_columns)`` where each raw row carries its
    ``row_index`` (and, for malformed rows, a ``_csv_error`` marker).
    Raises :class:`CsvFormatError` for structural problems.
    """
    if text is None or not str(text).strip():
        raise CsvFormatError("CSV content is empty")
    if len(str(text).encode("utf-8", "ignore")) > config.MAX_CSV_TEXT_BYTES:
        raise CsvFormatError(
            f"CSV exceeds the {config.MAX_CSV_TEXT_BYTES // (1024 * 1024)} MiB upload limit"
        )

    cleaned = str(text).lstrip("\ufeff")
    reader = csvlib.DictReader(io.StringIO(cleaned))
    if not reader.fieldnames:
        raise CsvFormatError("CSV has no header row")

    fieldnames = [(f or "").strip() for f in reader.fieldnames]
    if any(not f for f in fieldnames):
        raise CsvFormatError("CSV header contains an empty column name")
    if "timestamp" not in fieldnames:
        raise CsvFormatError(
            "CSV must contain a 'timestamp' column "
            f"(found: {', '.join(fieldnames) if fieldnames else 'none'})"
        )
    ignored = [f for f in fieldnames if f not in KNOWN_CSV_COLUMNS]

    rows: list[dict] = []
    for i, rec in enumerate(reader):
        if i >= config.MAX_IMPORT_ROWS:
            raise CsvFormatError(
                f"CSV has more than {config.MAX_IMPORT_ROWS} data rows; split the file and re-upload"
            )
        if None in rec or any(v is None for v in rec.values()):
            rows.append(
                {
                    "row_index": i,
                    "timestamp": str(rec.get("timestamp") or ""),
                    "_csv_error": "malformed row (wrong number of columns)",
                }
            )
            continue
        rows.append({"row_index": i, **{k: v for k, v in rec.items() if k}})
    return rows, ignored
