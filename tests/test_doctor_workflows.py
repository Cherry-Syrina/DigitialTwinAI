"""Doctor workflow tests: registration, profile edits, data entry, CSV import,
reports and persistence.

These exercise the write endpoints end-to-end through the ASGI app. A session
database (see conftest) backs the SQLite overlay, so every test uses unique
patient IDs and asserts the behaviour it creates.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.app.main import create_app

BASE_PATIENT = {
    "name": "Workflow Patient",
    "age": 57,
    "sex": "F",
    "diabetes_type": "Type 2",
    "years_since_diagnosis": 7,
    "height_cm": 164.0,
    "weight_kg": 72.5,
    "bmi": 27.0,
    "hba1c_pct": 7.3,
    "medical_history": ["Hypertension", "Dyslipidemia"],
    "current_medications": ["Metformin"],
    "family_history": "Type 2 diabetes (mother)",
    "smoking_status": "Never",
    "activity_level": "Moderate",
}


def _register(client: TestClient, patient_id: str, **overrides):
    return client.post("/api/patients", json={**BASE_PATIENT, "patient_id": patient_id, **overrides})


def _readings(n: int = 24, start_hour: int = 9):
    """Fully-specified readings so model features are all available."""
    return [
        {
            "timestamp": f"2026-10-15 {start_hour + i // 4:02d}:{(i % 4) * 15:02d}:00",
            "glucose_mg_dl": 128 + (i % 9) * 4,
            "heart_rate_bpm": 70 + (i % 6),
            "steps_5min": 4,
            "sleep_minutes": 0 if i % 3 else 5,
            "meal_event": 1 if i % 8 == 3 else 0,
            "minutes_since_meal": 60 if i % 8 == 3 else 180,
        }
        for i in range(n)
    ]


# ------------------------------------------------------------------ registration


def test_register_patient_returns_created_profile(client):
    pid = "TST-REG-01"
    r = _register(client, pid)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["patient_id"] == pid
    assert body["name"] == BASE_PATIENT["name"]
    assert body["medical_history"] == ["Hypertension", "Dyslipidemia"]
    assert body["data_label"] == "doctor_entered"
    assert body["disclaimer"]  # synthetic-data disclaimer always present
    # registration stores the entered HbA1c as a summary so the model has it
    assert any(s["hba1c_pct"] == 7.3 for s in body["glucose_summaries"])


def test_register_patient_appears_in_list(client):
    pid = "TST-REG-02"
    assert _register(client, pid).status_code == 201
    listing = client.get("/api/patients").json()
    assert isinstance(listing, list)
    entry = next(p for p in listing if p["patient_id"] == pid)
    assert entry["data_label"] == "doctor_entered"
    assert entry["latest_glucose_mg_dl"] is None  # no readings yet


def test_register_duplicate_id_conflicts(client):
    pid = "TST-DUP-01"
    assert _register(client, pid).status_code == 201
    r = _register(client, pid)
    assert r.status_code == 409
    assert pid in r.json()["detail"]


def test_register_validation_errors(client):
    # missing required field
    payload = {**BASE_PATIENT, "patient_id": "TST-BAD-01"}
    payload.pop("hba1c_pct")
    r = client.post("/api/patients", json=payload)
    assert r.status_code == 422
    assert any(e["loc"][-1] == "hba1c_pct" for e in r.json()["detail"])

    # invalid ID pattern
    assert _register(client, "bad id!").status_code == 422

    # out-of-range value
    assert _register(client, "TST-BAD-02", age=200).status_code == 422

    # list-of-free-text is bounded to meaningful entries
    assert _register(client, "TST-BAD-03", medical_history=[""]).status_code == 201
    assert _register(client, "TST-BAD-04", medical_history=["x" * 500]).status_code == 422


def test_registration_persists_across_app_instances(client):
    pid = "TST-PERSIST-01"
    assert _register(client, pid).status_code == 201
    # a completely new app instance reads the same SQLite overlay
    other = TestClient(create_app())
    r = other.get(f"/api/patients/{pid}")
    assert r.status_code == 200
    assert r.json()["name"] == BASE_PATIENT["name"]


# ----------------------------------------------------------------------- updates


def test_update_patient_fields(client):
    pid = "TST-UPD-01"
    assert _register(client, pid).status_code == 201
    r = client.put(f"/api/patients/{pid}", json={"weight_kg": 69.9, "current_medications": ["Insulin"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["weight_kg"] == 69.9
    assert body["current_medications"] == ["Insulin"]
    # re-read confirms the change was persisted
    assert client.get(f"/api/patients/{pid}").json()["weight_kg"] == 69.9


def test_update_rejects_unknown_fields_and_patients(client):
    pid = "TST-UPD-02"
    assert _register(client, pid).status_code == 201
    assert client.put(f"/api/patients/{pid}", json={"agee": 60}).status_code == 422
    assert client.put(f"/api/patients/{pid}", json={}).status_code == 422
    assert client.put("/api/patients/NOPE-404", json={"weight_kg": 70}).status_code == 404


def test_update_hba1c_appends_summary(client):
    pid = "TST-UPD-03"
    assert _register(client, pid).status_code == 201
    r = client.put(f"/api/patients/{pid}", json={"hba1c_pct": 6.8})
    assert r.status_code == 200
    summaries = r.json()["glucose_summaries"]
    assert any(s["hba1c_pct"] == 6.8 for s in summaries)
    # history is appended, not overwritten
    assert any(s["hba1c_pct"] == 7.3 for s in summaries)


# ---------------------------------------------------------------- ehr appends


def test_add_ehr_record(client):
    pid = "TST-EHR-01"
    assert _register(client, pid).status_code == 201
    r = client.post(
        f"/api/patients/{pid}/ehr",
        json={"record_date": "2026-02-10", "record_type": "Lab panel", "hba1c_pct": 7.0, "clinician_note": "stable"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["record_id"].startswith("EHR-DB-")
    profile = client.get(f"/api/patients/{pid}").json()
    assert any(e["record_type"] == "Lab panel" for e in profile["ehr_records"])


def test_add_ehr_record_bad_date(client):
    pid = "TST-EHR-02"
    assert _register(client, pid).status_code == 201
    r = client.post(f"/api/patients/{pid}/ehr", json={"record_date": "not-a-date", "record_type": "Lab"})
    assert r.status_code == 422
    assert client.post("/api/patients/NOPE-404/ehr", json={"record_date": "2026-02-10", "record_type": "Lab"}).status_code == 404


# ------------------------------------------------------- manual reading import


def test_manual_readings_dry_run_then_commit(client):
    pid = "TST-READ-01"
    assert _register(client, pid).status_code == 201
    readings = _readings(8)

    preview = client.post(f"/api/patients/{pid}/readings", json={"readings": readings, "dry_run": True})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["accepted_count"] == 8
    assert body["persisted"] is False
    assert body["dry_run"] is True
    assert "Dry run" in body["message"]
    # nothing persisted yet
    assert client.get(f"/api/patients/{pid}/digital-twin").json()["observed_rows"] == 0

    commit = client.post(f"/api/patients/{pid}/readings", json={"readings": readings})
    assert commit.status_code == 200
    assert commit.json()["persisted"] is True
    assert commit.json()["accepted_count"] == 8


def test_manual_readings_duplicates_and_invalid_timestamps(client):
    pid = "TST-READ-02"
    assert _register(client, pid).status_code == 201
    first = _readings(3)
    assert client.post(f"/api/patients/{pid}/readings", json={"readings": first}).json()["accepted_count"] == 3

    r = client.post(
        f"/api/patients/{pid}/readings",
        json={"readings": [first[0], {"timestamp": "garbage", "glucose_mg_dl": 120}, {"timestamp": first[0]["timestamp"]}]},
    )
    body = r.json()
    assert body["accepted_count"] == 0
    assert body["duplicate_count"] == 1  # vs stored + within the batch
    assert body["rejected_count"] == 3
    reasons = [row["reason"] for row in body["rows"]]
    assert any("duplicate" in (x or "") for x in reasons)
    assert any("could not be parsed" in (x or "") for x in reasons)


def test_readings_range_validation_is_422(client):
    pid = "TST-READ-03"
    assert _register(client, pid).status_code == 201
    r = client.post(f"/api/patients/{pid}/readings", json={"readings": [{"timestamp": "2026-10-15 09:00:00", "glucose_mg_dl": 5000}]})
    assert r.status_code == 422
    assert any(e["loc"][-1] == "glucose_mg_dl" for e in r.json()["detail"])


# ------------------------------------------------------------- CSV import


CSV_GOOD = (
    "timestamp,glucose_mg_dl,heart_rate_bpm,notes\n"
    "2026-10-14 08:00:00,141,74,first\n"
    "2026-10-14 08:30:00,,75,missing glucose\n"
    "2026-10-14 09:00:00,not-a-number,76,bad value\n"
)


def test_csv_import_preview_then_commit(client):
    pid = "TST-CSV-01"
    assert _register(client, pid).status_code == 201
    preview = client.post(f"/api/patients/{pid}/readings/csv", json={"csv_text": CSV_GOOD, "dry_run": True})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    # row 0 valid, row 1 has glucose missing but a valid heart rate (kept as NULL,
    # never imputed), row 2 has an unparseable glucose value and is rejected.
    assert body["accepted_count"] == 2
    assert body["rejected_count"] == 1
    assert body["duplicate_count"] == 0
    assert "notes" in body["message"]  # unknown column reported
    assert body["persisted"] is False
    rejected = next(row for row in body["rows"] if row["status"] == "rejected")
    assert "glucose_mg_dl" in rejected["reason"]
    accepted = [row for row in body["rows"] if row["status"] == "accepted"]
    assert any("glucose_mg_dl" in row["missing"] for row in accepted)

    commit = client.post(f"/api/patients/{pid}/readings/csv", json={"csv_text": CSV_GOOD})
    assert commit.status_code == 200
    assert commit.json()["persisted"] is True
    assert commit.json()["accepted_count"] == 2
    # importing the same file again is fully rejected as duplicates
    again = client.post(f"/api/patients/{pid}/readings/csv", json={"csv_text": CSV_GOOD}).json()
    assert again["accepted_count"] == 0
    assert again["duplicate_count"] == 2


def test_csv_import_structural_errors(client):
    pid = "TST-CSV-02"
    assert _register(client, pid).status_code == 201
    r = client.post(f"/api/patients/{pid}/readings/csv", json={"csv_text": "a,b\n1,2\n"})
    assert r.status_code == 422
    assert "timestamp" in r.json()["detail"]
    # unknown patient is rejected before parsing
    assert client.post("/api/patients/NOPE-404/readings/csv", json={"csv_text": CSV_GOOD}).status_code == 404


# ------------------------------------------------- CSV multipart file upload


def test_csv_upload_preview_then_commit(client):
    pid = "TST-UP-01"
    assert _register(client, pid).status_code == 201

    files = {"file": ("sensor_export.csv", CSV_GOOD.encode("utf-8"), "text/csv")}
    preview = client.post(
        f"/api/patients/{pid}/readings/csv/upload", files=files, data={"dry_run": "true"}
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["accepted_count"] == 2
    assert body["rejected_count"] == 1
    assert body["persisted"] is False
    assert body["filename"] == "sensor_export.csv"
    assert "sensor_export.csv" in body["message"]
    assert "notes" in body["message"]  # unknown column surfaced
    assert client.get(f"/api/patients/{pid}/digital-twin").json()["observed_rows"] == 0

    commit = client.post(
        f"/api/patients/{pid}/readings/csv/upload",
        files={"file": ("sensor_export.csv", CSV_GOOD.encode("utf-8"), "text/csv")},
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["persisted"] is True
    assert commit.json()["accepted_count"] == 2
    # the newly saved readings are observed by the digital twin
    assert client.get(f"/api/patients/{pid}/digital-twin").json()["observed_rows"] == 2

    # re-uploading the same file is fully rejected as duplicates
    again = client.post(
        f"/api/patients/{pid}/readings/csv/upload",
        files={"file": ("sensor_export.csv", CSV_GOOD.encode("utf-8"), "text/csv")},
    ).json()
    assert again["accepted_count"] == 0
    assert again["duplicate_count"] == 2


def test_csv_upload_handles_bom_and_latin1(client):
    pid = "TST-UP-02"
    assert _register(client, pid).status_code == 201
    # BOM + a latin-1 encoded name in an ignored column -> still parses
    raw = ("timestamp,glucose_mg_dl,patient_name\n2026-10-13 07:00:00,131,Jos\xe9\n").encode("latin-1")
    r = client.post(
        f"/api/patients/{pid}/readings/csv/upload",
        files={"file": ("latin.csv", raw, "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted_count"] == 1


def test_csv_upload_validation_errors(client):
    pid = "TST-UP-03"
    assert _register(client, pid).status_code == 201

    # structurally invalid: no timestamp column
    bad = client.post(
        f"/api/patients/{pid}/readings/csv/upload",
        files={"file": ("bad.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert bad.status_code == 422
    assert "timestamp" in bad.json()["detail"]

    # empty file
    empty = client.post(
        f"/api/patients/{pid}/readings/csv/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert empty.status_code == 422
    assert "empty" in empty.json()["detail"].lower()

    # oversized file rejected before persisting anything
    oversized = client.post(
        f"/api/patients/{pid}/readings/csv/upload",
        files={"file": ("huge.csv", b"x" * (2 * 1024 * 1024 + 1), "text/csv")},
    )
    assert oversized.status_code == 422
    assert "limit" in oversized.json()["detail"]

    # unknown patient 404 (checked before parsing)
    assert client.post(
        "/api/patients/NOPE-404/readings/csv/upload",
        files={"file": ("ok.csv", CSV_GOOD.encode("utf-8"), "text/csv")},
    ).status_code == 404


def test_csv_upload_rows_labelled_for_other_patient_rejected(client):
    pid = "TST-UP-04"
    assert _register(client, pid).status_code == 201
    text = (
        "timestamp,glucose_mg_dl,patient_id\n"
        f"2026-10-12 06:00:00,140,{pid}\n"
        "2026-10-12 06:30:00,138,SOMEONE-ELSE\n"
    )
    r = client.post(
        f"/api/patients/{pid}/readings/csv/upload",
        files={"file": ("mixed.csv", text.encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted_count"] == 1
    rejected = next(row for row in body["rows"] if row["status"] == "rejected")
    assert "SOMEONE-ELSE" in rejected["reason"]


def test_csv_upload_sanitises_filename(client):
    pid = "TST-UP-05"
    assert _register(client, pid).status_code == 201
    r = client.post(
        f"/api/patients/{pid}/readings/csv/upload",
        files={"file": ("..\\..\\windows\\system32\\evil.csv", CSV_GOOD.encode("utf-8"), "text/csv")},
        data={"dry_run": "true"},
    )
    assert r.status_code == 200, r.text
    # only the base name is echoed back, never a path
    assert r.json()["filename"] == "evil.csv"
    assert "system32" not in r.json()["message"]


# --------------------------------------------------- twin update + reports


def test_entered_patient_drives_twin_prediction(client):
    pid = "TST-TWIN-01"
    assert _register(client, pid).status_code == 201
    readings = _readings(48)
    assert client.post(f"/api/patients/{pid}/readings", json={"readings": readings}).json()["accepted_count"] == 48

    twin = client.get(f"/api/patients/{pid}/digital-twin")
    assert twin.status_code == 200, twin.text
    body = twin.json()
    assert body["observed_rows"] == 48
    assert body["total_rows"] == 48
    latest = body["latest_reading"]
    assert latest["source"] == "doctor_entered_reading"
    assert body["model_error"] is None
    assert body["prediction"] is not None
    assert body["prediction"]["predicted_glucose_mg_dl"] > 0
    assert body["sensor_feed"]["type"] == "doctor_entered_readings"


def test_report_includes_entered_data_and_sections(client):
    pid = "TST-TWIN-01"
    r = client.get(f"/api/patients/{pid}/report")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["data_label"] == "doctor_entered"
    md = body["content_markdown"]
    assert "Demonstration Patient Report" in md
    assert "## 1. Data source and provenance" in md
    assert "## 7. Recent observed sensor readings" in md
    assert "## 10. Model and evaluation metrics" in md
    assert "Configured risk thresholds" in md
    # provenance reflects the imported rows
    assert "48 doctor-entered" in md


def test_report_synthetic_patient_unchanged_title(client):
    r = client.get("/api/patients/GT-001/report")
    assert r.status_code == 200
    assert "Synthetic Patient Report" in r.json()["content_markdown"]


def test_report_unknown_patient_404(client):
    assert client.get("/api/patients/NOPE-404/report").status_code == 404


# ------------------------------------------------------------- PDF reports


def test_pdf_report_synthetic_patient(client):
    r = client.get("/api/patients/GT-001/report.pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf")
    assert "attachment" in r.headers["content-disposition"]
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 2000
    # observed vs predicted are both present and separately labelled
    assert b"Synthetic Patient Report" in r.content
    assert b"Historical observations" in r.content
    assert b"model prediction" in r.content
    assert b"Not a medical device" in r.content


def test_pdf_report_entered_patient_and_404(client):
    pid = "TST-PDF-01"
    assert _register(client, pid).status_code == 201
    assert client.post(f"/api/patients/{pid}/readings", json={"readings": _readings(48)}).json()["accepted_count"] == 48

    r = client.get(f"/api/patients/{pid}/report.pdf")
    assert r.status_code == 200, r.text
    body = r.content
    assert b"Demonstration Patient Report" in body
    assert b"doctor_entered" in body
    assert pid.encode() in body

    assert client.get("/api/patients/NOPE-404/report.pdf").status_code == 404
