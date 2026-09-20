#!/usr/bin/env python3
"""
Singularity Native Qwen Engine
==============================
Authentic, self-contained multi-account streaming driver for Alibaba Qwen (chat.qwen.ai).
Supports:
- Qwen3.8-Max, Qwen3.8-Omni-Flash, Qwen3.8-Plus, Qwen3.8-Flash-Next, Qwen3.7-Plus, Qwen3.7-Max, Qwen3.6-Plus, Qwen3.5-Flash
- Wanx / Qwen-Video (t2v) text-to-video generation with async task polling & live status streaming
- Thinking Mode (qwen-thinking) with live reasoning tokens (delta.reasoning_content)
- Real-time Web Search Grounding (qwen-search) and Deep Research (qwen-deep-research)
- Multi-account token rotation from Singularity SQLite credential vault
- Automatic session lifecycle creation, reuse, and cleanup
- Full OpenAI-compatible SSE chunk streaming with simulation fallback
- 100% self-contained pure Python with zero legacy runtime dependencies
"""

import asyncio
import json
import os
import random
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

import httpx

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    from singularity import db
    from singularity.providers import get_provider_host
except ImportError:
    import db
    from providers import get_provider_host


QWEN_BASE_URL = "https://chat.qwen.ai"
QWEN_USER_INFO_URL = f"{QWEN_BASE_URL}/api/v2/user/info"
QWEN_CREATE_CHAT_URL = f"{QWEN_BASE_URL}/api/v2/chats/new"
QWEN_LIST_CHATS_URL = f"{QWEN_BASE_URL}/api/v2/chats"
QWEN_COMPLETION_URL = f"{QWEN_BASE_URL}/api/v2/chat/completions"
QWEN_TASK_STATUS_URL = f"{QWEN_BASE_URL}/api/v1/tasks/status"

QWEN_BASE_HEADERS = {
    "Host": "chat.qwen.ai",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": QWEN_BASE_URL,
    "Referer": f"{QWEN_BASE_URL}/",
    "sec-ch-ua": '"Chromium";v="149", "Google Chrome";v="149", "Not-A.Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

_ACCOUNT_ROTATION_INDEX = 0
_ROTATION_LOCK = asyncio.Lock()


def _decode_jwt(token_str: str) -> Optional[Dict[str, Any]]:
    """Decode JWT payload without verifying signature."""
    try:
        import base64
        parts = token_str.strip().split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            decoded = base64.urlsafe_b64decode(payload_b64)
            return json.loads(decoded.decode("utf-8", errors="ignore"))
    except Exception:
        pass
    return None


def extract_qwen_credentials(raw_token: str) -> Dict[str, Any]:
    """Parse raw Qwen credential string or JSON dump."""
    raw = (raw_token or "").strip()
    cookies = ""
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                token = (
                    data.get("token")
                    or data.get("userToken")
                    or data.get("user_token")
                    or data.get("value")
                    or data.get("access_token")
                    or ""
                )
                cookies = data.get("cookies") or data.get("cookie") or ""
                email = data.get("email", "")
                uid = data.get("uid") or data.get("id") or ""
                return {
                    "email": email,
                    "token": token,
                    "uid": uid,
                    "plan": data.get("plan", "FREE"),
                    "cookies": cookies,
                }
        except Exception:
            pass

    # Format: token;cookies or cookies;token
    if ";" in raw:
        parts = [p.strip() for p in raw.split(";", 1)]
        if parts[0].startswith("eyJ"):
            token = parts[0]
            cookies = parts[1]
        elif "x5sec=" in parts[0] or "bx-v" in parts[0] or "cna=" in parts[0]:
            cookies = parts[0]
            token = parts[1]
        else:
            token = raw
    else:
        token = raw

    jwt_data = _decode_jwt(token)
    email = ""
    uid = ""
    if jwt_data:
        email = jwt_data.get("email", "")
        uid = jwt_data.get("sub") or jwt_data.get("uid") or jwt_data.get("user_id") or jwt_data.get("id") or ""

    return {
        "email": email,
        "token": token,
        "uid": uid,
        "plan": "FREE",
        "cookies": cookies,
    }


def get_qwen_accounts() -> List[Dict[str, Any]]:
    """Fetch stacked Qwen credentials from SQLite database vault."""
    try:
        raw_accounts = db.get_accounts("qwen")
        accounts = []
        for item in raw_accounts:
            token_str = item.get("token", "")
            meta_str = item.get("metadata", "") or ""
            creds = extract_qwen_credentials(token_str)
            creds["id"] = item.get("id")
            creds["identifier"] = (
                creds["email"]
                or creds.get("uid")
                or f"qwen-{item.get('id', 'account')}"
            )
            creds["metadata"] = meta_str
            if meta_str:
                try:
                    meta_obj = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
                    if isinstance(meta_obj, dict):
                        if meta_obj.get("cookies") and not creds.get("cookies"):
                            creds["cookies"] = meta_obj.get("cookies")
                except Exception:
                    pass
            accounts.append(creds)
        return accounts
    except Exception:
        return []


async def _rotate_account(accounts: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Rotate round-robin through available Qwen accounts, prioritizing accounts with x5sec cookies."""
    global _ACCOUNT_ROTATION_INDEX
    accs = accounts or get_qwen_accounts()
    if not accs:
        return None

    # Filter/prioritize accounts that have valid x5sec anti-bot cookies
    valid_accs = [
        a for a in accs
        if "x5sec=" in (a.get("cookies") or "") or "x5sec=" in (a.get("metadata") or "")
    ]
    pool = valid_accs if valid_accs else accs

    async with _ROTATION_LOCK:
        idx = _ACCOUNT_ROTATION_INDEX % len(pool)
        _ACCOUNT_ROTATION_INDEX += 1
        return pool[idx]


def _resolve_qwen_model_and_features(model: str, prompt: str = "") -> Tuple[str, str, bool, bool]:
    """
    Resolve requested model name into upstream base model, chat_type, thinking_enabled, and search_enabled.
    """
    m = (model or "").lower().strip()
    p = (prompt or "").lower().strip()

    chat_type = "t2t"
    thinking_enabled = False
    search_enabled = False

    # Check mode suffixes and modalities
    if any(k in m for k in ("video", "t2v", "wanx")) or any(k in p for k in ("generate video", "create video", "make video", "render video")):
        chat_type = "t2v"
    elif any(k in m for k in ("image", "t2i")) or any(k in p for k in ("generate image", "create image", "paint picture", "draw image")):
        chat_type = "t2i"
    elif "-deep-research" in m or "-deep_research" in m:
        chat_type = "deep_research"
        search_enabled = True
    elif "-thinking" in m:
        thinking_enabled = True
    elif "-search" in m:
        search_enabled = True

    # Base model resolution
    base_model = "qwen3.7-plus"
    if "3.8-max" in m or "qwen-max" in m:
        base_model = "qwen3.8-max"
    elif "3.8-omni" in m:
        base_model = "qwen3.8-omni-flash"
    elif "3.8-flash" in m or "flash-next" in m:
        base_model = "qwen3.8-flash-next"
    elif "3.8-plus" in m or "qwen-plus" in m:
        base_model = "qwen3.8-plus"
    elif "3.7-max" in m:
        base_model = "qwen3.7-max"
    elif "3.7-plus" in m:
        base_model = "qwen3.7-plus"
    elif "3.5-flash" in m or "turbo" in m:
        base_model = "qwen3.5-flash"
    elif "3.6-plus" in m or "coder" in m:
        base_model = "qwen3.6-plus"
    elif chat_type == "t2v":
        base_model = "qwen3.7-plus"

    return base_model, chat_type, thinking_enabled, search_enabled


def messages_prepare(messages: List[Dict[str, Any]]) -> str:
    """Prepare messages list into a single clean string prompt."""
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            texts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            text = "\n".join(texts)
        else:
            text = str(content or "")

        if role == "system":
            parts.append(f"[System Instructions]\n{text}")
        elif role == "assistant":
            parts.append(f"Assistant: {text}")
        else:
            parts.append(text)

    return "\n\n".join(parts)


def extract_video_urls(text: str) -> List[str]:
    """Extract direct video URLs (.mp4, .webm, cdn.qwenlm.ai, wanx.alicdn.com) from text/json."""
    urls = []
    patterns = [
        r'https?://[^\s"\'<>]+\.(?:mp4|webm|mov)(?:\?[^\s"\'<>]*)?',
        r'https?://(?:wanx\.alicdn\.com|cdn\.qwenlm\.ai|alicdn\.com)[^\s"\'<>]+(?:video|mp4|t2v)[^\s"\'<>]*',
    ]
    for pat in patterns:
        for m in re.findall(pat, text, re.IGNORECASE):
            clean = m.rstrip(".,;)\"'>")
            if clean and clean not in urls:
                urls.append(clean)
    return urls


def extract_task_ids(text_or_obj: Any) -> List[str]:
    """Extract vision/video task IDs from API response dictionary or raw text."""
    tasks = []
    if isinstance(text_or_obj, dict):
        for k in ("task_id", "taskId", "taskID"):
            val = text_or_obj.get(k)
            if isinstance(val, str) and len(val) >= 12 and not val.startswith("http"):
                tasks.append(val)
        for v in text_or_obj.values():
            if isinstance(v, (dict, list)):
                tasks.extend(extract_task_ids(v))
    elif isinstance(text_or_obj, list):
        for item in text_or_obj:
            tasks.extend(extract_task_ids(item))
    elif isinstance(text_or_obj, str):
        for m in re.findall(r'["\']task_?id["\']\s*:\s*["\']([a-zA-Z0-9_-]+)["\']', text_or_obj, re.IGNORECASE):
            if m not in tasks:
                tasks.append(m)
    return list(dict.fromkeys(tasks))


async def _create_or_get_chat(
    headers: Dict[str, str],
    model: str,
    chat_type: str = "t2t",
) -> Optional[str]:
    """Create a new chat conversation session or obtain an existing one from chat.qwen.ai."""
    ts = int(time.time())
    payload = {
        "title": f"api_{ts}",
        "models": [model],
        "chat_mode": "normal",
        "chat_type": chat_type,
        "timestamp": ts,
    }

    # 1. Try creating a new chat session
    try:
        if HAS_CURL_CFFI:
            async with cffi_requests.AsyncSession(impersonate="chrome124", timeout=15.0) as s:
                resp = await s.post(QWEN_CREATE_CHAT_URL, headers=headers, json=payload)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if data.get("success") is not False:
                            cid = data.get("data", {}).get("id")
                            if cid:
                                return cid
                    except Exception:
                        pass
        else:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(QWEN_CREATE_CHAT_URL, headers=headers, json=payload)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        if data.get("success") is not False:
                            cid = data.get("data", {}).get("id")
                            if cid:
                                return cid
                    except Exception:
                        pass
    except Exception:
        pass

    # 2. Fallback: Retrieve existing chat session from user account
    try:
        if HAS_CURL_CFFI:
            async with cffi_requests.AsyncSession(impersonate="chrome124", timeout=15.0) as s:
                r = await s.get(f"{QWEN_LIST_CHATS_URL}?limit=5", headers=headers)
                if r.status_code == 200:
                    items = r.json().get("data", [])
                    if items and isinstance(items, list) and len(items) > 0:
                        return items[0].get("id")
        else:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(f"{QWEN_LIST_CHATS_URL}?limit=5", headers=headers)
                if r.status_code == 200:
                    items = r.json().get("data", [])
                    if items and isinstance(items, list) and len(items) > 0:
                        return items[0].get("id")
    except Exception:
        pass

    # 3. Final fallback: Use random client-side UUIDv4
    return str(uuid.uuid4())


async def _poll_video_task(
    headers: Dict[str, str],
    task_id: str,
    timeout: float = 360.0,
) -> AsyncIterator[Tuple[str, Optional[str]]]:
    """
    Poll Qwen video generation task (/api/v1/tasks/status/{task_id}).
    Yields (status_message, video_url_or_none).
    """
    poll_url = f"{QWEN_TASK_STATUS_URL}/{task_id}"
    start_time = time.time()
    last_phase = ""

    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)
        try:
            body = ""
            status_code = 0
            if HAS_CURL_CFFI:
                async with cffi_requests.AsyncSession(impersonate="chrome124", timeout=20.0) as s:
                    r = await s.get(poll_url, headers=headers)
                    status_code = r.status_code
                    body = r.text
            else:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    r = await client.get(poll_url, headers=headers)
                    status_code = r.status_code
                    body = r.text

            if status_code == 200:
                urls = extract_video_urls(body)
                if urls:
                    yield ("Finished video rendering!", urls[0])
                    return

                try:
                    data = json.loads(body)
                    task_data = data.get("data", {})
                    task_status = str(task_data.get("task_status") or task_data.get("status") or "").upper()
                    phase = task_data.get("phase") or task_status

                    if task_status in ("SUCCESS", "SUCCEEDED"):
                        task_urls = extract_video_urls(str(data))
                        if task_urls:
                            yield ("Video synthesis completed successfully!", task_urls[0])
                            return
                        yield ("Video synthesis finished.", None)
                        return
                    elif task_status in ("FAILED", "ERROR"):
                        err_msg = task_data.get("message") or "Video task reported failure"
                        yield (f"Video generation error: {err_msg}", None)
                        return
                    else:
                        yield (f"Synthesizing video keyframes with Wanx 2.1 ({elapsed}s elapsed)...", None)
                except Exception:
                    yield (f"Rendering video stream ({elapsed}s elapsed)...", None)
        except Exception:
            yield (f"Awaiting video render completion ({elapsed}s)...", None)

        await asyncio.sleep(5.0)

    yield ("Video generation request timed out after 6 minutes.", None)


def _build_chat_payload(
    chat_id: str,
    model: str,
    prompt: str,
    chat_type: str,
    thinking_enabled: bool,
    search_enabled: bool,
    stream: bool = True,
) -> Dict[str, Any]:
    """Build the Qwen /api/v2/chat/completions JSON payload."""
    ts = int(time.time())
    fid = uuid.uuid4().hex
    cid = uuid.uuid4().hex

    if chat_type == "t2v":
        feature_config = {
            "thinking_enabled": False,
            "output_schema": "phase",
            "auto_thinking": False,
            "thinking_mode": "off",
            "auto_search": False,
            "code_interpreter": False,
            "function_calling": False,
            "plugins_enabled": True,
            "video_generation": True,
            "default_aspect_ratio": "1:1",
        }
        msg_chat_type = "t2v"
        sub_chat_type = "t2v"
        extra_meta = {
            "subChatType": "t2v",
            "mode": "video_generation",
            "aspectRatio": "1:1",
            "size": "1:1",
        }
    elif chat_type in ("t2i", "image_gen"):
        feature_config = {
            "thinking_enabled": False,
            "output_schema": "phase",
            "auto_thinking": False,
            "thinking_mode": "off",
            "auto_search": False,
            "code_interpreter": False,
            "function_calling": False,
            "plugins_enabled": True,
            "image_generation": True,
            "default_aspect_ratio": "1:1",
        }
        msg_chat_type = "t2t"
        sub_chat_type = "t2i"
        extra_meta = {
            "subChatType": "t2i",
            "mode": "image_generation",
            "aspectRatio": "1:1",
            "size": "1:1",
        }
    else:
        feature_config = {
            "thinking_enabled": thinking_enabled,
            "output_schema": "phase",
            "research_mode": "normal",
            "auto_thinking": thinking_enabled,
            "thinking_mode": "Auto" if thinking_enabled else "Disabled",
            "thinking_format": "summary",
            "auto_search": search_enabled or chat_type == "deep_research",
            "code_interpreter": False,
            "plugins_enabled": False,
            "function_calling": False,
            "enable_tools": False,
            "enable_function_call": False,
            "tool_choice": "none",
        }
        msg_chat_type = chat_type
        sub_chat_type = chat_type
        extra_meta = {"subChatType": chat_type}

    payload = {
        "stream": stream,
        "version": "2.1",
        "incremental_output": True,
        "chat_id": chat_id,
        "chat_mode": "normal",
        "model": model,
        "parent_id": None,
        "messages": [{
            "fid": fid,
            "parentId": None,
            "childrenIds": [cid],
            "role": "user",
            "content": prompt,
            "user_action": "chat",
            "files": [],
            "timestamp": ts,
            "models": [model],
            "chat_type": msg_chat_type,
            "feature_config": feature_config,
            "extra": {"meta": extra_meta},
            "sub_chat_type": sub_chat_type,
            "parent_id": None,
        }],
        "timestamp": ts,
    }

    if chat_type in ("t2v", "t2i", "image_gen"):
        payload["size"] = "1:1"

    return payload


# -------------------------------------------------------------------
# Universal Qwen Stream Handler
# -------------------------------------------------------------------

async def stream_qwen_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    stream: bool = True,
    simulate: bool = False,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream chat completion chunks from Alibaba Qwen (chat.qwen.ai).
    Supports text, reasoning, image, and native video (Wanx) generation.
    Yields OpenAI-compatible SSE chunk dictionaries.
    """
    req_id = f"chatcmpl-qwen-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    final_prompt = messages_prepare(messages)
    base_model, chat_type, thinking_enabled, search_enabled = _resolve_qwen_model_and_features(model, final_prompt)

    # 1. Device Simulation Mode
    if simulate or os.getenv("SINGULARITY_SIMULATE", "0") in ("1", "true", "yes", "on"):
        if chat_type == "t2v":
            sim_video_text = (
                f"🎬 **Singularity Cinematic Video Synthesis** (Simulated Response)\n\n"
                f"• **Model:** `{model}` (Upstream: `Wanx 2.1 / {base_model}`)\n"
                f"• **Prompt:** *\"{final_prompt or 'Dynamic neural frame generation'}\"*\n"
                f"• **Specs:** 720p HD • 24 FPS • H.264 MP4\n\n"
                f"[Generated Video](/static/demo_video.mp4)"
            )
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": sim_video_text}, "finish_reason": None}],
            }
            await asyncio.sleep(0.05)
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            return

        sim_thinking = "Analyzing query with Qwen3.8 cognitive architecture...\n1. Query intent extraction\n2. Knowledge verification\n3. Solution formulation."
        sim_response = f"Hello from Singularity's native Alibaba Qwen engine! Currently running simulated response for '{model}' (Upstream: {base_model}). Streaming SSE buffers and session management are functioning cleanly."

        if thinking_enabled:
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "reasoning_content": sim_thinking + "\n\n"},
                    "finish_reason": None,
                }],
            }
            await asyncio.sleep(0.05)

        for word in sim_response.split(" "):
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": word + " "},
                    "finish_reason": None,
                }],
            }
            await asyncio.sleep(0.02)

        yield {
            "id": req_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        return

    # 2. Direct Native Web2API Reverse-Proxy
    account = await _rotate_account(accounts)
    token = account.get("token", "").strip() if account else ""
    if not token:
        token = os.getenv("QWEN_TOKEN", "")

    cookies = (account.get("cookies") or "").strip() if account else ""
    if not cookies and account:
        meta_raw = account.get("metadata") or "{}"
        try:
            meta_obj = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            if isinstance(meta_obj, dict):
                cookies = meta_obj.get("cookies", "").strip()
        except Exception:
            pass
    if not cookies:
        cookies = os.getenv("QWEN_COOKIES", "").strip()

    if not token:
        yield {
            "id": req_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": "Qwen Notice: No active account found in Singularity vault.\nPlease import your credentials from chat.qwen.ai using './singular import <token_or_json>'."
                },
                "finish_reason": "error",
            }],
        }
        return

    # Ensure token cookie is present in Cookie string if omitted
    if cookies and "token=" not in cookies and token.startswith("eyJ"):
        cookies = f"token={token}; {cookies}"

    auth_headers = {
        **QWEN_BASE_HEADERS,
        "Authorization": f"Bearer {token}",
        "x-request-id": str(uuid.uuid4()),
    }
    if cookies:
        auth_headers["Cookie"] = cookies

    # Obtain chat session ID
    chat_id = await _create_or_get_chat(auth_headers, base_model, chat_type)

    # ---------------------------------------------------------------
    # Path A: Native Video Generation Workflow (chat_type == "t2v")
    # ---------------------------------------------------------------
    if chat_type == "t2v":
        payload = _build_chat_payload(
            chat_id, base_model, final_prompt, chat_type="t2v",
            thinking_enabled=False, search_enabled=False, stream=False
        )
        stream_url = f"{QWEN_COMPLETION_URL}?chat_id={chat_id}"
        req_headers = {
            **auth_headers,
            "Referer": f"{QWEN_BASE_URL}/c/{chat_id}",
            "x-request-id": str(uuid.uuid4()),
        }

        yield {
            "id": req_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": "🎬 Initializing video synthesis with Alibaba Wanx 2.1...\n\n"},
                "finish_reason": None,
            }],
        }

        body_text = ""
        status_code = 0
        try:
            if HAS_CURL_CFFI:
                async with cffi_requests.AsyncSession(impersonate="chrome124", timeout=90.0) as session:
                    resp = await session.post(stream_url, headers=req_headers, json=payload)
                    status_code = resp.status_code
                    body_text = resp.text
            else:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    resp = await client.post(stream_url, headers=req_headers, json=payload)
                    status_code = resp.status_code
                    body_text = resp.text
        except Exception as e:
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": f"\n\nVideo upstream error: {str(e)}"},
                    "finish_reason": "error",
                }],
            }
            return

        # Check for Aliyun WAF Slider Challenge
        if "RGV587" in body_text or "FAIL_SYS_USER_VALIDATE" in body_text or "bxpunish" in body_text:
            punish_url_match = re.search(r'https?://[^\s"\'<>]+\/punish\?[^\s"\'<>]+', body_text)
            punish_url = punish_url_match.group(0) if punish_url_match else f"{QWEN_BASE_URL}/"
            if "x5referer=" not in punish_url:
                sep = "&" if "?" in punish_url else "?"
                punish_url += f"{sep}x5referer=https%3A%2F%2Fchat.qwen.ai%2F"

            warn_msg = (
                "\n\n⚠️ **Alibaba Cloud Security Slider Verification Required (RGV587)**\n\n"
                "Alibaba Cloud WAF requires a quick one-time slider check to generate your session's anti-bot token (`x5sec`).\n\n"
                f"👉 **[Click Here to Complete Slider Verification]({punish_url})**\n\n"
                "1. Open the link above in your browser where `chat.qwen.ai` is logged in.\n"
                "2. Slide the verification puzzle piece to verify.\n"
                "3. Once verified, rerun your request.\n"
            )
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": warn_msg}, "finish_reason": "error"}],
            }
            return

        # Check for immediate video URLs
        urls = extract_video_urls(body_text)
        task_ids = extract_task_ids(body_text)

        if not urls and task_ids:
            task_id = task_ids[0]
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": f"Task ID registered: `{task_id}`. Rendering video sequence...\n"},
                    "finish_reason": None,
                }],
            }

            async for status_msg, found_url in _poll_video_task(auth_headers, task_id):
                if found_url:
                    urls = [found_url]
                    break
                yield {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"• {status_msg}\n"},
                        "finish_reason": None,
                    }],
                }

        if urls:
            vid_url = urls[0]
            final_md = (
                f"\n\n🎬 **Video Generated Successfully** (Wanx 2.1)\n\n"
                f"• **Model:** `{model}`\n"
                f"• **Prompt:** *\"{final_prompt}\"*\n\n"
                f"[Generated Video]({vid_url})\n\n"
            )
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": final_md},
                    "finish_reason": None,
                }],
            }
        else:
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": f"\n\nVideo generation completed but no video URL was returned. Upstream response:\n`{body_text[:300]}`"},
                    "finish_reason": "error",
                }],
            }

        yield {
            "id": req_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        return

    # ---------------------------------------------------------------
    # Path B: Standard Conversational & Reasoning Stream (chat_type == "t2t")
    # ---------------------------------------------------------------
    payload = _build_chat_payload(chat_id, base_model, final_prompt, chat_type, thinking_enabled, search_enabled, stream=True)
    stream_url = f"{QWEN_COMPLETION_URL}?chat_id={chat_id}"
    stream_headers = {
        **auth_headers,
        "Referer": f"{QWEN_BASE_URL}/c/{chat_id}",
        "x-request-id": str(uuid.uuid4()),
    }

    try:
        if HAS_CURL_CFFI:
            async with cffi_requests.AsyncSession(impersonate="chrome124", timeout=120.0) as session:
                resp = await session.post(stream_url, headers=stream_headers, json=payload, stream=True)
                first_chunk = True
                async for raw_line in resp.aiter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="ignore") if isinstance(raw_line, bytes) else raw_line
                    line = line.strip()

                    # Handle WAF challenge in stream
                    if "RGV587" in line or "FAIL_SYS_USER_VALIDATE" in line:
                        punish_url_match = re.search(r'https?://[^\s"\'<>]+\/punish\?[^\s"\'<>]+', line)
                        punish_url = punish_url_match.group(0) if punish_url_match else f"{QWEN_BASE_URL}/"
                        if "x5referer=" not in punish_url:
                            sep = "&" if "?" in punish_url else "?"
                            punish_url += f"{sep}x5referer=https%3A%2F%2Fchat.qwen.ai%2F"
                        yield {
                            "id": req_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {
                                    "content": (
                                        "⚠️ **Alibaba Cloud Security Slider Verification Required (RGV587)**\n\n"
                                        "Alibaba Cloud WAF requires a quick one-time slider check to generate your session's anti-bot token (`x5sec`).\n\n"
                                        f"👉 **[Click Here to Complete Slider Verification]({punish_url})**\n\n"
                                        "1. Open the link above in your browser where `chat.qwen.ai` is logged in.\n"
                                        "2. Slide the verification puzzle piece to verify.\n"
                                        "3. Once verified, rerun your request.\n"
                                    )
                                },
                                "finish_reason": "error",
                            }],
                        }
                        return

                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        break
                    try:
                        item = json.loads(data_str)
                    except Exception:
                        continue

                    if not isinstance(item, dict):
                        continue

                    content = ""
                    reasoning = ""
                    choices = item.get("choices", [])
                    if choices and isinstance(choices, list) and len(choices) > 0:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        reasoning = (
                            delta.get("reasoning_content")
                            or delta.get("reasoning")
                            or delta.get("reasoning_text")
                            or delta.get("thinking")
                            or ""
                        )
                    else:
                        content = item.get("content") or item.get("answer") or item.get("text") or ""
                        reasoning = item.get("reasoning_content") or item.get("reasoning") or item.get("thinking") or ""

                    delta_dict: Dict[str, Any] = {}
                    if first_chunk:
                        delta_dict["role"] = "assistant"
                        first_chunk = False

                    if reasoning:
                        delta_dict["reasoning_content"] = reasoning
                    elif content:
                        delta_dict["content"] = content

                    if delta_dict:
                        yield {
                            "id": req_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": delta_dict,
                                "finish_reason": None,
                            }],
                        }
        else:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", stream_url, headers=stream_headers, json=payload, timeout=120.0) as resp:
                    first_chunk = True
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        line = line.strip()

                        if "RGV587" in line or "FAIL_SYS_USER_VALIDATE" in line:
                            punish_url_match = re.search(r'https?://[^\s"\'<>]+\/punish\?[^\s"\'<>]+', line)
                            punish_url = punish_url_match.group(0) if punish_url_match else f"{QWEN_BASE_URL}/"
                            if "x5referer=" not in punish_url:
                                sep = "&" if "?" in punish_url else "?"
                                punish_url += f"{sep}x5referer=https%3A%2F%2Fchat.qwen.ai%2F"
                            yield {
                                "id": req_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {
                                        "content": (
                                            "⚠️ **Alibaba Cloud Security Slider Verification Required (RGV587)**\n\n"
                                            "Alibaba Cloud WAF requires a quick one-time slider check to generate your session's anti-bot token (`x5sec`).\n\n"
                                            f"👉 **[Click Here to Complete Slider Verification]({punish_url})**\n\n"
                                            "1. Open the link above in your browser where `chat.qwen.ai` is logged in.\n"
                                            "2. Slide the verification puzzle piece to verify.\n"
                                            "3. Once verified, rerun your request.\n"
                                        )
                                    },
                                    "finish_reason": "error",
                                }],
                            }
                            return

                        if not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            break
                        try:
                            item = json.loads(data_str)
                        except Exception:
                            continue

                        if not isinstance(item, dict):
                            continue

                        content = ""
                        reasoning = ""
                        choices = item.get("choices", [])
                        if choices and isinstance(choices, list) and len(choices) > 0:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            reasoning = (
                                delta.get("reasoning_content")
                                or delta.get("reasoning")
                                or delta.get("reasoning_text")
                                or delta.get("thinking")
                                or ""
                            )
                        else:
                            content = item.get("content") or item.get("answer") or item.get("text") or ""
                            reasoning = item.get("reasoning_content") or item.get("reasoning") or item.get("thinking") or ""

                        delta_dict = {}
                        if first_chunk:
                            delta_dict["role"] = "assistant"
                            first_chunk = False

                        if reasoning:
                            delta_dict["reasoning_content"] = reasoning
                        elif content:
                            delta_dict["content"] = content

                        if delta_dict:
                            yield {
                                "id": req_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": delta_dict,
                                    "finish_reason": None,
                                }],
                            }

        # Final stop chunk
        yield {
            "id": req_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    except Exception as stream_exc:
        yield {
            "id": req_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": f"\n\n[Qwen Streaming Exception: {str(stream_exc)}]"},
                "finish_reason": "error",
            }],
        }


async def generate_qwen_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Generate complete non-streaming chat completion from Qwen."""
    content_parts = []
    reasoning_parts = []
    req_id = f"chatcmpl-qwen-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    async for chunk in stream_qwen_chat(model, messages, accounts=accounts, stream=False, **kwargs):
        choices = chunk.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            if "content" in delta and delta["content"]:
                content_parts.append(delta["content"])
            if "reasoning_content" in delta and delta["reasoning_content"]:
                reasoning_parts.append(delta["reasoning_content"])

    full_content = "".join(content_parts)
    full_reasoning = "".join(reasoning_parts)

    msg: Dict[str, Any] = {"role": "assistant", "content": full_content}
    if full_reasoning:
        msg["reasoning_content"] = full_reasoning

    return {
        "id": req_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "message": msg,
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": len(str(messages)) // 4,
            "completion_tokens": len(full_content) // 4,
            "total_tokens": (len(str(messages)) + len(full_content)) // 4,
        },
    }
