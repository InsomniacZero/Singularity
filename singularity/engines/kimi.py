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
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

import httpx

KIMI_API_BASE = os.getenv("KIMI_API_BASE", "https://www.kimi.com")
KIMI_CHAT_PATH = "/apiv2/kimi.gateway.chat.v1.ChatService/Chat"
KIMI_DEFAULT_SCENARIO = "SCENARIO_K3"


def resolve_kimi_scenarios(model: str, enable_search: bool = False) -> List[str]:
    """
    Resolve ordered candidate scenarios for Moonshot Kimi models.
    Prioritizes SCENARIO_K3 for K3 variants and falls back gracefully to sibling
    scenarios if Moonshot temporarily sheds free load on a specific route.
    """
    m = model.lower()
    if enable_search:
        return ["SCENARIO_K3", "SCENARIO_SEARCH", "SCENARIO_K3_THINKING"]
    if "k3" in m:
        return ["SCENARIO_K3", "SCENARIO_K3_THINKING", "SCENARIO_SEARCH", "SCENARIO_CHAT"]
    if "k2" in m:
        # Note: K3 is prioritized over K2D5 on free tier because K2D5 is often
        # paywalled with REASON_SERVER_OVERLOADED_FOR_FREE_USER.
        return ["SCENARIO_K3", "SCENARIO_K2D5", "SCENARIO_SEARCH", "SCENARIO_CHAT"]
    return ["SCENARIO_K3", "SCENARIO_SEARCH", "SCENARIO_CHAT", "SCENARIO_K2D5"]

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


def _clean_token(raw_token: str) -> str:
    """Extract and unwrap clean JWT token from raw input (JSON, quotes, cookies, or Bearer prefix)."""
    if not raw_token:
        return ""
    t = raw_token.strip().replace("\r", "")
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            data = json.loads(t)
            if isinstance(data, dict):
                cand = (
                    data.get("refresh_token")
                    or data.get("kimi-refresh-token")
                    or data.get("access_token")
                    or data.get("token")
                    or data.get("value")
                )
                if cand:
                    t = str(cand).strip()
            elif isinstance(data, list) and data:
                if isinstance(data[0], str):
                    t = data[0].strip()
                elif isinstance(data[0], dict):
                    cand = (
                        data[0].get("refresh_token")
                        or data[0].get("kimi-refresh-token")
                        or data[0].get("access_token")
                        or data[0].get("token")
                        or data[0].get("value")
                    )
                    if cand:
                        t = str(cand).strip()
        except Exception:
            pass
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    
    # Extract pristine JWT token if embedded inside cookie string or key=value pair
    jwt_match = re.search(r"(eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)", t)
    if jwt_match:
        return jwt_match.group(1).strip()

    return t.strip().strip('"').strip("'")


def _extract_device_id_from_token(token: str) -> Optional[str]:
    payload = _parse_jwt(token)
    if payload and payload.get("device_id"):
        return str(payload.get("device_id"))
    return None


def _parse_jwt(token: str) -> Optional[Dict[str, Any]]:
    try:
        clean = _clean_token(token)
        parts = clean.split(".")
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
    """Exchange Kimi refresh token for active bearer access token with in-memory caching and failover."""
    token = _clean_token(refresh_token)
    if not token:
        raise ValueError("Empty Kimi token provided")

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

    device_id = _extract_device_id_from_token(token) or str(random.randint(7000000000000000000, 7999999999999999999))

    headers = {
        **FAKE_HEADERS,
        "Authorization": f"Bearer {token}",
        "X-Msh-Device-Id": device_id,
    }

    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0), follow_redirects=True)
        own_client = True

    # Try primary endpoint, then alternative fallback endpoints
    endpoints = [
        KIMI_API_BASE,
        "https://kimi.moonshot.cn",
        "https://www.kimi.com",
    ]
    seen = set()
    unique_endpoints = []
    for ep in endpoints:
        ep_clean = ep.rstrip("/")
        if ep_clean not in seen:
            seen.add(ep_clean)
            unique_endpoints.append(ep_clean)

    last_err = None
    try:
        for ep in unique_endpoints:
            try:
                ep_headers = {
                    **headers,
                    "Origin": ep,
                    "Referer": f"{ep}/",
                }
                resp = await client.get(f"{ep}/api/auth/token/refresh", headers=ep_headers)
                if resp.status_code != 200:
                    last_err = RuntimeError(f"Kimi token refresh failed ({resp.status_code}): {resp.text[:200]}")
                    continue
                data = resp.json()
                access_tok = data.get("access_token")
                if not access_tok:
                    last_err = RuntimeError("Kimi did not return access_token")
                    continue

                p = _parse_jwt(access_tok)
                exp = float(p.get("exp", now + 3600)) if p else now + 3600

                async with _CACHE_LOCK:
                    _ACCESS_TOKEN_CACHE[token] = (access_tok, exp)
                return access_tok
            except (httpx.ConnectError, httpx.TimeoutException, OSError) as net_err:
                last_err = net_err
                continue

        raise last_err or RuntimeError("Kimi token refresh failed on all candidate endpoints")
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
    if kwargs.get("thinking_budget") is not None:
        try:
            enable_thinking = int(kwargs["thinking_budget"]) > 0
        except Exception:
            pass
    elif kwargs.get("thinking") is not None:
        th = kwargs.get("thinking")
        if isinstance(th, dict):
            enable_thinking = th.get("type") == "enabled"
        elif isinstance(th, bool):
            enable_thinking = th
    enable_search = "search" in model.lower()
    prompt_text = _format_messages_to_prompt(messages)

    scenarios = resolve_kimi_scenarios(model, enable_search=enable_search)

    last_error_msg = ""
    role_yielded = False
    has_yielded_tokens = False

    for attempt_idx, account in enumerate(sorted_candidates):
        if has_yielded_tokens:
            return

        token_str = _clean_token(account["token"])
        acc_name = account.get("name") or account.get("identifier") or f"Account-{account.get('id')}"
        device_id = _extract_device_id_from_token(token_str) or str(random.randint(7000000000000000000, 7999999999999999999))

        account_success = False

        # Try candidate scenarios in prioritized order (e.g. SCENARIO_K3 -> SCENARIO_K3_THINKING -> SCENARIO_SEARCH)
        for current_scenario in scenarios:
            if account_success or has_yielded_tokens:
                break

            payload: Dict[str, Any] = {
                "scenario": current_scenario,
                "tools": [{"type": "TOOL_TYPE_SEARCH", "search": {}}] if enable_search else [],
                "message": {
                    "role": "user",
                    "blocks": [{"message_id": "", "text": {"content": prompt_text}}],
                    "scenario": current_scenario,
                },
                "options": {"thinking": enable_thinking},
            }
            connect_body = _encode_connect_request(payload)

            # Candidate endpoints to prevent DNS or connectivity failures
            candidate_endpoints = [
                KIMI_API_BASE,
                "https://kimi.moonshot.cn",
                "https://www.kimi.com",
            ]
            seen_ep = set()
            unique_eps = []
            for ep in candidate_endpoints:
                ep_clean = ep.rstrip("/")
                if ep_clean not in seen_ep:
                    seen_ep.add(ep_clean)
                    unique_eps.append(ep_clean)

            scenario_overloaded = False
            scenario_quota_depleted = False

            for current_base in unique_eps:
                if account_success or has_yielded_tokens:
                    break

                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0), follow_redirects=True) as client:
                        try:
                            access_token = await get_kimi_access_token(token_str, client=client)
                        except Exception as auth_err:
                            last_error_msg = f"Token refresh error on {acc_name}: {str(auth_err)}"
                            break

                        headers = {
                            **FAKE_HEADERS,
                            "Authorization": f"Bearer {access_token}",
                            "Origin": current_base,
                            "Referer": f"{current_base}/",
                            "X-Msh-Device-Id": device_id,
                            "X-Msh-Session-Id": session_id,
                            "Connect-Protocol-Version": "1",
                            "Content-Type": "application/connect+json",
                        }

                        async with client.stream(
                            "POST",
                            f"{current_base}{KIMI_CHAT_PATH}",
                            content=connect_body,
                            headers=headers,
                        ) as resp:
                            if resp.status_code >= 400:
                                err_text = (await resp.aread()).decode("utf-8", errors="ignore")
                                last_error_msg = f"HTTP {resp.status_code} on {acc_name}: {err_text[:200]}"
                                if resp.status_code in (401, 403, 429):
                                    break
                                continue

                            buffer = bytearray()
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
                                        details = err.get("details", []) if isinstance(err, dict) else []
                                        debug = details[0].get("debug", {}) if details and isinstance(details[0], dict) else {}
                                        err_reason = debug.get("reason") or ""
                                        loc_msg = debug.get("localizedMessage", {}).get("message")
                                        err_msg = (
                                            loc_msg
                                            or (err.get("localizedMessage", {}).get("message") if isinstance(err, dict) else None)
                                            or (err.get("message") if isinstance(err, dict) else None)
                                            or err_reason
                                            or "Kimi service busy"
                                        )

                                        is_overload = (
                                            "overload" in err_reason.lower()
                                            or "too many people" in err_msg.lower()
                                            or "priority access" in err_msg.lower()
                                        )
                                        is_quota = (
                                            "quota" in err_reason.lower()
                                            or "credits" in err_msg.lower()
                                            or "exhausted" in str(err_code).lower()
                                        )

                                        last_error_msg = f"{err_msg} ({err_reason or err_code})"

                                        if is_overload:
                                            scenario_overloaded = True
                                        elif is_quota:
                                            scenario_quota_depleted = True

                                        if not has_yielded_tokens:
                                            # We haven't sent tokens to user yet; transparently break to try next scenario or account
                                            break
                                        else:
                                            # If already yielding tokens mid-stream, finish with clean message
                                            yield {
                                                "id": chat_id,
                                                "object": "chat.completion.chunk",
                                                "created": created_ts,
                                                "model": model,
                                                "choices": [{
                                                    "index": 0,
                                                    "delta": {"content": f"\n\n*(Kimi stream interrupted: {err_msg})*"},
                                                    "finish_reason": "error",
                                                }],
                                            }
                                            return

                                    if is_trailer:
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

                            if has_yielded_tokens:
                                account_success = True
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

                                yield {
                                    "id": chat_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_ts,
                                    "model": model,
                                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                                }
                                return

                            if scenario_overloaded or scenario_quota_depleted:
                                break

                except Exception as conn_err:
                    last_error_msg = f"Connection error on {acc_name} ({current_base}): {str(conn_err)}"
                    if has_yielded_tokens:
                        return
                    continue

            # If this scenario worked, don't try fallback scenarios
            if account_success or has_yielded_tokens:
                return

        # If all scenarios failed on this account due to quota depletion, mark account temporarily
        if scenario_quota_depleted and not account_success:
            _EXHAUSTED_ACCOUNTS[token_str] = time.time() + 600

    # If all candidate accounts failed and no tokens were emitted
    if has_yielded_tokens:
        return

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
                    f"\n\n⚠️ **Kimi Inference Notice:**\n"
                    f"{last_error_msg or 'All stacked Kimi accounts / scenarios are currently busy or out of credits.'}\n\n"
                    f"Please check your credentials in the Singularity Control Center or try again in a few moments."
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
