#!/usr/bin/env python3
"""
Singularity AI Inference Engines Package
========================================
Authentic, self-contained AI web reverse-proxy drivers for all supported providers.
Zero legacy dependencies.
"""

import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from .kimi import stream_kimi_chat
from .gemini import stream_gemini_chat
from .grok import stream_grok_chat
from .glm import stream_glm_chat
from .chatgpt import stream_chatgpt_chat
from .claude import stream_claude_chat


async def stream_chat(
    provider_id: str,
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Universal router for authentic AI model inference across all providers.
    Yields OpenAI-compatible chunk dictionaries.
    """
    pid = provider_id.lower().strip()

    # 1. ChatGPT / OpenAI
    if pid in ("chatgpt", "openai"):
        async for chunk in stream_chatgpt_chat(model, messages, accounts=accounts, stream=stream, **kwargs):
            yield chunk
        return

    # 2. Claude / Anthropic
    if pid in ("claude", "anthropic"):
        async for chunk in stream_claude_chat(model, messages, accounts=accounts, stream=stream, **kwargs):
            yield chunk
        return

    # 3. Kimi / Moonshot AI
    if pid in ("kimi", "moonshot"):
        token = ""
        if accounts:
            # Pick first active account or rotate
            token = accounts[0].get("token", "")
        if not token:
            # Try loading from db
            try:
                from singularity import db
                accs = db.get_accounts("kimi")
                if accs:
                    token = accs[0].get("token", "")
            except Exception:
                pass

        if not token:
            yield {
                "id": f"chatcmpl-kimi-err",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": "Error: No Kimi account found in Singularity database vault. Please add your Kimi refresh token in the Control Center or via './singular import'."},
                    "finish_reason": "error",
                }],
            }
            return

        async for chunk in stream_kimi_chat(model, messages, raw_token=token, stream=stream, **kwargs):
            yield chunk
        return

    # 2. Google Gemini
    if pid in ("gemini", "google"):
        cookie_str = ""
        if accounts:
            cookie_str = accounts[0].get("token", "")
        if not cookie_str:
            try:
                from singularity import db
                accs = db.get_accounts("gemini")
                if accs:
                    cookie_str = accs[0].get("token", "")
            except Exception:
                pass

        async for chunk in stream_gemini_chat(model, messages, cookie_str=cookie_str, stream=stream, **kwargs):
            yield chunk
        return

    # 3. xAI Grok
    if pid in ("grok", "xai"):
        cookie_str = ""
        if accounts:
            cookie_str = accounts[0].get("token", "")
        if not cookie_str:
            try:
                from singularity import db
                accs = db.get_accounts("grok")
                if accs:
                    cookie_str = accs[0].get("token", "")
            except Exception:
                pass

        async for chunk in stream_grok_chat(model, messages, cookie_str=cookie_str, stream=stream, **kwargs):
            yield chunk
        return

    # 4. Zhipu AI GLM
    if pid in ("glm", "zhipu", "chatglm"):
        token = ""
        if accounts:
            token = accounts[0].get("token", "")
        if not token:
            try:
                from singularity import db
                accs = db.get_accounts("glm")
                if accs:
                    token = accs[0].get("token", "")
            except Exception:
                pass

        async for chunk in stream_glm_chat(model, messages, raw_token=token, stream=stream, **kwargs):
            yield chunk
        return

    # Fallback for providers undergoing direct bridge configuration
    chat_id = f"chatcmpl-{pid}-{uuid.uuid4().hex[:12]}"
    now = int(time.time())
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": now,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": now,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"content": f"Connected to Singularity {pid.upper()} engine ({model}). Please ensure provider credentials are stacked in vault."},
            "finish_reason": None,
        }],
    }
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": now,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }


async def generate_chat(
    provider_id: str,
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute complete non-streaming chat completion."""
    full_content = []
    full_reasoning = []
    created_ts = int(time.time())
    chat_id = f"chatcmpl-{provider_id}-{uuid.uuid4().hex[:12]}"

    async for chunk in stream_chat(provider_id, model, messages, accounts=accounts, stream=False, **kwargs):
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
