#!/usr/bin/env python3
"""
Universal-Gift: Universal Free Gemini Web2API Proxy
===================================================
A universal, zero-cookie, high-fidelity reverse proxy exposing Google Gemini
as a standard OpenAI-compatible API (/v1/chat/completions) and Google API
(/v1beta/models) for any application:
- Coding assistants: Cursor, VS Code Continue, Cline, Roo Code, Aider
- Web UIs: Open WebUI, LibreChat, Chatbox, NextChat, LobeChat
- Frameworks: LangChain, LlamaIndex, CrewAI, AutoGen
- Developers: Python openai SDK, Node.js, cURL
- Chatbots & Roleplay: SillyTavern, Janitor AI, etc.

Author: InsomniacZero
Repository: https://github.com/InsomniacZero/Universal-Gift
License: MIT
"""

import argparse
import base64
import hashlib
import http.server
import json
import os
import re
import socketserver
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# Optional httpx for high-performance HTTP/2 streaming
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# ─── Configuration ───────────────────────────────────────────────────────────

CONFIG = {
    "host": "0.0.0.0",
    "port": 8045,
    "default_model": "gemini-3.8-flash",
    "cookie_file": "cookie.txt",
    "auth_user": None,
    "api_key": "",
    "proxy": None,
    "gemini_bl": "boq_assistant-bard-web-server_20260309.06_p0",
    "xsrf_token": None,
    "request_timeout_sec": 120,
    "retry_attempts": 3,
    "retry_delay_sec": 2,
    "log_requests": True,
    "temporary_chats": True,
}

CONFIG_FILE = "config.json"
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as _f:
            CONFIG.update(json.load(_f))
    except Exception as _e:
        sys.stderr.write(f"[WARN] Failed to read {CONFIG_FILE}: {_e}\n")

# ─── Models ──────────────────────────────────────────────────────────────────
# Mapping from Google Gemini JS: MODE_CATEGORY enum
#   1=FAST, 2=THINKING, 3=PRO, 4=AUTO, 5=FAST_DYNAMIC_THINKING, 6=FLASH_LITE

MODELS = {
    "gemini-3.8-flash": {
        "mode": 1, "think": 4,
        "desc": "Latest all-around model (Gemini 3.8 Flash - Fast & Capable)",
    },
    "gemini-3.8-flash-thinking": {
        "mode": 2, "think": 0,
        "desc": "Gemini 3.8 Flash with deep reasoning mode (~20k chars)",
    },
    "gemini-3.1-pro": {
        "mode": 3, "think": 4,
        "desc": "Google Flagship Gemini 3.1 Pro (Advanced Coding & Logic)",
    },
    "gemini-3.1-pro-extended": {
        "mode": 3, "think": 0,
        "desc": "Gemini 3.1 Pro with Extended Thinking / Deep Reasoning",
    },
    "gemini-3.1-pro-thinking": {
        "mode": 3, "think": 0,
        "desc": "Gemini 3.1 Pro with deep thinking mode (~20k chars)",
    },
    "gemini-3.1-pro-enhanced": {
        "mode": 3, "think": 4, "extra": {31: 2, 80: 3},
        "desc": "Pro with expanded context decoding (experimental)",
    },
    "gemini-3.7-flash": {
        "mode": 1, "think": 4,
        "desc": "Gemini 3.7 Flash",
    },
    "gemini-3.6-flash": {
        "mode": 1, "think": 4,
        "desc": "Gemini 3.6 Flash",
    },
    "gemini-3.5-flash": {
        "mode": 1, "think": 4,
        "desc": "Gemini 3.5 Flash",
    },
    "gemini-3.5-flash-thinking": {
        "mode": 2, "think": 0,
        "desc": "Gemini 3.5 Flash with deep thinking mode",
    },
    "gemini-auto": {
        "mode": 4, "think": 4,
        "desc": "Automatic model selection",
    },
    "gemini-flash-lite": {
        "mode": 6, "think": 4,
        "desc": "Lightweight ultra-fast model",
    },
}

# ─── Utilities ───────────────────────────────────────────────────────────────

def log(msg: str):
    if CONFIG["log_requests"]:
        sys.stderr.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        sys.stderr.flush()


def load_cookie() -> tuple:
    """Load cookie from file. Returns (cookie_str, sapisid)."""
    cookie_file = CONFIG.get("cookie_file")
    if not cookie_file or not os.path.exists(cookie_file):
        return "", None
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content.startswith("{"):
            data = json.loads(content)
            cookie_str = data.get("cookie", "")
            sapisid = data.get("sapisid", "")
        else:
            cookie_str = content
            pairs = dict(p.split("=", 1) for p in cookie_str.split("; ") if "=" in p)
            sapisid = pairs.get("SAPISID", "")
        return cookie_str, sapisid if sapisid else None
    except Exception as e:
        log(f"Cookie load error: {e}")
        return "", None


def make_sapisidhash(sapisid: str) -> str:
    ts = int(time.time())
    h = hashlib.sha1(f"{ts} {sapisid} https://gemini.google.com".encode()).hexdigest()
    return f"SAPISIDHASH {ts}_{h}"


def account_prefix() -> str:
    auth_user = CONFIG.get("auth_user")
    if auth_user is None or auth_user == "":
        return ""
    return f"/u/{auth_user}"


def apply_chat_persistence_flags(inner: list) -> None:
    if CONFIG.get("temporary_chats", True):
        inner[41] = [1]
        inner[45] = 1
    else:
        inner[41] = [2]


def fetch_latest_bl() -> str:
    """Fetch current build label from Gemini Web frontend."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    cookie_str, sapisid = load_cookie()
    if cookie_str:
        headers["Cookie"] = cookie_str
    if sapisid:
        headers["Authorization"] = make_sapisidhash(sapisid)
    url = f"https://gemini.google.com{account_prefix()}/app"
    try:
        req = urllib.request.Request(url, headers=headers)
        ctx = ssl.create_default_context()
        proxy = CONFIG.get("proxy")
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                urllib.request.HTTPSHandler(context=ctx),
            )
            resp = opener.open(req, timeout=10)
        else:
            resp = urllib.request.urlopen(req, context=ctx, timeout=10)
        html = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'"cfb2h"\s*:\s*"([^"]+)"', html)
        if m:
            return m.group(1)
    except Exception as e:
        log(f"BL fetch error: {e}")
    return ""


def update_bl_if_needed() -> bool:
    new_bl = fetch_latest_bl()
    if new_bl and new_bl != CONFIG["gemini_bl"]:
        log(f"BL auto-updated: {CONFIG['gemini_bl']} -> {new_bl}")
        CONFIG["gemini_bl"] = new_bl
        return True
    return False

# ─── Multimodal Vision Uploads ───────────────────────────────────────────────

_page_tokens_cache = {"tokens": {}, "ts": 0}


def _get_page_tokens() -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    cookie_str, sapisid = load_cookie()
    if cookie_str:
        headers["Cookie"] = cookie_str
    if sapisid:
        headers["Authorization"] = make_sapisidhash(sapisid)
    try:
        req = urllib.request.Request(f"https://gemini.google.com{account_prefix()}/app", headers=headers)
        proxy = CONFIG.get("proxy")
        ctx = ssl.create_default_context()
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                urllib.request.HTTPSHandler(context=ctx),
            )
            resp = opener.open(req, timeout=30)
        else:
            resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        html = resp.read().decode("utf-8", errors="ignore")
        tokens = {}
        for key, pattern in [
            ("push_id", r'"qKIAYe":"([^"]+)"'),
            ("pctx", r'"Ylro7b":"([^"]+)"'),
            ("at", r'"thykhd":"([^"]+)"'),
        ]:
            m = re.search(pattern, html)
            if m:
                tokens[key] = m.group(1)
        return tokens
    except Exception as e:
        log(f"Page token fetch failed: {e}")
        return {}


def _cached_page_tokens() -> dict:
    now = time.time()
    if now - _page_tokens_cache["ts"] > 600:
        _page_tokens_cache["tokens"] = _get_page_tokens()
        _page_tokens_cache["ts"] = now
    return _page_tokens_cache["tokens"]


def detect_image_mime(image_bytes: bytes, fallback: str = "image/png") -> str:
    """Infer image MIME type from magic header bytes."""
    if not isinstance(image_bytes, bytes):
        return fallback
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if image_bytes.startswith(b"RIFF") and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes.startswith(b"BM"):
        return "image/bmp"
    if image_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if len(image_bytes) >= 12 and image_bytes[4:8] == b"ftyp":
        brand = image_bytes[8:12]
        if brand in (b"avif", b"avis"):
            return "image/avif"
        if brand in (b"heic", b"heix", b"hevc", b"hevx"):
            return "image/heic"
    return fallback


def fetch_image_bytes(url: str) -> bytes:
    """Fetch image from remote HTTP/HTTPS URL."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        log(f"Image fetch skipped for unsupported URL scheme: {parsed.scheme or 'none'}")
        return b""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        proxy = CONFIG.get("proxy")
        ctx = ssl.create_default_context()
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                urllib.request.HTTPSHandler(context=ctx),
            )
            resp = opener.open(req, timeout=30)
        else:
            resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        return resp.read()
    except Exception as e:
        log(f"Image fetch failed: {e}")
        return b""


def upload_image(image_bytes: bytes, filename: str = "image.png", mime_type: str = "image/png") -> str:
    """Upload image via Scotty resumable upload. Returns file reference path."""
    tokens = _cached_page_tokens()
    push_id = tokens.get("push_id", "feeds/mcudyrk2a4khkz")
    pctx = tokens.get("pctx", "CgcSBWjK7pYx")

    cookie_str, sapisid = load_cookie()
    ctx = ssl.create_default_context()
    proxy = CONFIG.get("proxy")

    start_headers = {
        "Push-ID": push_id,
        "X-Tenant-Id": "bard-storage",
        "X-Client-Pctx": pctx,
        "X-Goog-Upload-Header-Content-Length": str(len(image_bytes)),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if cookie_str:
        start_headers["Cookie"] = cookie_str
    if sapisid:
        start_headers["Authorization"] = make_sapisidhash(sapisid)

    start_url = "https://content-push.googleapis.com/upload/"
    req = urllib.request.Request(start_url, data=b"", headers=start_headers, method="POST")

    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
            urllib.request.HTTPSHandler(context=ctx)
        )
        resp = opener.open(req, timeout=30)
    else:
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)

    upload_url = resp.headers.get("X-Goog-Upload-URL") or resp.headers.get("x-goog-upload-url")
    if not upload_url:
        raise RuntimeError(f"No upload URL in response headers: {dict(resp.headers)}")

    upload_headers = {
        "X-Goog-Upload-Command": "upload, finalize",
        "X-Goog-Upload-Offset": "0",
        "Content-Type": "application/octet-stream",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    req2 = urllib.request.Request(upload_url, data=image_bytes, headers=upload_headers, method="POST")
    if proxy:
        resp2 = opener.open(req2, timeout=60)
    else:
        resp2 = urllib.request.urlopen(req2, context=ctx, timeout=60)

    file_ref = resp2.read().decode().strip()
    if not file_ref or not file_ref.startswith("/"):
        raise RuntimeError(f"Invalid file reference: {file_ref[:100]}")

    return file_ref


def upload_images(images: list) -> list:
    """Upload parsed image parts and return Gemini file references."""
    if not images:
        return None

    file_refs = []
    for item in images:
        if not (isinstance(item, tuple) and len(item) == 2):
            continue
        data, mime = item
        if isinstance(data, str):
            data = fetch_image_bytes(data)
            mime = mime or "image/png"
        if not data:
            raise RuntimeError("image fetch failed")
        mime = detect_image_mime(data, mime or "image/png")
        try:
            file_refs.append(upload_image(data, "image.png", mime or "image/png"))
        except Exception as e:
            raise RuntimeError(f"image upload failed: {e}") from e
    return file_refs if file_refs else None

# ─── Gemini Protocol ─────────────────────────────────────────────────────────

def gemini_stream_generate(prompt: str, model_id: int, think_mode: int, file_refs: list = None) -> str:
    """Send prompt to Gemini StreamGenerate with retry."""
    inner = [None] * 80
    if file_refs:
        refs = [[None, None, ref] for ref in file_refs]
        inner[0] = [prompt, 0, None, refs, None, None, 0]
    else:
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
    apply_chat_persistence_flags(inner)
    inner[53] = 0
    inner[59] = str(uuid.uuid4())
    inner[61] = []
    inner[68] = 1
    inner[79] = model_id

    outer = [None, json.dumps(inner)]
    params = {"f.req": json.dumps(outer)}
    if CONFIG.get("xsrf_token"):
        params["at"] = CONFIG["xsrf_token"]
    body = urllib.parse.urlencode(params).encode()
    reqid = int(time.time()) % 1000000
    prefix = account_prefix()
    url = (
        f"https://gemini.google.com{prefix}/_/BardChatUi/data/"
        "assistant.lamda.BardFrontendService/StreamGenerate"
        f"?bl={CONFIG['gemini_bl']}&hl=en&_reqid={reqid}&rt=c"
    )
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://gemini.google.com",
        "Referer": f"https://gemini.google.com{prefix}/app",
        "X-Same-Domain": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if prefix:
        headers["X-Goog-AuthUser"] = str(CONFIG["auth_user"])

    cookie_str, sapisid = load_cookie()
    if cookie_str:
        headers["Cookie"] = cookie_str
    if sapisid:
        headers["Authorization"] = make_sapisidhash(sapisid)

    last_err = None
    for attempt in range(CONFIG["retry_attempts"]):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            ctx = ssl.create_default_context()
            proxy = CONFIG.get("proxy")
            if proxy:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                    urllib.request.HTTPSHandler(context=ctx)
                )
                resp = opener.open(req, timeout=CONFIG["request_timeout_sec"])
            else:
                resp = urllib.request.urlopen(req, context=ctx, timeout=CONFIG["request_timeout_sec"])
            return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 405:
                log("HTTP 405 received. Checking for newer BL...")
                if update_bl_if_needed():
                    url = (
                        f"https://gemini.google.com{prefix}/_/BardChatUi/data/"
                        "assistant.lamda.BardFrontendService/StreamGenerate"
                        f"?bl={CONFIG['gemini_bl']}&hl=en&_reqid={reqid}&rt=c"
                    )
                    last_err = e
                    continue
            if e.code == 400:
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                    m = re.search(r'["\']?xsrf["\']?\s*,\s*["\']([^"\'\s]+)["\']', err_body)
                    if m:
                        CONFIG["xsrf_token"] = m.group(1)
                        log(f"Auto-recovered XSRF token from 400: {m.group(1)[:12]}...")
                        params["at"] = m.group(1)
                        body = urllib.parse.urlencode(params).encode()
                        last_err = e
                        continue
                except Exception:
                    pass
            last_err = e
            if attempt < CONFIG["retry_attempts"] - 1:
                log(f"Retry {attempt+1}/{CONFIG['retry_attempts']}: {e}")
                time.sleep(CONFIG["retry_delay_sec"])
        except Exception as e:
            last_err = e
            if attempt < CONFIG["retry_attempts"] - 1:
                log(f"Retry {attempt+1}/{CONFIG['retry_attempts']}: {e}")
                time.sleep(CONFIG["retry_delay_sec"])
    if last_err:
        raise last_err
    raise RuntimeError(f"Request failed after {CONFIG['retry_attempts']} attempts")


def gemini_stream_generate_iter(prompt: str, model_id: int, think_mode: int, file_refs: list = None):
    """Send prompt and yield incremental text deltas using httpx streaming."""
    inner = [None] * 80
    if file_refs:
        refs = [[None, None, ref] for ref in file_refs]
        inner[0] = [prompt, 0, None, refs, None, None, 0]
    else:
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
    apply_chat_persistence_flags(inner)
    inner[53] = 0
    inner[59] = str(uuid.uuid4())
    inner[61] = []
    inner[68] = 1
    inner[79] = model_id

    outer = [None, json.dumps(inner)]
    params = {"f.req": json.dumps(outer)}
    if CONFIG.get("xsrf_token"):
        params["at"] = CONFIG["xsrf_token"]
    body = urllib.parse.urlencode(params)
    reqid = int(time.time()) % 1000000
    prefix = account_prefix()
    url = (
        f"https://gemini.google.com{prefix}/_/BardChatUi/data/"
        "assistant.lamda.BardFrontendService/StreamGenerate"
        f"?bl={CONFIG['gemini_bl']}&hl=en&_reqid={reqid}&rt=c"
    )
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://gemini.google.com",
        "Referer": f"https://gemini.google.com{prefix}/app",
        "X-Same-Domain": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if prefix:
        headers["X-Goog-AuthUser"] = str(CONFIG["auth_user"])
    cookie_str, sapisid = load_cookie()
    if cookie_str:
        headers["Cookie"] = cookie_str
    if sapisid:
        headers["Authorization"] = make_sapisidhash(sapisid)

    proxy = CONFIG.get("proxy")

    if not HAS_HTTPX:
        raw = gemini_stream_generate(prompt, model_id, think_mode, file_refs)
        text = extract_response_text(raw)
        if text:
            yield text
        return

    prev_text = ""
    transport = httpx.HTTPTransport(proxy=proxy) if proxy else None
    with httpx.Client(transport=transport, timeout=CONFIG["request_timeout_sec"], verify=True) as client:
        try:
            with client.stream("POST", url, content=body, headers=headers) as resp:
                resp.raise_for_status()
                buf = ""
                for chunk in resp.iter_text():
                    buf += chunk
                    if "BardErrorInfo" in buf:
                        m = re.search(r'BardErrorInfo\s*\[(\d+)\]', buf)
                        if m:
                            raise RuntimeError(f"Gemini upstream rejected request: BardErrorInfo [{m.group(1)}]")
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        if '"wrb.fr"' not in line or len(line) < 200:
                            continue
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
                                                clean_full = clean_gemini_text(t, strip=False)
                                                clean_prev = clean_gemini_text(prev_text, strip=False)
                                                if len(clean_full) > len(clean_prev):
                                                    delta = clean_full[len(clean_prev):]
                                                    if delta:
                                                        yield delta
                                                prev_text = t
                        except (json.JSONDecodeError, IndexError, TypeError):
                            pass
        except Exception as e:
            if HAS_HTTPX and hasattr(e, 'response') and getattr(e.response, 'status_code', 0) == 405:
                if update_bl_if_needed():
                    log("BL updated, falling back to non-streaming for this request")
                    raw = gemini_stream_generate(prompt, model_id, think_mode, file_refs)
                    text = extract_response_text(raw)
                    if text:
                        yield text
                    return
            raise


def clean_gemini_text(text: str, strip: bool = True) -> str:
    """Remove internal code execution artifacts, suggestion chips, FollowUp tags, and evasive disclaimers."""
    # 1. Code execution artifacts
    text = re.sub(
        r'```(?:python|javascript|text)\?code_(?:reference|stdout)&code_event_index=\d+\n.*?```\n?',
        '', text, flags=re.DOTALL
    )
    # 2. Suggestion chips & internal action tags: Elicit, Suggest, FollowUp, ActionCard, RelatedQueries
    text = re.sub(
        r'</?(?:Elic[ia]t|Suggest|FollowUp|ActionCard|RelatedQueries)[A-Za-z0-9_]*[^>]*>.*?(?:</(?:Elic[ia]t|Suggest|FollowUp|ActionCard|RelatedQueries)[A-Za-z0-9_]*>|$)|</?(?:Elic[ia]t|Suggest|FollowUp|ActionCard|RelatedQueries)[A-Za-z0-9_]*[^>]*/?>',
        '', text, flags=re.DOTALL | re.IGNORECASE
    )
    # 3. Generic paired or self-closing tags with label= or query= (e.g. <FollowUp label="..." query="..."/>)
    text = re.sub(
        r'<[A-Za-z0-9_-]+[^>]*\b(?:label|query)=[\'"][^\'"]*[\'"][^>]*>.*?</[A-Za-z0-9_-]+>',
        '', text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r'<[A-Za-z0-9_-]+[^>]*\b(?:label|query)=[\'"][^\'"]*[\'"][^>]*/?>',
        '', text, flags=re.IGNORECASE
    )
    # 4. Incomplete / trailing unclosed tags at the very end of stream
    text = re.sub(
        r'</?(?:[A-Za-z0-9_]*(?:Elic|Sugg|Follow|Action)[A-Za-z0-9_]*)[^>]*$',
        '', text, flags=re.IGNORECASE
    )
    text = re.sub(r'<[A-Za-z0-9_]+[^>]*$', '', text)

    # 5. Role markers
    text = re.sub(r'^(?:\[(?:Assistant|Model)\]:?|(?:Assistant|Model):)\s*', '', text, flags=re.IGNORECASE)

    # 6. Refusal preambles and postambles
    text = re.sub(r'^(?:I cannot (?:fulfill|generate|participate)[^\n]+\n+)+(?:\*{3,}\n+)?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n*(?:I(?:\'m| am) (?:just )?a language model[^\n]*|As an AI[^\n]*)$', '', text, flags=re.IGNORECASE)
    return text.strip() if strip else text


def extract_response_text(raw: str) -> str:
    """Parse StreamGenerate response to extract final text."""
    bard_err = re.search(r'BardErrorInfo\s*\[(\d+)\]', raw)
    if bard_err:
        raise RuntimeError(f"Gemini upstream rejected request: BardErrorInfo [{bard_err.group(1)}]")
    texts = []
    for line in raw.split("\n"):
        if '"wrb.fr"' not in line or len(line) < 200:
            continue
        try:
            arr = json.loads(line)
            inner_str = arr[0][2]
            if not inner_str or len(inner_str) < 50:
                continue
            inner = json.loads(inner_str)
            if isinstance(inner, list) and len(inner) > 4 and inner[4]:
                for part in inner[4]:
                    if isinstance(part, list) and len(part) > 1 and part[1] and isinstance(part[1], list):
                        for t in part[1]:
                            if isinstance(t, str) and t.strip():
                                texts.append(t)
        except (json.JSONDecodeError, IndexError, TypeError):
            pass

    if not texts:
        return ""
    text = texts[-1]
    return clean_gemini_text(text)

# ─── Universal Message / Prompt Formatting ───────────────────────────────────

def messages_to_prompt(messages: list, tools: list = None) -> tuple:
    """Convert OpenAI messages to (prompt_str, images_list) with smart windowing and tool instructions."""
    system_parts = []
    turns = []
    images = []

    # If tools provided, format standard OpenAI function-calling instructions
    if tools:
        tool_defs = []
        for t in tools:
            fn = t.get("function", t) if t.get("type") == "function" else t
            tool_defs.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            })
        system_parts.append(
            "[Tool Instructions]: You have access to the following tools.\n"
            "To call a tool, respond with a tool_call block in this exact JSON format:\n"
            "```tool_call\n"
            '{"name": "function_name", "arguments": {...}}\n'
            "```\n"
            "Only call tools when needed.\n\n"
            f"Available tools:\n{json.dumps(tool_defs, indent=2)}"
        )

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Extract multimodal images if present
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    ptype = part.get("type", "")
                    if ptype in ("text", "input_text", "output_text"):
                        text_parts.append(part.get("text", ""))
                    elif ptype == "image_url":
                        url_obj = part.get("image_url", {})
                        url = url_obj.get("url", "") if isinstance(url_obj, dict) else str(url_obj)
                        if url:
                            if url.startswith("data:"):
                                mime = url.split(";", 1)[0].replace("data:", "")
                                b64 = url.split(",", 1)[1]
                                images.append((base64.b64decode(b64), mime))
                            else:
                                images.append((url, None))
                elif isinstance(part, str):
                    text_parts.append(part)
            content = " ".join(text_parts)
        else:
            content = str(content) if content is not None else ""

        # Scrub internal Google suggestion chips or FollowUp tags from history
        if role in ("assistant", "user"):
            content = clean_gemini_text(content, strip=False)

        if role == "system":
            if content.strip():
                system_parts.append(f"[System Instructions]:\n{content.strip()}")
        elif role == "tool":
            turns.append({
                "role": "user",
                "content": f"[Tool result for {msg.get('name', 'unknown')}]: {content.strip()}"
            })
        elif role == "assistant":
            # Check for OpenAI assistant tool_calls
            tool_calls = msg.get("tool_calls", [])
            tc_blocks = []
            for tc in tool_calls:
                fn = tc.get("function", {})
                tc_blocks.append(
                    "```tool_call\n" +
                    json.dumps({"name": fn.get("name", ""), "arguments": fn.get("arguments", "{}")}) +
                    "\n```"
                )
            full_assistant = content.strip()
            if tc_blocks:
                full_assistant = (full_assistant + "\n" + "\n".join(tc_blocks)).strip()
            if full_assistant:
                turns.append({"role": "assistant", "content": full_assistant})
        else:
            if content.strip():
                turns.append({"role": "user", "content": content.strip()})

    # Merge consecutive turns of same role
    merged_turns = []
    for turn in turns:
        if merged_turns and merged_turns[-1]["role"] == turn["role"]:
            merged_turns[-1]["content"] += f"\n\n{turn['content']}"
        else:
            merged_turns.append(turn)

    # Prefill handling (if assistant is last)
    prefill = None
    if merged_turns and merged_turns[-1]["role"] == "assistant":
        prefill = merged_turns.pop()["content"]

    # Sliding context window (~45,000 characters budget)
    sys_prompt = "\n\n".join(p for p in system_parts if p.strip())
    budget = max(45000 - len(sys_prompt) - 200, 6000)

    kept = []
    if merged_turns:
        last_turn = merged_turns[-1]
        kept = [last_turn]
        used = len(last_turn["content"]) + 20
        first_turn = merged_turns[0] if len(merged_turns) > 1 else None
        first_len = len(first_turn["content"]) + 20 if first_turn else 0

        for t in reversed(merged_turns[1:-1]):
            t_len = len(t["content"]) + 20
            if used + t_len + first_len < budget:
                kept.insert(0, t)
                used += t_len
            else:
                break

        if first_turn and used + first_len < budget:
            kept.insert(0, first_turn)
        merged_turns = kept

    dialogue_parts = []
    for t in merged_turns:
        prefix = "[Assistant]: " if t["role"] == "assistant" else "[User]: "
        dialogue_parts.append(f"{prefix}{t['content']}")

    all_parts = [p for p in system_parts if p.strip()] + dialogue_parts
    prompt = "\n\n".join(all_parts)

    if prefill:
        prompt += f"\n\n[Assistant]: {prefill}"
    else:
        prompt += "\n\n[Assistant]:"

    return prompt, images


def google_contents_to_prompt(req: dict) -> tuple:
    """Convert Google generateContent payload to (prompt_str, images_list)."""
    messages = []
    system_inst = req.get("system_instruction") or req.get("systemInstruction")
    if system_inst:
        parts = system_inst.get("parts", [])
        sys_text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p)
        if sys_text:
            messages.append({"role": "system", "content": sys_text})

    for content in req.get("contents", []):
        role = content.get("role", "user")
        if role == "model":
            role = "assistant"
        parts = content.get("parts", [])
        text_parts = []
        msg_images = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                if "text" in part:
                    text_parts.append(part["text"])
                elif "inline_data" in part or "inlineData" in part:
                    idata = part.get("inline_data") or part.get("inlineData")
                    mime = idata.get("mime_type") or idata.get("mimeType", "image/png")
                    b64 = idata.get("data", "")
                    if b64:
                        msg_images.append((base64.b64decode(b64), mime))
        content_val = " ".join(text_parts)
        if msg_images:
            content_list = [{"type": "text", "text": content_val}]
            for img_data, mime in msg_images:
                b64 = base64.b64encode(img_data).decode()
                content_list.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
            messages.append({"role": role, "content": content_list})
        else:
            messages.append({"role": role, "content": content_val})

    return messages_to_prompt(messages)


def parse_tool_calls(text: str) -> tuple:
    """Extract tool_call blocks. Returns (clean_text, tool_calls_list)."""
    tool_calls = []
    pattern = r"```tool_call\s*\n(.*?)\n```"
    matches = list(re.finditer(pattern, text, re.DOTALL))
    for m in matches:
        try:
            call_data = json.loads(m.group(1).strip())
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": call_data.get("name", ""),
                    "arguments": json.dumps(call_data.get("arguments", {}))
                    if isinstance(call_data.get("arguments"), dict)
                    else str(call_data.get("arguments", "{}")),
                },
            })
        except json.JSONDecodeError:
            pass
    clean_text = re.sub(pattern, "", text, flags=re.DOTALL).strip()
    return clean_text, tool_calls if tool_calls else None

# ─── HTTP Handler ─────────────────────────────────────────────────────────────

class GeminiHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _cors_headers(self):
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400",
        }

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in self._cors_headers().items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400, err_type: str = "invalid_request_error"):
        self._send_json({"error": {"message": message, "type": err_type, "code": status}}, status)

    def _authorized(self) -> bool:
        expected = CONFIG.get("api_key")
        if not expected:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == expected
        return self.headers.get("X-Api-Key", "") == expected

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in self._cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        if (self.path.startswith("/v1") or self.path.startswith("/chat") or self.path == "/models") and not self._authorized():
            return self._send_error("Unauthorized", 401, "auth_error")

        if self.path in ("/v1/models", "/models"):
            data = {
                "object": "list",
                "data": [
                    {"id": n, "object": "model", "created": 1700000000, "owned_by": "google", "permission": []}
                    for n in MODELS.keys()
                ]
            }
            self._send_json(data)
        elif self.path.startswith("/v1beta/models"):
            self._handle_google_models_list()
        elif self.path in ("/", "/health", "/status"):
            self._send_json({
                "service": "Universal-Gift",
                "status": "online",
                "models": list(MODELS.keys()),
                "default_model": CONFIG.get("default_model", "gemini-3.8-flash"),
                "endpoints": [
                    "/v1/chat/completions",
                    "/v1/models",
                    "/v1beta/models"
                ]
            })
        else:
            self._send_error("Not Found", 404)

    def _handle_google_models_list(self):
        gmodels = []
        for name, cfg in MODELS.items():
            gmodels.append({
                "name": f"models/{name}",
                "version": "1.0",
                "displayName": name,
                "description": cfg.get("desc", ""),
                "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
            })
        self._send_json({"models": gmodels})

    def _read_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            chunks = []
            while True:
                line = self.rfile.readline().strip()
                if not line:
                    break
                size = int(line, 16)
                if size == 0:
                    self.rfile.read(2)
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.read(2)
            return b"".join(chunks)

        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _resolve_model(self, model_name: str):
        think_override = None
        if "@think=" in model_name:
            model_name, think_str = model_name.rsplit("@think=", 1)
            try:
                think_override = int(think_str)
            except ValueError:
                pass

        norm = model_name.strip().lower().replace(" ", "-")
        cfg = MODELS.get(model_name) or MODELS.get(norm)
        if not cfg:
            if ("gemini-" + norm) in MODELS:
                model_name = "gemini-" + norm
                cfg = MODELS[model_name]
            elif norm in ("3.1-pro", "pro"):
                model_name = "gemini-3.1-pro"
                cfg = MODELS[model_name]
            elif norm in ("3.1-pro-extended", "3.1-pro-thinking", "pro-extended", "pro-thinking"):
                model_name = "gemini-3.1-pro-extended"
                cfg = MODELS[model_name]
            elif norm in ("3.8-flash", "flash"):
                model_name = "gemini-3.8-flash"
                cfg = MODELS[model_name]
            elif norm in ("3.8-flash-thinking", "flash-thinking"):
                model_name = "gemini-3.8-flash-thinking"
                cfg = MODELS[model_name]
            elif norm in ("gpt-4o", "gpt-4", "claude-3-5-sonnet", "claude-3-7-sonnet"):
                model_name = "gemini-3.1-pro"
                cfg = MODELS[model_name]
            else:
                default_name = CONFIG.get("default_model", "gemini-3.8-flash")
                log(f"Unknown model '{model_name}', falling back to default: {default_name}")
                model_name = default_name
                cfg = MODELS.get(model_name, MODELS["gemini-3.8-flash"])
        else:
            model_name = norm if norm in MODELS else model_name
        return model_name, cfg["mode"], (think_override if think_override is not None else cfg["think"]), None

    def _call_gemini(self, prompt, model_id, think_mode, tools, file_refs=None):
        raw = gemini_stream_generate(prompt, model_id, think_mode, file_refs)
        text = extract_response_text(raw)
        tool_calls = None
        if tools and text:
            text, tool_calls = parse_tool_calls(text)
        return text or "", tool_calls

    def handle_chat(self, body: bytes):
        req = json.loads(body)
        model_name, model_id, think_mode, err = self._resolve_model(
            req.get("model", CONFIG["default_model"]))
        if err:
            return self._send_error(err)

        stream = req.get("stream", False)
        tools = req.get("tools")
        prompt, images = messages_to_prompt(req.get("messages", []), tools)

        file_refs = None
        if images:
            try:
                file_refs = upload_images(images)
            except Exception as e:
                log(f"Image upload error: {e}")
                return self._send_error(f"Image upload failed: {e}")

        cmpl_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created = int(time.time())

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            for k, v in self._cors_headers().items():
                self.send_header(k, v)
            self.end_headers()

            def sse(d):
                return f"data: {json.dumps(d)}\n\n".encode("utf-8")

            try:
                self.wfile.write(sse({
                    "id": cmpl_id, "object": "chat.completion.chunk", "created": created,
                    "model": model_name, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}))
                for delta_text in gemini_stream_generate_iter(prompt, model_id, think_mode, file_refs):
                    self.wfile.write(sse({
                        "id": cmpl_id, "object": "chat.completion.chunk", "created": created,
                        "model": model_name, "choices": [{"index": 0, "delta": {"content": delta_text}, "finish_reason": None}]}))
                    self.wfile.flush()
                self.wfile.write(sse({
                    "id": cmpl_id, "object": "chat.completion.chunk", "created": created,
                    "model": model_name, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        try:
            text, tool_calls = self._call_gemini(prompt, model_id, think_mode, tools, file_refs)
            msg = {"role": "assistant"}
            finish = "stop"
            if tool_calls:
                msg["tool_calls"] = tool_calls
                msg["content"] = text if text else None
                finish = "tool_calls"
            else:
                msg["content"] = text

            self._send_json({
                "id": cmpl_id,
                "object": "chat.completion",
                "created": created,
                "model": model_name,
                "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                "usage": {"prompt_tokens": len(prompt) // 4, "completion_tokens": len(text) // 4, "total_tokens": (len(prompt) + len(text)) // 4},
            })
        except Exception as e:
            log(f"Chat completion error: {e}")
            self._send_error(str(e), 500, "upstream_error")

    def handle_google_generate(self, body: bytes, stream: bool = False):
        req = json.loads(body)
        model_part = self._extract_model_from_path()
        model_name, model_id, think_mode, err = self._resolve_model(model_part)
        if err:
            return self._send_error(err)

        prompt, images = google_contents_to_prompt(req)
        file_refs = None
        if images:
            try:
                file_refs = upload_images(images)
            except Exception as e:
                log(f"Image upload error: {e}")
                return self._send_error(f"Image upload failed: {e}")

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            for k, v in self._cors_headers().items():
                self.send_header(k, v)
            self.end_headers()

            def sse(d):
                return f"data: {json.dumps(d)}\n\n".encode("utf-8")

            try:
                for delta_text in gemini_stream_generate_iter(prompt, model_id, think_mode, file_refs):
                    self.wfile.write(sse({
                        "candidates": [{"content": {"parts": [{"text": delta_text}], "role": "model"}, "finishReason": None, "index": 0}]
                    }))
                    self.wfile.flush()
                self.wfile.write(sse({
                    "candidates": [{"content": {"parts": [{"text": ""}], "role": "model"}, "finishReason": "STOP", "index": 0}]
                }))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        try:
            raw = gemini_stream_generate(prompt, model_id, think_mode, file_refs)
            text = extract_response_text(raw)
            self._send_json({
                "candidates": [{
                    "content": {"parts": [{"text": text}], "role": "model"},
                    "finishReason": "STOP",
                    "index": 0,
                }],
                "usageMetadata": {
                    "promptTokenCount": len(prompt) // 4,
                    "candidatesTokenCount": len(text) // 4,
                    "totalTokenCount": (len(prompt) + len(text)) // 4,
                }
            })
        except Exception as e:
            log(f"Google generate error: {e}")
            self._send_error(str(e), 500, "upstream_error")

    def _extract_model_from_path(self) -> str:
        m = re.search(r"/v1beta/models/([^:]+)", self.path)
        return m.group(1) if m else CONFIG["default_model"]

    def do_POST(self):
        if not self._authorized():
            return self._send_error("Unauthorized", 401, "auth_error")

        body = self._read_body()
        if not body:
            return self._send_error("Empty request body")

        path = self.path.split("?")[0]
        if path in ("/v1/chat/completions", "/chat/completions"):
            self.handle_chat(body)
        elif ":streamGenerateContent" in path:
            self.handle_google_generate(body, stream=True)
        elif ":generateContent" in path:
            self.handle_google_generate(body, stream=False)
        else:
            self._send_error(f"Unknown POST endpoint: {path}", 404)

# ─── Main Entry Point ─────────────────────────────────────────────────────────

def run_server():
    parser = argparse.ArgumentParser(description="Universal-Gift: Universal Gemini Web2API Proxy")
    parser.add_argument("--host", default=CONFIG["host"], help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=CONFIG["port"], help="Bind port (default: 8045)")
    parser.add_argument("--model", default=CONFIG["default_model"], help="Default Gemini model")
    parser.add_argument("--api-key", default=CONFIG["api_key"], help="Optional API key for authorization")
    parser.add_argument("--cookie", default=CONFIG["cookie_file"], help="Cookie file path")
    parser.add_argument("--proxy", default=CONFIG["proxy"], help="HTTP/SOCKS proxy URL")
    parser.add_argument("--auth-user", default=CONFIG["auth_user"], help="Google Account index (e.g. 0, 1)")
    parser.add_argument("--quiet", action="store_true", help="Disable request logging")

    args = parser.parse_args()
    CONFIG["host"] = args.host
    CONFIG["port"] = args.port
    CONFIG["default_model"] = args.model
    CONFIG["api_key"] = args.api_key
    CONFIG["cookie_file"] = args.cookie
    CONFIG["proxy"] = args.proxy
    CONFIG["auth_user"] = args.auth_user
    if args.quiet:
        CONFIG["log_requests"] = False

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    server = ReusableTCPServer((CONFIG["host"], CONFIG["port"]), GeminiHandler)
    display_host = "localhost" if CONFIG["host"] in ("0.0.0.0", "") else CONFIG["host"]

    print("═════════════════════════════════════════════════════════════════════════")
    print("      🎁 Universal-Gift - Universal Gemini Web2API Proxy 🎁              ")
    print("═════════════════════════════════════════════════════════════════════════")
    print(f"  • Local API Base:       http://{display_host}:{CONFIG['port']}/v1")
    print(f"  • Chat Completions:     http://{display_host}:{CONFIG['port']}/v1/chat/completions")
    print(f"  • Models Endpoint:      http://{display_host}:{CONFIG['port']}/v1/models")
    print(f"  • Default Model:        {CONFIG['default_model']}")
    print(f"  • Pro Reasoning:        gemini-3.1-pro-extended (or gemini-3.1-pro)")
    print(f"  • Guest Mode:           Active (Zero cookies required, 100% Free)")
    print(f"  • Streaming (HTTP/2):   {'httpx enabled' if HAS_HTTPX else 'fallback (urllib)'}")
    print("═════════════════════════════════════════════════════════════════════════")
    print("  Ready to connect anywhere: Cursor, Open WebUI, LibreChat, Python, cURL!")
    print("  Press Ctrl+C to stop the server.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Universal-Gift stopped cleanly.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
