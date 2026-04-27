"""
Lightweight bearer-token auth guard using stdlib HMAC.

Purpose:
    - Prevent role/id spoofing via request body/path parameters.
    - Keep integration simple for existing frontend flow.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import HTTPException, Request, status


DEFAULT_TTL_SECONDS = 60 * 60 * 12  # 12 hours


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _auth_secret() -> bytes:
    # Prefer explicit app secret. Fallback is intentionally deterministic for local dev.
    secret = os.getenv("APP_AUTH_SECRET") or os.getenv("DB_PASSWORD") or "dev-only-secret"
    return secret.encode("utf-8")


def _sign(payload_b64: str) -> str:
    digest = hmac.new(_auth_secret(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64url_encode(digest)


def create_access_token(user_id: str, role: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    now = int(time.time())
    payload = {
        "uid": user_id,
        "role": role,
        "iat": now,
        "exp": now + max(60, int(ttl_seconds)),
    }
    payload_raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_raw)
    signature_b64 = _sign(payload_b64)
    return f"{payload_b64}.{signature_b64}"


def _parse_token(token: str) -> dict[str, Any]:
    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")

    expected_sig = _sign(payload_b64)
    if not hmac.compare_digest(signature_b64, expected_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")

    exp = int(payload.get("exp", 0))
    if exp < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập đã hết hạn")

    uid = payload.get("uid")
    role = payload.get("role")
    if not uid or not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")
    return payload


def authenticate_request(request: Request, allowed_roles: set[str] | None = None) -> dict[str, Any]:
    authz = request.headers.get("Authorization", "").strip()
    if not authz.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Thiếu token xác thực")
    token = authz[7:].strip()
    payload = _parse_token(token)

    if allowed_roles and payload["role"] not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bạn không có quyền truy cập")
    return payload


def ensure_actor_matches(payload: dict[str, Any], claimed_user_id: str, field_name: str = "user_id") -> None:
    if payload["uid"] != claimed_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{field_name} không khớp với phiên đăng nhập",
        )

