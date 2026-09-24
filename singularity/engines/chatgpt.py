#!/usr/bin/env python3
"""
Singularity Native ChatGPT Engine
=================================
Authentic, self-contained multi-account streaming driver for OpenAI / ChatGPT.
Supports:
- 100% self-contained pure Python with zero legacy dependencies
- Pure-Python Sentinel Proof-of-Work (PoW) and Turnstile solver inline
- High-performance browser TLS fingerprint impersonation via curl_cffi
- Account pool rotation across SQLite vault credentials with automatic JWT / Session token refresh
- Real-time OpenAI-compatible SSE streaming chunks and full completion formats
- Fully compatible with Windows, macOS, Linux, and Android/Termux
"""

import asyncio
import base64
import hashlib
import json
import os
import random
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple, Union

SCRIPT_DIR = Path(__file__).resolve().parent
STATIC_GEN_DIR = SCRIPT_DIR.parent / "static" / "generated"

try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession
    from curl_cffi.curl import CurlOpt
    HAVE_CURL_CFFI = True
except ImportError:
    CurlAsyncSession = None  # type: ignore
    CurlOpt = None  # type: ignore
    HAVE_CURL_CFFI = False

import httpx

try:
    from singularity import db, providers
    from singularity.providers import get_provider_host
    from singularity import personas
except ImportError:
    import db
    import providers
    from providers import get_provider_host
    try:
        import personas
    except ImportError:
        personas = None


# -------------------------------------------------------------------
# Constants & Model Aliases
# -------------------------------------------------------------------

DEFAULT_POW_SCRIPT = "https://chatgpt.com/backend-api/sentinel/sdk.js"
DEFAULT_DATA_BUILD = "prod-d37e1fc55745f08c94d6b79feb2f3743ea88447d"
DEFAULT_CLIENT_VERSION = "prod-a194cd50d4416d3c0b47c740f206b12ce60f5887"
DEFAULT_CLIENT_BUILD_NUMBER = "6708908"

CORES = [8, 16, 24, 32]
DOCUMENT_KEYS = ["__reactContainer$fzelfjyxej8", "_reactListening5dehydibo78", "location"]
SCREEN_RESOLUTIONS = [[1920, 1080], [1440, 900], [2560, 1440], [3840, 2160]]

TEXT_MODEL_ALIASES = {
    "sol": "gpt-5-6",
    "gpt-5.6-sol": "gpt-5-6",
    "gpt-5-6-sol": "gpt-5-6",
    "gpt-5.6": "gpt-5-6",
    "terra": "gpt-5-6-mini",
    "gpt-5.6-terra": "gpt-5-6-mini",
    "gpt-5-6-terra": "gpt-5-6-mini",
    "luna": "gpt-5-6-t-mini",
    "gpt-5.6-luna": "gpt-5-6-t-mini",
    "gpt-5-6-luna": "gpt-5-6-t-mini",
    "gpt-6-astra": "gpt-5-6",
    "gpt-6": "gpt-5-6",
    "astra": "gpt-5-6",
    "gpt-image-2.5-flare": "auto",
    "gpt-image-2.5-sunburst": "auto",
    "gpt-image-2": "auto",
    "image-2.5-flare": "auto",
    "image-2.5-sunburst": "auto",
    "image-2": "auto",
    "flare": "auto",
    "sunburst": "auto",
    "default": "auto",
    "chatgpt-default": "auto",
}

_BOOTSTRAP_CACHE: Dict[str, Any] = {
    "data_build": DEFAULT_DATA_BUILD,
    "script_sources": [DEFAULT_POW_SCRIPT],
    "ts": 0.0,
}
_BOOTSTRAP_LOCK = asyncio.Lock()

_ACCESS_TOKEN_CACHE: Dict[str, Tuple[str, float]] = {}
_CACHE_LOCK = asyncio.Lock()
_ACCOUNT_ROTATION_INDEX = 0
_ROTATION_LOCK = asyncio.Lock()


# -------------------------------------------------------------------
# Embedded Sentinel & Proof-of-Work Solver
# -------------------------------------------------------------------

class ScriptSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.script_sources: List[str] = []
        self.data_build = ""

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag != "script":
            return
        attrs_dict = dict(attrs)
        src = attrs_dict.get("src")
        if not src:
            return
        self.script_sources.append(src)
        match = re.search(r"c/[^/]*/_", src)
        if match:
            self.data_build = match.group(0)


def parse_pow_resources(html_content: str) -> Tuple[List[str], str]:
    """Extract dynamic Sentinel script references and build ID from web HTML."""
    parser = ScriptSrcParser()
    try:
        parser.feed(html_content)
    except Exception:
        pass
    script_sources = parser.script_sources or [DEFAULT_POW_SCRIPT]
    data_build = parser.data_build
    if not data_build:
        match = re.search(r'<html[^>]*data-build="([^"]*)"', html_content)
        if match:
            data_build = match.group(1)
    return script_sources, data_build or DEFAULT_DATA_BUILD


def _legacy_parse_time() -> str:
    now = datetime.now(timezone(timedelta(hours=-5)))
    return now.strftime("%a %b %d %Y %H:%M:%S") + " GMT-0500 (Eastern Standard Time)"


def build_pow_config(
    user_agent: str,
    script_sources: Optional[Sequence[str]] = None,
    data_build: str = "",
) -> List[Any]:
    navigator_key = random.choice([
        "registerProtocolHandler−function registerProtocolHandler() { [native code] }",
        "storage−[object StorageManager]",
        "locks−[object LockManager]",
        "appCodeName−Mozilla",
        "permissions−[object Permissions]",
        "share−function share() { [native code] }",
        "webdriver−false",
        "vendor−Google Inc.",
        "cookieEnabled−true",
        "product−Gecko",
        "onLine−true",
        "hardwareConcurrency−32",
    ])
    window_key = random.choice([
        "0", "window", "self", "document", "name", "location", "crypto",
        "performance", "indexedDB", "sessionStorage", "localStorage",
    ])
    script_source = random.choice(list(script_sources)) if script_sources else DEFAULT_POW_SCRIPT
    return [
        sum(random.choices(SCREEN_RESOLUTIONS, k=1)[0]),
        _legacy_parse_time(),
        4294705152,
        1,
        user_agent,
        script_source,
        data_build or DEFAULT_DATA_BUILD,
        "en-US",
        "en-US,es-US,en,es",
        random.random(),
        navigator_key,
        random.choice(DOCUMENT_KEYS),
        window_key,
        time.perf_counter() * 1000,
        str(uuid.uuid4()),
        "",
        random.choice(CORES),
        time.time() * 1000 - (time.perf_counter() * 1000),
        0, 0, 0, 0, 0, 0,
        0,
    ]


def _pow_generate(seed: str, difficulty: str, config: List[Any], limit: int = 500000) -> Tuple[str, bool]:
    """Solve SHA3-512 target-hash challenge for proof token."""
    target = bytes.fromhex(difficulty)
    diff_len = len(difficulty) // 2
    seed_bytes = seed.encode()
    static_1 = (json.dumps(config[:3], separators=(",", ":"), ensure_ascii=False)[:-1] + ",").encode()
    static_2 = ("," + json.dumps(config[4:9], separators=(",", ":"), ensure_ascii=False)[1:-1] + ",").encode()
    static_3 = ("," + json.dumps(config[10:], separators=(",", ":"), ensure_ascii=False)[1:]).encode()
    for i in range(limit):
        final_json = static_1 + str(i).encode() + static_2 + str(i >> 1).encode() + static_3
        encoded = base64.b64encode(final_json)
        digest = hashlib.sha3_512(seed_bytes + encoded).digest()
        if digest[:diff_len] <= target:
            return encoded.decode(), True
    fallback = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D" + base64.b64encode(f'"{seed}"'.encode()).decode()
    return fallback, False


def build_legacy_requirements_token(
    user_agent: str,
    script_sources: Optional[Sequence[str]] = None,
    data_build: str = "",
) -> str:
    config = build_pow_config(user_agent, script_sources=script_sources, data_build=data_build)
    return "gAAAAAC" + base64.b64encode(
        json.dumps(config, separators=(",", ":"), ensure_ascii=False).encode()
    ).decode()


def build_proof_token(
    seed: str,
    difficulty: str,
    user_agent: str,
    script_sources: Optional[Sequence[str]] = None,
    data_build: str = "",
) -> str:
    config = build_pow_config(user_agent, script_sources=script_sources, data_build=data_build)
    answer, solved = _pow_generate(seed, difficulty, config)
    if not solved:
        raise RuntimeError(f"failed to solve proof token: difficulty={difficulty}")
    return "gAAAAAB" + answer


# -------------------------------------------------------------------
# Embedded Turnstile Solver
# -------------------------------------------------------------------

class OrderedMap:
    def __init__(self) -> None:
        self.keys: List[str] = []
        self.values: Dict[str, Any] = {}

    def add(self, key: str, value: Any) -> None:
        if key not in self.values:
            self.keys.append(key)
        self.values[key] = value


def _turnstile_to_str(value: Any) -> str:
    if value is None:
        return "undefined"
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        special = {
            "window.Math": "[object Math]",
            "window.Reflect": "[object Reflect]",
            "window.performance": "[object Performance]",
            "window.localStorage": "[object Storage]",
            "window.Object": "function Object() { [native code] }",
            "window.Reflect.set": "function set() { [native code] }",
            "window.performance.now": "function () { [native code] }",
            "window.Object.create": "function create() { [native code] }",
            "window.Object.keys": "function keys() { [native code] }",
            "window.Math.random": "function random() { [native code] }",
        }
        return special.get(value, value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ",".join(value)
    return str(value)


def _xor_string(text: str, key: str) -> str:
    if not key:
        return text
    return "".join(chr(ord(ch) ^ ord(key[i % len(key)])) for i, ch in enumerate(text))


def solve_turnstile_token(dx: str, p: str) -> Optional[str]:
    """Execute dynamic Turnstile virtual machine instructions."""
    try:
        decoded = base64.b64decode(dx).decode()
        token_list = json.loads(_xor_string(decoded, p))
    except Exception:
        return None

    process_map: Dict[Any, Any] = {}
    start_time = time.time()
    result = ""

    def func_1(e: float, t: float) -> None:
        process_map[e] = _xor_string(_turnstile_to_str(process_map[e]), _turnstile_to_str(process_map[t]))

    def func_2(e: float, t: Any) -> None:
        process_map[e] = t

    def func_3(e: str) -> None:
        nonlocal result
        result = base64.b64encode(e.encode()).decode()

    def func_5(e: float, t: float) -> None:
        current = process_map[e]
        incoming = process_map[t]
        if isinstance(current, (list, tuple)):
            process_map[e] = list(current) + [incoming]
            return
        if isinstance(current, (str, float)) or isinstance(incoming, (str, float)):
            process_map[e] = _turnstile_to_str(current) + _turnstile_to_str(incoming)
            return
        process_map[e] = "NaN"

    def func_6(e: float, t: float, n: float) -> None:
        tv = process_map[t]
        nv = process_map[n]
        if isinstance(tv, str) and isinstance(nv, str):
            value = f"{tv}.{nv}"
            process_map[e] = "https://chatgpt.com/" if value == "window.document.location" else value

    def func_7(e: float, *args: float) -> None:
        target = process_map[e]
        values = [process_map[arg] for arg in args]
        if isinstance(target, str) and target == "window.Reflect.set":
            obj, key_name, val = values
            obj.add(str(key_name), val)
        elif callable(target):
            target(*values)

    def func_8(e: float, t: float) -> None:
        process_map[e] = process_map[t]

    def func_14(e: float, t: float) -> None:
        process_map[e] = json.loads(process_map[t])

    def func_15(e: float, t: float) -> None:
        process_map[e] = json.dumps(process_map[t])

    def func_17(e: float, t: float, *args: float) -> None:
        call_args = [process_map[arg] for arg in args]
        target = process_map[t]
        if target == "window.performance.now":
            elapsed_ns = time.time_ns() - int(start_time * 1e9)
            process_map[e] = (elapsed_ns + random.random()) / 1e6
        elif target == "window.Object.create":
            process_map[e] = OrderedMap()
        elif target == "window.Object.keys":
            if call_args and call_args[0] == "window.localStorage":
                process_map[e] = [
                    "STATSIG_LOCAL_STORAGE_INTERNAL_STORE_V4",
                    "STATSIG_LOCAL_STORAGE_STABLE_ID",
                    "client-correlated-secret",
                    "oai/apps/capExpiresAt",
                    "oai-did",
                    "STATSIG_LOCAL_STORAGE_LOGGING_REQUEST",
                    "UiState.isNavigationCollapsed.1",
                ]
        elif target == "window.Math.random":
            process_map[e] = random.random()
        elif callable(target):
            process_map[e] = target(*call_args)

    def func_18(e: float) -> None:
        process_map[e] = base64.b64decode(_turnstile_to_str(process_map[e])).decode()

    def func_19(e: float) -> None:
        process_map[e] = base64.b64encode(_turnstile_to_str(process_map[e]).encode()).decode()

    def func_20(e: float, t: float, n: float, *args: float) -> None:
        if process_map[e] == process_map[t]:
            target = process_map[n]
            if callable(target):
                target(*[process_map[arg] for arg in args])

    def func_21(*_: Any) -> None:
        return

    def func_23(e: float, t: float, *args: float) -> None:
        if process_map[e] is not None and callable(process_map[t]):
            process_map[t](*args)

    def func_24(e: float, t: float, n: float) -> None:
        tv = process_map[t]
        nv = process_map[n]
        if isinstance(tv, str) and isinstance(nv, str):
            process_map[e] = f"{tv}.{nv}"

    process_map.update({
        1: func_1, 2: func_2, 3: func_3, 5: func_5, 6: func_6, 7: func_7,
        8: func_8, 9: token_list, 10: "window", 14: func_14, 15: func_15,
        16: p, 17: func_17, 18: func_18, 19: func_19, 20: func_20,
        21: func_21, 23: func_23, 24: func_24,
    })

    for token in token_list:
        try:
            fn = process_map.get(token[0])
            if callable(fn):
                fn(*token[1:])
        except Exception:
            continue
    return result or None


# -------------------------------------------------------------------
# Account & Credential Management
# -------------------------------------------------------------------

def _decode_jwt(token_str: str) -> Optional[Dict[str, Any]]:
    """Decode JWT payload without cryptographic verification."""
    try:
        parts = token_str.strip().split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            decoded_bytes = base64.urlsafe_b64decode(payload_b64)
            return json.loads(decoded_bytes.decode("utf-8", errors="ignore"))
    except Exception:
        pass
    return None


def extract_chatgpt_credentials(raw_token: str) -> Dict[str, Any]:
    """Parse JSON dump or raw string into structured credentials."""
    raw = raw_token.strip()
    if raw.startswith("{") or raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                user = data.get("user", {}) if isinstance(data.get("user"), dict) else {}
                email = user.get("email") or data.get("email") or ""
                name = user.get("name") or data.get("name") or ""
                access_token = data.get("accessToken") or data.get("access_token") or ""
                session_token = data.get("sessionToken") or data.get("session_token") or ""
                plan = data.get("account", {}).get("planType") or data.get("plan_type") or data.get("type") or "free"

                if not access_token and "token" in data:
                    access_token = data["token"]

                return {
                    "email": email,
                    "name": name,
                    "access_token": access_token,
                    "session_token": session_token,
                    "plan": plan,
                    "proxy": data.get("proxy", ""),
                }
        except Exception:
            pass

    # Raw string (either JWT access token or session token)
    jwt = _decode_jwt(raw)
    if jwt:
        email = jwt.get("https://api.openai.com/profile", {}).get("email") or jwt.get("email") or ""
        name = jwt.get("https://api.openai.com/profile", {}).get("name") or ""
        return {
            "email": email,
            "name": name,
            "access_token": raw,
            "session_token": "",
            "plan": "free",
            "proxy": "",
        }

    return {
        "email": "",
        "name": "",
        "access_token": "",
        "session_token": raw,
        "plan": "free",
        "proxy": "",
    }


async def get_valid_access_token(
    account: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Ensure active access token for account, auto-refreshing via session token if expired.
    Uses curl_cffi with browser impersonation to bypass Cloudflare.
    Returns (access_token, account_identifier).
    """
    raw_token = account.get("token", "")
    ident = account.get("identifier") or account.get("name") or str(account.get("id", "chatgpt"))
    creds = extract_chatgpt_credentials(raw_token)

    access_token = creds.get("access_token", "")
    session_token = creds.get("session_token", "")
    now = time.time()

    # 1. Check in-memory cache first
    async with _CACHE_LOCK:
        cached = _ACCESS_TOKEN_CACHE.get(ident)
        if cached and now < cached[1] - 120:
            return cached[0], ident

    # 2. Check if access token is still valid
    if access_token:
        jwt = _decode_jwt(access_token)
        if jwt:
            exp = float(jwt.get("exp", now + 3600))
            if now < exp - 120:
                async with _CACHE_LOCK:
                    _ACCESS_TOKEN_CACHE[ident] = (access_token, exp)
                return access_token, ident

    # 3. If no session token, return current access token or raw string
    if not session_token:
        return access_token or raw_token, ident

    # 4. Refresh via ChatGPT NextAuth session endpoint using browser TLS impersonation
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
    )
    headers = {
        "User-Agent": user_agent,
        "Cookie": f"__Secure-next-auth.session-token={session_token}",
        "Accept": "application/json",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
    }

    if HAVE_CURL_CFFI:
        try:
            async with CurlAsyncSession(
                impersonate="chrome120",
                curl_options={CurlOpt.IPRESOLVE: 1} if CurlOpt else {},
                headers=headers,
            ) as session:
                resp = await session.get("https://chatgpt.com/api/auth/session", timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    new_at = data.get("accessToken")
                    if new_at:
                        jwt = _decode_jwt(new_at)
                        exp = float(jwt.get("exp", now + 3600)) if jwt else now + 3600
                        async with _CACHE_LOCK:
                            _ACCESS_TOKEN_CACHE[ident] = (new_at, exp)
                        return new_at, ident
        except Exception:
            pass
    else:
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get("https://chatgpt.com/api/auth/session", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    new_at = data.get("accessToken")
                    if new_at:
                        jwt = _decode_jwt(new_at)
                        exp = float(jwt.get("exp", now + 3600)) if jwt else now + 3600
                        async with _CACHE_LOCK:
                            _ACCESS_TOKEN_CACHE[ident] = (new_at, exp)
                        return new_at, ident
        except Exception:
            pass

    return access_token or raw_token, ident


async def get_next_account(accounts: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Rotate through available accounts in SQLite vault."""
    global _ACCOUNT_ROTATION_INDEX
    if not accounts:
        try:
            accounts = db.get_accounts("chatgpt")
        except Exception:
            accounts = []

    if not accounts:
        return None

    async with _ROTATION_LOCK:
        idx = _ACCOUNT_ROTATION_INDEX % len(accounts)
        _ACCOUNT_ROTATION_INDEX += 1
        return accounts[idx]


# -------------------------------------------------------------------
# Format Helpers & SSE Event Parsers
# -------------------------------------------------------------------

def _format_messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    """Flatten OpenAI messages array into conversational prompt."""
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            sub_txt = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    sub_txt.append(item.get("text", ""))
                elif isinstance(item, str):
                    sub_txt.append(item)
            content = " ".join(sub_txt)
        content_str = str(content).strip()
        if not content_str:
            continue
        if role == "system":
            parts.append(f"Instructions: {content_str}")
        elif role == "assistant":
            parts.append(f"Assistant: {content_str}")
        else:
            parts.append(f"User: {content_str}")
    return "\n\n".join(parts) if parts else "Hello"


def _api_messages_to_conversation_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI messages array into ChatGPT web conversation format."""
    conv_messages = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            sub_txt = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    sub_txt.append(item.get("text", ""))
                elif isinstance(item, str):
                    sub_txt.append(item)
            content = " ".join(sub_txt)
        text_content = str(content).strip()
        if not text_content:
            continue
        conv_messages.append({
            "id": str(uuid.uuid4()),
            "author": {"role": role},
            "content": {"content_type": "text", "parts": [text_content]},
            "metadata": {},
        })
    if not conv_messages:
        conv_messages.append({
            "id": str(uuid.uuid4()),
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": ["Hello"]},
            "metadata": {},
        })
    return conv_messages


def is_thought_message(message: Dict[str, Any]) -> bool:
    """Filter to internal thinking / reasoning chain-of-thought messages."""
    if not isinstance(message, dict):
        return False
    channel = str(message.get("channel") or "").strip().lower()
    if channel in ("thought", "analysis", "commentary"):
        return True
    content = message.get("content") or {}
    if isinstance(content, dict):
        c_type = str(content.get("content_type") or "").strip().lower()
        if c_type in ("thought", "reasoning", "thinking"):
            return True
    return False


def thought_message_text(message: Dict[str, Any]) -> str:
    """Extract assistant reasoning / chain-of-thought text."""
    content = message.get("content") or {}
    parts = content.get("parts") or []
    if isinstance(parts, list) and parts:
        text = "".join(part for part in parts if isinstance(part, str))
        if text:
            return text
    text_field = str(content.get("text") or "")
    if text_field:
        return text_field
    return ""


def is_visible_assistant_message(message: Dict[str, Any]) -> bool:
    """Filter to only assistant responses intended for user visibility."""
    if not isinstance(message, dict):
        return False
    author = message.get("author")
    if not isinstance(author, dict):
        return False
    role = str(author.get("role") or "").strip().lower()
    if role != "assistant":
        return False
    metadata = message.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("is_visually_hidden_from_conversation") is True:
        return False
    recipient = str(message.get("recipient") or "").strip().lower()
    if recipient and recipient != "all":
        return False
    channel = str(message.get("channel") or "").strip().lower()
    if channel and channel != "final":
        return False
    return True


def assistant_message_text(message: Dict[str, Any]) -> str:
    """Extract assistant textual content from payload."""
    content = message.get("content") or {}
    parts = content.get("parts") or []
    if isinstance(parts, list) and parts:
        text = "".join(part for part in parts if isinstance(part, str))
        if text:
            return text
    text_field = str(content.get("text") or "")
    if text_field:
        return text_field
    return ""


def assistant_history_text(messages: Sequence[Dict[str, Any]]) -> str:
    """Extract concatenated assistant content from prior conversational turns."""
    texts = []
    for m in messages:
        if m.get("role") == "assistant":
            c = m.get("content", "")
            if isinstance(c, str):
                texts.append(c)
            elif isinstance(c, list):
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "text":
                        texts.append(str(part.get("text", "")))
                    elif isinstance(part, str):
                        texts.append(part)
    return "".join(texts).strip()


def assistant_history_messages(messages: Sequence[Dict[str, Any]]) -> List[str]:
    """Extract individual assistant messages from prior conversational turns."""
    msgs = []
    for m in messages:
        if m.get("role") == "assistant":
            c = m.get("content", "")
            if isinstance(c, str) and c.strip():
                msgs.append(c.strip())
            elif isinstance(c, list):
                sub = []
                for part in c:
                    if isinstance(part, dict) and part.get("type") == "text":
                        sub.append(str(part.get("text", "")))
                    elif isinstance(part, str):
                        sub.append(part)
                combined = "".join(sub).strip()
                if combined:
                    msgs.append(combined)
    return msgs


def strip_history(text: str, history_text: str = "", history_messages: Optional[List[str]] = None) -> str:
    """Strip prior conversation history prefixes that ChatGPT web echoes in the assistant output."""
    if not text:
        return ""

    s_text = text.strip()
    if not s_text:
        return ""

    # Build candidates list
    candidates: List[str] = []
    if history_text:
        ht = history_text.strip()
        if ht and ht not in candidates:
            candidates.append(ht)
    if history_messages:
        for hm in reversed(history_messages):
            hms = hm.strip()
            if hms and hms not in candidates:
                candidates.append(hms)

    # In-flight check: if incoming stream text is currently just an initial prefix of any history candidate,
    # suppress output until we have gotten past the echoed history turn.
    for cand in candidates:
        if cand.startswith(s_text):
            return ""

    # Iteratively strip matched history from the beginning of text
    changed = True
    while changed:
        changed = False
        cur_lstrip = text.lstrip()
        for cand in candidates:
            if cur_lstrip.startswith(cand):
                text = cur_lstrip[len(cand):].lstrip()
                changed = True
                break

    return text


def sanitize_output_text(text: str) -> str:
    """Remove ChatGPT web internal citation tokens (※...※) and PUA tags (message_reaction...)."""
    if not text:
        return ""
    # Strip citation sequence starting with ※ up to whitespace or end-of-string
    text = re.sub(r"※[^\s]*", "", text)
    # Strip residual citation words (e.g. citeturn0search2, turn0news10)
    text = re.sub(r"\bcite[a-zA-Z0-9_]*turn[a-zA-Z0-9_]*\b", "", text)
    text = re.sub(r"\bturn\d+[a-zA-Z0-9_]*\b", "", text)
    # Strip OpenAI private unicode PUA markers and message reactions (e.g. message_reaction👍)
    text = re.sub(r"[\ue200-\ue20f]message_reaction[\ue200-\ue20f][^\ue200-\ue20f]*[\ue200-\ue20f]", "", text)
    text = re.sub(r"[\ue200-\ue20f]", "", text)
    return text


def apply_text_patch(event: Dict[str, Any], current_text: str = "") -> str:
    """Handle delta text patch events emitted by newer ChatGPT streaming backends."""
    if event.get("p") == "/message/content/parts/0":
        v = event.get("v")
        if isinstance(v, str):
            op = event.get("o")
            if op == "append":
                return current_text + v
            elif op == "replace":
                return v
            return current_text + v

    operations = event.get("v")
    if isinstance(operations, str) and current_text and not event.get("p") and not event.get("o"):
        return current_text + operations

    if event.get("o") == "patch" and isinstance(operations, list):
        text = current_text
        for item in operations:
            if isinstance(item, dict):
                text = apply_text_patch(item, text)
        return text

    if isinstance(operations, list):
        text = current_text
        for item in operations:
            if isinstance(item, dict):
                text = apply_text_patch(item, text)
        return text

    return current_text


# -------------------------------------------------------------------
# Sentinel Pre-Warm & Challenge Resolver
# -------------------------------------------------------------------

async def _get_chat_requirements(
    session: Any,
    access_token: str,
    user_agent: str,
    script_sources: List[str],
    data_build: str,
) -> Dict[str, str]:
    """
    Execute Sentinel prepare + PoW/Turnstile solve + finalize workflow.
    Returns dictionary with required tokens: {"token": ..., "proof_token": ..., "turnstile_token": ..., "so_token": ...}.
    """
    base_path = "/backend-api/sentinel/chat-requirements" if access_token else "/backend-anon/sentinel/chat-requirements"
    p_token = build_legacy_requirements_token(user_agent, script_sources=script_sources, data_build=data_build)

    prepare_url = f"https://chatgpt.com{base_path}/prepare"
    prep_headers = {
        "Content-Type": "application/json",
        "X-OpenAI-Target-Path": f"{base_path}/prepare",
    }
    if access_token:
        prep_headers["Authorization"] = f"Bearer {access_token}"

    prep_resp = await session.post(prepare_url, headers=prep_headers, json={"p": p_token}, timeout=15.0)
    if prep_resp.status_code != 200:
        raise RuntimeError(f"Sentinel prepare failed with HTTP {prep_resp.status_code}: {prep_resp.text[:120]}")

    prep_data = prep_resp.json()
    prepare_token = prep_data.get("prepare_token", "")

    proof_token = ""
    proof_info = prep_data.get("proofofwork") or {}
    if proof_info.get("required"):
        proof_token = build_proof_token(
            seed=proof_info.get("seed", ""),
            difficulty=proof_info.get("difficulty", ""),
            user_agent=user_agent,
            script_sources=script_sources,
            data_build=data_build,
        )

    turnstile_token = ""
    turnstile_info = prep_data.get("turnstile") or {}
    if turnstile_info.get("required") and turnstile_info.get("dx"):
        turnstile_token = solve_turnstile_token(turnstile_info["dx"], p_token) or ""

    finalize_url = f"https://chatgpt.com{base_path}/finalize"
    fin_headers = {
        "Content-Type": "application/json",
        "X-OpenAI-Target-Path": f"{base_path}/finalize",
    }
    if access_token:
        fin_headers["Authorization"] = f"Bearer {access_token}"

    fin_resp = await session.post(
        finalize_url,
        headers=fin_headers,
        json={
            "prepare_token": prepare_token,
            "proof_token": proof_token,
            "turnstile_token": turnstile_token,
        },
        timeout=15.0,
    )
    if fin_resp.status_code != 200:
        raise RuntimeError(f"Sentinel finalize failed with HTTP {fin_resp.status_code}: {fin_resp.text[:120]}")

    fin_data = fin_resp.json()
    token = fin_data.get("token", "")
    if not token:
        raise RuntimeError(f"Missing Sentinel requirements token in response: {fin_data}")

    return {
        "token": token,
        "proof_token": proof_token,
        "turnstile_token": turnstile_token,
        "so_token": fin_data.get("so_token", ""),
    }


# -------------------------------------------------------------------
# Universal Streaming Inference Engine
# -------------------------------------------------------------------

async def stream_chatgpt_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    stream: bool = True,
    simulate: bool = False,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Universal streaming inference engine for ChatGPT.
    1. Checks Device Simulation Mode.
    2. Rotates across SQLite credential vault accounts.
    3. Solves Sentinel PoW and Turnstile challenges automatically.
    4. Executes direct Web2API reverse-proxy stream with browser TLS impersonation.
    Yields standard OpenAI-compatible SSE chunks.
    """
    chat_id = f"chatcmpl-chatgpt-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    # 1. Device Simulation Mode
    if simulate or providers.is_simulation_active() or os.getenv("SINGULARITY_SIMULATE", "0") in ("1", "true", "yes", "on"):
        prompt_preview = _format_messages_to_prompt(messages)
        sim_response = (
            f"Hello from Singularity's native ChatGPT engine! "
            f"Currently running simulated response for '{model}'. "
            f"All model routing, multi-account rotation, and Sentinel challenge solvers are active."
        )
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        for word in sim_response.split(" "):
            yield {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": word + " "}, "finish_reason": None}],
            }
            await asyncio.sleep(0.02)
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        return

    # 2. Account Acquisition & Rotation
    if accounts is None:
        try:
            accounts = db.get_accounts("chatgpt")
        except Exception:
            accounts = []

    if not accounts:
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": (
                        "Error: No active ChatGPT credentials found in Singularity vault.\n\n"
                        "Please add your ChatGPT session token or credentials dump in the Control Center "
                        "(http://localhost:9000) or run: './singular import <path_or_json>'."
                    )
                },
                "finish_reason": "error",
            }],
        }
        return

    # Map target model slug & check persona mapping (e.g. GPT-6 Astra)
    model_lower = model.lower().strip()
    is_image_model = any(k in model_lower for k in ("image", "flare", "sunburst", "dalle", "t2i"))
    persona_cfg = personas.get_persona_config(model) if personas else None
    if persona_cfg:
        messages = personas.inject_persona_messages(messages, persona_cfg)
        target_model_slug = persona_cfg.backend_model
    elif is_image_model:
        target_model_slug = "auto"
    else:
        target_model_slug = TEXT_MODEL_ALIASES.get(model_lower, model)
    if target_model_slug in ("default", "chatgpt-default", "auto"):
        target_model_slug = "auto"

    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
    )

    # 3. Attempt Execution across Vault Accounts
    last_error_msg = ""
    max_attempts = min(len(accounts), 3)

    for attempt in range(max_attempts):
        account = await get_next_account(accounts)
        if not account:
            break

        token, account_ident = await get_valid_access_token(account)
        if not token:
            continue

        device_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        base_headers = {
            "User-Agent": user_agent,
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/",
            "Accept-Language": "en-US,en;q=0.9",
            "OAI-Device-Id": device_id,
            "OAI-Session-Id": session_id,
            "Sec-Ch-Ua": '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Authorization": f"Bearer {token}",
        }

        # Check / update bootstrap cache
        async with _BOOTSTRAP_LOCK:
            now = time.time()
            data_build = _BOOTSTRAP_CACHE["data_build"]
            script_sources = _BOOTSTRAP_CACHE["script_sources"]
            if now - _BOOTSTRAP_CACHE["ts"] > 600:
                try:
                    if HAVE_CURL_CFFI:
                        async with CurlAsyncSession(
                            impersonate="chrome120",
                            curl_options={CurlOpt.IPRESOLVE: 1} if CurlOpt else {},
                            headers=base_headers,
                        ) as b_sess:
                            b_resp = await b_sess.get("https://chatgpt.com/", timeout=4.0)
                            if b_resp.status_code == 200:
                                parsed_scripts, parsed_build = parse_pow_resources(b_resp.text)
                                _BOOTSTRAP_CACHE["script_sources"] = parsed_scripts
                                _BOOTSTRAP_CACHE["data_build"] = parsed_build
                                _BOOTSTRAP_CACHE["ts"] = now
                                data_build = parsed_build
                                script_sources = parsed_scripts
                except Exception:
                    pass

        # Execute conversation with curl_cffi AsyncSession
        if HAVE_CURL_CFFI:
            try:
                async with CurlAsyncSession(
                    impersonate="chrome120",
                    curl_options={CurlOpt.IPRESOLVE: 1} if CurlOpt else {},
                    headers=base_headers,
                ) as sess:
                    # Solve Sentinel challenges
                    try:
                        sentinel_reqs = await _get_chat_requirements(
                            sess,
                            access_token=token,
                            user_agent=user_agent,
                            script_sources=script_sources,
                            data_build=data_build,
                        )
                    except Exception as sent_err:
                        last_error_msg = f"Sentinel handshake error: {str(sent_err)}"
                        continue

                    # Construct conversation payload
                    conv_path = "/backend-api/conversation"
                    conv_payload = {
                        "action": "next",
                        "messages": _api_messages_to_conversation_messages(messages),
                        "model": target_model_slug,
                        "parent_message_id": str(uuid.uuid4()),
                        "timezone_offset_min": -330,
                        "history_and_training_disabled": not is_image_model,
                        "conversation_mode": {"kind": "primary_assistant"},
                    }
                    if is_image_model:
                        conv_payload["system_hints"] = ["picture_v2"]

                    conv_headers = {
                        "Accept": "text/event-stream",
                        "Content-Type": "application/json",
                        "OpenAI-Sentinel-Chat-Requirements-Token": sentinel_reqs["token"],
                        "X-OpenAI-Target-Path": conv_path,
                        "X-OpenAI-Target-Route": conv_path,
                    }
                    if sentinel_reqs.get("proof_token"):
                        conv_headers["OpenAI-Sentinel-Proof-Token"] = sentinel_reqs["proof_token"]
                    if sentinel_reqs.get("turnstile_token"):
                        conv_headers["OpenAI-Sentinel-Turnstile-Token"] = sentinel_reqs["turnstile_token"]
                    if sentinel_reqs.get("so_token"):
                        conv_headers["OpenAI-Sentinel-SO-Token"] = sentinel_reqs["so_token"]

                    resp = await sess.post(
                        "https://chatgpt.com" + conv_path,
                        headers=conv_headers,
                        json=conv_payload,
                        stream=True,
                        timeout=120.0,
                    )

                    if resp.status_code in (401, 403):
                        async with _CACHE_LOCK:
                            _ACCESS_TOKEN_CACHE.pop(account_ident, None)
                        last_error_msg = f"HTTP {resp.status_code} on account {account_ident}"
                        continue

                    if resp.status_code >= 400:
                        err_text = ""
                        try:
                            err_text = resp.text[:200]
                        except Exception:
                            pass
                        last_error_msg = f"HTTP {resp.status_code}: {err_text}"
                        continue

                    # Yield initial assistant role chunk
                    yield {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                    }

                    is_reasoning_model = any(k in model.lower() for k in ("sol", "gpt-5", "o1", "o3", "reasoner", "thinking")) or int(kwargs.get("thinking_budget") or 0) > 0
                    hist_text = assistant_history_text(messages)
                    hist_msgs = assistant_history_messages(messages)
                    raw_text = ""
                    prev_text = ""
                    raw_thought = ""
                    prev_thought = ""
                    emitted_thought = False
                    emitted_any = False
                    seen_file_ids = set()
                    last_conversation_id = None

                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        line_str = line.decode("utf-8", errors="ignore") if isinstance(line, bytes) else line
                        line_str = line_str.strip()
                        if line_str.startswith("data: "):
                            data_str = line_str[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                evt = json.loads(data_str)
                                if evt.get("conversation_id"):
                                    last_conversation_id = evt.get("conversation_id")

                                # Check for image asset pointers emitted by DALL-E / picture_v2
                                asset_matches = re.findall(r"(?:file-service|sediment)://([A-Za-z0-9_-]+)", data_str)
                                for file_id in asset_matches:
                                    if file_id not in seen_file_ids:
                                        seen_file_ids.add(file_id)
                                        try:
                                            d_resp = await sess.get(f"https://chatgpt.com/backend-api/files/{file_id}/download", timeout=25.0)
                                            if d_resp.status_code == 200:
                                                d_info = d_resp.json()
                                                d_url = d_info.get("download_url") or d_info.get("url")
                                                if d_url:
                                                    img_resp = await sess.get(d_url, timeout=40.0)
                                                    if img_resp.status_code == 200 and len(img_resp.content) > 500:
                                                        img_bytes = img_resp.content
                                                        STATIC_GEN_DIR.mkdir(parents=True, exist_ok=True)
                                                        dest_file = STATIC_GEN_DIR / f"{file_id}.png"
                                                        dest_file.write_bytes(img_bytes)

                                                        b64_str = base64.b64encode(img_bytes).decode("utf-8")
                                                        data_uri = f"data:image/png;base64,{b64_str}"
                                                        img_md = f"\n\n![Generated Image]({data_uri})\n\n"
                                                        emitted_any = True
                                                        yield {
                                                            "id": chat_id,
                                                            "object": "chat.completion.chunk",
                                                            "created": created_ts,
                                                            "model": model,
                                                            "choices": [{"index": 0, "delta": {"content": img_md}, "finish_reason": None}],
                                                        }
                                        except Exception:
                                            pass

                                msg = evt.get("message")
                                if msg and is_thought_message(msg):
                                    raw_thought = thought_message_text(msg)
                                    if raw_thought:
                                        delta_thought = raw_thought[len(prev_thought):] if raw_thought.startswith(prev_thought) else raw_thought
                                        if delta_thought:
                                            prev_thought = raw_thought
                                            emitted_thought = True
                                            yield {
                                                "id": chat_id,
                                                "object": "chat.completion.chunk",
                                                "created": created_ts,
                                                "model": model,
                                                "choices": [{"index": 0, "delta": {"reasoning_content": delta_thought}, "finish_reason": None}],
                                            }
                                elif msg and is_visible_assistant_message(msg):
                                    raw_text = assistant_message_text(msg)
                                    cleaned_text = sanitize_output_text(strip_history(raw_text, hist_text, hist_msgs))
                                    if cleaned_text:
                                        delta = cleaned_text[len(prev_text):] if cleaned_text.startswith(prev_text) else cleaned_text
                                        if delta:
                                            prev_text = cleaned_text
                                            emitted_any = True
                                            yield {
                                                "id": chat_id,
                                                "object": "chat.completion.chunk",
                                                "created": created_ts,
                                                "model": model,
                                                "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                                            }
                                # Handle JSON patch operations for continuous token streaming
                                elif evt.get("o") == "patch" or evt.get("p"):
                                    raw_patched = apply_text_patch(evt, raw_text)
                                    if raw_patched != raw_text:
                                        raw_text = raw_patched
                                        cleaned_text = sanitize_output_text(strip_history(raw_text, hist_text, hist_msgs))
                                        if cleaned_text:
                                            delta = cleaned_text[len(prev_text):] if cleaned_text.startswith(prev_text) else cleaned_text
                                            if delta:
                                                prev_text = cleaned_text
                                                emitted_any = True
                                                yield {
                                                    "id": chat_id,
                                                    "object": "chat.completion.chunk",
                                                    "created": created_ts,
                                                    "model": model,
                                                    "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                                                }
                            except Exception:
                                continue

                    # Auto-hide image generation conversations from the user's ChatGPT sidebar
                    if is_image_model and last_conversation_id:
                        try:
                            del_headers = {
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json",
                                "User-Agent": user_agent,
                                "Referer": f"https://chatgpt.com/c/{last_conversation_id}",
                                "X-OpenAI-Target-Route": f"/backend-api/conversation/{last_conversation_id}",
                            }
                            await sess.patch(
                                f"https://chatgpt.com/backend-api/conversation/{last_conversation_id}",
                                headers=del_headers,
                                json={"is_visible": False},
                                timeout=10.0,
                            )
                        except Exception:
                            pass

                    # Final completion chunk
                    yield {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    return

            except Exception as e:
                last_error_msg = str(e)
                continue
        else:
            # Fallback if curl_cffi is missing
            last_error_msg = "curl_cffi package is required for native ChatGPT TLS fingerprint impersonation."
            break

    # 4. If all accounts failed, report clear error
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {
                "content": f"\n\n[ChatGPT Engine Error: All available accounts failed to respond. Last error: {last_error_msg}]"
            },
            "finish_reason": "error",
        }],
    }


async def generate_chatgpt_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute complete non-streaming chat completion."""
    full_content = []
    created_ts = int(time.time())
    chat_id = f"chatcmpl-chatgpt-{uuid.uuid4().hex[:12]}"

    async for chunk in stream_chatgpt_chat(model, messages, accounts=accounts, stream=False, **kwargs):
        choices = chunk.get("choices", [])
        if choices:
            c = choices[0].get("delta", {}).get("content")
            if c:
                full_content.append(c)

    content_str = "".join(full_content)
    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created_ts,
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content_str},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": len(str(messages)) // 4,
            "completion_tokens": len(content_str) // 4,
            "total_tokens": (len(str(messages)) + len(content_str)) // 4,
        },
    }
