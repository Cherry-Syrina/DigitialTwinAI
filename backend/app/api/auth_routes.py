"""Authentication endpoints (active only when ``GLUCOTWIN_AUTH_ENABLED`` is on).

These routes are intentionally explicit rather than decorative:

* ``POST /api/auth/register`` requires the ``X-Admin-Key`` shared secret, so a
  public deployment cannot be farmed for accounts.
* ``POST /api/auth/login`` verifies a PBKDF2 password digest and issues a random
  bearer token (only its SHA-256 fingerprint is stored).
* ``POST /api/auth/logout`` revokes the presented token.
* ``GET  /api/auth/me`` reports the caller's identity.

When authentication is disabled every endpoint answers ``400`` with a clear
message instead of silently doing nothing.
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from .. import config
from ..schemas import api as schemas
from ..services.auth import AuthError

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _ensure_enabled() -> None:
    if not config.auth_enabled():
        raise HTTPException(
            status_code=400,
            detail=(
                "Authentication is disabled. Set GLUCOTWIN_AUTH_ENABLED=1 (and "
                "GLUCOTWIN_ADMIN_KEY) to enable clinician accounts."
            ),
        )


def _bearer_token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Authentication required: send an 'Authorization: Bearer <token>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.strip()


@router.post("/register", response_model=schemas.ClinicianOut, status_code=201)
def register(
    body: schemas.RegisterRequest,
    request: Request,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    """Create a clinician account (requires the admin key)."""
    _ensure_enabled()
    try:
        clinician_id = request.app.state.auth.register(
            body.username, body.password, admin_key=x_admin_key or ""
        )
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return request.app.state.auth.get(clinician_id["clinician_id"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest, request: Request):
    """Exchange username + password for a short-lived bearer token."""
    _ensure_enabled()
    clinician = request.app.state.auth.authenticate(body.username, body.password)
    if clinician is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    issued = request.app.state.auth.issue_token(clinician["clinician_id"])
    return {
        "token": issued["token"],
        "token_type": "bearer",
        "expires_at": issued["expires_at"],
        "clinician": request.app.state.auth.get(clinician["clinician_id"]),
    }


@router.post("/logout", response_model=schemas.RevokeResponse)
def logout(request: Request):
    """Revoke the bearer token that was presented."""
    _ensure_enabled()
    token = _bearer_token(request)
    return {"revoked": request.app.state.auth.revoke(token)}


@router.get("/me", response_model=schemas.ClinicianOut)
def me(request: Request):
    """Return the identity of the authenticated caller."""
    _ensure_enabled()
    clinician = request.app.state.auth.resolve(_bearer_token(request))
    if clinician is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return clinician
