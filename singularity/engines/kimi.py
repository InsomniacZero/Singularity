#!/usr/bin/env python3
"""
Singularity Native Kimi (Moonshot AI) Engine
=============================================
Direct Connect-protocol streaming and completion client for Moonshot AI / Kimi Web.
100% self-contained pure Python with zero legacy dependencies.
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

KIMI_API_BASE = os.getenv("KIMI_API_BASE", "https://www.kimi.com")
KIMI_CHAT_PATH = "/apiv2/kimi.gateway.chat.v1.ChatService/Chat"
KIMI_SCENARIO = "SCENARIO_K2D5"

FAKE_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    "Origin": KIMI_API_BASE,
    "Referer": f"{KIMI_API_BASE}/",
    "R-Timezone": "Asia/Shanghai",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "X-Msh-Platform": "web",
}


def _parse_jwt(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
    except Exception:
        return None


def _encode_connect_request(payload: Dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = bytearray(5)
    header[0] = 0x00
    header[1:5] = len(body).to_bytes(4, "big")
    return bytes(header) + body


def _format_messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            text_sub = []
            for sub in content:
                if isinstance(sub, dict) and sub.get("type") == "text":
                    text_sub.append(sub.get("text", ""))
                elif isinstance(sub, str):
                    text_sub.append(sub)
            content = " ".join(text_sub)
        content_str = str(content).strip()
        if not content_str:
            continue
        if role == "system":
            parts.append(f"system:{content_str}")
        elif role == "assistant":
            parts.append(f"assistant:{content_str}")
        else:
            parts.append(f"user:{content_str}")
    return "\n".join(parts) if parts else "Hello"


# Cached access tokens: refresh_token_str -> (access_token, expiry_timestamp)
_ACCESS_TOKEN_CACHE: Dict[str, Tuple[str, float]] = {}
_CACHE_LOCK = asyncio.Lock()


async def get_kimi_access_token(refresh_token: str, client: Optional[httpx.AsyncClient] = None) -> str:
    """Exchange Kimi refresh token for active bearer access token with in-memory caching."""
    token = refresh_token.strip()
    if token.startswith("Bearer "):
        token = token[7:].strip()

    # Check if already a valid non-expired access token
    payload = _parse_jwt(token)
    now = time.time()
    if payload and payload.get("app_id") == "kimi" and payload.get("typ") == "access":
        exp = float(payload.get("exp", now + 3600))
        if now < exp - 60:
            return token

    # Check cache
    async with _CACHE_LOCK:
        cached = _ACCESS_TOKEN_CACHE.get(token)
        if cached and now < cached[1] - 60:
            return cached[0]

    headers = {
        **FAKE_HEADERS,
        "Authorization": f"Bearer {token}",
    }

    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
        own_client = True

    try:
        resp = await client.get(f"{KIMI_API_BASE}/api/auth/token/refresh", headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Kimi token refresh failed ({resp.status_code}): {resp.text[:200]}")
        data = resp.json()
        access_tok = data.get("access_token")
        if not access_tok:
            raise RuntimeError("Kimi did not return access_token")

        p = _parse_jwt(access_tok)
        exp = float(p.get("exp", now + 3600)) if p else now + 3600

        async with _CACHE_LOCK:
            _ACCESS_TOKEN_CACHE[token] = (access_tok, exp)
        return access_tok
    finally:
        if own_client:
            await client.aclose()


def get_kimi_accounts() -> List[Dict[str, Any]]:
    """Fetch stacked Kimi credentials from SQLite database vault."""
    try:
        from singularity import db
        raw_accounts = db.get_accounts("kimi")
        accounts = []
        for item in raw_accounts:
            token_str = item.get("token", "").strip()
            if not token_str:
                continue
            accounts.append({
                "id": item.get("id"),
                "identifier": item.get("identifier") or item.get("name") or f"kimi-{item.get('id', 'account')}",
                "name": item.get("name") or f"Kimi ({item.get('id', 'account')})",
                "token": token_str,
                "status": item.get("status", "active"),
                "plan": item.get("plan", "free"),
            })
        return accounts
    except Exception:
        return []


_ACCOUNT_ROTATION_INDEX: int = 0
_ROTATION_LOCK = asyncio.Lock()
# In-memory tracking of accounts whose free credits are depleted: token -> expiration_ts
_EXHAUSTED_ACCOUNTS: Dict[str, float] = {}


async def stream_kimi_chat(
    model: str,
    messages: List[Dict[str, Any]],
    raw_token: Optional[str] = None,
    accounts: Optional[List[Dict[str, Any]]] = None,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream chat completion events directly from Moonshot AI / Kimi Web API.
    Supports multi-account rotation, transparent quota failover, and clean
    separation of reasoning_content vs final content.
    Yields OpenAI-compatible chunk dicts.
    """
    device_id = str(random.randint(7000000000000000000, 7999999999999999999))
    session_id = str(random.randint(1700000000000000000, 1799999999999999999))
    chat_id = f"chatcmpl-kimi-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    # 1. Resolve candidate accounts
    candidates: List[Dict[str, Any]] = []
    if accounts:
        for acc in accounts:
            t = acc.get("token", "").strip()
            if t:
                candidates.append({
                    "id": acc.get("id", 0),
                    "identifier": acc.get("identifier") or acc.get("name") or "kimi-acc",
                    "name": acc.get("name") or "Kimi Account",
                    "token": t,
                    "status": acc.get("status", "active"),
                })
    elif raw_token and raw_token.strip():
        candidates = [{
            "id": 0,
            "identifier": "kimi-direct",
            "name": "Kimi Direct",
            "token": raw_token.strip(),
            "status": "active",
        }]
    else:
        candidates = get_kimi_accounts()

    if not candidates:
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": "⚠️ **Kimi Error:** No active Kimi account found in Singularity database vault. Please add your Kimi refresh token in the Control Center or via './singular import'."
                },
                "finish_reason": "error",
            }],
        }
        return

    # Filter out active vs disabled
    active_candidates = [c for c in candidates if c.get("status") != "disabled"]
    if not active_candidates:
        active_candidates = list(candidates)

    # Prioritize accounts that haven't hit quota recently
    now = time.time()
    non_exhausted = [c for c in active_candidates if _EXHAUSTED_ACCOUNTS.get(c["token"], 0) < now]
    if non_exhausted:
        sorted_candidates = non_exhausted
    else:
        sorted_candidates = active_candidates

    # Round-robin rotation across available non-exhausted accounts
    if len(sorted_candidates) > 1:
        async with _ROTATION_LOCK:
            global _ACCOUNT_ROTATION_INDEX
            idx = _ACCOUNT_ROTATION_INDEX % len(sorted_candidates)
            _ACCOUNT_ROTATION_INDEX += 1
        sorted_candidates = sorted_candidates[idx:] + sorted_candidates[:idx]

    enable_thinking = "thinking" in model.lower() or "k3" in model.lower()
    enable_search = "search" in model.lower()
    prompt_text = _format_messages_to_prompt(messages)

    payload: Dict[str, Any] = {
        "scenario": KIMI_SCENARIO,
        "tools": [{"type": "TOOL_TYPE_SEARCH", "search": {}}] if enable_search else [],
        "message": {
            "role": "user",
            "blocks": [{"message_id": "", "text": {"content": prompt_text}}],
            "scenario": KIMI_SCENARIO,
        },
        "options": {"thinking": enable_thinking},
    }
    connect_body = _encode_connect_request(payload)

    last_error_msg = ""
    role_yielded = False
    has_yielded_tokens = False

    for attempt_idx, account in enumerate(sorted_candidates):
        token_str = account["token"]
        acc_name = account.get("name") or account.get("identifier") or f"Account-{account.get('id')}"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0), follow_redirects=True) as client:
                try:
                    access_token = await get_kimi_access_token(token_str, client=client)
                except Exception as auth_err:
                    last_error_msg = f"Token refresh error on {acc_name}: {str(auth_err)}"
                    continue

                headers = {
                    **FAKE_HEADERS,
                    "Authorization": f"Bearer {access_token}",
                    "X-Msh-Device-Id": device_id,
                    "X-Msh-Session-Id": session_id,
                    "Connect-Protocol-Version": "1",
                    "Content-Type": "application/connect+json",
                }

                async with client.stream(
                    "POST",
                    f"{KIMI_API_BASE}{KIMI_CHAT_PATH}",
                    content=connect_body,
                    headers=headers,
                ) as resp:
                    if resp.status_code >= 400:
                        err_text = (await resp.aread()).decode("utf-8", errors="ignore")
                        last_error_msg = f"HTTP {resp.status_code} on {acc_name}: {err_text[:200]}"
                        if resp.status_code in (401, 403, 429) and attempt_idx + 1 < len(sorted_candidates):
                            continue
                        break

                    buffer = bytearray()
                    account_failed = False
                    total_reasoning = ""
                    total_content = ""

                    async for chunk in resp.aiter_bytes():
                        buffer.extend(chunk)
                        while len(buffer) >= 5:
                            flag = buffer[0]
                            length = int.from_bytes(buffer[1:5], "big")
                            if len(buffer) < 5 + length:
                                break

                            frame = bytes(buffer[5 : 5 + length])
                            del buffer[: 5 + length]

                            if flag & 0x80:
                                continue

                            try:
                                evt_str = frame.decode("utf-8", errors="ignore").strip()
                                if not evt_str:
                                    continue
                                evt = json.loads(evt_str)
                            except Exception:
                                continue

                            # Check for Connect Protocol trailer (flag & 0x02) or error
                            err = evt.get("error")
                            is_trailer = bool(flag & 0x02)

                            if err:
                                err_code = err.get("code", "error") if isinstance(err, dict) else "error"
                                err_msg = ""
                                if isinstance(err, dict):
                                    err_msg = err.get("localizedMessage", {}).get("message") or err.get("message") or str(err)
                                else:
                                    err_msg = str(evt)

                                is_quota = (
                                    "exhausted" in str(err_code).lower()
                                    or "quota" in str(err_msg).lower()
                                    or "credits" in str(err_msg).lower()
                                )
                                if is_quota:
                                    _EXHAUSTED_ACCOUNTS[token_str] = time.time() + 1800

                                if not has_yielded_tokens and attempt_idx + 1 < len(sorted_candidates):
                                    account_failed = True
                                    last_error_msg = f"Quota depleted on {acc_name} ({err_msg}). Rotating..."
                                    break
                                else:
                                    if not role_yielded:
                                        yield {
                                            "id": chat_id,
                                            "object": "chat.completion.chunk",
                                            "created": created_ts,
                                            "model": model,
                                            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                                        }
                                        role_yielded = True
                                    yield {
                                        "id": chat_id,
                                        "object": "chat.completion.chunk",
                                        "created": created_ts,
                                        "model": model,
                                        "choices": [{
                                            "index": 0,
                                            "delta": {"content": f"\n\n⚠️ **Kimi Error ({err_code}):** {err_msg}\n"},
                                            "finish_reason": "error",
                                        }],
                                    }
                                    return

                            if is_trailer:
                                # Clean normal end-of-stream trailer frame
                                break

                            mask = evt.get("mask", "")
                            block = evt.get("block", {})
                            think_obj = block.get("think")
                            text_obj = block.get("text")

                            delta_reasoning = None
                            delta_content = None

                            if "block.think" in mask or (isinstance(think_obj, dict) and think_obj.get("content")):
                                delta_reasoning = think_obj.get("content") if isinstance(think_obj, dict) else None

                            if "block.text" in mask or (isinstance(text_obj, dict) and text_obj.get("content")):
                                delta_content = text_obj.get("content") if isinstance(text_obj, dict) else None

                            if delta_reasoning or delta_content:
                                if not role_yielded:
                                    yield {
                                        "id": chat_id,
                                        "object": "chat.completion.chunk",
                                        "created": created_ts,
                                        "model": model,
                                        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                                    }
                                    role_yielded = True

                            if delta_reasoning:
                                has_yielded_tokens = True
                                total_reasoning += delta_reasoning
                                yield {
                                    "id": chat_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_ts,
                                    "model": model,
                                    "choices": [{"index": 0, "delta": {"reasoning_content": delta_reasoning}, "finish_reason": None}],
                                }

                            if delta_content:
                                has_yielded_tokens = True
                                total_content += delta_content
                                yield {
                                    "id": chat_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_ts,
                                    "model": model,
                                    "choices": [{"index": 0, "delta": {"content": delta_content}, "finish_reason": None}],
                                }

                    if account_failed:
                        continue

                    # If response finished with only reasoning and 0 text, yield clear conclusion
                    if has_yielded_tokens:
                        if not total_content and total_reasoning:
                            yield {
                                "id": chat_id,
                                "object": "chat.completion.chunk",
                                "created": created_ts,
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": "\n\n*(Thinking process completed)*"},
                                    "finish_reason": None,
                                }],
                            }

                        # Final stop chunk
                        yield {
                            "id": chat_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        }
                        return

        except Exception as conn_err:
            last_error_msg = f"Connection error on {acc_name}: {str(conn_err)}"
            if not has_yielded_tokens and attempt_idx + 1 < len(sorted_candidates):
                continue
            break

    # If all candidate accounts failed
    if not role_yielded:
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {
                "content": (
                    f"\n\n⚠️ **Kimi Inference Error:**\n"
                    f"{last_error_msg or 'All stacked Kimi accounts have depleted their available quota or failed to respond.'}\n\n"
                    f"Please add a fresh Kimi token in the Singularity Control Center or via `./singular import`."
                )
            },
            "finish_reason": "error",
        }],
    }
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
