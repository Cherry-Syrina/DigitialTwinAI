"""Optional token authentication and patient-ownership isolation.

Design notes
------------
* **Opt-in.** Everything here is only enforced when ``GLUCOTWIN_AUTH_ENABLED``
  is truthy (see :func:`backend.app.config.auth_enabled`). The default local
  demo therefore keeps working with no setup, while deployments can turn on
  real protection.
* **No recoverable secrets.** Passwords are stored as salted PBKDF2-SHA256
  digests; session tokens are random 256-bit values and only their SHA-256
  fingerprint is persisted, so a leaked database file yields no usable
  password or token.
* **Account creation is closed.** ``/api/auth/register`` requires the
  ``GLUCOTWIN_ADMIN_KEY`` shared secret, so a public deployment cannot be
  mined for free accounts.
* **Least privilege.** Patients carry an ``owner_id``; a clinician may only
  read or mutate patients they own, plus the shared synthetic demo cohort
  (owner ``NULL``).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from .. import config

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 240_000
_SALT_BYTES = 16


class AuthError(ValueError):
    """Raised for invalid credentials or unsupported operations."""


def _hash(password: str, salt: bytes, iterations: int) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return digest.hex()


def hash_password(password: str) -> str:
    """Return a self-describing PBKDF2 digest: ``pbkdf2_sha256$iters$salt$hash``."""
    if not isinstance(password, str) or len(password) < config.MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters.")
    if password.strip() == "":
        raise AuthError("Password must not be blank.")
    salt = secrets.token_bytes(_SALT_BYTES)
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${_hash(password, salt, PBKDF2_ITERATIONS)}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verification of a stored digest."""
    if not password or not encoded:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
        if algorithm != PBKDF2_ALGORITHM:
            return False
        candidate = _hash(password, bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, digest_hex)


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


class AuthService:
    """Clinician accounts + bearer tokens backed by the shared Database."""

    def __init__(self, db):
        self.db = db

    # ----------------------------------------------------------- accounts
    def register(self, username: str, password: str, *, role: str = "clinician", admin_key: str) -> dict:
        expected = config.admin_key()
        if not expected or not hmac.compare_digest(str(admin_key or ""), expected):
            raise AuthError("A valid admin key is required to create clinician accounts.")
        username = (username or "").strip()
        if len(username) < 3:
            raise AuthError("Username must be at least 3 characters.")
        if self.db.get_clinician_by_username(username) is not None:
            raise AuthError(f"Username '{username}' is already taken.")
        clinician_id = f"CLN-{uuid.uuid4().hex[:12]}"
        self.db.insert_clinician(
            {
                "clinician_id": clinician_id,
                "username": username,
                "password_hash": hash_password(password),
                "role": role if role in {"clinician", "admin"} else "clinician",
            }
        )
        return self._public(clinician_id)

    def authenticate(self, username: str, password: str) -> dict | None:
        row = self.db.get_clinician_by_username((username or "").strip())
        if row is None:
            # Spend roughly the same time on unknown users as on known ones.
            verify_password(password or "", hash_password("placeholder-value"))
            return None
        if not verify_password(password or "", row["password_hash"]):
            return None
        return self._public(row["clinician_id"])

    @staticmethod
    def _public(clinician_id: str) -> dict:
        return {"clinician_id": clinician_id}

    def get(self, clinician_id: str) -> dict | None:
        row = self.db.get_clinician(clinician_id)
        if row is None:
            return None
        return {"clinician_id": row["clinician_id"], "username": row["username"], "role": row["role"]}

    # ------------------------------------------------------------- tokens
    def issue_token(self, clinician_id: str) -> dict:
        if self.db.get_clinician(clinician_id) is None:
            raise AuthError("Unknown clinician.")
        token = secrets.token_urlsafe(32)
        expires = _now() + timedelta(hours=config.auth_token_ttl_hours())
        self.db.purge_expired_tokens(_iso(_now()))
        self.db.insert_token(_fingerprint(token), clinician_id, _iso(_now()), _iso(expires))
        return {"token": token, "expires_at": _iso(expires)}

    def resolve(self, token: str) -> dict | None:
        if not token:
            return None
        row = self.db.get_token(_fingerprint(token))
        if row is None:
            return None
        if row["expires_at"] <= _iso(_now()):
            self.db.delete_token(row["token_hash"])
            return None
        return self.get(row["clinician_id"])

    def revoke(self, token: str) -> bool:
        if not token:
            return False
        return self.db.delete_token(_fingerprint(token)) > 0
