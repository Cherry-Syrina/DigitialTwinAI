"""Authentication + patient-ownership isolation tests.

These run against a client with ``GLUCOTWIN_AUTH_ENABLED=1`` and a dedicated
SQLite file (see the ``auth_client`` fixture), so they prove the protection is
real rather than decorative: no token -> 401, wrong owner -> 403, and secrets
are never recoverable from the database.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from backend.app.services.auth import hash_password, verify_password

ADMIN_KEY = "test-admin-key"

PATIENT = {
    "name": "Owned Patient",
    "age": 61,
    "sex": "M",
    "diabetes_type": "Type 2",
    "years_since_diagnosis": 9,
    "height_cm": 178.0,
    "weight_kg": 88.0,
    "bmi": 27.8,
    "hba1c_pct": 7.6,
    "medical_history": ["Hypertension"],
    "current_medications": ["Metformin"],
    "family_history": "Type 2 diabetes (father)",
    "smoking_status": "Former",
    "activity_level": "Low",
}


def _username() -> str:
    return f"dr_{uuid.uuid4().hex[:10]}"


def _register(client, username, password="correct-horse-battery", key=ADMIN_KEY):
    return client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
        headers={"X-Admin-Key": key} if key is not None else {},
    )


def _login(client, username, password="correct-horse-battery"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _new_clinician(client):
    username = _username()
    assert _register(client, username).status_code == 201
    token = _login(client, username).json()["token"]
    return username, token


# ------------------------------------------------------------------ passwords


def test_password_hash_roundtrip_and_rejects_others():
    digest = hash_password("correct-horse-battery")
    assert digest.startswith("pbkdf2_sha256$")
    assert "correct-horse-battery" not in digest
    assert verify_password("correct-horse-battery", digest) is True
    assert verify_password("wrong-password", digest) is False
    assert verify_password("correct-horse-battery", "garbage") is False
    # A unique salt means the same password hashes differently each time.
    assert hash_password("correct-horse-battery") != digest


# ------------------------------------------------------------ auth disabled


def test_auth_endpoints_disabled_by_default(client):
    for path, payload in [
        ("/api/auth/register", {"username": "x_1", "password": "correct-horse-battery"}),
        ("/api/auth/login", {"username": "x_1", "password": "correct-horse-battery"}),
    ]:
        r = client.post(path, json=payload)
        assert r.status_code == 400, r.text
    assert client.get("/api/auth/me").status_code == 400


# ------------------------------------------------------------- registration


def test_register_requires_admin_key(auth_client):
    username = _username()
    assert _register(auth_client, username, key=None).status_code == 403
    assert _register(auth_client, username, key="not-the-key").status_code == 403
    body = _register(auth_client, username).json()
    assert body["username"] == username
    assert body["role"] == "clinician"
    assert body["clinician_id"].startswith("CLN-")


def test_register_rejects_weak_and_duplicate(auth_client):
    username = _username()
    assert _register(auth_client, username, password="short").status_code == 422
    assert _register(auth_client, username).status_code == 201
    assert _register(auth_client, username).status_code == 403  # duplicate


def test_password_never_stored_in_plaintext(auth_client):
    username = _username()
    password = "correct-horse-battery"
    _register(auth_client, username, password=password)
    row = auth_client.app.state.repo.db.get_clinician_by_username(username)
    assert password not in row["password_hash"]
    assert row["password_hash"].startswith("pbkdf2_sha256$")
    # Correct password works, wrong one does not.
    assert _login(auth_client, username, password).status_code == 200
    assert _login(auth_client, username, "nope-nope-nope").status_code == 401


# ------------------------------------------------------------------- tokens


def test_login_me_and_token_lifecycle(auth_client):
    username, token = _new_clinician(auth_client)

    me = auth_client.get("/api/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["username"] == username

    # Bad credentials and missing tokens are rejected.
    assert _login(auth_client, username, "wrong-password").status_code == 401
    assert auth_client.get("/api/auth/me").status_code == 401
    assert auth_client.get("/api/auth/me", headers=_auth("not-a-real-token")).status_code == 401

    # Logout revokes the token immediately.
    assert auth_client.post("/api/auth/logout", headers=_auth(token)).json() == {"revoked": True}
    assert auth_client.get("/api/auth/me", headers=_auth(token)).status_code == 401


def test_expired_token_is_rejected(auth_client):
    _, token = _new_clinician(auth_client)
    clinician = auth_client.get("/api/auth/me", headers=_auth(token)).json()
    # Force the stored session to be already expired.
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
    fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()
    auth_client.app.state.repo.db.insert_token(
        fingerprint, clinician["clinician_id"], past, past
    )
    assert auth_client.get("/api/auth/me", headers=_auth(token)).status_code == 401


# ------------------------------------------------------ ownership isolation


def test_patient_data_requires_a_token(auth_client):
    assert auth_client.get("/api/patients").status_code == 401
    assert auth_client.get("/api/patients/GT-001").status_code == 401
    assert auth_client.get("/api/patients/GT-001/history").status_code == 401
    assert auth_client.get("/api/patients/GT-001/digital-twin").status_code == 401
    assert auth_client.get("/api/patients/GT-001/report").status_code == 401
    assert auth_client.get("/api/patients/GT-001/report.pdf").status_code == 401
    assert auth_client.post("/api/patients/GT-001/predict", json={}).status_code == 401


def test_cross_clinician_patient_access_is_denied(auth_client):
    pid = f"OWN-{uuid.uuid4().hex[:8]}"
    _, token_a = _new_clinician(auth_client)
    _, token_b = _new_clinician(auth_client)

    created = auth_client.post("/api/patients", json={**PATIENT, "patient_id": pid}, headers=_auth(token_a))
    assert created.status_code == 201, created.text

    # Owner sees it; other clinician is refused on every patient-scoped route.
    assert auth_client.get(f"/api/patients/{pid}", headers=_auth(token_a)).status_code == 200
    assert auth_client.get(f"/api/patients/{pid}", headers=_auth(token_b)).status_code == 403
    assert auth_client.put(f"/api/patients/{pid}", json={"name": "Hacked"}, headers=_auth(token_b)).status_code == 403
    assert auth_client.get(f"/api/patients/{pid}/history", headers=_auth(token_b)).status_code == 403
    assert auth_client.get(f"/api/patients/{pid}/digital-twin", headers=_auth(token_b)).status_code == 403
    assert auth_client.get(f"/api/patients/{pid}/report", headers=_auth(token_b)).status_code == 403
    assert auth_client.get(f"/api/patients/{pid}/report.pdf", headers=_auth(token_b)).status_code == 403
    assert auth_client.post(f"/api/patients/{pid}/predict", json={}, headers=_auth(token_b)).status_code == 403

    # The owner's list contains the patient; the other clinician's does not.
    ids_a = {p["patient_id"] for p in auth_client.get("/api/patients", headers=_auth(token_a)).json()}
    ids_b = {p["patient_id"] for p in auth_client.get("/api/patients", headers=_auth(token_b)).json()}
    assert pid in ids_a
    assert pid not in ids_b


def test_shared_synthetic_patient_visible_to_all_clinicians(auth_client):
    _, token_a = _new_clinician(auth_client)
    _, token_b = _new_clinician(auth_client)
    # Synthetic demo patients (owner NULL) stay readable by any signed-in clinician.
    assert auth_client.get("/api/patients/GT-001", headers=_auth(token_a)).status_code == 200
    assert auth_client.get("/api/patients/GT-001", headers=_auth(token_b)).status_code == 200
    ids_b = {p["patient_id"] for p in auth_client.get("/api/patients", headers=_auth(token_b)).json()}
    assert "GT-001" in ids_b
