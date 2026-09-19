#!/usr/bin/env python3
"""
Singularity Native Claude Engine
================================
Multi-account streaming and completion driver for Anthropic / Claude.
Supports:
- Multi-session rotation across SQLite vault credentials
- Upstream daemon proxying (port 8080) when service daemon is active
- Direct Web2API reverse-proxy execution with automatic organization discovery
- Full SSE streaming deltas, extended thinking (CoT), and standard completions
- 100% self-contained pure Python with zero legacy dependencies
"""

import asyncio
import json
import os
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

import httpx

try:
    from curl_cffi.requests import AsyncSession as CurlAsyncSession
    HAVE_CURL_CFFI = True
except ImportError:
    CurlAsyncSession = None  # type: ignore
    HAVE_CURL_CFFI = False

try:
    from singularity import db
    from singularity.providers import get_provider_host
except ImportError:
    import db
    from providers import get_provider_host


# -------------------------------------------------------------------
# Account & Session Key Management
# -------------------------------------------------------------------

_ORG_ID_CACHE: Dict[str, str] = {}
_ORG_LOCK = asyncio.Lock()
_ACCOUNT_ROTATION_INDEX = 0
_ROTATION_LOCK = asyncio.Lock()


def extract_claude_session_key(raw_token: str) -> str:
    """Extract clean sessionKey (sk-ant-sid02-...) from cookie string, JSON, or raw key."""
    raw = raw_token.strip()
    if not raw:
        return ""

    # 1. JSON dump
    if raw.startswith("{") or raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return (
                    data.get("sessionKey")
                    or data.get("session_key")
                    or data.get("token")
                    or data.get("cookie")
                    or ""
                ).strip()
        except Exception:
            pass

    # 2. Cookie string (e.g. sessionKey=sk-ant-sid02-...;)
    m = re.search(r"sessionKey=([a-zA-Z0-9_\-]+)", raw)
    if m:
        return m.group(1).strip()

    # 3. Raw sessionKey format
    if raw.startswith("sk-ant-sid"):
        return raw

    return raw


async def get_next_claude_account(accounts: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Rotate through available Claude accounts in SQLite vault."""
    global _ACCOUNT_ROTATION_INDEX
    if not accounts:
        try:
            accounts = db.get_accounts("claude")
        except Exception:
            accounts = []

    if not accounts:
        return None

    async with _ROTATION_LOCK:
        idx = _ACCOUNT_ROTATION_INDEX % len(accounts)
        _ACCOUNT_ROTATION_INDEX += 1
        return accounts[idx]


async def get_claude_org_id(session_key: str) -> Optional[str]:
    """Fetch user's organization UUID from claude.ai with in-memory caching."""
    async with _ORG_LOCK:
        cached = _ORG_ID_CACHE.get(session_key)
        if cached:
            return cached

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Cookie": f"sessionKey={session_key}",
        "Accept": "application/json",
        "Referer": "https://claude.ai/",
        "Origin": "https://claude.ai",
    }

    # Attempt 1: curl_cffi with chrome120 impersonation to bypass Cloudflare
    if HAVE_CURL_CFFI:
        try:
            async with CurlAsyncSession(impersonate="chrome120", timeout=15.0) as s:
                resp = await s.get("https://claude.ai/api/organizations", headers=headers)
                if resp.status_code == 200:
                    orgs = resp.json()
                    if isinstance(orgs, list) and orgs:
                        org_uuid = orgs[0].get("uuid")
                        if org_uuid:
                            async with _ORG_LOCK:
                                _ORG_ID_CACHE[session_key] = org_uuid
                            return org_uuid
        except Exception:
            pass

    # Attempt 2: Fallback httpx
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get("https://claude.ai/api/organizations", headers=headers)
            if resp.status_code == 200:
                orgs = resp.json()
                if isinstance(orgs, list) and orgs:
                    org_uuid = orgs[0].get("uuid")
                    if org_uuid:
                        async with _ORG_LOCK:
                            _ORG_ID_CACHE[session_key] = org_uuid
                        return org_uuid
    except Exception:
        pass

    return None


# -------------------------------------------------------------------
# Format Helpers
# -------------------------------------------------------------------

def _format_messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    """Format OpenAI messages list into Claude prompt format."""
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
            parts.append(f"System: {content_str}")
        elif role == "assistant":
            parts.append(f"Assistant: {content_str}")
        else:
            parts.append(f"Human: {content_str}")
    return "\n\n".join(parts) if parts else "Hello"


# -------------------------------------------------------------------
# Core Streaming Inference
# -------------------------------------------------------------------

async def stream_claude_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Universal streaming inference engine for Claude.
    1. First attempts high-speed daemon on port 8080 (if running).
    2. Falls back to direct in-process Web2API conversation endpoint with multi-account rotation.
    Yields OpenAI-compatible chunk dictionaries.
    """
    chat_id = f"chatcmpl-claude-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    # Resolve target host & port
    host = get_provider_host("claude")
    port = int(os.getenv("CLAUDE_PORT", 8080))
    bridge_url = f"http://{host}:{port}/v1/chat/completions"

    account = await get_next_claude_account(accounts)
    session_key = ""
    account_name = "Claude Session"
    if account:
        session_key = extract_claude_session_key(account.get("token", ""))
        account_name = account.get("name") or account.get("identifier") or "Claude Session"

    # 1. Attempt Daemon Proxy (Port 8080)
    daemon_available = False
    try:
        async with httpx.AsyncClient(timeout=1.0) as check_client:
            health_resp = await check_client.get(
                f"http://{host}:{port}/v1/models",
                headers={"Authorization": "Bearer sk-claude-local"},
            )
            if health_resp.status_code in (200, 401, 403):
                daemon_available = True
    except Exception:
        daemon_available = False

    if daemon_available:
        daemon_headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer sk-claude-local",
        }
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }

        client = httpx.AsyncClient(timeout=120.0)
        try:
            async with client.stream("POST", bridge_url, json=body, headers=daemon_headers) as upstream:
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
    if not session_key:
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": "Error: No active Claude sessionKey found in Singularity vault. Please add your sessionKey (sk-ant-sid02-...) in the Control Center or run './singular import <path>'."
                },
                "finish_reason": "error",
            }],
        }
        return

    # Obtain organization UUID
    org_id = await get_claude_org_id(session_key)
    if not org_id:
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": f"\n\n[Claude Authentication Note: Could not verify organization with sessionKey for {account_name}. Please verify sessionKey is valid or start Claude service daemon on port {port}.]"
                },
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

    # Prepare direct conversation
    conv_uuid = str(uuid.uuid4())
    base_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Cookie": f"sessionKey={session_key}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Referer": f"https://claude.ai/chat/{conv_uuid}",
        "Origin": "https://claude.ai",
    }

    prompt_text = _format_messages_to_prompt(messages)
    web_model = model
    if web_model.startswith("claude-"):
        web_model = "claude-sonnet-5"

    comp_payload = {
        "prompt": prompt_text,
        "timezone": "UTC",
        "model": web_model,
        "rendering_mode": "messages",
    }

    if HAVE_CURL_CFFI:
        try:
            async with CurlAsyncSession(impersonate="chrome120", timeout=120.0) as session:
                # Create conversation
                try:
                    await session.post(
                        f"https://claude.ai/api/organizations/{org_id}/chat_conversations",
                        json={"uuid": conv_uuid, "name": ""},
                        headers={**base_headers, "Accept": "application/json"},
                        timeout=10.0,
                    )
                except Exception:
                    pass

                stream_resp = await session.post(
                    f"https://claude.ai/api/organizations/{org_id}/chat_conversations/{conv_uuid}/completion",
                    json=comp_payload,
                    headers=base_headers,
                    stream=True,
                )

                if stream_resp.status_code == 429:
                    yield {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "content": "\n\n[Claude Quota Note: You have reached Claude's message limit for this 5-hour rolling window on this account. Please try again after the window resets or add an additional Claude account to the vault.]"
                            },
                            "finish_reason": "error",
                        }],
                    }
                    return

                if stream_resp.status_code >= 400:
                    err_text = stream_resp.text
                    yield {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created_ts,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {
                                "content": f"\n\n[Claude Web Ingestion Note: Direct upstream returned HTTP {stream_resp.status_code}: {err_text[:160]}]"
                            },
                            "finish_reason": "error",
                        }],
                    }
                    return

                async for line in stream_resp.aiter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8", errors="ignore") if isinstance(line, bytes) else str(line)
                    line_str = line_str.strip()
                    if line_str.startswith("data: "):
                        data_str = line_str[6:].strip()
                        if data_str in ("[DONE]", ""):
                            continue
                        try:
                            evt = json.loads(data_str)
                            completion = evt.get("completion")
                            if completion:
                                yield {
                                    "id": chat_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_ts,
                                    "model": model,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"content": completion},
                                        "finish_reason": None,
                                    }],
                                }

                            delta = evt.get("delta", {})
                            if delta.get("type") == "text_delta" and delta.get("text"):
                                yield {
                                    "id": chat_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_ts,
                                    "model": model,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"content": delta["text"]},
                                        "finish_reason": None,
                                    }],
                                }
                            elif delta.get("type") == "thinking_delta" and delta.get("thinking"):
                                yield {
                                    "id": chat_id,
                                    "object": "chat.completion.chunk",
                                    "created": created_ts,
                                    "model": model,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"reasoning_content": delta["thinking"]},
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
                    "delta": {"content": f"\n\n[Claude Engine Exception: {str(e)}]"},
                    "finish_reason": "error",
                }],
            }
    else:
        # Fallback to standard httpx client
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                try:
                    await client.post(
                        f"https://claude.ai/api/organizations/{org_id}/chat_conversations",
                        json={"uuid": conv_uuid, "name": ""},
                        headers={**base_headers, "Accept": "application/json"},
                        timeout=10.0,
                    )
                except Exception:
                    pass

                async with client.stream(
                    "POST",
                    f"https://claude.ai/api/organizations/{org_id}/chat_conversations/{conv_uuid}/completion",
                    json=comp_payload,
                    headers=base_headers,
                ) as resp:
                    if resp.status_code == 429:
                        yield {
                            "id": chat_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {
                                    "content": "\n\n[Claude Quota Note: You have reached Claude's message limit for this 5-hour rolling window on this account. Please try again after the window resets or add an additional Claude account to the vault.]"
                                },
                                "finish_reason": "error",
                            }],
                        }
                        return

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
                                    "content": f"\n\n[Claude Web Ingestion Note: Direct upstream returned HTTP {resp.status_code}: {err_text[:160]}]"
                                },
                                "finish_reason": "error",
                            }],
                        }
                        return

                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str in ("[DONE]", ""):
                                continue
                            try:
                                evt = json.loads(data_str)
                                completion = evt.get("completion")
                                if completion:
                                    yield {
                                        "id": chat_id,
                                        "object": "chat.completion.chunk",
                                        "created": created_ts,
                                        "model": model,
                                        "choices": [{
                                            "index": 0,
                                            "delta": {"content": completion},
                                            "finish_reason": None,
                                        }],
                                    }

                                delta = evt.get("delta", {})
                                if delta.get("type") == "text_delta" and delta.get("text"):
                                    yield {
                                        "id": chat_id,
                                        "object": "chat.completion.chunk",
                                        "created": created_ts,
                                        "model": model,
                                        "choices": [{
                                            "index": 0,
                                            "delta": {"content": delta["text"]},
                                            "finish_reason": None,
                                        }],
                                    }
                                elif delta.get("type") == "thinking_delta" and delta.get("thinking"):
                                    yield {
                                        "id": chat_id,
                                        "object": "chat.completion.chunk",
                                        "created": created_ts,
                                        "model": model,
                                        "choices": [{
                                            "index": 0,
                                            "delta": {"reasoning_content": delta["thinking"]},
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
                    "delta": {"content": f"\n\n[Claude Engine Exception: {str(e)}]"},
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


async def generate_claude_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute complete non-streaming chat completion."""
    full_content = []
    full_reasoning = []
    created_ts = int(time.time())
    chat_id = f"chatcmpl-claude-{uuid.uuid4().hex[:12]}"

    async for chunk in stream_claude_chat(model, messages, accounts=accounts, stream=False, **kwargs):
        choices = chunk.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            c = delta.get("content")
            r = delta.get("reasoning_content")
            if c:
                full_content.append(c)
            if r:
                full_reasoning.append(r)

    content_str = "".join(full_content)
    reasoning_str = "".join(full_reasoning) if full_reasoning else None

    msg_obj = {"role": "assistant", "content": content_str}
    if reasoning_str:
        msg_obj["reasoning_content"] = reasoning_str

    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created_ts,
        "model": model,
        "choices": [{
            "index": 0,
            "message": msg_obj,
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": len(str(messages)) // 4,
            "completion_tokens": len(content_str) // 4,
            "total_tokens": (len(str(messages)) + len(content_str)) // 4,
        },
    }
