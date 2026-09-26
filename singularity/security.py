#!/usr/bin/env python3
"""
Singularity Gateway Access Control
==================================
One policy shared by the :9000 gateway (ASGI middleware) and the provider workers.

A request is let through when all of these hold:
  1. Cross-site browser requests are refused: an Origin header must be a loopback origin,
     the gateway's own host (any port, e.g. Tavern on :5173), or listed in
     SINGULARITY_ALLOWED_ORIGINS. "Origin: null" (sandboxed artifacts) is refused too.
  2. It is authenticated by ANY of:
       - Authorization: Bearer <gateway key>  (or X-API-Key)      API clients, phones, tunnel
       - the HttpOnly session cookie set by POST /api/auth/login  the playground in a browser
       - trusted local: loopback peer, loopback Host header, no proxy/forwarding headers
         (CLI, Tavern's server, local SDKs; the ngrok tunnel never qualifies)
Static UI assets and the login endpoints are public; everything else needs rule 2.
"""

import hmac
import hashlib
import json
import os
import secrets
import threading
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urlsplit

try:
    from singularity import db
except ImportError:
    import db

SESSION_COOKIE = "singularity_session"
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}
FORWARDING_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "forwarded", "x-real-ip")

PUBLIC_PATHS = {"/", "/logo.svg", "/favicon.ico", "/healthz", "/api/auth/status", "/api/auth/login", "/api/auth/logout"}
PUBLIC_PREFIXES = ("/static/",)
PROTECTED_PREFIXES = ("/static/generated/",)

_KEY_CACHE: Optional[str] = None
_KEY_LOCK = threading.Lock()


# ==============================================================================
# Gateway key & browser session
# ==============================================================================

def get_gateway_key() -> str:
    """Return the gateway API key, generating and storing (encrypted) one on first use."""
    global _KEY_CACHE
    if _KEY_CACHE:
        return _KEY_CACHE
    with _KEY_LOCK:
        if not _KEY_CACHE:
            key = db.get_setting("gateway_key")
            if not key:
                key = "sk-sing-" + secrets.token_urlsafe(32)
                db.set_setting("gateway_key", key)
            _KEY_CACHE = key
    return _KEY_CACHE


def rotate_gateway_key() -> str:
    """Replace the gateway key. Existing browser sessions and API clients must log in again."""
    global _KEY_CACHE
    with _KEY_LOCK:
        key = "sk-sing-" + secrets.token_urlsafe(32)
        db.set_setting("gateway_key", key)
        _KEY_CACHE = key
    return key


def session_token() -> str:
    """Stateless session cookie value; changes whenever the gateway key is rotated."""
    return hmac.new(get_gateway_key().encode(), b"singularity-browser-session-v1", hashlib.sha256).hexdigest()


def check_key(candidate: Optional[str]) -> bool:
    if not candidate:
        return False
    return hmac.compare_digest(candidate.strip().encode(), get_gateway_key().encode())


def is_lan_mode() -> bool:
    return os.getenv("SINGULARITY_LAN", "").lower() in ("1", "true", "yes", "on")


# ==============================================================================
# Request classification
# ==============================================================================

def _hostname(host_header: str) -> str:
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


def _extra_allowed_origins() -> Iterable[str]:
    raw = os.getenv("SINGULARITY_ALLOWED_ORIGINS", "")
    return {o.strip().rstrip("/").lower() for o in raw.split(",") if o.strip()}


def origin_allowed(origin: str, host_header: str) -> bool:
    origin = origin.strip().rstrip("/").lower()
    if not origin or origin == "null":
        return False
    if origin in _extra_allowed_origins():
        return True
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    if parts.hostname in LOOPBACK_NAMES:
        return True
    # Same machine, other port (Tavern on :5173 calling the gateway on :9000 over the LAN).
    return parts.hostname == _hostname(host_header)


def is_loopback_ip(ip: Optional[str]) -> bool:
    if not ip:
        return False
    return ip == "::1" or ip.startswith("127.") or ip == "::ffff:127.0.0.1"


def is_trusted_local(client_ip: Optional[str], headers: Dict[str, str]) -> bool:
    if not is_loopback_ip(client_ip):
        return False
    if _hostname(headers.get("host", "")) not in LOOPBACK_NAMES:
        return False  # DNS-rebinding and tunnelled requests carry a foreign Host header
    return not any(h in headers for h in FORWARDING_HEADERS)


def _bearer(headers: Dict[str, str]) -> Optional[str]:
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return headers.get("x-api-key")


def _cookie(headers: Dict[str, str], name: str) -> Optional[str]:
    for part in headers.get("cookie", "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return None


def is_authenticated(client_ip: Optional[str], headers: Dict[str, str]) -> bool:
    if check_key(_bearer(headers)):
        return True
    cookie = _cookie(headers, SESSION_COOKIE)
    if cookie and hmac.compare_digest(cookie.encode(), session_token().encode()):
        return True
    return is_trusted_local(client_ip, headers)


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    if path.startswith(PROTECTED_PREFIXES):
        return False
    return path.startswith(PUBLIC_PREFIXES)


def evaluate(method: str, path: str, client_ip: Optional[str], headers: Dict[str, str]) -> Tuple[int, str]:
    """Return (0, "") to allow, else (http_status, reason)."""
    origin = headers.get("origin")
    host = headers.get("host", "")
    if method in ("GET", "HEAD") and is_public_path(path):
        # UI assets carry no secrets; sandboxed artifacts load /static/vendor/* cross-origin.
        return 0, ""
    if origin is not None and not origin_allowed(origin, host):
        return 403, "Cross-origin request blocked by Singularity"
    if origin is None and headers.get("sec-fetch-site") == "cross-site":
        return 403, "Cross-site request blocked by Singularity"
    if method == "OPTIONS" or is_public_path(path):
        return 0, ""
    if is_authenticated(client_ip, headers):
        return 0, ""
    return 401, "Singularity gateway key required"


# ==============================================================================
# ASGI middleware (gateway :9000)
# ==============================================================================

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", b"frame-ancestors 'none'"),
]


class SecurityMiddleware:
    """Authentication, origin checks and CORS for the gateway. Replaces Starlette's CORSMiddleware."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        client = scope.get("client")
        client_ip = client[0] if client else None
        method = scope.get("method", "GET")
        path = scope.get("path", "/")

        status, reason = evaluate(method, path, client_ip, headers)
        origin = headers.get("origin")
        cors = []
        if origin and origin_allowed(origin, headers.get("host", "")):
            cors = [
                (b"access-control-allow-origin", origin.encode("latin-1")),
                (b"access-control-allow-credentials", b"true"),
                (b"vary", b"Origin"),
            ]

        if scope["type"] == "websocket":
            if status:
                await send({"type": "websocket.close", "code": 4401 if status == 401 else 4403})
                return
            return await self.app(scope, receive, send)

        if status:
            body = json.dumps({"error": {"message": reason, "type": "auth_error", "code": status}}).encode()
            await send({
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
                + cors + SECURITY_HEADERS,
            })
            await send({"type": "http.response.body", "body": body})
            return

        if method == "OPTIONS" and origin and "access-control-request-method" in headers:
            req_headers = headers.get("access-control-request-headers", "")
            await send({
                "type": "http.response.start",
                "status": 204,
                "headers": cors + [
                    (b"access-control-allow-methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS"),
                    (b"access-control-allow-headers", req_headers.encode("latin-1") or b"*"),
                    (b"access-control-max-age", b"600"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in cors + SECURITY_HEADERS if k not in existing]
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_wrapper)
