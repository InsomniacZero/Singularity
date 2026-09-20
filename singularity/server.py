#!/usr/bin/env python3
"""
Singularity Unified AI Hub & Universal Gateway
Port 9000
"""

import asyncio
import base64
import json
import os
import time
import inspect
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

try:
    if os.getenv("NO_FASTAPI", "").strip() in ("1", "true", "yes"):
        raise ImportError("FastAPI disabled by NO_FASTAPI env var")
    from fastapi import FastAPI, HTTPException, Request, Response, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="Singularity Unified AI Gateway", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
except Exception:
    # Lightweight pure-Python fallback for Termux / mobile (no Rust / Pydantic build needed!)
    from starlette.applications import Starlette
    from starlette.exceptions import HTTPException
    from starlette.requests import Request
    from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
    from starlette.middleware.cors import CORSMiddleware
    from starlette.staticfiles import StaticFiles
    from starlette.routing import Route, Mount

    from contextlib import asynccontextmanager

    async def _http_exception_handler(request, exc):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @asynccontextmanager
    async def _gateway_lifespan(gateway_app):
        for handler in gateway_app._startup_handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception:
                pass
        yield
        for handler in gateway_app._shutdown_handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception:
                pass

    class StarletteGateway(Starlette):
        def __init__(self):
            self._startup_handlers = []
            self._shutdown_handlers = []
            super().__init__(
                exception_handlers={HTTPException: _http_exception_handler},
                lifespan=_gateway_lifespan,
            )
            self.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        def _route_decorator(self, path: str, methods: list):
            def decorator(func):
                sig = inspect.signature(func)
                async def handler(request):
                    kwargs = {}
                    for p in sig.parameters.values():
                        if p.name in ("request", "req"):
                            kwargs[p.name] = request
                        elif p.name in request.path_params:
                            kwargs[p.name] = request.path_params[p.name]
                    if inspect.iscoroutinefunction(func):
                        res = await func(**kwargs)
                    else:
                        res = func(**kwargs)
                    if isinstance(res, (dict, list)):
                        return JSONResponse(res)
                    return res
                self.router.routes.append(Route(path, handler, methods=methods))
                return func
            return decorator

        def get(self, path: str):
            return self._route_decorator(path, ["GET"])

        def post(self, path: str):
            return self._route_decorator(path, ["POST"])

        def delete(self, path: str):
            return self._route_decorator(path, ["DELETE"])

        def put(self, path: str):
            return self._route_decorator(path, ["PUT"])

        def patch(self, path: str):
            return self._route_decorator(path, ["PATCH"])

        def head(self, path: str):
            return self._route_decorator(path, ["HEAD", "GET"])

        def on_event(self, event_type: str):
            def decorator(func):
                if event_type == "startup":
                    self._startup_handlers.append(func)
                elif event_type == "shutdown":
                    self._shutdown_handlers.append(func)
                return func
            return decorator

    app = StarletteGateway()

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"

import sys
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import httpx
import uvicorn

import tunnel
import db
import providers
try:
    from singularity import worker
except ImportError:
    import worker
try:
    from singularity import engines
except ImportError:
    import engines
from providers import (
    MODELS_CATALOG,
    PROVIDERS_CONFIG,
    get_all_limits,
    get_all_services_status,
    get_dynamic_models_catalog,
    get_pid_for_port,
    get_stored_cookies,
    remove_stacked_cookie,
    save_stacked_cookies,
    start_all_services,
    start_provider,
    stop_all_services,
    stop_provider,
)


def resolve_model_provider(model_name: str) -> str:
    """Route a model name to its respective provider service."""
    m = (model_name or "").lower().strip()

    # 1. Search in catalog first for exact ID match
    for item in MODELS_CATALOG:
        if item["id"].lower() == m:
            return item["provider"]

    # 2. Explicit prefixes or known names
    if m.startswith("claude"):
        return "claude"
    if m.startswith("gemini") or m.startswith("imagen") or m.startswith("nano-banana"):
        return "gemini"
    if m.startswith("kimi") or m.startswith("moonshot"):
        return "kimi"
    if m.startswith("glm") or m.startswith("cogview"):
        return "glm"
    if m.startswith("grok") or m in ["fast", "heavy"]:
        return "grok"
    if m.startswith("deepseek") or m.startswith("ds-") or m.startswith("r1") or m.startswith("v3") or m.startswith("v4") or m.startswith("coder") or m == "flash":
        return "deepseek"
    if m.startswith("qwen") or m.startswith("tongyi") or m.startswith("wanx"):
        return "qwen"
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4") or m in ["auto", "research", "flare", "astra", "luna", "sol", "terra", "sunburst"] or m.startswith("image-2.5"):
        return "chatgpt"

    # Fallback to chatgpt
    return "chatgpt"


# -------------------------------------------------------------------
# Universal OpenAI Gateway Endpoints (/v1)
# -------------------------------------------------------------------

@app.get("/v1/models")
async def list_models():
    """Return unified OpenAI-compatible models list across all 8 providers."""
    now = int(time.time())
    data = []
    catalog = get_dynamic_models_catalog()
    for m in catalog:
        data.append({
            "id": m["id"],
            "object": "model",
            "created": now,
            "owned_by": m["provider"],
            "permission": [],
            "root": m["id"],
            "parent": None,
            "locked": m.get("locked", False),
            "reason": m.get("reason"),
            "capabilities": m.get("capabilities", []),
        })
    return {"object": "list", "data": data}


def is_simulation_mode() -> bool:
    """Check if device simulation mode is enabled."""
    return providers.is_simulation_active()


def _generate_simulated_image_svg(prompt: str) -> str:
    """Generate a crisp, authentic SVG image for simulation testing."""
    prompt_lower = (prompt or "").lower()
    if "apple" in prompt_lower:
        # High quality vector artwork of a glossy red Apple
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <radialGradient id="bgGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#1c2333"/>
      <stop offset="100%" stop-color="#0b0e14"/>
    </radialGradient>
    <radialGradient id="appleGrad" cx="35%" cy="30%" r="65%">
      <stop offset="0%" stop-color="#ff6b6b"/>
      <stop offset="30%" stop-color="#e03131"/>
      <stop offset="70%" stop-color="#c92a2a"/>
      <stop offset="100%" stop-color="#5c0909"/>
    </radialGradient>
    <linearGradient id="leafGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#69db7c"/>
      <stop offset="60%" stop-color="#2f9e44"/>
      <stop offset="100%" stop-color="#1b5e20"/>
    </linearGradient>
    <linearGradient id="stemGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#a67c52"/>
      <stop offset="100%" stop-color="#4e3620"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="16" stdDeviation="24" flood-color="#c92a2a" flood-opacity="0.4"/>
    </filter>
  </defs>
  <rect width="512" height="512" rx="28" fill="url(#bgGlow)"/>
  <ellipse cx="256" cy="420" rx="140" ry="24" fill="#000000" opacity="0.6"/>
  <!-- Stem -->
  <path d="M 256 160 C 254 110, 275 85, 298 70 C 294 76, 276 102, 270 160 Z" fill="url(#stemGrad)"/>
  <!-- Leaf -->
  <path d="M 270 120 C 330 90, 365 110, 370 140 C 335 155, 290 145, 270 120 Z" fill="url(#leafGrad)"/>
  <path d="M 275 122 Q 320 128 360 138" stroke="#8ce99a" stroke-width="2" fill="none" opacity="0.7"/>
  <!-- Apple Body -->
  <path d="M 256 185 C 230 160, 140 160, 130 250 C 120 340, 190 410, 256 410 C 322 410, 392 340, 382 250 C 372 160, 282 160, 256 185 Z" fill="url(#appleGrad)" filter="url(#glow)"/>
  <!-- Specular Highlights -->
  <ellipse cx="195" cy="225" rx="36" ry="58" transform="rotate(-30 195 225)" fill="#ffffff" opacity="0.32"/>
  <ellipse cx="180" cy="210" rx="14" ry="24" transform="rotate(-30 180 210)" fill="#ffffff" opacity="0.6"/>
  <!-- Bottom indents -->
  <path d="M 230 405 C 245 400, 267 400, 282 405" stroke="#380505" stroke-width="4" stroke-linecap="round" fill="none"/>
</svg>"""
    else:
        # Futuristic Cybernetic / Digital Art SVG
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0d1117"/>
      <stop offset="100%" stop-color="#161b22"/>
    </linearGradient>
    <linearGradient id="neonCyan" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00f2fe"/>
      <stop offset="100%" stop-color="#4facfe"/>
    </linearGradient>
    <linearGradient id="neonPurple" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#b176f2"/>
      <stop offset="100%" stop-color="#f857a6"/>
    </linearGradient>
    <filter id="neonGlow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="12" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <rect width="512" height="512" rx="28" fill="url(#bgGrad)"/>
  <circle cx="256" cy="256" r="160" fill="none" stroke="url(#neonCyan)" stroke-width="3" stroke-dasharray="12 8" opacity="0.4"/>
  <circle cx="256" cy="256" r="120" fill="none" stroke="url(#neonPurple)" stroke-width="5" filter="url(#neonGlow)"/>
  <polygon points="256,150 348,310 164,310" fill="none" stroke="url(#neonCyan)" stroke-width="4" filter="url(#neonGlow)"/>
  <circle cx="256" cy="256" r="48" fill="url(#neonPurple)" opacity="0.85" filter="url(#neonGlow)"/>
  <circle cx="256" cy="256" r="22" fill="#ffffff"/>
</svg>"""

    b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64}"


def _get_simulated_response_payload(model_name: str, provider_id: str, prompt_text: str = "") -> str:
    """Determine simulated response text (handling text, image, and video modalities)."""
    m_lower = (model_name or "").lower()
    p_lower = (prompt_text or "").lower()

    # Detect Video Modality
    if any(k in m_lower for k in ("video", "t2v", "wanx-2.1", "cogvideox", "kling", "sora", "runway")) or any(k in p_lower for k in ("video", "movie", "animation", "motion clip")):
        video_url = "/static/demo_video.mp4"
        return (
            f"🎬 **Singularity Cinematic Video Synthesis** (Simulated Response)\n\n"
            f"• **Model:** `{model_name}`\n"
            f"• **Prompt:** *\"{prompt_text or 'Autonomous dynamic frame sequence'}\"*\n"
            f"• **Specs:** 720p HD • 24 FPS • H.264 MP4\n\n"
            f"[Generated Video]({video_url})"
        )

    # Detect Image Modality
    if any(k in m_lower for k in ("image", "imagine", "cogview", "dall-e", "flux", "imagen", "sdxl", "wanx")) or any(k in p_lower for k in ("img", "image", "picture", "photo", "drawing", "illustration", "wallpaper")):
        img_url = _generate_simulated_image_svg(prompt_text)
        return (
            f"🎨 **Singularity Neural Image Synthesis** (Simulated Response)\n\n"
            f"• **Model:** `{model_name}`\n"
            f"• **Prompt:** *\"{prompt_text or 'Creative synthesis'}\"*\n"
            f"• **Resolution:** 1024x1024 High-Definition Vector Output\n\n"
            f"![Generated Image]({img_url})"
        )

    # Standard Text Response
    return (
        f"⚡ **Singularity Portable Gateway** (Simulated Response)\n\n"
        f"• **Model:** `{model_name}`\n"
        f"• **Provider:** `{provider_id.upper()}`\n"
        f"• **Gateway Status:** 100% Self-Contained (Zero Legacy Dependencies)\n\n"
        f"Your device simulation is verified and running cleanly. Streaming SSE buffers, token rotation, and headers are functioning as expected."
    )


async def generate_simulated_stream(model_name: str, provider_id: str, prompt_text: str = "") -> AsyncIterator[bytes]:
    """Yield OpenAI-compatible SSE chunks for offline/device simulation testing."""
    created_ts = int(time.time())
    sim_id = f"chatcmpl-sim-{int(time.time()*1000)}"

    role_chunk = {
        "id": sim_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model_name,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    yield f"data: {json.dumps(role_chunk)}\n\n".encode("utf-8")
    await asyncio.sleep(0.04)

    sim_text = _get_simulated_response_payload(model_name, provider_id, prompt_text)

    # Stream in natural chunk sizes
    words = sim_text.split(" ")
    for w in words:
        c = {
            "id": sim_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model_name,
            "choices": [{"index": 0, "delta": {"content": w + " "}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(c)}\n\n".encode("utf-8")
        await asyncio.sleep(0.02)

    finish_chunk = {
        "id": sim_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": model_name,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(finish_chunk)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Universal router for chat completions across all 7 providers."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    model_name = body.get("model", "gpt-5-6-mini")
    res = resolve_model_provider(model_name)
    if isinstance(res, tuple):
        provider_id, target_port = res
    else:
        provider_id = res
        meta_cfg = providers.PROVIDERS_CONFIG.get(provider_id, providers.PROVIDERS_CONFIG.get("chatgpt", {}))
        target_port = meta_cfg.get("port", 8000)

    # If simulation mode is requested or active, we can skip target resolution
    target_url = f"http://127.0.0.1:{target_port}/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Singularity-Universal-Gateway/2.0",
    }

    # Pass through incoming authorization header or look up default account token
    incoming_auth = request.headers.get("Authorization")
    meta = providers.PROVIDERS_CONFIG.get(provider_id, {})
    if incoming_auth:
        headers["Authorization"] = incoming_auth
    elif meta.get("auth_env"):
        env_token = os.getenv(meta["auth_env"])
        if env_token:
            headers["Authorization"] = f"Bearer {env_token}"
        elif meta["auth_header"]:
            headers["Authorization"] = meta["auth_header"]
    elif meta["auth_header"]:
        headers["Authorization"] = meta["auth_header"]

    is_stream = body.get("stream", False)
    simulate_requested = is_simulation_mode() or body.get("simulate", False)

    # Extract user prompt text for modality detection & simulation
    messages = body.get("messages", [])
    prompt_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                prompt_text = content
            elif isinstance(content, list):
                prompt_text = " ".join(item.get("text", "") for item in content if isinstance(item, dict))
            break

    if simulate_requested:
        if is_stream:
            return StreamingResponse(
                generate_simulated_stream(model_name, provider_id, prompt_text=prompt_text),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Singularity-Provider": provider_id,
                    "X-Singularity-Simulated": "true",
                },
            )
        else:
            sim_content = _get_simulated_response_payload(model_name, provider_id, prompt_text)
            return JSONResponse(
                status_code=200,
                content={
                    "id": f"chatcmpl-sim-{int(time.time()*1000)}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": sim_content,
                        },
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
                },
            )

    if is_stream:
        async def stream_generator() -> AsyncIterator[bytes]:
            client = httpx.AsyncClient(timeout=120.0)
            try:
                async with client.stream("POST", target_url, json=body, headers=headers) as upstream:
                    if upstream.status_code < 400:
                        async for chunk in upstream.aiter_bytes():
                            if chunk:
                                yield chunk
                        return
            except Exception:
                pass
            finally:
                await client.aclose()

            # Direct in-process native engine fallback (when upstream daemon is down or returned >= 400)
            try:
                async for chunk in engines.stream_chat(provider_id, model_name, body.get("messages", []), stream=True):
                    yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
                return
            except Exception as inner_e:
                p_name = meta.get("name", provider_id)
                err_msg = f"Provider {p_name} error: {str(inner_e)}"
                yield f"data: {json.dumps({'error': err_msg})}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Singularity-Provider": provider_id,
            },
        )

    # Non-streaming request
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(target_url, json=body, headers=headers)
            if resp.status_code < 400:
                try:
                    data = resp.json()
                    return JSONResponse(status_code=resp.status_code, content=data)
                except Exception:
                    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
        except Exception:
            pass

    # Direct in-process native engine fallback
    try:
        data = await engines.generate_chat(provider_id, model_name, body.get("messages", []))
        return JSONResponse(status_code=200, content=data)
    except Exception as inner_e:
        raise HTTPException(
            status_code=502,
            detail=f"Provider {meta['name']} error: {str(inner_e)}",
        )


@app.post("/v1/images/generations")
async def image_generations(request: Request):
    """Route image generation requests to Gemini, Grok, or GLM."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    model = body.get("model", "gemini-3.8-flash")
    provider_id = resolve_model_provider(model)
    meta = PROVIDERS_CONFIG.get(provider_id, PROVIDERS_CONFIG["gemini"])

    simulate_requested = is_simulation_mode() or body.get("simulate", False)
    if simulate_requested:
        return JSONResponse(status_code=200, content={
            "created": int(time.time()),
            "data": [{
                "url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1024&q=80",
                "revised_prompt": body.get("prompt", "A high-fidelity futuristic rendering generated by Singularity")
            }]
        })

    target_port = meta["port"]
    target_host = providers.get_provider_host(provider_id)
    target_url = f"http://{target_host}:{target_port}/v1/images/generations"
    headers = {"Content-Type": "application/json"}
    if meta["auth_header"]:
        headers["Authorization"] = meta["auth_header"]

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(target_url, json=body, headers=headers)
            try:
                return JSONResponse(status_code=resp.status_code, content=resp.json())
            except Exception:
                return Response(content=resp.content, status_code=resp.status_code)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Image generation failed: {str(e)}")


# -------------------------------------------------------------------
# Singularity Management APIs (/api)
# -------------------------------------------------------------------

@app.get("/healthz")
async def health():
    return {"status": "ok", "app": "Singularity", "version": "1.0.0", "port": 9000}


@app.get("/api/services")
async def api_get_services():
    services = await get_all_services_status()
    # Also attach Singularity itself
    singularity_info = {
        "id": "singularity",
        "name": "Singularity Hub",
        "badge": "Core Gateway",
        "port": 9000,
        "color": "#D97757",
        "pid": os.getpid(),
        "running": True,
        "latency_ms": 0.5,
        "health_path": "/healthz",
        "cookie_label": "System Master Gateway",
    }
    return {"services": services, "hub": singularity_info}


@app.post("/api/services/start_all")
async def api_start_all():
    return start_all_services()


@app.post("/api/services/stop_all")
async def api_stop_all():
    return stop_all_services()


@app.post("/api/services/{provider_id}/start")
async def api_start_service(provider_id: str):
    res = start_provider(provider_id)
    return res


@app.post("/api/services/{provider_id}/stop")
async def api_stop_service(provider_id: str):
    res = stop_provider(provider_id)
    return res


@app.post("/api/services/{provider_id}/restart")
async def api_restart_service(provider_id: str):
    stop_provider(provider_id)
    time.sleep(1.0)
    return start_provider(provider_id)


@app.get("/api/simulation")
async def api_get_simulation():
    active = providers.is_simulation_active()
    return {
        "enabled": active,
        "mode": "simulated" if active else "live",
        "description": "Device Simulation Mode allows testing UI, models, and clients without local backends.",
    }


@app.post("/api/simulation")
async def api_toggle_simulation(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    enabled = body.get("enabled")
    if enabled is None:
        enabled = not providers.is_simulation_active()
    db.set_setting("simulation_mode", "1" if enabled else "0")
    return {
        "status": "ok",
        "enabled": bool(enabled),
        "mode": "simulated" if enabled else "live",
    }


@app.get("/api/config")
async def api_get_config():
    return {
        "simulation_mode": providers.is_simulation_active(),
        "remote_host": db.get_setting("remote_host", "127.0.0.1"),
        "settings": db.get_all_settings(),
        "vault_stats": db.get_stats(),
    }


@app.post("/api/config")
async def api_set_config(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    for k, v in body.items():
        db.set_setting(k, str(v))
    return {
        "status": "ok",
        "settings": db.get_all_settings(),
    }


@app.get("/api/limits")
async def api_get_limits():
    return await get_all_limits()


@app.get("/api/models")
async def api_get_models():
    return {"models": get_dynamic_models_catalog()}


@app.get("/api/cookies")
async def api_get_cookies():
    return get_stored_cookies()


@app.get("/api/cookies/export")
async def api_export_cookies():
    return db.export_all_json()


@app.post("/api/cookies/import")
async def api_import_cookies(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        res = db.import_all_json(data)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/cookies/{provider_id}")
async def api_save_cookies(provider_id: str, request: Request):
    body = await request.json()
    accounts = body.get("accounts", [])
    if isinstance(accounts, str):
        # Split by newlines (strictly NOT by comma)
        accounts = [line.strip() for line in accounts.splitlines() if line.strip()]
    res = save_stacked_cookies(provider_id, accounts)
    return res


@app.post("/api/cookies/{provider_id}/remove")
@app.delete("/api/cookies/{provider_id}")
async def api_remove_cookie(provider_id: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    identifier = body.get("identifier")
    index = body.get("index")
    account_id = body.get("id")
    res = remove_stacked_cookie(provider_id, identifier=identifier, index=account_id if account_id is not None else index)
    return res



# -------------------------------------------------------------------
# Cloud Tunnel (ngrok) Endpoints
# -------------------------------------------------------------------

@app.get("/api/tunnel/status")
async def api_get_tunnel_status():
    return tunnel.get_tunnel_status()


@app.post("/api/tunnel/start")
async def api_start_tunnel():
    return tunnel.start_tunnel(port=9000)


@app.post("/api/tunnel/stop")
async def api_stop_tunnel():
    return tunnel.stop_tunnel()


@app.post("/api/tunnel/authtoken")
async def api_save_authtoken(request: Request):
    body = await request.json()
    token = body.get("token", "")
    return tunnel.save_authtoken(token)


# -------------------------------------------------------------------
# Static Frontend Serving
# -------------------------------------------------------------------

@app.get("/")
@app.head("/")
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    return FileResponse(index_path, media_type="text/html")


@app.get("/logo.svg")
@app.head("/logo.svg")
async def serve_logo():
    logo_path = STATIC_DIR / "logo.svg"
    return FileResponse(logo_path, media_type="image/svg+xml")


@app.get("/favicon.ico")
@app.head("/favicon.ico")
async def serve_favicon():
    logo_path = STATIC_DIR / "logo.svg"
    return FileResponse(logo_path, media_type="image/svg+xml")


# Mount static assets directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def on_startup():
    """Start supervisor watchdog and auto-launch in-process workers (chatgpt, kimi, grok, glm, deepseek, qwen) if offline."""
    try:
        worker.ensure_supervisor_running()
        for p in ["chatgpt", "kimi", "grok", "glm", "deepseek", "qwen"]:
            try:
                start_provider(p)
            except Exception:
                pass
    except Exception:
        pass


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "9000"))
    try:
        worker.ensure_supervisor_running()
        for p in ["chatgpt", "kimi", "grok", "glm", "deepseek", "qwen"]:
            try:
                start_provider(p)
            except Exception:
                pass
    except Exception:
        pass
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
