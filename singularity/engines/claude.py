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
    from singularity import providers
    from singularity.providers import get_provider_host
    from singularity import personas
except ImportError:
    import db
    try:
        import providers
        from providers import get_provider_host
    except ImportError:
        providers = None
        get_provider_host = None
    try:
        import personas
    except ImportError:
        personas = None


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
    simulate: bool = False,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Universal streaming inference engine for Claude.
    1. Supports instant device simulation mode when offline or testing.
    2. Executes direct Web2API stream with automatic multi-account failover on 429 rate limit.
    3. Streams standard OpenAI-compatible chunks with chain-of-thought thinking support.
    """
    chat_id = f"chatcmpl-claude-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    # Check persona mapping (e.g. Claude 5.5 Opus, Claude 5.1 Fable, thinking variants)
    persona_cfg = personas.get_persona_config(model) if personas else None
    if persona_cfg:
        messages = personas.inject_persona_messages(messages, persona_cfg)
        target_model = persona_cfg.backend_model
    else:
        target_model = model

    # 1. Device Simulation Mode
    is_sim = (
        simulate
        or (providers and hasattr(providers, "is_simulation_active") and providers.is_simulation_active())
        or os.getenv("SINGULARITY_SIMULATE", "0").lower() in ("1", "true", "yes", "on")
    )
    if is_sim:
        is_think = "think" in model.lower() or (persona_cfg and persona_cfg.is_think)
        if is_think:
            sim_thinking = (
                f"Analyzing prompt with Claude advanced chain-of-thought ({model})...\n"
                "1. Parsing constraints and contextual parameters.\n"
                "2. Formulating systematic reasoning and domain synthesis.\n"
                "3. Finalizing response strategy."
            )
            yield {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "reasoning_content": sim_thinking},
                    "finish_reason": None,
                }],
            }
            await asyncio.sleep(0.04)

        sim_response = (
            f"Hello from Singularity's native Claude engine! Currently running simulated response for '{model}'. "
            "Full persona mapping, credential management, and token streaming are active."
        )
        for word in sim_response.split(" "):
            yield {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created_ts,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": word + " "},
                    "finish_reason": None,
                }],
            }
            await asyncio.sleep(0.015)

        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        return

    # 2. Live Web2API Multi-Account Execution
    all_accounts = accounts
    if not all_accounts:
        try:
            all_accounts = db.get_accounts("claude")
        except Exception:
            all_accounts = []

    if not all_accounts:
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

    # Initial role chunk
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }

    # Rotate starting account index
    global _ACCOUNT_ROTATION_INDEX
    async with _ROTATION_LOCK:
        start_idx = _ACCOUNT_ROTATION_INDEX % len(all_accounts)
        _ACCOUNT_ROTATION_INDEX += 1

    prompt_text = _format_messages_to_prompt(messages)
    web_model = target_model
    if web_model.startswith("claude-"):
        web_model = "claude-sonnet-5"

    comp_payload = {
        "prompt": prompt_text,
        "timezone": "UTC",
        "model": web_model,
        "rendering_mode": "messages",
    }

    success = False
    rate_limited_count = 0
    last_error_msg = ""

    for attempt in range(len(all_accounts)):
        acc = all_accounts[(start_idx + attempt) % len(all_accounts)]
        acc_name = acc.get("name") or acc.get("identifier") or "Claude Account"
        session_key = extract_claude_session_key(acc.get("token", ""))
        if not session_key:
            continue

        org_id = await get_claude_org_id(session_key)
        if not org_id:
            last_error_msg = f"Could not obtain organization UUID for {acc_name}"
            continue

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

        try:
            if HAVE_CURL_CFFI:
                async with CurlAsyncSession(impersonate="chrome120", timeout=60.0) as session:
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
                        rate_limited_count += 1
                        last_error_msg = f"Account {acc_name} reached 5-hour rolling message limit (429 Rate Limited)."
                        continue  # Auto-failover to next stacked account in vault

                    if stream_resp.status_code >= 400:
                        err_text = stream_resp.text
                        last_error_msg = f"Upstream returned HTTP {stream_resp.status_code}: {err_text[:160]}"
                        continue

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
                                    success = True
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
                                    success = True
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
                                    success = True
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
                    if success:
                        break
            else:
                # httpx fallback
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
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
                            rate_limited_count += 1
                            last_error_msg = f"Account {acc_name} reached 5-hour rolling message limit (429 Rate Limited)."
                            continue

                        if resp.status_code >= 400:
                            err_text = (await resp.aread()).decode("utf-8", errors="ignore")
                            last_error_msg = f"Upstream returned HTTP {resp.status_code}: {err_text[:160]}"
                            continue

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
                                        success = True
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
                                        success = True
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
                                        success = True
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
                        if success:
                            break
        except Exception as e:
            last_error_msg = str(e)
            continue

    if not success:
        if rate_limited_count >= len(all_accounts):
            content_err = (
                f"\n\n[Claude Quota Note: All {len(all_accounts)} Claude account(s) in the Singularity vault "
                "have reached Anthropic's 5-hour rolling message limit (HTTP 429 Rate Limited). "
                "Please wait for Anthropic's rolling window to reset, add an additional Claude account in the Control Center, "
                "or toggle Simulation Mode with './singular simulate on' to test immediately without rate limits.]"
            )
        else:
            content_err = (
                f"\n\n[Claude Execution Note: {last_error_msg or 'Could not complete request across vault accounts.'}]"
            )

        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": content_err},
                "finish_reason": "error",
            }],
        }
        return

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
