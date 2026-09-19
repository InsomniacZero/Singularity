#!/usr/bin/env python3
"""
Singularity Native Grok Engine
===============================
Direct xAI Grok Web WebSocket reverse-proxy client.
100% self-contained pure Python with zero legacy dependencies.
"""

import asyncio
import json
import os
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    import websockets
except ImportError:
    websockets = None


def _format_messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            sub_txt = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    sub_txt.append(item.get("text", ""))
                elif isinstance(sub, str):
                    sub_txt.append(item)
            content = " ".join(sub_txt)
        content_str = str(content).strip()
        if not content_str:
            continue
        if role == "system":
            parts.append(f"[System: {content_str}]")
        elif role == "assistant":
            parts.append(f"[Assistant]: {content_str}")
        else:
            parts.append(f"[User]: {content_str}")
    return "\n\n".join(parts) if parts else "Hello"


def _parse_grok_creds(cookie_str: str) -> Dict[str, str]:
    sso = ""
    uid = ""
    sso_m = re.search(r"sso=([^;]+)", cookie_str)
    uid_m = re.search(r"x-userid=([^;]+)", cookie_str)
    if sso_m:
        sso = sso_m.group(1).strip()
    if uid_m:
        uid = uid_m.group(1).strip()
    if not sso and len(cookie_str) > 20 and ";" not in cookie_str:
        sso = cookie_str.strip()
    if not uid:
        uid = "b9e803ff-94ed-46c1-88bd-4baf02c5ccfe"
    return {"sso": sso, "uid": uid}


async def stream_grok_chat(
    model: str,
    messages: List[Dict[str, Any]],
    cookie_str: Optional[str] = None,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """Stream chat completions from xAI Grok Web WebSocket API."""
    if not websockets:
        yield {
            "id": f"chatcmpl-grok-err",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"content": "Error: 'websockets' python library is required for Grok."}, "finish_reason": "error"}],
        }
        return

    creds = _parse_grok_creds(cookie_str or os.getenv("GROK_COOKIE", ""))
    sso = creds["sso"]
    uid = creds["uid"]
    if not sso:
        yield {
            "id": f"chatcmpl-grok-err",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {"content": "Error: No Grok SSO cookie found in vault."}, "finish_reason": "error"}],
        }
        return

    m_clean = model.lower().strip()
    mode_name = "grok-3"
    if "thinking" in m_clean:
        mode_name = "thinking"
    elif "deepsearch" in m_clean or "search" in m_clean:
        mode_name = "deepsearch"
    elif "fast" in m_clean:
        mode_name = "fast"
    elif "auto" in m_clean:
        mode_name = "auto"
    elif "heavy" in m_clean:
        mode_name = "heavy"

    prompt = _format_messages_to_prompt(messages)
    chat_id = f"chatcmpl-grok-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    ws_url = f"wss://grok.com/ws/mgw/?uid={uid}"
    headers = {
        "Origin": "https://grok.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Cookie": f"sso={sso}; sso-rw={sso}; x-userid={uid}",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    # Initial role chunk
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }

    try:
        async with websockets.connect(ws_url, additional_headers=headers, open_timeout=15) as ws:
            init_payload = {
                "event": {
                    "type": "session.create",
                    "event_id": f"evt_{uuid.uuid4()}",
                    "session": {
                        "model": mode_name,
                        "x_grok": {
                            "protocol_capabilities": ["conversation_attached", "custom_methods_v1"],
                            "use_chunk": True,
                            "enable_side_by_side": True,
                            "force_side_by_side": False,
                            "enable_image_generation": False,
                            "disable_text_follow_ups": False,
                            "disable_artifact": True,
                            "force_concise": False,
                            "keep_context": False,
                            "is_temporary": True,
                            "disable_memory": True,
                        },
                    },
                }
            }
            await ws.send(json.dumps(init_payload))

            turn_sent = False
            session_id = ""

            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=45)
                data = json.loads(msg)
                evt = data.get("event", {})
                etype = evt.get("type", "")

                if etype == "session.created":
                    session_id = data.get("session_id", "")
                elif etype == "conversation.attached" or (session_id and not turn_sent):
                    turn_sent = True
                    turn_payload = {
                        "event": {
                            "type": "conversation.turn_create",
                            "event_id": f"evt_turn_{uuid.uuid4()}",
                            "turn": {
                                "messages": [{
                                    "role": "user",
                                    "content": prompt,
                                }]
                            }
                        }
                    }
                    await ws.send(json.dumps(turn_payload))
                elif etype == "response.chunk":
                    chunk = evt.get("chunk", {})
                    text_obj = chunk.get("text", {})
                    channel = text_obj.get("channel", "")
                    chunk_str = text_obj.get("text", "")
                    if chunk_str:
                        if "THINK" in channel.upper():
                            yield {
                                "id": chat_id,
                                "object": "chat.completion.chunk",
                                "created": created_ts,
                                "model": model,
                                "choices": [{"index": 0, "delta": {"reasoning_content": chunk_str}, "finish_reason": None}],
                            }
                        else:
                            yield {
                                "id": chat_id,
                                "object": "chat.completion.chunk",
                                "created": created_ts,
                                "model": model,
                                "choices": [{"index": 0, "delta": {"content": chunk_str}, "finish_reason": None}],
                            }
                elif etype in ("response.completed", "response.done", "conversation.turn_completed"):
                    break
    except Exception as e:
        yield {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": f"\n\n[Grok Stream Error: {str(e)}]"}, "finish_reason": "error"}],
        }
        return

    # Final stop chunk
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
