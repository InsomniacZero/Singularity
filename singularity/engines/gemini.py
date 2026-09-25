#!/usr/bin/env python3
"""
Singularity Native Gemini Engine
=================================
Direct Google Gemini Web (Batchexecute / assistant-bard) reverse-proxy client.
Supports guest mode (zero cookie) and authenticated mode (__Secure-1PSID).
100% self-contained pure Python with zero legacy dependencies.
"""

import asyncio
import base64
import json
import os
from pathlib import Path
import re
import time
import urllib.parse
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

GEMINI_BL = os.getenv("GEMINI_BL", "boq_assistant-bard-web-server_20260923.22_p0")

MODEL_CONFIGS = {
    "gemini-3.8-flash": {"mode": 1, "think": 4},
    "gemini-3.8-flash-thinking": {"mode": 2, "think": 0},
    "gemini-3.7-flash": {"mode": 1, "think": 4},
    "gemini-3.7-flash-thinking": {"mode": 2, "think": 0},
    "gemini-3.6-flash": {"mode": 1, "think": 4},
    "gemini-3.6-flash-thinking": {"mode": 2, "think": 0},
    "gemini-3.5-flash": {"mode": 1, "think": 4},
    "gemini-3.5-flash-thinking": {"mode": 2, "think": 0},
    "gemini-3.5-flash-lite": {"mode": 6, "think": 4},
    "gemini-3.1-pro": {"mode": 3, "think": 4},
    "gemini-3.1-pro-thinking": {"mode": 3, "think": 0},
    # Google Omni Family (Any-to-any multimodal & conversational video editing)
    "gemini-omni-flash": {"mode": 1, "think": 4},
    "gemini-omni-1.1-flash": {"mode": 1, "think": 4},
    "gemini-omni-pro": {"mode": 3, "think": 4},
    "google-omni": {"mode": 1, "think": 4},
    "google-omni-flash": {"mode": 1, "think": 4},
    "gemini-omni": {"mode": 1, "think": 4},
    # Google Veo Family (Cinematic generative video & synced audio)
    "veo-3.1-generate-preview": {"mode": 1, "think": 4},
    "veo-3.1-fast-generate-preview": {"mode": 1, "think": 4},
    "veo-3.1-lite": {"mode": 1, "think": 4},
    "veo-3.0": {"mode": 1, "think": 4},
    "veo-2.0-generate-001": {"mode": 1, "think": 4},
    "veo-2": {"mode": 1, "think": 4},
    # Nano Banana / Imagen Image Models
    "nano-banana-2": {"mode": 1, "think": 4},
    "nano-banana-pro": {"mode": 3, "think": 4},
    "nano-banana-2-lite": {"mode": 6, "think": 4},
    "nano-banana": {"mode": 1, "think": 4},
    "imagen-4.0-generate-proto": {"mode": 1, "think": 4},
}

_SESSION_CACHE: Dict[str, Dict[str, Any]] = {}


async def _get_gemini_session_context(cookie_str: Optional[str]) -> Tuple[str, str]:
    """Retrieve or dynamically extract SNlM0e XSRF token and active build label for Google Gemini."""
    cache_key = cookie_str or "guest"
    now = time.time()
    cached = _SESSION_CACHE.get(cache_key)
    if cached and (now - cached.get("ts", 0) < 600.0) and cached.get("snlm0e"):
        return cached["snlm0e"], cached["bl"]

    snlm0e = ""
    bl = os.getenv("GEMINI_BL", "boq_assistant-bard-web-server_20260923.22_p0")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://gemini.google.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if cookie_str:
        headers["Cookie"] = cookie_str

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get("https://gemini.google.com/app", headers=headers)
            if resp.status_code == 200:
                sn_match = re.findall(r'"SNlM0e":"([^"]+)"', resp.text)
                if sn_match:
                    snlm0e = sn_match[0]
                bl_match = re.findall(r'"cfb2h":"([^"]+)"', resp.text)
                if bl_match:
                    bl = bl_match[0]
    except Exception:
        pass

    if snlm0e:
        _SESSION_CACHE[cache_key] = {"snlm0e": snlm0e, "bl": bl, "ts": now}
    return snlm0e, bl


async def _download_gemini_image(img_url: str, cookie_str: Optional[str]) -> Optional[str]:
    """Download Google Gemini generated image via authenticated ALR redirection hops."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://gemini.google.com/",
    }
    if cookie_str:
        headers["Cookie"] = cookie_str

    curr = img_url
    if "=d-I?alr=yes" not in curr:
        curr = curr + "=d-I?alr=yes"

    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            for _ in range(4):
                r = await client.get(curr)
                ct = r.headers.get("content-type", "")
                if "image/" in ct or len(r.content) > 10000:
                    file_id = f"gemini_{uuid.uuid4().hex[:12]}"
                    gen_dir = Path(__file__).resolve().parent.parent / "static" / "generated"
                    gen_dir.mkdir(parents=True, exist_ok=True)
                    out_path = gen_dir / f"{file_id}.png"
                    out_path.write_bytes(r.content)
                    b64 = base64.b64encode(r.content).decode("utf-8")
                    return f"data:image/png;base64,{b64}"
                nxt = r.text.strip()
                if nxt.startswith("http"):
                    curr = nxt
                else:
                    break
    except Exception:
        pass
    return None


def _clean_gemini_text(text: str, strip: bool = True) -> str:
    """Clean internal Google Gemini artifacts and chips."""
    text = re.sub(
        r'```(?:python|javascript|text)\?code_(?:reference|stdout)&code_event_index=\d+\n.*?```\n?',
        '', text, flags=re.DOTALL
    )
    text = re.sub(
        r'</?(?:Elic[ia]t|Suggest|FollowUp|ActionCard|RelatedQueries)[A-Za-z0-9_]*[^>]*>.*?(?:</(?:Elic[ia]t|Suggest|FollowUp|ActionCard|RelatedQueries)[A-Za-z0-9_]*>|$)|</?(?:Elic[ia]t|Suggest|FollowUp|ActionCard|RelatedQueries)[A-Za-z0-9_]*[^>]*/?>',
        '', text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r'<[A-Za-z0-9_-]+[^>]*\b(?:label|query)=[\'"][^\'"]*[\'"][^>]*>.*?</[A-Za-z0-9_-]+>',
        '', text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r'<[A-Za-z0-9_-]+[^>]*\b(?:label|query)=[\'"][^\'"]*[\'"][^>]*/?>',
        '', text, flags=re.IGNORECASE
    )
    text = re.sub(r'</?(?:[A-Za-z0-9_]*(?:Elic|Sugg|Follow|Action)[A-Za-z0-9_]*)[^>]*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<[A-Za-z0-9_]+[^>]*$', '', text)
    text = re.sub(r'^(?:\[(?:Assistant|Model)\]:?|(?:Assistant|Model):)\s*', '', text, flags=re.IGNORECASE)
    return text.strip() if strip else text


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
                elif isinstance(item, str):
                    sub_txt.append(item)
            content = " ".join(sub_txt)
        content_str = str(content).strip()
        if not content_str:
            continue
        if role == "system":
            parts.append(f"[System Instructions: {content_str}]")
        elif role == "assistant":
            parts.append(f"[Assistant]: {content_str}")
        else:
            parts.append(f"[User]: {content_str}")
    return "\n\n".join(parts) if parts else "Hello"


async def stream_gemini_chat(
    model: str,
    messages: List[Dict[str, Any]],
    cookie_str: Optional[str] = None,
    accounts: Optional[List[Dict[str, Any]]] = None,
    stream: bool = True,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """Stream chat completions from Google Gemini Web API with authentic session & image generation support."""
    # Resolve candidate cookies from parameters or active SQLite vault accounts
    candidates: List[str] = []
    if cookie_str:
        candidates.append(cookie_str)
    if accounts:
        for acc in accounts:
            tok = acc.get("token")
            if tok and acc.get("status") == "active" and tok not in candidates:
                candidates.append(tok)
    try:
        from singularity import db
        accs = db.get_accounts("gemini")
        for acc in accs:
            tok = acc.get("token")
            if tok and acc.get("status") == "active" and tok not in candidates:
                candidates.append(tok)
    except Exception:
        pass

    is_image_model = any(k in model.lower() for k in ("nano-banana", "imagen", "image"))

    chosen_cookie = candidates[0] if candidates else ""
    snlm0e = ""
    bl = os.getenv("GEMINI_BL", "boq_assistant-bard-web-server_20260923.22_p0")

    # Try candidate cookies in priority order to find an active authenticated session
    for cand in candidates:
        s, b = await _get_gemini_session_context(cand)
        if s:
            chosen_cookie = cand
            snlm0e = s
            bl = b
            break
        elif not bl and b:
            bl = b

    help_instruction = (
        "⚠️ **Google Gemini Image Generation Notice**\n\n"
        "Google Gemini returned: *\"I can search for images, but can't create any for you right now. It's possible you're signed out or image creation isn't available in your location yet.\"*\n\n"
        "### 🔍 Why this happens:\n"
        "1. **Full Cookie Requirement**: Google Gemini's image generation (Imagen) requires authentication via `__Secure-1PSID`, `__Secure-1PSIDTS`, AND `SAPISID` (for SAPISIDHASH token verification).\n"
        "2. **Account / Workspace Restrictions**: School, Google Workspace, or under-18 accounts have Imagen disabled by Google.\n\n"
        "### 🔑 How to resolve in 30 seconds:\n"
        "1. Open [gemini.google.com](https://gemini.google.com) in your browser.\n"
        "2. Open DevTools (`F12`), go to the **Network** tab, type any message in Gemini, click on the `StreamGenerate` or `batchexecute` request.\n"
        "3. In the Request Headers, copy the entire **Cookie** header (which includes `__Secure-1PSID`, `__Secure-1PSIDTS`, and `SAPISID`).\n"
        "4. Paste it into Singularity Control Center -> **Cookie Stacker** -> **Gemini** tab and save!"
    )

    chat_id = f"chatcmpl-gemini-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    cfg = MODEL_CONFIGS.get(model.lower(), {"mode": 1, "think": 4})
    model_id = cfg["mode"]
    think_mode = cfg["think"]

    tb = kwargs.get("thinking_budget")
    if tb is not None:
        try:
            tb_val = int(tb)
            if tb_val == 0:
                think_mode = 4
                if model_id == 2:
                    model_id = 1
            elif tb_val > 0:
                think_mode = 0
                if model_id == 1:
                    model_id = 2
        except Exception:
            pass
    elif kwargs.get("thinking") is not None:
        th = kwargs.get("thinking")
        if isinstance(th, dict) and th.get("type") == "disabled":
            think_mode = 4
            if model_id == 2:
                model_id = 1
        elif (isinstance(th, dict) and th.get("type") == "enabled") or th is True:
            think_mode = 0
            if model_id == 1:
                model_id = 2

    prompt = _format_messages_to_prompt(messages)

    inner = [None] * 80
    inner[0] = [prompt, 0, None, None, None, None, 0]
    inner[1] = ["en"]
    inner[2] = ["", "", "", None, None, None, None, None, None, ""]
    inner[6] = [0]
    inner[7] = 1
    inner[10] = 1
    inner[11] = 0
    inner[17] = [[think_mode]]
    inner[18] = 0
    inner[27] = 1
    inner[30] = [4]
    inner[53] = 0
    inner[59] = str(uuid.uuid4())
    inner[61] = []
    inner[68] = 1
    inner[79] = model_id

    outer = [None, json.dumps(inner)]

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://gemini.google.com",
        "Referer": "https://gemini.google.com/app",
        "X-Same-Domain": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }
    if chosen_cookie:
        headers["Cookie"] = chosen_cookie
        # Compute SAPISIDHASH if SAPISID is available in cookies
        sapisid_m = re.search(r'(?:SAPISID|__Secure-1PAPISID|__Secure-3PAPISID)=([^;]+)', chosen_cookie)
        if sapisid_m:
            sapisid = sapisid_m.group(1).strip()
            ts = int(time.time())
            h = hashlib.sha1(f"{ts} {sapisid} https://gemini.google.com".encode()).hexdigest()
            headers["Authorization"] = f"SAPISIDHASH {ts}_{h}"

    # Initial assistant chunk
    yield {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }

    prev_text = ""
    yielded_any = False
    emitted_images = set()

    for attempt in range(2):
        params = {"f.req": json.dumps(outer)}
        if snlm0e:
            params["at"] = snlm0e
        body = urllib.parse.urlencode(params)
        reqid = int(time.time()) % 1000000

        url = (
            f"https://gemini.google.com/_/BardChatUi/data/"
            "assistant.lamda.BardFrontendService/StreamGenerate"
            f"?bl={bl}&hl=en&_reqid={reqid}&rt=c"
        )

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0), follow_redirects=True) as client:
                async with client.stream("POST", url, content=body.encode("utf-8"), headers=headers) as resp:
                    if resp.status_code >= 400:
                        err_txt = (await resp.aread()).decode("utf-8", errors="ignore")
                        # Auto-heal: If Google returns a new XSRF token in error 400, capture and retry
                        xsrf_match = re.findall(r'\["xsrf","([^"]+)"\]', err_txt)
                        if xsrf_match and attempt == 0:
                            snlm0e = xsrf_match[0]
                            cache_key = cookie_str or "guest"
                            _SESSION_CACHE[cache_key] = {"snlm0e": snlm0e, "bl": bl, "ts": time.time()}
                            continue

                        yield {
                            "id": chat_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": {"content": f"\n\n[Gemini Web Error {resp.status_code}: {err_txt[:140]}]"},
                                "finish_reason": "error",
                            }],
                        }
                        return

                    buf = ""
                    async for chunk in resp.aiter_text():
                        buf += chunk
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            if '"wrb.fr"' not in line or len(line) < 200:
                                continue

                            # Detect generated image assets in line
                            img_matches = re.findall(r'https://lh3\.googleusercontent\.com/gg-dl/([A-Za-z0-9_-]+)', line)
                            for file_key in img_matches:
                                full_img_url = f"https://lh3.googleusercontent.com/gg-dl/{file_key}"
                                if full_img_url not in emitted_images:
                                    emitted_images.add(full_img_url)
                                    data_uri = await _download_gemini_image(full_img_url, chosen_cookie)
                                    if data_uri:
                                        yield {
                                            "id": chat_id,
                                            "object": "chat.completion.chunk",
                                            "created": created_ts,
                                            "model": model,
                                            "choices": [{
                                                "index": 0,
                                                "delta": {"content": f"\n\n![Generated Image]({data_uri})\n\n"},
                                                "finish_reason": None,
                                            }],
                                        }
                                        yielded_any = True

                            try:
                                arr = json.loads(line)
                                inner_str = arr[0][2]
                                if not inner_str or len(inner_str) < 50:
                                    continue
                                inner2 = json.loads(inner_str)
                                if isinstance(inner2, list) and len(inner2) > 4 and inner2[4]:
                                    for part in inner2[4]:
                                        if isinstance(part, list) and len(part) > 1 and part[1] and isinstance(part[1], list):
                                            for t in part[1]:
                                                if isinstance(t, str):
                                                    # Strip raw internal image placeholder url
                                                    t_cleaned = re.sub(r'http://googleusercontent\.com/image_generation_content/[0-9_]+', '', t)
                                                    if is_image_model and not emitted_images and any(ref in t_cleaned for ref in ("signed out", "can't seem to create", "can't create it right now", "image creation isn't available")):
                                                        t_cleaned = help_instruction
                                                    clean_full = _clean_gemini_text(t_cleaned, strip=False)
                                                    clean_prev = _clean_gemini_text(prev_text, strip=False)
                                                    if len(clean_full) > len(clean_prev):
                                                        delta = clean_full[len(clean_prev):]
                                                        if delta and delta.strip():
                                                            yield {
                                                                "id": chat_id,
                                                                "object": "chat.completion.chunk",
                                                                "created": created_ts,
                                                                "model": model,
                                                                "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                                                            }
                                                            yielded_any = True
                                                    prev_text = t_cleaned
                            except Exception:
                                pass
            break
        except Exception as e:
            if attempt == 0:
                continue
            if not yielded_any:
                yield {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"\n\n[Gemini Engine Error: {str(e)}]"},
                        "finish_reason": "error",
                    }],
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

