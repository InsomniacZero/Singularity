#!/usr/bin/env python3
"""
Singularity Native ChatGPT Engine
=================================
Multi-account streaming and completion driver for OpenAI / ChatGPT.
Supports:
- Account pool rotation across SQLite vault credentials
- Upstream bridge proxying (port 8000) when service daemon is active
- Direct Web2API reverse-proxy execution with automatic session token refresh
- SSE streaming deltas and full completion formats
- 100% self-contained pure Python with zero legacy dependencies
"""

import asyncio
import base64
import json
import os
import random
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

import httpx

try:
    from singularity import db
    from singularity.providers import get_provider_host
except ImportError:
    import db
    from providers import get_provider_host


# -------------------------------------------------------------------
# Account & Token Management
# -------------------------------------------------------------------

_ACCESS_TOKEN_CACHE: Dict[str, Tuple[str, float]] = {}
_CACHE_LOCK = asyncio.Lock()
_ACCOUNT_ROTATION_INDEX = 0
_ROTATION_LOCK = asyncio.Lock()


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
    client: Optional[httpx.AsyncClient] = None,
) -> Tuple[str, str]:
    """
    Ensure active access token for account, auto-refreshing via session token if expired.
    Returns (access_token, account_identifier).
    """
    raw_token = account.get("token", "")
    ident = account.get("identifier") or account.get("name") or str(account.get("id", "chatgpt"))
    creds = extract_chatgpt_credentials(raw_token)
    
    access_token = creds.get("access_token", "")
    session_token = creds.get("session_token", "")
    now = time.time()

    # Check in-memory cache first
    async with _CACHE_LOCK:
        cached = _ACCESS_TOKEN_CACHE.get(ident)
        if cached and now < cached[1] - 120:
            return cached[0], ident

    # Check if access token is still valid
    if access_token:
        jwt = _decode_jwt(access_token)
        if jwt:
            exp = float(jwt.get("exp", now + 3600))
            if now < exp - 120:
                async with _CACHE_LOCK:
                    _ACCESS_TOKEN_CACHE[ident] = (access_token, exp)
                return access_token, ident

    # If no session token, return current access token or raw string
    if not session_token:
        return access_token or raw_token, ident

    # Refresh via ChatGPT NextAuth session endpoint
    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
        own_client = True

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Cookie": f"__Secure-next-auth.session-token={session_token}",
            "Accept": "application/json",
        }
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
    finally:
        if own_client:
            await client.aclose()

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
# Format Helpers
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


# -------------------------------------------------------------------
# Core Streaming Inference
# -------------------------------------------------------------------

async def stream_chatgpt_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Universal streaming inference engine for ChatGPT.
    1. First attempts high-speed bridge daemon on port 8000 (if running).
    2. Falls back to direct in-process Web2API conversation endpoint with multi-account rotation.
    Yields OpenAI-compatible chunk dictionaries.
    """
    chat_id = f"chatcmpl-chatgpt-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    # Resolve target port & host
    host = get_provider_host("chatgpt")
    port = int(os.getenv("CHATGPT_PORT", 8000))
    bridge_url = f"http://{host}:{port}/v1/chat/completions"

    account = await get_next_account(accounts)
    token = ""
    account_name = "ChatGPT Account"
    if account:
        token, account_name = await get_valid_access_token(account)

    # 1. Attempt Bridge Proxy (Port 8000)
    bridge_available = False
    try:
        async with httpx.AsyncClient(timeout=1.0) as check_client:
            health_resp = await check_client.get(f"http://{host}:{port}/healthz")
            if health_resp.status_code in (200, 404):
                bridge_available = True
    except Exception:
        bridge_available = False

    if bridge_available:
        bridge_headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer chatgpt2api",
        }
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }

        client = httpx.AsyncClient(timeout=120.0)
        try:
            async with client.stream("POST", bridge_url, json=body, headers=bridge_headers) as upstream:
                if upstream.status_code < 400:
                    async for line in upstream.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if line.startswith("data: "):
                            raw_data = line[6:].strip()
                            if raw_data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(raw_data)
                                yield chunk
                            except Exception:
                                continue
                    return
        except Exception:
            pass  # Fall through to direct engine
        finally:
            await client.aclose()

    # 2. Direct In-Process Web Engine
    if not token:
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": "Error: No active ChatGPT credentials found in Singularity vault. Please add your NextAuth session JSON or access token in the Control Center or run './singular import <path>'."
                },
                "finish_reason": "error",
            }],
        }
        return

    # Yield initial role chunk
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }

    # Prepare ChatGPT web conversation payload
    prompt_text = _format_messages_to_prompt(messages)
    web_model = model if model not in ("auto", "chatgpt-default") else "auto"

    conv_payload = {
        "action": "next",
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": [prompt_text]},
                "metadata": {},
            }
        ],
        "parent_message_id": str(uuid.uuid4()),
        "model": web_model,
        "timezone_offset_min": -330,
        "history_and_training_disabled": True,
        "conversation_mode": {"kind": "primary_assistant"},
    }

    web_headers = {
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
        "Oai-Device-Id": str(uuid.uuid4()),
        "Oai-Language": "en-US",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    }

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        try:
            async with client.stream(
                "POST",
                "https://chatgpt.com/backend-api/conversation",
                json=conv_payload,
                headers=web_headers,
            ) as resp:
                if resp.status_code >= 400:
                    err_text = (await resp.aread()).decode("utf-8", errors="ignore")
                    yield {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "content": f"\n\n[ChatGPT Web Ingestion Note: Direct upstream returned HTTP {resp.status_code}. Ensure service bridge daemon is running on port {port} for automated challenge bypass: {err_text[:160]}]"
                            },
                            "finish_reason": "error",
                        }],
                    }
                    return

                prev_text = ""
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            evt = json.loads(data_str)
                            msg = evt.get("message", {})
                            parts = msg.get("content", {}).get("parts", [])
                            if parts and isinstance(parts[0], str):
                                full_text = parts[0]
                                delta = full_text[len(prev_text):]
                                if delta:
                                    prev_text = full_text
                                    yield {
                                        "id": chat_id,
                                        "object": "chat.completion.chunk",
                                        "created": created_ts,
                                        "model": model,
                                        "choices": [{
                                            "index": 0,
                                            "delta": {"content": delta},
                                            "finish_reason": None,
                                        }],
                                    }
                        except Exception:
                            continue

        except Exception as e:
            yield {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": f"\n\n[ChatGPT Engine Exception: {str(e)}]"},
                    "finish_reason": "error",
                }],
            }

    # Final completion chunk
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
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
