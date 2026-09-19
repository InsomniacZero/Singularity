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


async def stream_kimi_chat(
    model: str,
    messages: List[Dict[str, Any]],
    raw_token: str,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream chat completion events directly from Moonshot AI / Kimi Web API.
    Yields OpenAI-compatible chunk dicts.
    """
    device_id = str(random.randint(7000000000000000000, 7999999999999999999))
    session_id = str(random.randint(1700000000000000000, 1799999999999999999))
    chat_id = f"chatcmpl-kimi-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0), follow_redirects=True) as client:
        access_token = await get_kimi_access_token(raw_token, client=client)

        enable_thinking = "thinking" in model.lower()
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
                yield {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"\n\n[Kimi Web Error {resp.status_code}: {err_text}]"},
                        "finish_reason": "error",
                    }],
                }
                return

            # Initial role chunk
            yield {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }

            buffer = bytearray()
            current_phase = "thinking" if enable_thinking else "answer"

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

                        # Detect stage / phase
                        stages = evt.get("block", {}).get("multiStage", {}).get("stages", [])
                        if stages:
                            first_stage = stages[0]
                            if first_stage.get("name") == "STAGE_NAME_THINKING":
                                if first_stage.get("status") in {"STAGE_STATUS_END", "completed"}:
                                    current_phase = "answer"
                                else:
                                    current_phase = "thinking"

                        mask = evt.get("mask", "")
                        block = evt.get("block", {})
                        think_obj = block.get("think")
                        text_obj = block.get("text")

                        delta_content = None
                        delta_reasoning = None

                        if "block.think" in mask or (isinstance(think_obj, dict) and think_obj.get("content")):
                            delta_reasoning = think_obj.get("content") if isinstance(think_obj, dict) else None
                        elif "block.text" in mask or (isinstance(text_obj, dict) and text_obj.get("content")):
                            txt = text_obj.get("content") if isinstance(text_obj, dict) else None
                            if current_phase == "thinking":
                                delta_reasoning = txt
                            else:
                                delta_content = txt

                        if delta_content:
                            yield {
                                "id": chat_id,
                                "object": "chat.completion.chunk",
                                "created": created_ts,
                                "model": model,
                                "choices": [{"index": 0, "delta": {"content": delta_content}, "finish_reason": None}],
                            }
                        elif delta_reasoning:
                            yield {
                                "id": chat_id,
                                "object": "chat.completion.chunk",
                                "created": created_ts,
                                "model": model,
                                "choices": [{"index": 0, "delta": {"reasoning_content": delta_reasoning}, "finish_reason": None}],
                            }

                    except Exception:
                        pass

            # Final stop chunk
            yield {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
