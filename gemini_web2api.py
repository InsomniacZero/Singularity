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
import io
import json
import os
import re
import socket
import socketserver
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

# Force IPv4 resolution to eliminate 40s IPv6 connection timeouts on Linux
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(host, port, family=0, *args):
    return _orig_getaddrinfo(host, port, socket.AF_INET, *args)
socket.getaddrinfo = _getaddrinfo_ipv4

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
    # ─── Nano Banana Family (Image & Multimodal Synthesis) ───────────────
    "nano-banana-2": {
        "mode": 1, "think": 4,
        "desc": "Nano Banana 2 (Gemini 3.1 Flash Image - State-of-the-art fast image generation & editing)",
    },
    "nano-banana-pro": {
        "mode": 3, "think": 4,
        "desc": "Nano Banana Pro (Gemini 3 Pro Image - High-fidelity reasoning & photorealistic generation)",
    },
    "nano-banana": {
        "mode": 1, "think": 4,
        "desc": "Nano Banana (Gemini 2.5 Flash Image - Original viral image generator & editor)",
    },
    "nano-banana-2-lite": {
        "mode": 6, "think": 4,
        "desc": "Nano Banana 2 Lite (Gemini 3.1 Flash-Lite Image - Rapid lightweight image model)",
    },
    "gemini-3.1-flash-image": {
        "mode": 1, "think": 4,
        "desc": "Gemini 3.1 Flash Image (Nano Banana 2)",
    },
    "gemini-3-pro-image": {
        "mode": 3, "think": 4,
        "desc": "Gemini 3 Pro Image (Nano Banana Pro)",
    },
    "gemini-2.5-flash-image": {
        "mode": 1, "think": 4,
        "desc": "Gemini 2.5 Flash Image (Nano Banana)",
    },
    "gemini-3.1-flash-lite-image": {
        "mode": 6, "think": 4,
        "desc": "Gemini 3.1 Flash-Lite Image (Nano Banana 2 Lite)",
    },
    "imagen-3": {
        "mode": 3, "think": 4,
        "desc": "Imagen 3 / Nano Banana Pro Image Model",
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
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(base_dir, "cookie-safe.txt"),
            os.path.join(base_dir, "cookie.txt"),
            os.path.join(base_dir, "..", "cookie-safe.txt"),
            os.path.join(base_dir, "..", "cookie.txt"),
            os.path.join(os.getcwd(), "cookie-safe.txt"),
            os.path.join(os.getcwd(), "cookie.txt"),
            os.path.join(os.getcwd(), "universal-gift", "cookie-safe.txt"),
            "cookie-safe.txt",
            "cookie.txt",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                cookie_file = candidate
                break
        else:
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
    """Fetch image from remote HTTP/HTTPS URL with auth headers if Google."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        log(f"Image fetch skipped for unsupported URL scheme: {parsed.scheme or 'none'}")
        return b""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
        if "googleusercontent.com" in url or "google.com" in url:
            cookie_str, _ = load_cookie()
            if cookie_str:
                headers["Cookie"] = cookie_str
        req = urllib.request.Request(url, headers=headers)
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


def upload_to_catbox(image_bytes: bytes, filename: str = "image.png") -> str:
    """Upload image bytes to catbox.moe and return public direct URL."""
    if not image_bytes:
        return ""
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="reqtype"\r\n\r\n')
    body.extend(b"fileupload\r\n")

    mime = detect_image_mime(image_bytes, "image/png")
    ext = mime.split("/")[-1] if "/" in mime else "png"
    if not filename.endswith(f".{ext}"):
        filename = f"image.{ext}"

    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'.encode("utf-8"))
    body.extend(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
    body.extend(image_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        "https://catbox.moe/user/api.php",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        method="POST"
    )
    try:
        ctx = ssl.create_default_context()
        proxy = CONFIG.get("proxy")
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                urllib.request.HTTPSHandler(context=ctx),
            )
            resp = opener.open(req, timeout=30)
        else:
            resp = urllib.request.urlopen(req, context=ctx, timeout=30)
        url = resp.read().decode("utf-8").strip()
        if url.startswith("http"):
            log(f"Image hosted on Catbox: {url}")
            return url
    except Exception as e:
        log(f"Catbox upload failed: {e}")
    return ""


def make_1080p_widescreen(image_bytes: bytes) -> bytes:
    """Ensure image is true 1080p (1920x1080) high-resolution widescreen with Lanczos resampling."""
    if not image_bytes:
        return image_bytes
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        target_w, target_h = 1920, 1080

        if img.size == (target_w, target_h):
            return image_bytes

        cur_w, cur_h = img.size
        target_ratio = 16.0 / 9.0
        cur_ratio = float(cur_w) / float(cur_h)

        # Center-crop cleanly to 16:9 widescreen before scaling to prevent distortion
        if cur_ratio > target_ratio + 0.01:
            crop_w = int(cur_h * target_ratio)
            crop_h = cur_h
            left = (cur_w - crop_w) // 2
            top = 0
            img = img.crop((left, top, left + crop_w, top + crop_h))
        elif cur_ratio < target_ratio - 0.01:
            crop_w = cur_w
            crop_h = int(cur_w / target_ratio)
            left = 0
            top = (cur_h - crop_h) // 2
            img = img.crop((left, top, left + crop_w, top + crop_h))

        # Lanczos high-fidelity scaling to exact 1920x1080
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception as e:
        log(f"1080p widescreen processing failed: {e}")
        return image_bytes


def remove_chroma_background(image_bytes: bytes) -> bytes:
    """
    Produce a transparent PNG character sprite from an image with a solid studio / chroma-key screen.
    Uses rembg if installed; otherwise uses Boundary-Constrained Chroma Matting with NumPy & SciPy
    to strictly flood from image borders inward, preserving interior white hair, dresses, and ornaments.
    """
    if not image_bytes:
        return image_bytes

    try:
        import rembg
        return rembg.remove(image_bytes)
    except ImportError:
        pass
    except Exception as e:
        log(f"[rembg] Neural matting error: {e}")

    try:
        from PIL import Image, ImageFilter
        import numpy as np
        import scipy.ndimage as ndi

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img, dtype=np.float32)
        h, w, _ = arr.shape
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        # Sample the 4 perimeter corners to detect the background screen color
        corners = np.array([arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]])
        corner_color = np.median(corners, axis=0)

        # Detect if green screen or general solid backdrop
        is_green = (corner_color[1] > corner_color[0] + 25) and (corner_color[1] > corner_color[2] + 25)

        if is_green:
            dist = np.linalg.norm(arr - corner_color, axis=2)
            bg_candidate = (dist < 110) | ((g - np.maximum(r, b)) > 25)
        else:
            dist = np.linalg.norm(arr - corner_color, axis=2)
            bg_candidate = dist < 75

        # Strictly flood from outer image borders so internal white/light areas are never erased
        labeled, num_features = ndi.label(bg_candidate)
        border_labels = set(np.unique(np.concatenate([
            labeled[0, :], labeled[-1, :], labeled[:, 0], labeled[:, -1]
        ])))
        border_labels.discard(0)

        if border_labels:
            is_exterior_bg = np.isin(labeled, list(border_labels))
        else:
            is_exterior_bg = bg_candidate

        # Also clear pure green interior pockets (e.g. between hair strands and neck)
        if is_green:
            pure_green = (g > 130) & (g > r + 30) & (g > b + 30) & (dist < 95)
            is_exterior_bg = is_exterior_bg | pure_green

        alpha = np.where(is_exterior_bg, 0, 255).astype(np.uint8)
        alpha_img = Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(1.2))

        # Green de-spill on semi-transparent silhouette edges
        if is_green:
            alpha_arr = np.array(alpha_img, dtype=np.float32) / 255.0
            edge_mask = (alpha_arr > 0.05) & (alpha_arr < 0.95)
            g[edge_mask] = np.minimum(g[edge_mask], np.maximum(r[edge_mask], b[edge_mask]))
            arr[:, :, 1] = g

        res = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        res.putalpha(alpha_img)

        out = io.BytesIO()
        res.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception as e:
        log(f"Transparent sprite cutout failed: {e}")
        return image_bytes


# ─── Visual Novel Location Memory Engine ─────────────────────────────────────

SCENE_MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".scene_location_memory.json")
_SCENE_MEMORY_LOCK = threading.Lock()
SCENE_MEMORY: dict = {}


def load_location_memory():
    global SCENE_MEMORY
    try:
        if os.path.exists(SCENE_MEMORY_FILE):
            with open(SCENE_MEMORY_FILE, "r", encoding="utf-8") as f:
                SCENE_MEMORY = json.load(f)
        else:
            SCENE_MEMORY = {}
    except Exception as e:
        log(f"Failed to load scene location memory: {e}")
        SCENE_MEMORY = {}


def save_location_memory():
    try:
        with _SCENE_MEMORY_LOCK:
            with open(SCENE_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(SCENE_MEMORY, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"Failed to save scene location memory: {e}")


def normalize_location_key(location: str) -> str:
    if not location:
        return "default"
    loc = location.lower().strip()
    loc = re.sub(r'[^a-z0-9\s]', '', loc)
    loc = re.sub(r'\s+', ' ', loc).strip()
    return loc or "default"


def get_remembered_location(chat_id: str, location: str, time_phase: str = "") -> dict:
    norm_loc = normalize_location_key(location)
    chat_key = str(chat_id or "default")

    if time_phase:
        exact_key = f"{chat_key}:{norm_loc}:{time_phase.lower().strip()}"
        if exact_key in SCENE_MEMORY:
            return SCENE_MEMORY[exact_key]

    base_key = f"{chat_key}:{norm_loc}"
    if base_key in SCENE_MEMORY:
        return SCENE_MEMORY[base_key]

    global_key = f"global:{norm_loc}"
    if global_key in SCENE_MEMORY:
        return SCENE_MEMORY[global_key]

    return {}


def store_remembered_location(chat_id: str, location: str, url: str, time_phase: str = "", prompt: str = ""):
    if not location or not url:
        return
    norm_loc = normalize_location_key(location)
    chat_key = str(chat_id or "default")
    entry = {
        "url": url,
        "location": location,
        "norm_location": norm_loc,
        "time_phase": time_phase,
        "chat_id": chat_key,
        "prompt": prompt,
        "timestamp": int(time.time()),
        "width": 1920,
        "height": 1080
    }
    with _SCENE_MEMORY_LOCK:
        base_key = f"{chat_key}:{norm_loc}"
        SCENE_MEMORY[base_key] = entry
        if time_phase:
            SCENE_MEMORY[f"{chat_key}:{norm_loc}:{time_phase.lower().strip()}"] = entry
        SCENE_MEMORY[f"global:{norm_loc}"] = entry
    save_location_memory()


def clear_remembered_location(chat_id: str = "", location: str = ""):
    with _SCENE_MEMORY_LOCK:
        if not chat_id and not location:
            SCENE_MEMORY.clear()
        else:
            to_del = []
            for k in list(SCENE_MEMORY.keys()):
                if chat_id and k.startswith(f"{chat_id}:"):
                    to_del.append(k)
                elif location and normalize_location_key(location) in k:
                    to_del.append(k)
            for k in to_del:
                SCENE_MEMORY.pop(k, None)
    save_location_memory()


load_location_memory()



_UPLOAD_CACHE = {}


def upload_image(image_bytes: bytes, filename: str = "image.png", mime_type: str = "image/png") -> str:
    """Upload image via Scotty resumable upload. Returns file reference path."""
    digest = hashlib.sha256(image_bytes).hexdigest()
    if digest in _UPLOAD_CACHE:
        return _UPLOAD_CACHE[digest]

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

    _UPLOAD_CACHE[digest] = file_ref
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
        refs = [[[ref, 1]] for ref in file_refs]
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
        refs = [[[ref, 1]] for ref in file_refs]
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

    for attempt in range(CONFIG["retry_attempts"]):
        if CONFIG.get("xsrf_token"):
            params["at"] = CONFIG["xsrf_token"]
        body = urllib.parse.urlencode(params)
        prev_text = ""
        transport = httpx.HTTPTransport(proxy=proxy) if proxy else None
        yielded_any = False
        try:
            with httpx.Client(transport=transport, timeout=CONFIG["request_timeout_sec"], verify=True) as client:
                with client.stream("POST", url, content=body.encode("utf-8"), headers=headers) as resp:
                    if resp.status_code == 400:
                        err_text = resp.read().decode("utf-8", errors="replace")
                        m = re.search(r'["\']?xsrf["\']?\s*,\s*["\']([^"\'\s]+)["\']', err_text)
                        if m:
                            CONFIG["xsrf_token"] = m.group(1)
                            log(f"Auto-recovered XSRF token from 400 in stream: {m.group(1)[:12]}...")
                            params["at"] = m.group(1)
                            continue
                        resp.raise_for_status()
                    elif resp.status_code == 405:
                        if update_bl_if_needed():
                            url = (
                                f"https://gemini.google.com{prefix}/_/BardChatUi/data/"
                                "assistant.lamda.BardFrontendService/StreamGenerate"
                                f"?bl={CONFIG['gemini_bl']}&hl=en&_reqid={reqid}&rt=c"
                            )
                            continue
                        resp.raise_for_status()
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
                                                            yielded_any = True
                                                    prev_text = t
                            except (json.JSONDecodeError, IndexError, TypeError):
                                pass
            if yielded_any:
                return
        except Exception as e:
            log(f"Stream generation attempt {attempt+1} error: {e}")
            if attempt < CONFIG["retry_attempts"] - 1:
                time.sleep(CONFIG["retry_delay_sec"])
                continue

    # Fall back to non-streaming if stream yielded nothing
    log("Falling back to non-streaming gemini_stream_generate...")
    raw = gemini_stream_generate(prompt, model_id, think_mode, file_refs)
    text = extract_response_text(raw)
    if text:
        yield text


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

    # 7. Internal image placeholders
    text = re.sub(r'https?://[^\s\"\'<>]*googleusercontent\.com/image_generation_content[^\s\"\'<>]*', '', text)
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


def extract_response_images(raw: str) -> list:
    """Extract generated image URLs from Gemini StreamGenerate response."""
    images = []
    seen = set()

    def add_url(u: str):
        if not u:
            return
        if any(h in u for h in ("googleusercontent.com", "ggpht.com", "work.fife.usercontent.google.com")):
            u = re.sub(r'=[swhd0-9\-]+$', '', u) + "=s0"
        if u and u not in seen:
            seen.add(u)
            images.append(u)

    # 1. Parse markdown image tags in response text
    text = extract_response_text(raw)
    if text:
        for u in re.findall(r'!\[.*?\]\((https?://[^\s\)]+)\)', text):
            if "image_generation_content" not in u:
                add_url(u)

    # 2. Parse inner JSON lines for Google image CDN urls
    for line in raw.split("\n"):
        if '"wrb.fr"' not in line or len(line) < 200:
            continue
        try:
            arr = json.loads(line)
            inner_str = arr[0][2]
            if not inner_str or len(inner_str) < 50:
                continue
            found = re.findall(
                r'https?://(?:[a-zA-Z0-9_\-]+\.)*(?:googleusercontent\.com|ggpht\.com|generativeai\.google\.com)/[^\s"\'<>\\]+',
                inner_str
            )
            for u in found:
                u = u.replace("\\u003d", "=").replace("\\u0026", "&")
                if any(skip in u.lower() for skip in ("googlelogo", "avatar", "photo.jpg", "profile", "image_generation_content")):
                    continue
                log(f"Extracted Google image candidate URL: {u}")
                add_url(u)
        except Exception:
            pass

    return images

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
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for k, v in self._cors_headers().items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

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
        path = self.path.split("?")[0]
        if (path.startswith("/v1") or path.startswith("/chat") or path == "/models") and not self._authorized():
            return self._send_error("Unauthorized", 401, "auth_error")

        if path in ("/v1/models", "/models"):
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
        elif path in ("/v1/scene/memory", "/scene/memory"):
            chat_id = ""
            if "?" in self.path:
                qs = urllib.parse.parse_qs(self.path.split("?", 1)[1])
                chat_id = qs.get("chatId", [""])[0] or qs.get("chat_id", [""])[0]
            if chat_id:
                filtered = {k: v for k, v in SCENE_MEMORY.items() if k.startswith(f"{chat_id}:")}
                self._send_json({"chatId": chat_id, "locations": filtered})
            else:
                self._send_json({"locations": SCENE_MEMORY})
        elif path in ("/", "/health", "/status"):
            self._send_json({
                "service": "Universal-Gift",
                "status": "online",
                "models": list(MODELS.keys()),
                "default_model": CONFIG.get("default_model", "gemini-3.8-flash"),
                "endpoints": [
                    "/v1/chat/completions",
                    "/v1/images/generations",
                    "/v1/scene/illustrate",
                    "/v1/scene/memory",
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
            elif norm in ("nano-banana-2", "nanobanana-2", "banana-2", "nano-banana2", "banana2"):
                model_name = "nano-banana-2"
                cfg = MODELS[model_name]
            elif norm in ("nano-banana-pro", "nanobanana-pro", "banana-pro", "nanobananapro", "bananapro"):
                model_name = "nano-banana-pro"
                cfg = MODELS[model_name]
            elif norm in ("nano-banana", "nanobanana", "banana", "nano-banana-1", "banana-1"):
                model_name = "nano-banana"
                cfg = MODELS[model_name]
            elif norm in ("nano-banana-2-lite", "nanobanana-2-lite", "banana-2-lite", "banana-lite"):
                model_name = "nano-banana-2-lite"
                cfg = MODELS[model_name]
            elif norm in ("imagen-3", "imagen-3.0-generate-002", "imagen", "imagen3"):
                model_name = "imagen-3"
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
        images = extract_response_images(raw)
        if images:
            for img_url in images:
                img_bytes = fetch_image_bytes(img_url)
                catbox_url = upload_to_catbox(img_bytes) if img_bytes else ""
                final_url = catbox_url or img_url
                if final_url not in text:
                    text = (text + "\n\n" if text else "") + f"![Generated Image]({final_url})\n\n[Direct Image Link]({final_url})"
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
            self.send_header("Connection", "close")
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
                self.close_connection = True
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

    def handle_images(self, body: bytes):
        try:
            req = json.loads(body)
        except Exception as e:
            return self._send_error(f"Invalid JSON body: {e}")

        prompt = req.get("prompt")
        if not prompt or not isinstance(prompt, str):
            return self._send_error("Field 'prompt' is required and must be a string", 400)

        raw_model = req.get("model", "nano-banana-2")
        model_name, model_id, think_mode, err = self._resolve_model(raw_model)
        if err:
            return self._send_error(err)

        n = min(max(int(req.get("n", 1)), 1), 4)
        response_format = req.get("response_format", "url")
        size = req.get("size", "1024x1024")
        transparent = bool(req.get("transparent", False))

        # 1. Handle Reference Image (Character portrait conditioning)
        ref_img = req.get("reference_image") or req.get("image") or req.get("portrait_image")
        file_refs = None
        if ref_img:
            log(f"[Image Reference] Incoming request contains reference image: type={type(ref_img).__name__}")
            images_to_upload = []

            def parse_single_ref(r):
                if not r or not isinstance(r, (str, bytes)):
                    return None
                if isinstance(r, bytes):
                    return (r, "image/png")
                r_str = r.strip()
                if r_str.startswith("data:"):
                    try:
                        mime = r_str.split(";", 1)[0].replace("data:", "")
                        b64 = r_str.split(",", 1)[1]
                        return (base64.b64decode(b64), mime)
                    except Exception as e:
                        log(f"[Image Reference] Failed decoding data URI: {e}")
                        return None
                elif r_str.startswith("http://") or r_str.startswith("https://"):
                    return (r_str, None)
                elif r_str.startswith("/") or r_str.startswith("./"):
                    # Local path or relative endpoint
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    search_paths = [
                        r_str,
                        os.path.join(base_dir, "TAVERN", "data", r_str.lstrip("/")),
                        os.path.join(base_dir, "TAVERN", r_str.lstrip("/")),
                        os.path.join(base_dir, r_str.lstrip("/")),
                        os.path.join(base_dir, "..", "data", r_str.lstrip("/")),
                        os.path.join(base_dir, "..", r_str.lstrip("/")),
                        os.path.join(os.getcwd(), "data", r_str.lstrip("/")),
                        os.path.join(os.getcwd(), r_str.lstrip("/")),
                    ]
                    for p in search_paths:
                        if os.path.isfile(p):
                            try:
                                with open(p, "rb") as f:
                                    log(f"[Image Reference] Loaded local reference file from disk: {p}")
                                    return (f.read(), "image/png")
                            except Exception as e:
                                log(f"[Image Reference] Failed reading local file {p}: {e}")
                    # Try local Vite/Express dev servers
                    for port in (5173, 3001):
                        try:
                            test_url = f"http://localhost:{port}/{r_str.lstrip('/')}"
                            req_t = urllib.request.Request(test_url, headers={"User-Agent": "UniversalGift"})
                            with urllib.request.urlopen(req_t, timeout=3) as resp_t:
                                if resp_t.status == 200:
                                    log(f"[Image Reference] Fetched local reference from dev server: {test_url}")
                                    return (resp_t.read(), "image/png")
                        except Exception:
                            pass
                    log(f"[Image Reference] Unable to resolve relative path {r_str}")
                    return None
                else:
                    # Raw base64 string
                    try:
                        decoded = base64.b64decode(r_str)
                        if len(decoded) > 100:
                            return (decoded, "image/png")
                    except Exception as e:
                        log(f"[Image Reference] Error decoding raw base64 string: {e}")
                    return None

            if isinstance(ref_img, list):
                for item in ref_img:
                    res = parse_single_ref(item)
                    if res:
                        images_to_upload.append(res)
            else:
                res = parse_single_ref(ref_img)
                if res:
                    images_to_upload.append(res)

            if images_to_upload:
                try:
                    file_refs = upload_images(images_to_upload)
                    log(f"[Image Reference] Conditioned on {len(images_to_upload)} character reference image(s): {file_refs}")
                except Exception as e:
                    log(f"[Image Reference ERROR] upload_images failed: {e}")
                    return self._send_error(f"Failed to upload reference image to Gemini: {e}", 400)
            else:
                log(f"[Image Reference ERROR] Failed to resolve provided reference image!")
                return self._send_error("Reference image was provided but could not be parsed or resolved. Provide a valid base64 data URL, image URL, or avatar file path.", 400)

        image_prompt = prompt.strip()
        if not any(image_prompt.lower().startswith(p) for p in ("generate an image", "create an image", "draw ", "render ")):
            image_prompt = f"Generate an image: {image_prompt}"

        if file_refs:
            # 1. Dress / Outfit consistency
            if not any(k in image_prompt.lower() for k in ("outfit", "dress", "clothing", "wear the exact", "same clothes")):
                image_prompt += " The character MUST wear the EXACT SAME dress and clothing shown in the reference image (identical outfit design, neckline, collar, colors, and accessories). Do NOT alter or change the clothes."

            # 2. Framing: Full shoulders, elbows, and hands completely inside canvas
            if not any(k in image_prompt.lower() for k in ("framing", "shoulders", "elbows", "hands stay")):
                image_prompt += " Vertical upper body portrait framed from mid-chest upward. Ensure both full shoulders, and all raised elbows and hands, are completely visible inside the frame borders without edge cutoff."

            # 3. Authentic art style & strict anti-smoothing
            if not any(k in image_prompt.lower() for k in ("anti-smoothing", "airbrush", "line art weight")):
                image_prompt += " Duplicate the exact art style, line art weight, linework texture, and shading of the reference image. Strictly do not smooth it out, do not airbrush, and do not use 3D CGI plastic rendering."

        if transparent and "green background" not in image_prompt.lower():
            if any(k in image_prompt.lower() for k in ("bust", "upper chest", "portrait", "shoulders")):
                image_prompt += " on a solid bright green background, flat plain backdrop, framed centered with both full shoulders, elbows, and hands completely inside the frame borders."
            else:
                image_prompt += " on a solid bright green background, flat plain backdrop, character standing centered with all limbs completely inside the frame borders."

        try:
            raw = gemini_stream_generate(image_prompt, model_id, think_mode, file_refs)
            image_urls = extract_response_images(raw)
            text = extract_response_text(raw)
            created = int(time.time())

            data = []
            if image_urls:
                for img_url in image_urls[:n]:
                    img_bytes = fetch_image_bytes(img_url)
                    if img_bytes and transparent:
                        img_bytes = remove_chroma_background(img_bytes)

                    catbox_url = ""
                    # Skip external Catbox upload when client only requests local base64 (saves ~5-6s per image)
                    if response_format != "b64_json" and img_bytes:
                        catbox_url = upload_to_catbox(img_bytes)
                    final_url = catbox_url or img_url

                    if response_format == "b64_json":
                        if img_bytes:
                            b64 = base64.b64encode(img_bytes).decode("utf-8")
                            data.append({"b64_json": b64, "url": final_url, "revised_prompt": prompt})
                        else:
                            data.append({"url": final_url, "revised_prompt": prompt})
                    else:
                        data.append({"url": final_url, "revised_prompt": prompt})
            else:
                err_msg = text or "Gemini did not return an image. Prompt may have been filtered or refused."
                log(f"[Image Generation Failed] {err_msg}")
                return self._send_error(err_msg, 502, "upstream_refusal")

            self._send_json({
                "created": created,
                "data": data
            })
        except Exception as e:
            log(f"Image generation error: {e}")
            self._send_error(str(e), 500, "upstream_error")


    def handle_scene_illustrate(self, body: bytes):
        try:
            req = json.loads(body)
        except Exception as e:
            return self._send_error(f"Invalid JSON body: {e}")

        text = req.get("text") or req.get("scene") or req.get("prompt") or ""
        location = req.get("location") or ""
        chat_id = req.get("chat_id") or req.get("chatId") or "default"
        time_phase = req.get("time_phase") or req.get("timePhase") or ""
        force = bool(req.get("force") or req.get("force_regenerate") or False)
        style = req.get("style", "visual novel anime digital scenery background, cinematic lighting, masterpiece, 1080p widescreen wallpaper")

        if not text and "messages" in req:
            msgs = req.get("messages", [])
            recent = [m.get("content", "") for m in msgs[-3:] if m.get("content")]
            text = " ".join(recent)

        if not text and not location:
            return self._send_error("No scene text or location provided", 400)

        # 1. Location Memory Cache Check (Instant 0 ms recall if already visited & not forced)
        if not force and location:
            remembered = get_remembered_location(chat_id, location, time_phase)
            if remembered and remembered.get("url"):
                log(f"[Location Memory HIT] Recalled background for '{location}': {remembered['url']}")
                return self._send_json({
                    "url": remembered["url"],
                    "cached": True,
                    "location": location,
                    "time_phase": time_phase,
                    "prompt": remembered.get("prompt", ""),
                    "success": True
                })

        # 2. Clean narrative text strictly for environment / scenery (NO characters, NO dialogue)
        clean_text = text
        clean_text = re.sub(r'<{1,2}scene:[^>]*>{1,2}', '', clean_text)
        clean_text = re.sub(r'!\[.*?\]\(.*?\)', '', clean_text)
        clean_text = re.sub(r'\[.*?\]\(.*?\)', '', clean_text)
        clean_text = re.sub(r'["“「][^"”」]*["”」]', '', clean_text)
        clean_text = re.sub(r'[*_~`]', '', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        if len(clean_text) > 300:
            clean_text = clean_text[:300]

        env_cues = []
        if location:
            env_cues.append(f"Setting: {location}")
        if time_phase:
            env_cues.append(f"Time of day: {time_phase}")
        if clean_text:
            env_cues.append(f"Environment: {clean_text}")

        env_desc = ". ".join(env_cues) if env_cues else "scenic anime visual novel setting"

        image_prompt = (
            f"Generate an image: {style}. {env_desc}. "
            "Anime visual novel background art, empty scenic architecture, interior or exterior scenery backdrop, "
            "atmospheric cinematic lighting, highly detailed environment, 16:9 widescreen composition, 1080p full HD wallpaper. "
            "STRICT NEGATIVE CONSTRAINT: Strictly empty background, NO people, NO characters, NO human beings, NO silhouettes, NO faces, nobody. Scenery backdrop only."
        )

        try:
            raw_model = req.get("model", "nano-banana-2")
            _, model_id, think_mode, _ = self._resolve_model(raw_model)
            raw = gemini_stream_generate(image_prompt, model_id, think_mode)
            image_urls = extract_response_images(raw)
            final_url = ""
            if image_urls:
                img_bytes = fetch_image_bytes(image_urls[0])
                if img_bytes:
                    hd_bytes = make_1080p_widescreen(img_bytes)
                    final_url = upload_to_catbox(hd_bytes) or image_urls[0]
                else:
                    final_url = image_urls[0]

            if final_url and location:
                store_remembered_location(chat_id, location, final_url, time_phase, image_prompt)
                log(f"[Location Memory SAVED] Stored background for '{location}': {final_url}")

            self._send_json({
                "url": final_url,
                "cached": False,
                "location": location,
                "prompt": image_prompt,
                "success": bool(final_url)
            })
        except Exception as e:
            log(f"Scene illustration error: {e}")
            self._send_error(str(e), 500)

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
        elif path in ("/v1/images/generations", "/images/generations"):
            self.handle_images(body)
        elif path in ("/v1/scene/illustrate", "/scene/illustrate", "/v1/chat/illustrate"):
            self.handle_scene_illustrate(body)
        elif path in ("/v1/scene/clear_memory", "/scene/clear_memory"):
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}
            cid = data.get("chatId") or data.get("chat_id") or ""
            loc = data.get("location") or ""
            clear_remembered_location(cid, loc)
            self._send_json({"cleared": True, "chatId": cid, "location": loc})
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

    class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = ReusableTCPServer((CONFIG["host"], CONFIG["port"]), GeminiHandler)
    display_host = "localhost" if CONFIG["host"] in ("0.0.0.0", "") else CONFIG["host"]

    print("═════════════════════════════════════════════════════════════════════════")
    print("      🎁 Universal-Gift - Universal Gemini Web2API Proxy 🎁              ")
    print("═════════════════════════════════════════════════════════════════════════")
    print(f"  • Local API Base:       http://{display_host}:{CONFIG['port']}/v1")
    print(f"  • Chat Completions:     http://{display_host}:{CONFIG['port']}/v1/chat/completions")
    print(f"  • Image Generations:    http://{display_host}:{CONFIG['port']}/v1/images/generations")
    print(f"  • Models Endpoint:      http://{display_host}:{CONFIG['port']}/v1/models")
    print(f"  • Default Model:        {CONFIG['default_model']}")
    print(f"  • Pro Reasoning:        gemini-3.1-pro-extended (or gemini-3.1-pro)")
    print(f"  • Nano Banana:          nano-banana-2, nano-banana-pro, nano-banana")
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
