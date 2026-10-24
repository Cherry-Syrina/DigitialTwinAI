"""API integration tests via FastAPI TestClient."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def pid():
    return "GT-001"


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert 60 in body["model_horizons_minutes"]
    assert body["dataset_patients"] == 8


def test_list_patients(client):
    resp = client.get("/api/patients")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 8
    assert "patient_id" in body[0]
    sample = body[0]
    assert sample["data_label"] == "synthetic"
    assert sample["age"] > 0


def test_get_patient(client, pid):
    resp = client.get(f"/api/patients/{pid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["patient_id"] == pid
    assert body["diabetes_type"]
    assert len(body["ehr_records"]) >= 1
    assert len(body["glucose_summaries"]) >= 1


def test_patient_not_found(client):
    resp = client.get("/api/patients/GT-999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_history(client, pid):
    resp = client.get(f"/api/patients/{pid}/history", params={"hours": 6, "limit": 200})
    assert resp.status_code == 200
    body = resp.json()
    assert body["unit"] == "mg/dL"
    assert len(body["readings"]) > 0
    assert len(body["readings"]) <= 200


def test_history_invalid_hours(client, pid):
    resp = client.get(f"/api/patients/{pid}/history", params={"hours": -1})
    assert resp.status_code == 422


def test_digital_twin(client, pid):
    resp = client.get(f"/api/patients/{pid}/digital-twin")
    assert resp.status_code == 200
    body = resp.json()
    assert body["patient_id"] == pid
    assert body["prediction"] is not None
    assert body["prediction"]["source"] == "model_prediction"
    assert len(body["prediction"]["trajectory"]) == 4
    assert "risk" in body and body["risk"]["level"] in {"none", "medium", "high", "critical"}


def test_prediction_endpoint(client, pid):
    resp = client.post(f"/api/patients/{pid}/predict", json={"horizon_minutes": 60})
    assert resp.status_code == 200
    body = resp.json()
    assert body["horizon_minutes"] == 60
    assert body["predicted_glucose_mg_dl"] > 0
    assert body["model"]["framework"] == "scikit-learn"
    assert body["disclaimer"]


def test_prediction_bad_horizon(client, pid):
    resp = client.post(f"/api/patients/{pid}/predict", json={"horizon_minutes": 73})
    assert resp.status_code == 422


def test_prediction_missing_body_validates(client, pid):
    resp = client.post(f"/api/patients/{pid}/predict", json={"horizon_minutes": "nope"})
    assert resp.status_code == 422


def test_what_if_ok(client, pid):
    resp = client.post(
        f"/api/patients/{pid}/what-if",
        json={"horizon_minutes": 60, "overrides": {"steps_last_60m": 800, "heart_rate_last_60m": 115}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"]["overrides"]["steps_last_60m"] == 800
    assert "feature_contributions" in body


def test_what_if_bad_key(client, pid):
    resp = client.post(
        f"/api/patients/{pid}/what-if",
        json={"horizon_minutes": 60, "overrides": {"not_a_feature": 1}},
    )
    assert resp.status_code == 422


def test_what_if_empty_overrides(client, pid):
    resp = client.post(
        f"/api/patients/{pid}/what-if",
        json={"horizon_minutes": 60, "overrides": {}},
    )
    assert resp.status_code == 422


def test_demo_advance_all_and_single(client):
    resp = client.post("/api/demo/advance", json={"steps": 6})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["advanced"]) == 8
    assert all(a["added_rows"] == 6 for a in body["advanced"])


def test_demo_advance_single_patient(client, pid, fresh_client):
    current = fresh_client.get(f"/api/patients/{pid}/digital-twin").json()
    resp = fresh_client.post("/api/demo/advance", json={"patient_id": pid, "steps": 12})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["advanced"]) == 1
    assert body["advanced"][0]["added_rows"] == 12
    after = fresh_client.get(f"/api/patients/{pid}/digital-twin").json()
    assert after["observed_rows"] == current["observed_rows"] + 12


def test_model_metrics(client):
    resp = client.get("/api/model/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["framework"] == "scikit-learn"
    assert "60" in body["horizons"]
    mae = body["horizons"]["60"]["metrics"]["mae"]
    pers = body["horizons"]["60"]["baselines"]["persistence"]["mae"]
    assert 0 < mae < pers


def test_thresholds(client):
    resp = client.get("/api/model/thresholds")
    assert resp.status_code == 200
    body = resp.json()
    assert body["hyper_high_mg_dl"] == 180
    assert body["hypo_low_mg_dl"] == 70


def test_report(client, pid):
    resp = client.get(f"/api/patients/{pid}/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["patient_id"] == pid
    assert "Synthetic Patient Report" in body["content_markdown"]
    assert "SYNTHETIC" in body["content_markdown"].upper()


def test_swagger_ui_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for required in [
        "/api/health",
        "/api/patients",
        "/api/patients/{patient_id}",
        "/api/patients/{patient_id}/history",
        "/api/patients/{patient_id}/digital-twin",
        "/api/patients/{patient_id}/predict",
        "/api/demo/advance",
        "/api/model/metrics",
    ]:
        assert required in paths, f"missing OpenAPI path {required}"