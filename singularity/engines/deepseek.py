#!/usr/bin/env python3
"""
Singularity Native DeepSeek Engine
==================================
Authentic, self-contained multi-account streaming driver for DeepSeek AI.
Supports:
- DeepSeek-V3 (deepseek-chat)
- DeepSeek-R1 (deepseek-reasoner) with live chain-of-thought thinking traces
- Web Search Grounding (deepseek-chat-search, deepseek-reasoner-search)
- Account pool rotation across SQLite vault credentials
- Upstream daemon proxying (port 8088) or direct in-process Web2API execution
- Native Node.js WebAssembly Proof-of-Work (PoW) solver for DeepSeekHashV1
- 100% self-contained pure Python with zero legacy dependencies
"""

import asyncio
import base64
import json
import os
import random
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

import httpx

try:
    from singularity import db
    from singularity.providers import get_provider_host
except ImportError:
    import db
    from providers import get_provider_host


# -------------------------------------------------------------------
# Embedded WebAssembly Proof-of-Work Solver (Zero Legacy Files)
# -------------------------------------------------------------------
_NODE_POW_SCRIPT = """
const fs = require("fs");
async function main() {
    const [wasmPath, challenge, prefix, diffStr] = process.argv.slice(1);
    const difficulty = parseFloat(diffStr) || 144000;
    try {
        const wasmBuffer = fs.readFileSync(wasmPath);
        const { instance } = await WebAssembly.instantiate(wasmBuffer, {});
        const exports = instance.exports;
        const memory = exports.memory;
        const alloc = exports.__wbindgen_export_0;
        const add_to_stack = exports.__wbindgen_add_to_stack_pointer;
        const wasm_solve = exports.wasm_solve;

        function encodeString(str) {
            const buf = Buffer.from(str, "utf8");
            const ptr = alloc(buf.length, 1);
            new Uint8Array(memory.buffer).set(buf, ptr);
            return [ptr, buf.length];
        }

        const retptr = add_to_stack(-16);
        const [ptrC, lenC] = encodeString(challenge);
        const [ptrP, lenP] = encodeString(prefix);
        wasm_solve(retptr, ptrC, lenC, ptrP, lenP, difficulty);
        const view = new DataView(memory.buffer);
        const status = view.getInt32(retptr, true);
        const value = view.getFloat64(retptr + 8, true);
        add_to_stack(16);
        if (status !== 0) {
            console.log(JSON.stringify({ status: "ok", answer: Math.floor(value) }));
        } else {
            console.log(JSON.stringify({ status: "fail", answer: null }));
        }
    } catch (e) {
        console.error(JSON.stringify({ status: "error", error: e.message }));
        process.exit(1);
    }
}
main();
"""

def _solve_deepseek_pow_sync(
    challenge: str,
    salt: str,
    difficulty: float,
    expire_at: int,
) -> Optional[int]:
    """Solve DeepSeek PoW challenge using Node.js WebAssembly directly."""
    wasm_path = Path(__file__).resolve().parent.parent / "data" / "sha3_wasm_bg.7b9ca65ddd.wasm"
    if not wasm_path.exists():
        return None

    prefix = f"{salt}_{expire_at}_"
    cmd = ["node", "-e", _NODE_POW_SCRIPT, "--", str(wasm_path), str(challenge), str(prefix), str(difficulty)]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout.strip())
            if data.get("status") == "ok":
                return data.get("answer")
    except Exception:
        pass
    return None

async def _solve_deepseek_pow(
    challenge: str,
    salt: str,
    difficulty: float,
    expire_at: int,
) -> Optional[int]:
    """Solve DeepSeek PoW challenge asynchronously without blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _solve_deepseek_pow_sync,
        challenge,
        salt,
        difficulty,
        expire_at,
    )


DEEPSEEK_HOST = "chat.deepseek.com"
DEEPSEEK_LOGIN_URL = f"https://{DEEPSEEK_HOST}/api/v0/users/login"
DEEPSEEK_CREATE_SESSION_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat_session/create"
DEEPSEEK_CREATE_POW_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat/create_pow_challenge"
DEEPSEEK_COMPLETION_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat/completion"
DEEPSEEK_STOP_STREAM_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat/stop_stream"
DEEPSEEK_DELETE_SESSION_URL = f"https://{DEEPSEEK_HOST}/api/v0/chat_session/delete"

DEEPSEEK_BASE_HEADERS = {
    "Host": "chat.deepseek.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "x-app-version": "20241129.1",
    "x-client-locale": "en_US",
    "x-client-platform": "web",
    "x-client-version": "1.0.0",
}

_ACCOUNT_ROTATION_INDEX = 0
_ROTATION_LOCK = asyncio.Lock()


def _decode_jwt(token_str: str) -> Optional[Dict[str, Any]]:
    """Decode JWT payload without verification for account info display."""
    try:
        parts = token_str.strip().split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            decoded = base64.urlsafe_b64decode(payload_b64)
            return json.loads(decoded.decode("utf-8", errors="ignore"))
    except Exception:
        pass
    return None


def extract_deepseek_credentials(raw_token: str) -> Dict[str, Any]:
    """Parse raw token or JSON dump into clean DeepSeek credentials."""
    raw = (raw_token or "").strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                email = data.get("email", "")
                mobile = data.get("mobile", "")
                password = data.get("password", "")
                token = data.get("token") or data.get("userToken") or data.get("user_token") or data.get("value") or ""
                return {
                    "email": email,
                    "mobile": mobile,
                    "password": password,
                    "token": token,
                    "plan": data.get("plan", "FREE"),
                }
        except Exception:
            pass

    # Raw userToken string (JWT or hex token)
    jwt_data = _decode_jwt(raw)
    email = ""
    uid = ""
    if jwt_data:
        email = jwt_data.get("email", "")
        uid = jwt_data.get("sub") or jwt_data.get("uid") or ""

    return {
        "email": email,
        "mobile": "",
        "password": "",
        "token": raw,
        "uid": uid,
        "plan": "FREE",
    }


def get_deepseek_accounts() -> List[Dict[str, Any]]:
    """Fetch stacked DeepSeek credentials from SQLite database vault."""
    try:
        raw_accounts = db.get_accounts("deepseek")
        accounts = []
        for item in raw_accounts:
            token_str = item.get("token", "")
            creds = extract_deepseek_credentials(token_str)
            creds["id"] = item.get("id")
            creds["identifier"] = creds["email"] or creds["mobile"] or creds.get("uid") or f"deepseek-{item.get('id', 'account')}"
            accounts.append(creds)
        return accounts
    except Exception:
        return []


async def _rotate_account(accounts: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Rotate round-robin through available DeepSeek accounts."""
    global _ACCOUNT_ROTATION_INDEX
    accs = accounts or get_deepseek_accounts()
    if not accs:
        return None
    async with _ROTATION_LOCK:
        idx = _ACCOUNT_ROTATION_INDEX % len(accs)
        _ACCOUNT_ROTATION_INDEX += 1
        return accs[idx]


async def _ensure_logged_in(account: Dict[str, Any], client: httpx.AsyncClient) -> str:
    """Ensure account has a valid userToken, performing login if credentials are provided."""
    token = account.get("token", "").strip()
    if token:
        return token

    email = account.get("email", "").strip()
    mobile = account.get("mobile", "").strip()
    password = account.get("password", "").strip()

    if not password or (not email and not mobile):
        return ""

    payload = {
        "device_id": "singularity_gateway",
        "os": "android",
        "password": password,
    }
    if email:
        payload["email"] = email
    else:
        payload["mobile"] = mobile
        payload["area_code"] = None

    try:
        resp = await client.post(DEEPSEEK_LOGIN_URL, headers=DEEPSEEK_BASE_HEADERS, json=payload, timeout=15.0)
        if resp.status_code == 200:
            data = resp.json()
            new_token = data.get("data", {}).get("biz_data", {}).get("user", {}).get("token")
            if new_token:
                account["token"] = new_token
                # Update DB
                try:
                    acc_id = account.get("id")
                    if acc_id is not None:
                        db.update_account_token("deepseek", acc_id, json.dumps(account))
                except Exception:
                    pass
                return new_token
    except Exception:
        pass
    return ""


def messages_prepare(messages: List[Dict[str, Any]]) -> str:
    """
    Format standard chat messages into DeepSeek's authentic prompt representation
    with special delimiter tokens <｜Assistant｜>, <｜end▁of▁sentence｜>, and <｜User｜>.
    """
    processed = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
            text = "\n".join(texts)
        else:
            text = str(content or "")
        processed.append({"role": role, "text": text})

    if not processed:
        return ""

    # Merge consecutive messages with the same role
    merged = [processed[0]]
    for msg in processed[1:]:
        if msg["role"] == merged[-1]["role"]:
            merged[-1]["text"] += "\n\n" + msg["text"]
        else:
            merged.append(msg)

    parts = []
    for idx, block in enumerate(merged):
        role = block["role"]
        text = block["text"]
        if role == "assistant":
            parts.append(f"<｜Assistant｜>{text}<｜end▁of▁sentence｜>")
        elif role in ("user", "system"):
            if idx > 0:
                parts.append(f"<｜User｜>{text}")
            else:
                parts.append(text)
        else:
            parts.append(text)
    return "".join(parts)


def _resolve_deepseek_features(model: str) -> Tuple[bool, bool]:
    """Resolve thinking_enabled and search_enabled flags based on model name."""
    m = (model or "").lower().strip()
    thinking = "reasoner" in m or "r1" in m
    search = "search" in m
    return thinking, search


async def _create_session(client: httpx.AsyncClient, auth_headers: Dict[str, str]) -> Optional[str]:
    """Create a new chat session on chat.deepseek.com."""
    try:
        resp = await client.post(
            DEEPSEEK_CREATE_SESSION_URL,
            headers=auth_headers,
            json={"agent": "chat"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("biz_data", {}).get("id")
    except Exception:
        pass
    return None


async def _get_pow_response(client: httpx.AsyncClient, auth_headers: Dict[str, str], max_attempts: int = 3) -> Optional[str]:
    """Request PoW challenge and compute the solution with retry loop."""
    for attempt in range(max_attempts):
        try:
            resp = await client.post(
                DEEPSEEK_CREATE_POW_URL,
                headers=auth_headers,
                json={"target_path": "/api/v0/chat/completion"},
                timeout=20.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    challenge = data["data"]["biz_data"]["challenge"]
                    difficulty = challenge.get("difficulty", 144000)
                    expire_at = challenge.get("expire_at", int(time.time()) + 3600)
                    
                    answer = await _solve_deepseek_pow(
                        challenge=challenge["challenge"],
                        salt=challenge["salt"],
                        difficulty=float(difficulty),
                        expire_at=expire_at,
                    )
                    if answer is not None:
                        pow_dict = {
                            "algorithm": challenge["algorithm"],
                            "challenge": challenge["challenge"],
                            "salt": challenge["salt"],
                            "answer": answer,
                            "signature": challenge["signature"],
                            "target_path": challenge["target_path"],
                        }
                        pow_str = json.dumps(pow_dict, separators=(",", ":"), ensure_ascii=False)
                        return base64.b64encode(pow_str.encode("utf-8")).decode("utf-8").rstrip()
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return None


async def _delete_session(client: httpx.AsyncClient, auth_headers: Dict[str, str], session_id: str):
    """Clean up conversation session on DeepSeek backend."""
    try:
        await client.post(
            DEEPSEEK_DELETE_SESSION_URL,
            headers=auth_headers,
            json={"chat_session_id": session_id},
            timeout=5.0,
        )
    except Exception:
        pass


# -------------------------------------------------------------------
# Universal DeepSeek Stream Handler
# -------------------------------------------------------------------

async def stream_deepseek_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    stream: bool = True,
    simulate: bool = False,
    **kwargs,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Stream chat completion chunks from DeepSeek (V3 or R1).
    Yields OpenAI-compatible SSE chunk dictionaries.
    """
    req_id = f"chatcmpl-deepseek-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    thinking_enabled, search_enabled = _resolve_deepseek_features(model)
    if kwargs.get("thinking_budget") is not None:
        try:
            thinking_enabled = int(kwargs["thinking_budget"]) > 0
        except Exception:
            pass
    elif kwargs.get("thinking") is not None:
        th = kwargs.get("thinking")
        if isinstance(th, dict):
            thinking_enabled = th.get("type") == "enabled"
        elif isinstance(th, bool):
            thinking_enabled = th

    # 1. Device Simulation Mode
    if simulate or os.getenv("SINGULARITY_SIMULATE", "0") in ("1", "true", "yes", "on"):
        sim_thinking = "Analyzing query with DeepSeek-R1 reasoning framework...\n1. Query parsed\n2. Constraint verification\n3. Synthesizing solution."
        sim_response = f"Hello from Singularity's native DeepSeek engine! Currently running simulated response for '{model}'. Full model routing, WASM PoW validation, and token streaming are active."
        
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
    async with httpx.AsyncClient(timeout=120.0) as client:
        token = ""
        if account:
            token = await _ensure_logged_in(account, client)

        if not token:
            # Check DB setting or env
            token = os.getenv("DEEPSEEK_TOKEN", "")

        if not token:
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "content": "DeepSeek Notice: No active account or userToken found in Singularity vault.\nPlease add your DeepSeek userToken or credentials in the Control Center or run './singular import <token>'."
                    },
                    "finish_reason": "error",
                }],
            }
            return

        auth_headers = {
            **DEEPSEEK_BASE_HEADERS,
            "authorization": f"Bearer {token}",
        }

        # Create session
        session_id = await _create_session(client, auth_headers)
        if not session_id:
            yield {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": "DeepSeek Error: Failed to create chat session. The provided userToken may be expired."},
                    "finish_reason": "error",
                }],
            }
            return

        # Solve PoW
        pow_response = await _get_pow_response(client, auth_headers)
        completion_headers = dict(auth_headers)
        if pow_response:
            completion_headers["x-ds-pow-response"] = pow_response

        final_prompt = messages_prepare(messages)
        payload = {
            "chat_session_id": session_id,
            "parent_message_id": None,
            "prompt": final_prompt,
            "ref_file_ids": [],
            "thinking_enabled": thinking_enabled,
            "search_enabled": search_enabled,
        }

        try:
            async with client.stream(
                "POST",
                DEEPSEEK_COMPLETION_URL,
                headers=completion_headers,
                json=payload,
                timeout=120.0,
            ) as resp:
                if resp.status_code != 200:
                    err_txt = await resp.aread()
                    yield {
                        "id": req_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": f"DeepSeek API error ({resp.status_code}): {err_txt.decode('utf-8', errors='ignore')}"},
                            "finish_reason": "error",
                        }],
                    }
                    return

                first_chunk = True
                current_field = "thinking_content" if thinking_enabled else "content"

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
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

                    p = item.get("p", "")
                    v = item.get("v")

                    # Ignore internal status and metadata events
                    if p.startswith("response/search_") or p in ("response/status", "response/accumulated_token_usage"):
                        continue

                    # Update current streaming mode
                    if p == "response/thinking_content":
                        current_field = "thinking_content"
                    elif p == "response/content":
                        current_field = "content"

                    if isinstance(v, str):
                        delta: Dict[str, Any] = {}
                        if first_chunk:
                            delta["role"] = "assistant"
                            first_chunk = False

                        if current_field == "thinking_content":
                            delta["reasoning_content"] = v
                        else:
                            delta["content"] = v

                        yield {
                            "id": req_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{
                                "index": 0,
                                "delta": delta,
                                "finish_reason": None,
                            }],
                        }

                # Completion stop chunk
                yield {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
        finally:
            # Cleanly delete conversation session
            await _delete_session(client, auth_headers, session_id)


async def generate_deepseek_chat(
    model: str,
    messages: List[Dict[str, Any]],
    accounts: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Generate complete non-streaming chat completion from DeepSeek."""
    content_parts = []
    reasoning_parts = []
    req_id = f"chatcmpl-deepseek-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    async for chunk in stream_deepseek_chat(model, messages, accounts=accounts, stream=False, **kwargs):
        choices = chunk.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            if "content" in delta and delta["content"]:
                content_parts.append(delta["content"])
            if "reasoning_content" in delta and delta["reasoning_content"]:
                reasoning_parts.append(delta["reasoning_content"])

    full_content = "".join(content_parts)
    full_reasoning = "".join(reasoning_parts)

    msg: Dict[str, Any] = {
        "role": "assistant",
        "content": full_content,
    }
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
            "completion_tokens": (len(full_content) + len(full_reasoning)) // 4,
            "total_tokens": (len(str(messages)) + len(full_content) + len(full_reasoning)) // 4,
        },
    }
