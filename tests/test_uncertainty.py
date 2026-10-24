"""Forecast-uncertainty tests.

Covers the split-conformal prediction intervals produced at training time:
metrics must carry a calibration + held-out coverage record, predictions must
carry a matching band, and the report/PDF must show it only when it exists.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_metrics_expose_interval_and_held_out_coverage(client):
    metrics = client.get("/api/model/metrics").json()
    assert "uncertainty" in metrics
    horizons = metrics["horizons"]
    assert horizons, "expected trained horizons"
    for key, entry in horizons.items():
        unc = entry["uncertainty"]
        assert unc["method"] == "split_conformal_residual_quantile"
        assert 0 < unc["half_width_mg_dl"] < 200
        assert 0.0 <= unc["coverage_pct"] <= 100.0
        assert unc["n_calibration"] > 0 and unc["n_eval"] > 0
        assert unc["n_calibration"] + unc["n_eval"] + unc["n_embargoed"] == entry["rows_test"]
        assert unc["n_embargoed"] > 0


def test_prediction_returns_interval_that_brackets_the_point(client, pid="GT-001"):
    payload = client.post(f"/api/patients/{pid}/predict", json={"horizon_minutes": 60}).json()
    interval = payload["interval"]
    assert interval["lower_mg_dl"] < payload["predicted_glucose_mg_dl"] < interval["upper_mg_dl"]
    assert interval["method"] == "split_conformal_residual_quantile"
    assert interval["coverage_pct"] is not None
    assert interval["source"] == "model_interval"
    assert "clinically validated" in interval["disclaimer"]
    # every trajectory point carries its own horizon-specific band
    for point in payload["trajectory"]:
        band = point["interval"]
        assert band["lower_mg_dl"] < point["predicted_glucose_mg_dl"] < band["upper_mg_dl"]


def test_twin_state_exposes_interval(client):
    state = client.get("/api/patients/GT-001/digital-twin").json()
    assert state["prediction"]["interval"] is not None


def test_report_and_pdf_include_uncertainty(client):
    md = client.get("/api/patients/GT-001/report").json()["content_markdown"]
    assert "Uncertainty (80% interval)" in md
    assert "Empirical coverage (held-out synthetic test)" in md

    pdf = client.get("/api/patients/GT-001/report.pdf")
    assert pdf.status_code == 200
    assert b"Prediction interval" in pdf.content
    assert b"Empirical coverage" in pdf.content
    assert b"NOT clinically validated" in pdf.content
