#!/usr/bin/env python3
"""
Singularity Unified AI Hub & Universal Gateway
Port 9000
"""

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

    async def _http_exception_handler(request, exc):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    class StarletteGateway(Starlette):
        def __init__(self):
            super().__init__(
                exception_handlers={HTTPException: _http_exception_handler}
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

        def head(self, path: str):
            return self._route_decorator(path, ["HEAD", "GET"])

    app = StarletteGateway()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

import sys
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import httpx
import uvicorn

import tunnel
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
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4") or m in ["auto", "research", "flare", "astra", "luna", "sol", "terra", "sunburst"] or m.startswith("image-2.5"):
        return "chatgpt"

    # Fallback to chatgpt
    return "chatgpt"


# -------------------------------------------------------------------
# Universal OpenAI Gateway Endpoints (/v1)
# -------------------------------------------------------------------

@app.get("/v1/models")
async def list_models():
    """Return unified OpenAI-compatible models list across all 6 providers."""
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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Universal router for chat completions across all 6 providers."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    model_name = body.get("model", "auto")
    provider_id = resolve_model_provider(model_name)
    meta = PROVIDERS_CONFIG.get(provider_id)
    if not meta:
        raise HTTPException(status_code=400, detail=f"No provider found for model: {model_name}")

    target_port = meta["port"]
    target_url = f"http://127.0.0.1:{target_port}/v1/chat/completions"

    headers = {"Content-Type": "application/json"}
    if meta["auth_header"]:
        headers["Authorization"] = meta["auth_header"]

    is_stream = body.get("stream", False)

    if is_stream:
        async def stream_generator() -> AsyncIterator[bytes]:
            client = httpx.AsyncClient(timeout=120.0)
            try:
                async with client.stream("POST", target_url, json=body, headers=headers) as upstream:
                    if upstream.status_code >= 400:
                        err_content = await upstream.aread()
                        yield f"data: {json.dumps({'error': err_content.decode('utf-8', errors='ignore')})}\n\n".encode("utf-8")
                        yield b"data: [DONE]\n\n"
                        return

                    async for chunk in upstream.aiter_bytes():
                        if chunk:
                            yield chunk
            except Exception as e:
                yield f"data: {json.dumps({'error': f'Singularity Gateway Error: {str(e)}'})}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
            finally:
                await client.aclose()

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
            try:
                data = resp.json()
                return JSONResponse(status_code=resp.status_code, content=data)
            except Exception:
                return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))
        except httpx.ConnectError:
            raise HTTPException(
                status_code=502,
                detail=f"Provider {meta['name']} is offline on port {target_port}. Start it in the Singularity Control Center.",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


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

    target_url = f"http://127.0.0.1:{meta['port']}/v1/images/generations"
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


@app.get("/api/limits")
async def api_get_limits():
    return await get_all_limits()


@app.get("/api/models")
async def api_get_models():
    return {"models": get_dynamic_models_catalog()}


@app.get("/api/cookies")
async def api_get_cookies():
    return get_stored_cookies()


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
    res = remove_stacked_cookie(provider_id, identifier=identifier, index=index)
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


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "9000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
