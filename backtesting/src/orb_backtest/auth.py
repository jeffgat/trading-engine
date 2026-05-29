"""Clerk-backed API authentication for public dashboard routes."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

_DISABLED_VALUES = {"", "0", "false", "no", "off"}
_PUBLIC_PATHS = {"/health", "/api/health"}
_PUBLIC_GET_PREFIXES = ("/api/backtests/",)
_EMAIL_CACHE_TTL_SECONDS = 300
_email_cache: dict[str, tuple[float, set[str]]] = {}
_jwks_clients: dict[str, Any] = {}


def auth_enabled() -> bool:
    return os.environ.get("BACKEND_AUTH_ENABLED", "0").strip().lower() not in _DISABLED_VALUES


def _split_env(name: str) -> set[str]:
    raw = os.environ.get(name, "")
    return {item.strip().lower() for item in raw.replace(";", ",").split(",") if item.strip()}


def _extract_bearer(value: str | None) -> str:
    if not value:
        return ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()


def _json_error(message: str, status_code: int = 401) -> JSONResponse:
    return JSONResponse(
        {"success": False, "error": {"code": "unauthorized", "message": message}},
        status_code=status_code,
    )


def _emails_from_claims(claims: dict[str, Any]) -> set[str]:
    emails: set[str] = set()
    for key in ("email", "primary_email", "email_address"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            emails.add(value.strip().lower())
    claim_emails = claims.get("email_addresses")
    if isinstance(claim_emails, list):
        for item in claim_emails:
            if isinstance(item, str) and item.strip():
                emails.add(item.strip().lower())
    return emails


def _fetch_clerk_user_emails(user_id: str) -> set[str]:
    now = time.time()
    cached = _email_cache.get(user_id)
    if cached and cached[0] > now:
        return cached[1]

    secret_key = os.environ.get("CLERK_SECRET_KEY", "").strip()
    if not secret_key:
        return set()

    request = urllib.request.Request(
        f"https://api.clerk.com/v1/users/{user_id}",
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Accept": "application/json",
            "User-Agent": "gat-capital-backend/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))

    emails: set[str] = set()
    for item in data.get("email_addresses", []):
        email = item.get("email_address") if isinstance(item, dict) else None
        if isinstance(email, str) and email.strip():
            emails.add(email.strip().lower())

    _email_cache[user_id] = (now + _EMAIL_CACHE_TTL_SECONDS, emails)
    return emails


def _get_jwks_client(jwks_url: str) -> Any:
    from jwt import PyJWKClient

    client = _jwks_clients.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url)
        _jwks_clients[jwks_url] = client
    return client


def _verify_token(token: str) -> tuple[bool, str]:
    if not token:
        return False, "Missing bearer token"

    try:
        import jwt

        unverified_claims = jwt.decode(token, options={"verify_signature": False})
        issuer = str(unverified_claims.get("iss", "")).rstrip("/")
        configured_issuer = os.environ.get("CLERK_ISSUER", "").strip().rstrip("/")
        if not configured_issuer:
            return False, "CLERK_ISSUER is not configured"
        if issuer != configured_issuer:
            return False, "Token issuer is not allowed"
        if not issuer.startswith("https://"):
            return False, "Token issuer is invalid"

        jwks_url = os.environ.get("CLERK_JWKS_URL", "").strip() or f"{issuer}/.well-known/jwks.json"
        signing_key = _get_jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
    except Exception:
        return False, "Invalid bearer token"

    user_id = str(claims.get("sub", ""))
    allowed_user_ids = _split_env("BACKEND_AUTH_ALLOWED_USER_IDS")
    if allowed_user_ids:
        if user_id.lower() in allowed_user_ids:
            return True, ""
        return False, "User is not allowed"

    allowed_emails = _split_env("BACKEND_AUTH_ALLOWED_EMAILS") or _split_env("VITE_ALLOWED_AUTH_EMAIL")
    if allowed_emails:
        emails = _emails_from_claims(claims)
        if user_id and (not emails or emails.isdisjoint(allowed_emails)):
            try:
                emails.update(_fetch_clerk_user_emails(user_id))
            except Exception:
                pass
        if emails.isdisjoint(allowed_emails):
            return False, "Email is not allowed"

    return True, ""


async def authenticate_http_request(request: Request) -> JSONResponse | None:
    is_public_get = request.method == "GET" and any(
        request.url.path.startswith(prefix) for prefix in _PUBLIC_GET_PREFIXES
    )
    if (
        not auth_enabled()
        or request.method == "OPTIONS"
        or request.url.path in _PUBLIC_PATHS
        or is_public_get
    ):
        return None

    ok, message = _verify_token(_extract_bearer(request.headers.get("Authorization")))
    if not ok:
        return _json_error(message)
    return None
