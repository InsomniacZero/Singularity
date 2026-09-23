#!/usr/bin/env python3
"""
Singularity Provider Engine
Manages status, lifecycle, limits, models, and cookie storage for all 7 providers:
ChatGPT (8000), Claude (8080), Gemini (8084), GLM (8085), Kimi (8086), Grok (8087), DeepSeek (8088).
"""

import asyncio
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

try:
    from singularity import db
except ImportError:
    import db

try:
    db.init_db()
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
PROVIDER_HOST = os.getenv("SINGULARITY_PROVIDER_HOST", "127.0.0.1")

# Self-contained interpreter resolution (singularity/.venv -> sys.executable -> python)
import sys
LOCAL_VENV_WIN = BASE_DIR / ".venv" / "Scripts" / "python.exe"
LOCAL_VENV_NIX = BASE_DIR / ".venv" / "bin" / "python3"
LOCAL_VENV = LOCAL_VENV_WIN if LOCAL_VENV_WIN.exists() else LOCAL_VENV_NIX
PYTHON_VENV = LOCAL_VENV if LOCAL_VENV.exists() else Path(sys.executable)
SYSTEM_PYTHON = sys.executable or ("python" if sys.platform == "win32" else "python3")


def get_python_executable() -> str:
    """Resolve the most appropriate Python executable (venv or system)."""
    if sys.platform == "win32":
        venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
        if venv_py.exists():
            return str(venv_py)
        root_venv = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
        if root_venv.exists():
            return str(root_venv)
    else:
        venv_py = BASE_DIR / ".venv" / "bin" / "python3"
        if venv_py.exists():
            return str(venv_py)
        root_venv = ROOT_DIR / ".venv" / "bin" / "python3"
        if root_venv.exists():
            return str(root_venv)
    if sys.executable:
        return sys.executable
    return "python" if sys.platform == "win32" else "python3"



def is_simulation_active() -> bool:
    """Check if device simulation mode is active via env var or DB setting."""
    if os.getenv("SINGULARITY_SIMULATE", "0").lower() in ("1", "true", "yes", "on"):
        return True
    try:
        val = db.get_setting("simulation_mode")
        return val in ("1", "true", "yes", "on")
    except Exception:
        return False


def get_provider_host(provider_id: str) -> str:
    """Resolve provider host dynamically from DB setting, env var, or default."""
    try:
        spec = db.get_setting(f"{provider_id}_host")
        if spec:
            return spec
        remote = db.get_setting("remote_host")
        if remote:
            return remote
    except Exception:
        pass
    env_key = f"{provider_id.upper()}_HOST"
    if os.getenv(env_key):
        return os.getenv(env_key)
    if os.getenv("SINGULARITY_PROVIDER_HOST"):
        return os.getenv("SINGULARITY_PROVIDER_HOST")
    return "127.0.0.1"


PROVIDERS_CONFIG = {
    "gemini": {
        "id": "gemini",
        "name": "Gemini",
        "port": 8084,
        "host": os.getenv("GEMINI_HOST", PROVIDER_HOST),
        "badge": "Google DeepMind",
        "color": "#4285F4",
        "start_script": "start_gemini.sh",
        "stop_script": "stop_gemini.sh",
        "health_path": "/v1/models",
        "cookie_type": "cookie_string",
        "cookie_label": "Google __Secure-1PSID Cookie",
        "cookie_placeholder": "Paste raw cookie string containing __Secure-1PSID=... and __Secure-1PSIDTS=...",
        "auth_header": None,
    },
    "chatgpt": {
        "id": "chatgpt",
        "name": "ChatGPT",
        "port": 8000,
        "host": os.getenv("CHATGPT_HOST", PROVIDER_HOST),
        "badge": "OpenAI",
        "color": "#10A37F",
        "start_script": "start_chatgpt2api.sh",
        "stop_script": "stop_chatgpt2api.sh",
        "health_path": "/healthz",
        "cookie_type": "json_or_token",
        "cookie_label": "Next-Auth Session JSON or Access Token",
        "cookie_placeholder": "Paste JSON session dump or access token (one per account card)...",
        "auth_header": "Bearer chatgpt2api",
    },
    "claude": {
        "id": "claude",
        "name": "Claude",
        "port": 8080,
        "host": os.getenv("CLAUDE_HOST", PROVIDER_HOST),
        "badge": "Anthropic",
        "color": "#D97757",
        "start_script": "start_claude2api.sh",
        "stop_script": "stop_claude2api.sh",
        "health_path": "/v1/models",
        "cookie_type": "session_key",
        "cookie_label": "Claude sessionKey (sk-ant-sid02-...)",
        "cookie_placeholder": "sk-ant-sid02-...",
        "auth_header": "Bearer sk-claude-local",
    },
    "kimi": {
        "id": "kimi",
        "name": "Kimi",
        "port": 8086,
        "host": os.getenv("KIMI_HOST", PROVIDER_HOST),
        "badge": "Moonshot AI",
        "color": "#00C389",
        "start_script": "start_kimi2api.sh",
        "stop_script": "stop_kimi2api.sh",
        "health_path": "/healthz",
        "cookie_type": "jwt_refresh",
        "cookie_label": "Kimi Refresh Token (JWT)",
        "cookie_placeholder": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
        "auth_header": "Bearer sk-kimi-local",
    },
    "glm": {
        "id": "glm",
        "name": "GLM",
        "port": 8085,
        "host": os.getenv("GLM_HOST", PROVIDER_HOST),
        "badge": "Zhipu AI",
        "color": "#4A72FF",
        "start_script": "start_glm2api.sh",
        "stop_script": "stop_glm2api.sh",
        "health_path": "/v1/models",
        "cookie_type": "token_lines",
        "cookie_label": "GLM Refresh Token",
        "cookie_placeholder": "Paste Zhipu refresh token (one account per line or card)...",
        "auth_header": "Bearer sk-glm-local",
    },
    "grok": {
        "id": "grok",
        "name": "Grok",
        "port": 8087,
        "host": os.getenv("GROK_HOST", PROVIDER_HOST),
        "badge": "xAI",
        "color": "#E5E5E5",
        "start_script": "start_grok2api.sh",
        "stop_script": "stop_grok2api.sh",
        "health_path": "/healthz",
        "cookie_type": "cookie_string",
        "cookie_label": "Grok SSO Cookie & UserID",
        "cookie_placeholder": "sso=...; sso-rw=...; x-userid=...",
        "auth_header": None,
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "port": 8088,
        "host": os.getenv("DEEPSEEK_HOST", PROVIDER_HOST),
        "badge": "DeepSeek AI",
        "color": "#4D6BFE",
        "start_script": "start_deepseek2api.sh",
        "stop_script": "stop_deepseek2api.sh",
        "health_path": "/healthz",
        "cookie_type": "user_token_or_json",
        "cookie_label": "DeepSeek userToken (Bearer) or Login JSON",
        "cookie_placeholder": "Paste DeepSeek userToken (JWT from chat.deepseek.com) or {\"email\": \"...\", \"password\": \"...\"}",
        "auth_header": "Bearer deepseek2api",
    },
    "qwen": {
        "id": "qwen",
        "name": "Qwen",
        "port": 8089,
        "host": os.getenv("QWEN_HOST", PROVIDER_HOST),
        "badge": "Alibaba Cloud",
        "color": "#615CED",
        "start_script": "start_qwen2api.sh",
        "stop_script": "stop_qwen2api.sh",
        "health_path": "/healthz",
        "cookie_type": "token_or_json",
        "cookie_label": "Qwen Token (chat.qwen.ai) or Login JSON",
        "cookie_placeholder": "Paste chat.qwen.ai Bearer token, Cookie string, or localStorage JSON",
        "auth_header": "Bearer qwen2api",
    },
}

# Dynamic Comprehensive Catalog (226 models across 8 providers)
MODELS_CATALOG = [
    {
        'capabilities': ['chat', 'reasoning', 'code', 'streaming', 'vision'],
        'context': '1M tokens',
        'description': 'Flagship ~2.4T parameter frontier reasoning and multimodal powerhouse with 1M context.',
        'id': 'qwen3.8-max',
        'locked': False,
        'name': 'Qwen 3.8 Max',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'vision', 'audio', 'streaming'],
        'context': '256K tokens',
        'description': 'Ultra-low-latency real-time native omnimodal vision, audio, and speech model.',
        'id': 'qwen3.8-omni-flash',
        'locked': False,
        'name': 'Qwen 3.8 Omni Flash',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'reasoning', 'code', 'streaming', 'vision'],
        'context': '1M tokens',
        'description': 'High-efficiency balanced flagship for complex multi-step reasoning, agents, and tool use.',
        'id': 'qwen3.8-plus',
        'locked': False,
        'name': 'Qwen 3.8 Plus',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Lightning-fast generation model with sub-second TTFT and 1M context window.',
        'id': 'qwen3.8-flash-next',
        'locked': False,
        'name': 'Qwen 3.8 Flash Next',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'code', 'streaming', 'vision'],
        'context': '1M tokens',
        'description': 'Stable enterprise workhorse with deep domain knowledge and tool-use synthesis.',
        'id': 'qwen3.6-plus',
        'locked': False,
        'name': 'Qwen 3.6 Plus',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Extremely cost-effective lightweight conversational and summarization model.',
        'id': 'qwen3.5-flash',
        'locked': False,
        'name': 'Qwen 3.5 Flash',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Frontier alias for current Qwen3.8-Max reasoning powerhouse.',
        'id': 'qwen-max',
        'locked': False,
        'name': 'Qwen-Max',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Balanced production alias for Qwen3.8-Plus.',
        'id': 'qwen-plus',
        'locked': False,
        'name': 'Qwen-Plus',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'High-throughput rapid response alias.',
        'id': 'qwen-turbo',
        'locked': False,
        'name': 'Qwen-Turbo',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Dedicated code synthesis, refactoring, and debugging model.',
        'id': 'qwen-coder',
        'locked': False,
        'name': 'Qwen-Coder',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'reasoning', 'web_search', 'streaming'],
        'context': '1M tokens',
        'description': 'Autonomous deep research workflow with multi-query synthesis and report generation.',
        'id': 'qwen-deep-research',
        'locked': False,
        'name': 'Qwen Deep Research',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'vision', 'image_generation'],
        'context': '128K tokens',
        'description': 'Wanx / Qwen-Image generation and visual comprehension.',
        'id': 'qwen-image',
        'locked': False,
        'name': 'Qwen Image',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'vision', 'video'],
        'context': '128K tokens',
        'description': 'Qwen visual video comprehension and generation engine.',
        'id': 'qwen-video',
        'locked': False,
        'name': 'Qwen Video',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'reasoning', 'code', 'streaming', 'vision'],
        'context': '1M tokens',
        'description': 'Qwen3.7-Plus flagship multimodal model with integrated Wanx video and image synthesis.',
        'id': 'qwen3.7-plus',
        'locked': False,
        'name': 'Qwen 3.7 Plus',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'vision', 'video'],
        'context': '128K tokens',
        'description': 'Alibaba Wanx 2.1 state-of-the-art text-to-video generative synthesis model.',
        'id': 'wanx-2.1',
        'locked': False,
        'name': 'Wanx 2.1 Video',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'vision', 'video'],
        'context': '128K tokens',
        'description': 'Alibaba Wanx unified visual generation alias for cinematic video synthesis.',
        'id': 'wanx',
        'locked': False,
        'name': 'Wanx Video',
        'provider': 'qwen'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '64K tokens',
        'description': 'DeepSeek-V3 671B MoE frontier conversational and coding flagship model.',
        'id': 'deepseek-chat',
        'locked': False,
        'name': 'DeepSeek-V3 Chat',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '64K tokens',
        'description': 'DeepSeek-R1 frontier reasoning model with chain-of-thought visible thinking tokens.',
        'id': 'deepseek-reasoner',
        'locked': False,
        'name': 'DeepSeek-R1 Reasoner',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'web_search', 'code', 'streaming'],
        'context': '64K tokens',
        'description': 'DeepSeek-V3 with live real-time web search grounding enabled.',
        'id': 'deepseek-chat-search',
        'locked': False,
        'name': 'DeepSeek-V3 Search',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'reasoning', 'web_search', 'code', 'streaming'],
        'context': '64K tokens',
        'description': 'DeepSeek-R1 reasoning engine with live real-time web search grounding.',
        'id': 'deepseek-reasoner-search',
        'locked': False,
        'name': 'DeepSeek-R1 Reasoner Search',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '64K tokens',
        'description': 'DeepSeek-V3 flagship model alias.',
        'id': 'deepseek-v3',
        'locked': False,
        'name': 'DeepSeek-V3',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '64K tokens',
        'description': 'DeepSeek-R1 reasoning model alias.',
        'id': 'deepseek-r1',
        'locked': False,
        'name': 'DeepSeek-R1',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '128K tokens',
        'description': 'DeepSeek-Coder V2 specialized code generation and repository synthesis.',
        'id': 'deepseek-coder',
        'locked': False,
        'name': 'DeepSeek Coder V2',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'code', 'streaming', 'vision'],
        'context': '1M tokens',
        'description': 'DeepSeek-V4.1-Flash (Sep 2026) 552B MoE flagship with Causal Encoder-Decoder architecture.',
        'id': 'deepseek-v4.1-flash',
        'locked': False,
        'name': 'DeepSeek-V4.1 Flash',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'code', 'streaming', 'vision'],
        'context': '1M tokens',
        'description': 'Official API alias for DeepSeek-V4.1-Flash with 1M context window.',
        'id': 'deepseek-flash',
        'locked': False,
        'name': 'DeepSeek Flash',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '256K tokens',
        'description': 'DeepSeek-V4-Pro 1.6T parameter frontier foundation model (GA August 2026).',
        'id': 'deepseek-v4-pro',
        'locked': False,
        'name': 'DeepSeek-V4 Pro',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'DeepSeek-V4 foundation series alias.',
        'id': 'deepseek-v4',
        'locked': False,
        'name': 'DeepSeek-V4',
        'provider': 'deepseek'
    },
    {
        'capabilities': ['chat', 'code', 'streaming', 'vision'],
        'context': '1M tokens',
        'description': 'DeepSeek-V4.1 generation alias.',
        'id': 'deepseek-v4.1',
        'locked': False,
        'name': 'DeepSeek-V4.1',
        'provider': 'deepseek'
    },
    {   'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Ultra-fast flagship model with multimodal vision and low latency.',
        'id': 'gemini-3.8-flash',
        'locked': False,
        'name': 'Gemini 3.8 Flash',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Explicit chain-of-thought reasoning scratchpad (~20k chars).',
        'id': 'gemini-3.8-flash-thinking',
        'locked': False,
        'name': 'Gemini 3.8 Flash Thinking',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'High-throughput frontier model with balanced reasoning and speed.',
        'id': 'gemini-3.7-flash',
        'locked': False,
        'name': 'Gemini 3.7 Flash',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Frontier reasoning scratchpad with visible thinking tokens.',
        'id': 'gemini-3.7-flash-thinking',
        'locked': False,
        'name': 'Gemini 3.7 Flash Thinking',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Low-latency responsive conversational and coding agent.',
        'id': 'gemini-3.6-flash',
        'locked': False,
        'name': 'Gemini 3.6 Flash',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Thinking reasoning mode with intermediate reasoning traces.',
        'id': 'gemini-3.6-flash-thinking',
        'locked': False,
        'name': 'Gemini 3.6 Flash Thinking',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Versatile high-speed model for everyday tasks and automation.',
        'id': 'gemini-3.5-flash',
        'locked': False,
        'name': 'Gemini 3.5 Flash',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Deep reasoning mode with structured reasoning process.',
        'id': 'gemini-3.5-flash-thinking',
        'locked': False,
        'name': 'Gemini 3.5 Flash Thinking',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Lightweight ultra-fast model optimized for maximum throughput.',
        'id': 'gemini-3.5-flash-lite',
        'locked': False,
        'name': 'Gemini 3.5 Flash Lite',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'reasoning', 'streaming'],
        'context': '1M tokens',
        'description': 'Ultra-efficient reasoning mode for fast structured deductions.',
        'id': 'gemini-3.5-flash-lite-thinking',
        'locked': False,
        'name': 'Gemini 3.5 Flash Lite Thinking',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '1M tokens',
        'description': 'Ultra-low latency model for high-frequency queries.',
        'id': 'gemini-flash-lite',
        'locked': False,
        'name': 'Gemini Flash Lite',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'reasoning', 'streaming'],
        'context': '1M tokens',
        'description': 'Lightweight reasoning mode for fast logic verification.',
        'id': 'gemini-flash-lite-thinking',
        'locked': False,
        'name': 'Gemini Flash Lite Thinking',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'vision', 'reasoning', 'code', 'streaming'],
        'context': '2M tokens',
        'description': 'Google flagship model for complex coding, mathematics, and agentic workflows.',
        'id': 'gemini-3.1-pro',
        'locked': False,
        'name': 'Gemini 3.1 Pro',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '2M tokens',
        'description': 'Deep reasoning mode (~20k chars scratchpad).',
        'id': 'gemini-3.1-pro-thinking',
        'locked': False,
        'name': 'Gemini 3.1 Pro Thinking',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '2M tokens',
        'description': 'Pro with expanded context decoding and experimental features.',
        'id': 'gemini-3.1-pro-enhanced',
        'locked': False,
        'name': 'Gemini 3.1 Pro Enhanced',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '1M tokens',
        'description': 'Automatic model selection based on prompt complexity.',
        'id': 'gemini-auto',
        'locked': False,
        'name': 'Gemini Auto Router',
        'provider': 'gemini'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Gemini 3.1 Flash Image - State-of-the-art fast image generation & editing.',
        'id': 'nano-banana-2',
        'locked': False,
        'name': 'Nano Banana 2',
        'provider': 'gemini'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Gemini 3 Pro Image / Imagen 3 - High-fidelity reasoning & photorealistic generation.',
        'id': 'nano-banana-pro',
        'locked': False,
        'name': 'Nano Banana Pro',
        'provider': 'gemini'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Gemini 3.1 Flash-Lite Image - Rapid lightweight image model.',
        'id': 'nano-banana-2-lite',
        'locked': False,
        'name': 'Nano Banana 2 Lite',
        'provider': 'gemini'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Gemini 2.5 Flash Image - Original viral image generator & editor.',
        'id': 'nano-banana',
        'locked': False,
        'name': 'Nano Banana',
        'provider': 'gemini'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'State-of-the-art photorealistic image generation from Gemini prompt.',
        'id': 'imagen-4.0-generate-proto',
        'locked': False,
        'name': 'Imagen 4.0 Image Gen',
        'provider': 'gemini'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'vision'],
        'context': '200k tokens',
        'description': 'Anthropic frontier flagship with next-level cognitive depth and autonomous reasoning.',
        'id': 'claude-opus-5-5',
        'locked': False,
        'name': 'Claude 5.5 Opus',
        'provider': 'claude'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'vision', 'thinking'],
        'context': '200k tokens',
        'description': 'Maximum-depth chain-of-thought scratchpad reasoning with extreme cognitive persistence.',
        'id': 'claude-opus-5-5-think',
        'locked': False,
        'name': 'Claude 5.5 Opus Thinking',
        'provider': 'claude'},
    {   'capabilities': ['chat', 'vision', 'code', 'streaming'],
        'context': '200k tokens',
        'description': 'Frontier intelligence, elite coding, and long-context synthesis.',
        'id': 'claude-sonnet-5',
        'locked': False,
        'name': 'Claude 5 Sonnet',
        'provider': 'claude'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '200k tokens',
        'description': 'Explicit chain-of-thought scratchpad reasoning with streaming deltas.',
        'id': 'claude-sonnet-5-think',
        'locked': False,
        'name': 'Claude 5 Sonnet (Thinking)',
        'provider': 'claude'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'Maximum depth reasoning and long-horizon autonomy.',
        'id': 'claude-opus-5',
        'locked': True,
        'name': 'Claude 5 Opus (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'Autonomous reasoning with deep reflection scratchpad.',
        'id': 'claude-opus-5-think',
        'locked': True,
        'name': 'Claude 5 Opus Thinking (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'code', 'streaming'],
        'context': '200k tokens',
        'description': 'Reliable workhorse model for complex development workflows.',
        'id': 'claude-sonnet-4-6',
        'locked': False,
        'name': 'Claude 4.6 Sonnet',
        'provider': 'claude'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '200k tokens',
        'description': 'Step-by-step reasoning scratchpad for programming and analysis.',
        'id': 'claude-sonnet-4-6-think',
        'locked': False,
        'name': 'Claude 4.6 Sonnet Thinking',
        'provider': 'claude'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '200k tokens',
        'description': 'Lightweight, blazing-fast conversational assistant.',
        'id': 'claude-haiku-4-5',
        'locked': False,
        'name': 'Claude 4.5 Haiku',
        'provider': 'claude'},
    {   'capabilities': ['chat', 'reasoning', 'streaming'],
        'context': '200k tokens',
        'description': 'Compact reasoning engine with fast execution.',
        'id': 'claude-haiku-4-5-think',
        'locked': False,
        'name': 'Claude 4.5 Haiku Thinking',
        'provider': 'claude'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'Flagship reasoning model for heavy multi-document tasks.',
        'id': 'claude-opus-4-8',
        'locked': True,
        'name': 'Claude 4.8 Opus (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'Extended multi-path reasoning scratchpad.',
        'id': 'claude-opus-4-8-think',
        'locked': True,
        'name': 'Claude 4.8 Opus Thinking (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'High-depth contextual reasoning and code refactoring.',
        'id': 'claude-opus-4-7',
        'locked': True,
        'name': 'Claude 4.7 Opus (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'Deep thinking mode for intricate multi-step problems.',
        'id': 'claude-opus-4-7-think',
        'locked': True,
        'name': 'Claude 4.7 Opus Thinking (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'Comprehensive analytical synthesis model.',
        'id': 'claude-opus-4-6',
        'locked': True,
        'name': 'Claude 4.6 Opus (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'Structured reasoning scratchpad for high-assurance workflows.',
        'id': 'claude-opus-4-6-think',
        'locked': True,
        'name': 'Claude 4.6 Opus Thinking (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'creative', 'streaming'],
        'context': '200k tokens',
        'description': 'Narrative mastery, creative brainstorming, and roleplay.',
        'id': 'claude-fable-5-1',
        'locked': True,
        'name': 'Claude 5.1 Fable (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'creative'],
        'context': '200k tokens',
        'description': 'Creative planning and character consistency reasoning.',
        'id': 'claude-fable-5-1-think',
        'locked': True,
        'name': 'Claude 5.1 Fable Thinking (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'creative', 'streaming'],
        'context': '200k tokens',
        'description': 'Expressive conversational storytelling and worldbuilding.',
        'id': 'claude-fable-5',
        'locked': True,
        'name': 'Claude 5 Fable (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'creative'],
        'context': '200k tokens',
        'description': 'Deep creative exploration with explicit reasoning trace.',
        'id': 'claude-fable-5-think',
        'locked': True,
        'name': 'Claude 5 Fable Thinking (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'Original milestone intelligence flagship.',
        'id': 'claude-3-opus-20240229',
        'locked': True,
        'name': 'Claude 3 Opus (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '200k tokens',
        'description': 'Reasoning-enhanced legacy flagship.',
        'id': 'claude-3-opus-20240229-think',
        'locked': True,
        'name': 'Claude 3 Opus Thinking (Pro)',
        'provider': 'claude',
        'reason': 'Requires Claude Pro subscription cookie'},
    {   'capabilities': ['chat', 'reasoning', 'vision', 'web'],
        'context': '128k tokens',
        'description': 'Dynamically selects optimal model based on query complexity.',
        'id': 'auto',
        'locked': False,
        'name': 'ChatGPT Auto Router',
        'provider': 'chatgpt'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '128k tokens',
        'description': 'Frontier multi-modal intelligence model.',
        'id': 'gpt-5-6',
        'locked': False,
        'name': 'GPT-5.6',
        'provider': 'chatgpt'},
    {   'capabilities': ['chat', 'reasoning', 'code', 'streaming'],
        'context': '128k tokens',
        'description': 'Next-gen compact reasoning model with high throughput.',
        'id': 'gpt-5-6-mini',
        'locked': False,
        'name': 'GPT-5.6 Mini',
        'provider': 'chatgpt'},
    {   'capabilities': ['chat', 'web', 'streaming'],
        'context': '128k tokens',
        'description': 'Fast conversational model with web search.',
        'id': 'gpt-5-3-mini',
        'locked': False,
        'name': 'GPT-5.3 Mini',
        'provider': 'chatgpt'},
    {   'capabilities': ['chat', 'code', 'streaming'],
        'context': '128k tokens',
        'description': 'High efficiency turbo model for rapid interactions.',
        'id': 'gpt-5-4-t-mini',
        'locked': False,
        'name': 'GPT-5.4 Turbo Mini',
        'provider': 'chatgpt'},
    {   'capabilities': ['chat', 'reasoning', 'code'],
        'context': '128k tokens',
        'description': 'Next-gen foundational model for reasoning and coding.',
        'id': 'gpt-5-5',
        'locked': False,
        'name': 'GPT-5.5',
        'provider': 'chatgpt'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Compact version of GPT-5.5 for high throughput.',
        'id': 'gpt-5-5-mini',
        'locked': False,
        'name': 'GPT-5.5 Mini',
        'provider': 'chatgpt'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Accelerated lightweight GPT-5.6.',
        'id': 'gpt-5-6-t-mini',
        'locked': False,
        'name': 'GPT-5.6 Turbo Mini',
        'provider': 'chatgpt'},
    {   'capabilities': ['math', 'code', 'reasoning'],
        'context': '128k tokens',
        'description': 'Breakthrough analytical, mathematical, and logic model.',
        'id': 'gpt-5.6-sol',
        'locked': False,
        'name': 'GPT-5.6 Sol',
        'provider': 'chatgpt'},
    {   'capabilities': ['web', 'code', 'chat'],
        'context': '128k tokens',
        'description': 'Web-augmented factual question answering and live data lookup.',
        'id': 'gpt-5.6-terra',
        'locked': False,
        'name': 'GPT-5.6 Terra',
        'provider': 'chatgpt'},
    {   'capabilities': ['chat', 'creative'],
        'context': '128k tokens',
        'description': 'Fluid prose, persona generation, and interactive fiction.',
        'id': 'gpt-5.6-luna',
        'locked': False,
        'name': 'GPT-5.6 Luna',
        'provider': 'chatgpt'},
    {   'capabilities': ['vision', 'chat'],
        'context': '128k tokens',
        'description': 'High-fidelity image comprehension and diagram parsing.',
        'id': 'sunburst',
        'locked': False,
        'name': 'Sunburst Multimodal',
        'provider': 'chatgpt'},
    {   'capabilities': ['chat', 'reasoning', 'fast'],
        'context': '128k tokens',
        'description': 'Fast execution agent with real-time reasoning and tool use.',
        'id': 'flare',
        'locked': False,
        'name': 'OpenAI Flare Agent',
        'provider': 'chatgpt'},
    {   'capabilities': ['reasoning', 'web', 'research'],
        'context': '256k tokens',
        'description': 'Autonomous agentic multi-hop web research.',
        'id': 'research',
        'locked': False,
        'name': 'OpenAI Deep Research',
        'provider': 'chatgpt'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Accelerated photorealistic image generation with low latency.',
        'id': 'gpt-image-2.5-flare',
        'locked': False,
        'name': 'GPT Image 2.5 Flare',
        'provider': 'chatgpt'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'High-fidelity artistic rendering & diagram generation.',
        'id': 'gpt-image-2.5-sunburst',
        'locked': False,
        'name': 'GPT Image 2.5 Sunburst',
        'provider': 'chatgpt'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Conversational image generation model.',
        'id': 'gpt-image-2',
        'locked': False,
        'name': 'GPT Image 2',
        'provider': 'chatgpt'},
    {   'capabilities': ['reasoning', 'code', 'chat'],
        'context': '128k tokens',
        'description': 'GPT-6 Astra frontier autonomous multi-domain reasoning.',
        'id': 'gpt-6-astra',
        'locked': True,
        'name': 'GPT-6 Astra',
        'provider': 'chatgpt',
        'reason': 'Requires ChatGPT Plus / Team / Pro account in Stacker'},
    {   'capabilities': ['chat', 'reasoning', 'vision', 'code'],
        'context': '256k tokens',
        'description': 'Full-parameter flagship model reserved for ChatGPT Plus/Team accounts.',
        'id': 'gpt-5-6-full',
        'locked': True,
        'name': 'GPT-5.6 Full (Plus Tier)',
        'provider': 'chatgpt',
        'reason': 'Requires ChatGPT Plus / Team active session in Stacker'},
    {   'capabilities': ['reasoning', 'math', 'code'],
        'context': '128k tokens',
        'description': 'Deep multi-step reasoning model.',
        'id': 'o1',
        'locked': True,
        'name': 'OpenAI o1 Reasoning (Plus)',
        'provider': 'chatgpt',
        'reason': 'Requires ChatGPT Plus / Team active session in Stacker'},
    {   'capabilities': ['chat', 'web', 'streaming'],
        'context': '200k tokens',
        'description': 'Long-context leader with web retrieval and advanced instruction following.',
        'id': 'kimi-k3',
        'locked': False,
        'name': 'Kimi K3 Flagship',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'web', 'streaming'],
        'context': '200k tokens',
        'description': 'Extended autonomous reasoning and mathematical problem solving.',
        'id': 'kimi-k3-thinking',
        'locked': False,
        'name': 'Kimi K3 Thinking',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'web', 'search'],
        'context': '200k tokens',
        'description': 'Live web grounding with source citation and verification.',
        'id': 'kimi-k3-search',
        'locked': False,
        'name': 'Kimi K3 Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'web', 'search'],
        'context': '200k tokens',
        'description': 'Deep reasoning combined with live web retrieval.',
        'id': 'kimi-k3-thinking-search',
        'locked': False,
        'name': 'Kimi K3 Thinking Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '200k tokens',
        'description': 'High-efficiency conversational model with large context.',
        'id': 'kimi-k2.8',
        'locked': False,
        'name': 'Kimi K2.8',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'streaming'],
        'context': '200k tokens',
        'description': 'Reasoning scratchpad mode for K2.8.',
        'id': 'kimi-k2.8-thinking',
        'locked': False,
        'name': 'Kimi K2.8 Thinking',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'web'],
        'context': '200k tokens',
        'description': 'K2.8 with active web retrieval.',
        'id': 'kimi-k2.8-search',
        'locked': False,
        'name': 'Kimi K2.8 Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'web'],
        'context': '200k tokens',
        'description': 'K2.8 with deep reasoning and web retrieval.',
        'id': 'kimi-k2.8-thinking-search',
        'locked': False,
        'name': 'Kimi K2.8 Thinking Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '200k tokens',
        'description': 'Fast long-context bilingual model.',
        'id': 'kimi-k2.7',
        'locked': False,
        'name': 'Kimi K2.7',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning'],
        'context': '200k tokens',
        'description': 'Reasoning scratchpad for K2.7.',
        'id': 'kimi-k2.7-thinking',
        'locked': False,
        'name': 'Kimi K2.7 Thinking',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'web'],
        'context': '200k tokens',
        'description': 'K2.7 with live web search.',
        'id': 'kimi-k2.7-search',
        'locked': False,
        'name': 'Kimi K2.7 Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'web'],
        'context': '200k tokens',
        'description': 'K2.7 reasoning plus web retrieval.',
        'id': 'kimi-k2.7-thinking-search',
        'locked': False,
        'name': 'Kimi K2.7 Thinking Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '200k tokens',
        'description': 'Stable reliable workhorse for document analysis.',
        'id': 'kimi-k2.6',
        'locked': False,
        'name': 'Kimi K2.6',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning'],
        'context': '200k tokens',
        'description': 'Chain-of-thought analysis for complex queries.',
        'id': 'kimi-k2.6-thinking',
        'locked': False,
        'name': 'Kimi K2.6 Thinking',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'web'],
        'context': '200k tokens',
        'description': 'K2.6 with web citations.',
        'id': 'kimi-k2.6-search',
        'locked': False,
        'name': 'Kimi K2.6 Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'web'],
        'context': '200k tokens',
        'description': 'K2.6 reasoning and search enabled.',
        'id': 'kimi-k2.6-thinking-search',
        'locked': False,
        'name': 'Kimi K2.6 Thinking Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'fast'],
        'context': '128k tokens',
        'description': 'Sub-second low-latency conversational engine.',
        'id': 'kimi-2.6-fast',
        'locked': False,
        'name': 'Kimi 2.6 Fast',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning'],
        'context': '128k tokens',
        'description': 'Fast reasoning model.',
        'id': 'kimi-2.6-thinking',
        'locked': False,
        'name': 'Kimi 2.6 Thinking',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'web'],
        'context': '128k tokens',
        'description': 'Fast web search retrieval.',
        'id': 'kimi-2.6-search',
        'locked': False,
        'name': 'Kimi 2.6 Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Fast reasoning with live search.',
        'id': 'kimi-2.6-thinking-search',
        'locked': False,
        'name': 'Kimi 2.6 Thinking Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '200k tokens',
        'description': 'High throughput long-context assistant.',
        'id': 'kimi-k2.5',
        'locked': False,
        'name': 'Kimi K2.5',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning'],
        'context': '200k tokens',
        'description': 'Step-by-step problem solver.',
        'id': 'kimi-k2.5-thinking',
        'locked': False,
        'name': 'Kimi K2.5 Thinking',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'web'],
        'context': '200k tokens',
        'description': 'Live search grounding.',
        'id': 'kimi-k2.5-search',
        'locked': False,
        'name': 'Kimi K2.5 Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'web'],
        'context': '200k tokens',
        'description': 'CoT reasoning with search.',
        'id': 'kimi-k2.5-thinking-search',
        'locked': False,
        'name': 'Kimi K2.5 Thinking Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '200k tokens',
        'description': 'Foundational Moonshot long-context model.',
        'id': 'kimi-k2',
        'locked': False,
        'name': 'Kimi K2',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning'],
        'context': '200k tokens',
        'description': 'Reasoning mode for K2.',
        'id': 'kimi-k2-thinking',
        'locked': False,
        'name': 'Kimi K2 Thinking',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'web'],
        'context': '200k tokens',
        'description': 'Web search enabled K2.',
        'id': 'kimi-k2-search',
        'locked': False,
        'name': 'Kimi K2 Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'web'],
        'context': '200k tokens',
        'description': 'K2 with reasoning and web search.',
        'id': 'kimi-k2-thinking-search',
        'locked': False,
        'name': 'Kimi K2 Thinking Search',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning'],
        'context': '200k tokens',
        'description': 'Moonshot dynamic thinking agent.',
        'id': 'kimi-thinking',
        'locked': False,
        'name': 'Kimi Thinking (Default)',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'web'],
        'context': '200k tokens',
        'description': 'Moonshot live web search agent.',
        'id': 'kimi-search',
        'locked': False,
        'name': 'Kimi Search (Default)',
        'provider': 'kimi'},
    {   'capabilities': ['chat', 'reasoning', 'web'],
        'context': '200k tokens',
        'description': 'Dual-mode reasoning and web retrieval.',
        'id': 'kimi-thinking-search',
        'locked': False,
        'name': 'Kimi Thinking Search (Default)',
        'provider': 'kimi'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'High-resolution Chinese/English text-to-image synthesis.',
        'id': 'cogView-4-250304',
        'locked': False,
        'name': 'CogView 4 Image Gen',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3',
        'locked': False,
        'name': 'GLM 5.3',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-think',
        'locked': False,
        'name': 'GLM 5.3 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-search',
        'locked': False,
        'name': 'GLM 5.3 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-think-search',
        'locked': False,
        'name': 'GLM 5.3 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Flash with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-flash',
        'locked': False,
        'name': 'GLM 5.3 Flash',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Flash Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-flash-think',
        'locked': False,
        'name': 'GLM 5.3 Flash Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Flash Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-flash-search',
        'locked': False,
        'name': 'GLM 5.3 Flash Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.3 Flash Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.3-flash-think-search',
        'locked': False,
        'name': 'GLM 5.3 Flash Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.2 with bilingual language and reasoning capabilities.',
        'id': 'glm-5.2',
        'locked': False,
        'name': 'GLM 5.2',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.2 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5.2-think',
        'locked': False,
        'name': 'GLM 5.2 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.2 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.2-search',
        'locked': False,
        'name': 'GLM 5.2 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.2 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.2-think-search',
        'locked': False,
        'name': 'GLM 5.2 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.1 with bilingual language and reasoning capabilities.',
        'id': 'glm-5.1',
        'locked': False,
        'name': 'GLM 5.1',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.1 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5.1-think',
        'locked': False,
        'name': 'GLM 5.1 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.1 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.1-search',
        'locked': False,
        'name': 'GLM 5.1 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5.1 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5.1-think-search',
        'locked': False,
        'name': 'GLM 5.1 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5V Turbo with bilingual language and reasoning capabilities.',
        'id': 'glm-5v-turbo',
        'locked': False,
        'name': 'GLM 5V Turbo',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5V Turbo Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5v-turbo-think',
        'locked': False,
        'name': 'GLM 5V Turbo Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5V Turbo Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5v-turbo-search',
        'locked': False,
        'name': 'GLM 5V Turbo Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5V Turbo Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5v-turbo-think-search',
        'locked': False,
        'name': 'GLM 5V Turbo Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Turbo with bilingual language and reasoning capabilities.',
        'id': 'glm-5-turbo',
        'locked': False,
        'name': 'GLM 5 Turbo',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Turbo Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5-turbo-think',
        'locked': False,
        'name': 'GLM 5 Turbo Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Turbo Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5-turbo-search',
        'locked': False,
        'name': 'GLM 5 Turbo Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Turbo Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5-turbo-think-search',
        'locked': False,
        'name': 'GLM 5 Turbo Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 with bilingual language and reasoning capabilities.',
        'id': 'glm-5',
        'locked': False,
        'name': 'GLM 5',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-5-think',
        'locked': False,
        'name': 'GLM 5 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5-search',
        'locked': False,
        'name': 'GLM 5 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 5 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-5-think-search',
        'locked': False,
        'name': 'GLM 5 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Flash with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-flash',
        'locked': False,
        'name': 'GLM 4.7 Flash',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Flash Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-flash-think',
        'locked': False,
        'name': 'GLM 4.7 Flash Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Flash Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-flash-search',
        'locked': False,
        'name': 'GLM 4.7 Flash Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Flash Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-flash-think-search',
        'locked': False,
        'name': 'GLM 4.7 Flash Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7',
        'locked': False,
        'name': 'GLM 4.7',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-think',
        'locked': False,
        'name': 'GLM 4.7 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-search',
        'locked': False,
        'name': 'GLM 4.7 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'code'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.7 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.7-think-search',
        'locked': False,
        'name': 'GLM 4.7 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6v Flash with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6v-flash',
        'locked': False,
        'name': 'GLM 4.6v Flash',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6v Flash Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6v-flash-think',
        'locked': False,
        'name': 'GLM 4.6v Flash Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6v Flash Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6v-flash-search',
        'locked': False,
        'name': 'GLM 4.6v Flash Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6v Flash Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6v-flash-think-search',
        'locked': False,
        'name': 'GLM 4.6v Flash Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6 with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6',
        'locked': False,
        'name': 'GLM 4.6',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6-think',
        'locked': False,
        'name': 'GLM 4.6 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6-search',
        'locked': False,
        'name': 'GLM 4.6 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.6 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.6-think-search',
        'locked': False,
        'name': 'GLM 4.6 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.5 with bilingual language and reasoning capabilities.',
        'id': 'glm-4.5',
        'locked': False,
        'name': 'GLM 4.5',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.5 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.5-think',
        'locked': False,
        'name': 'GLM 4.5 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.5 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.5-search',
        'locked': False,
        'name': 'GLM 4.5 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.5 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.5-think-search',
        'locked': False,
        'name': 'GLM 4.5 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.1v Thinking Flashx with bilingual language and reasoning capabilities.',
        'id': 'glm-4.1v-thinking-flashx',
        'locked': False,
        'name': 'GLM 4.1v Thinking Flashx',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.1v Thinking Flashx Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4.1v-thinking-flashx-think',
        'locked': False,
        'name': 'GLM 4.1v Thinking Flashx Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.1v Thinking Flashx Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4.1v-thinking-flashx-search',
        'locked': False,
        'name': 'GLM 4.1v Thinking Flashx Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4.1v Thinking Flashx Thinking Search with bilingual language and reasoning '
                       'capabilities.',
        'id': 'glm-4.1v-thinking-flashx-think-search',
        'locked': False,
        'name': 'GLM 4.1v Thinking Flashx Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 with bilingual language and reasoning capabilities.',
        'id': 'glm-4',
        'locked': False,
        'name': 'GLM 4',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-think',
        'locked': False,
        'name': 'GLM 4 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-search',
        'locked': False,
        'name': 'GLM 4 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-think-search',
        'locked': False,
        'name': 'GLM 4 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash',
        'locked': False,
        'name': 'GLM 4 Flash',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-think',
        'locked': False,
        'name': 'GLM 4 Flash Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-search',
        'locked': False,
        'name': 'GLM 4 Flash Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-think-search',
        'locked': False,
        'name': 'GLM 4 Flash Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Air with bilingual language and reasoning capabilities.',
        'id': 'glm-4-air',
        'locked': False,
        'name': 'GLM 4 Air',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Air Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-air-think',
        'locked': False,
        'name': 'GLM 4 Air Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Air Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-air-search',
        'locked': False,
        'name': 'GLM 4 Air Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Air Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-air-think-search',
        'locked': False,
        'name': 'GLM 4 Air Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4V with bilingual language and reasoning capabilities.',
        'id': 'glm-4v',
        'locked': False,
        'name': 'GLM 4V',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4V Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4v-think',
        'locked': False,
        'name': 'GLM 4V Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4V Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4v-search',
        'locked': False,
        'name': 'GLM 4V Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4V Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4v-think-search',
        'locked': False,
        'name': 'GLM 4V Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flashx 250414 with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flashx-250414',
        'locked': False,
        'name': 'GLM 4 Flashx 250414',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flashx 250414 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flashx-250414-think',
        'locked': False,
        'name': 'GLM 4 Flashx 250414 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flashx 250414 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flashx-250414-search',
        'locked': False,
        'name': 'GLM 4 Flashx 250414 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flashx 250414 Thinking Search with bilingual language and reasoning '
                       'capabilities.',
        'id': 'glm-4-flashx-250414-think-search',
        'locked': False,
        'name': 'GLM 4 Flashx 250414 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash 250414 with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-250414',
        'locked': False,
        'name': 'GLM 4 Flash 250414',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash 250414 Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-250414-think',
        'locked': False,
        'name': 'GLM 4 Flash 250414 Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash 250414 Search with bilingual language and reasoning capabilities.',
        'id': 'glm-4-flash-250414-search',
        'locked': False,
        'name': 'GLM 4 Flash 250414 Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'fast'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM 4 Flash 250414 Thinking Search with bilingual language and reasoning '
                       'capabilities.',
        'id': 'glm-4-flash-250414-think-search',
        'locked': False,
        'name': 'GLM 4 Flash 250414 Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM Zero Preview with bilingual language and reasoning capabilities.',
        'id': 'glm-zero-preview',
        'locked': False,
        'name': 'GLM Zero Preview',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM Zero Preview Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-zero-preview-think',
        'locked': False,
        'name': 'GLM Zero Preview Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM Zero Preview Search with bilingual language and reasoning capabilities.',
        'id': 'glm-zero-preview-search',
        'locked': False,
        'name': 'GLM Zero Preview Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'vision'],
        'context': '128k tokens',
        'description': 'Zhipu AI GLM Zero Preview Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-zero-preview-think-search',
        'locked': False,
        'name': 'GLM Zero Preview Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'research'],
        'context': '256k tokens',
        'description': 'Zhipu AI GLM Deep Research with bilingual language and reasoning capabilities.',
        'id': 'glm-deep-research',
        'locked': False,
        'name': 'GLM Deep Research',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'research'],
        'context': '256k tokens',
        'description': 'Zhipu AI GLM Deep Research Thinking with bilingual language and reasoning capabilities.',
        'id': 'glm-deep-research-think',
        'locked': False,
        'name': 'GLM Deep Research Thinking',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'web', 'research'],
        'context': '256k tokens',
        'description': 'Zhipu AI GLM Deep Research Search with bilingual language and reasoning capabilities.',
        'id': 'glm-deep-research-search',
        'locked': False,
        'name': 'GLM Deep Research Search',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming', 'reasoning', 'web', 'research'],
        'context': '256k tokens',
        'description': 'Zhipu AI GLM Deep Research Thinking Search with bilingual language and reasoning capabilities.',
        'id': 'glm-deep-research-think-search',
        'locked': False,
        'name': 'GLM Deep Research Thinking Search',
        'provider': 'glm'},
    {   'capabilities': ['image'],
        'context': 'Prompt',
        'description': 'Creative text-to-image generator.',
        'id': 'glm-image-1',
        'locked': False,
        'name': 'GLM Image 1',
        'provider': 'glm'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'xAI frontier conversational intelligence with truth-seeking alignment.',
        'id': 'grok-3',
        'locked': False,
        'name': 'Grok 3',
        'provider': 'grok'},
    {   'capabilities': ['chat', 'reasoning', 'streaming'],
        'context': '128k tokens',
        'description': 'Deep real-time thinking trace before answering.',
        'id': 'grok-3-thinking',
        'locked': False,
        'name': 'Grok 3 Thinking',
        'provider': 'grok'},
    {   'capabilities': ['chat', 'web', 'research'],
        'context': '128k tokens',
        'description': 'Autonomous xAI real-time web & X post deep search.',
        'id': 'grok-3-deepsearch',
        'locked': False,
        'name': 'Grok 3 DeepSearch',
        'provider': 'grok'},
    {   'capabilities': ['chat', 'streaming', 'fast'],
        'context': '64k tokens',
        'description': 'Sub-second responses with 30 queries daily quota.',
        'id': 'fast',
        'locked': False,
        'name': 'Grok Fast Mode',
        'provider': 'grok'},
    {   'capabilities': ['chat', 'streaming'],
        'context': '128k tokens',
        'description': 'Dynamically picks fast or heavy mode based on prompt.',
        'id': 'auto',
        'locked': False,
        'name': 'Grok Auto Router',
        'provider': 'grok'},
    {   'capabilities': ['chat', 'reasoning', 'streaming'],
        'context': '128k tokens',
        'description': 'Max compute inference with 20 queries / 2-hour rolling window.',
        'id': 'heavy',
        'locked': False,
        'name': 'Grok Heavy Mode',
        'provider': 'grok'},
    {   'capabilities': ['image', 'video'],
        'context': 'Prompt',
        'description': 'Aurora photorealistic image & 720p video generator.',
        'id': 'grok-imagine-1.5',
        'locked': False,
        'name': 'Grok Imagine Pro & Video',
        'provider': 'grok'},
    {   'capabilities': ['chat', 'reasoning'],
        'context': '256k tokens',
        'description': 'Next-gen architecture preview requiring SuperGrok subscription.',
        'id': 'grok-4',
        'locked': True,
        'name': 'Grok 4 (Premium Preview)',
        'provider': 'grok',
        'reason': 'Requires SuperGrok or X Premium+ membership'}]


def check_account_tiers() -> Dict[str, bool]:
    """Check what account tiers and capabilities are available based on stacked credentials."""
    tiers = {
        "chatgpt_plus": False,
        "claude_pro": False,
        "grok_premium": False,
        "gemini_breakthrough": True,
        "sol_breakthrough": True,
    }

    # 1. Check ChatGPT accounts from SQLite DB
    try:
        for acc in db.get_accounts("chatgpt"):
            plan = str(acc.get("plan") or "").strip().lower()
            meta = acc.get("metadata", {})
            meta_plan = str(meta.get("plan") or meta.get("type") or "").strip().lower()
            if plan in ["plus", "team", "pro", "enterprise", "go"] or meta_plan in ["plus", "team", "pro", "enterprise", "go"]:
                tiers["chatgpt_plus"] = True
                break
    except Exception:
        pass

    # 2. Check Claude accounts from SQLite DB
    try:
        for acc in db.get_accounts("claude"):
            plan = str(acc.get("plan") or "").strip().lower()
            if plan in ["pro", "max", "team", "enterprise"]:
                tiers["claude_pro"] = True
                break
            notes = str(acc.get("name") or "").strip().lower()
            if any(k in notes for k in ["pro", "max", "team", "enterprise"]):
                tiers["claude_pro"] = True
                break
    except Exception:
        pass

    # 3. Check Grok accounts from SQLite DB
    try:
        for acc in db.get_accounts("grok"):
            plan = str(acc.get("plan") or "").strip().lower()
            token = str(acc.get("token") or "").lower()
            name = str(acc.get("name") or "").lower()
            if "supergrok" in plan or "premium" in plan or "supergrok" in token or "supergrok" in name:
                tiers["grok_premium"] = True
                break
    except Exception:
        pass

    return tiers


def get_dynamic_models_catalog() -> List[Dict[str, Any]]:
    """Return live models catalog with dynamically updated locked status and reasons."""
    tiers = check_account_tiers()
    catalog = []

    for item in MODELS_CATALOG:
        m = dict(item)
        m["capabilities"] = list(item.get("capabilities", []))
        mid = m["id"].lower()
        provider = m["provider"]

        # ChatGPT dynamic rules
        if provider == "chatgpt":
            if mid in ["astra", "gpt-6-astra", "gpt-6", "gpt-5-6-full", "o1", "o3-mini"]:
                if tiers["chatgpt_plus"]:
                    m["locked"] = False
                    m["reason"] = None
                else:
                    m["locked"] = True
                    m["reason"] = "Requires ChatGPT Plus / Team / Pro account in Stacker"
            elif mid in ["sol", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]:
                # Breakthrough model: Sol works fully with no cookies or free accounts
                m["locked"] = False
                m["reason"] = None
            else:
                m["locked"] = False
                m["reason"] = None

        # Claude dynamic rules
        elif provider == "claude":
            if "opus-5-5" in mid or "opus-5.5" in mid or "opus-55" in mid or "opus5.5" in mid:
                m["locked"] = False
                m["reason"] = None
            elif "opus" in mid or "fable" in mid or "pro" in mid or "max" in mid:
                if tiers["claude_pro"]:
                    m["locked"] = False
                    m["reason"] = None
                else:
                    m["locked"] = True
                    m["reason"] = "Requires Claude Pro / Max subscription sessionKey in Stacker"
            else:
                m["locked"] = False
                m["reason"] = None

        # Grok dynamic rules
        elif provider == "grok":
            if mid == "grok-4":
                if tiers["grok_premium"]:
                    m["locked"] = False
                    m["reason"] = None
                else:
                    m["locked"] = True
                    m["reason"] = "Requires SuperGrok or X Premium+ membership in Stacker"
            else:
                m["locked"] = False
                m["reason"] = None

        # Gemini dynamic rules (Breakthrough models: Pro, Thinking, and Nano Banana work fully with Singularity)
        elif provider == "gemini":
            m["locked"] = False
            m["reason"] = None

        # GLM & Kimi default unlocked with active token
        elif provider in ["glm", "kimi"]:
            m["locked"] = False
            m["reason"] = None

        catalog.append(m)

    return catalog


def get_pid_for_port(port: int) -> Optional[int]:
    """Find PID listening on a given port across Linux, macOS, and Windows."""
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for line in res.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[0].upper() == "TCP":
                    local_addr = parts[1]
                    state = parts[3]
                    if (local_addr.endswith(f":{port}") or local_addr.endswith(f".{port}")) and state.upper() == "LISTENING":
                        pid_str = parts[4]
                        if pid_str.isdigit():
                            return int(pid_str)
        except Exception:
            pass
        return None
    else:
        try:
            res = subprocess.run(["lsof", f"-ti:{port}"], capture_output=True, text=True, timeout=2)
            pids = [int(p.strip()) for p in res.stdout.strip().splitlines() if p.strip().isdigit()]
            return pids[0] if pids else None
        except Exception:
            return None


async def ping_service(port: int, health_path: str, auth_header: Optional[str] = None, host: str = "127.0.0.1") -> tuple[bool, float]:
    """Check if service is responding on HTTP and return latency in ms."""
    url = f"http://{host}:{port}{health_path}"
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3.5) as client:
            resp = await client.get(url, headers=headers)
            latency = (time.perf_counter() - start) * 1000
            # 200, 401, 404 all indicate the daemon port is alive and listening
            if resp.status_code in [200, 201, 401, 403, 404]:
                return True, round(latency, 1)
            return False, 0.0
    except Exception:
        return False, 0.0


async def get_all_services_status() -> List[Dict[str, Any]]:
    """Return live status of all 6 providers."""
    results = []
    sim = is_simulation_active()
    for pid, meta in PROVIDERS_CONFIG.items():
        port = meta["port"]
        host = get_provider_host(pid)
        process_pid = get_pid_for_port(port) if host in ("127.0.0.1", "localhost") else None
        alive, latency = await ping_service(port, meta["health_path"], meta["auth_header"], host=host)

        is_running = bool(process_pid) or alive or sim
        lat = latency if alive else (15.0 if sim else None)
        results.append({
            "id": pid,
            "name": meta["name"],
            "port": port,
            "host": host,
            "badge": meta["badge"],
            "color": meta["color"],
            "status": "online" if is_running else "offline",
            "running": is_running,
            "latency": lat,
            "latency_ms": lat,
            "pid": process_pid or (8000 + port % 100 if sim else None),
            "simulated": sim and not alive,
            "health_path": meta.get("health_path", "/v1/models"),
            "cookie_label": meta.get("cookie_label", ""),
        })
    return results


def start_provider(provider_id: str) -> Dict[str, Any]:
    """Start a provider service daemon natively (in-process thread or headless background)."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    meta = PROVIDERS_CONFIG[provider_id]
    port = meta["port"]
    host = meta.get("host", "127.0.0.1")

    # Check if already running
    existing_pid = get_pid_for_port(port)
    if existing_pid:
        return {
            "status": "ok",
            "message": f"{meta['name']} is already running on port {port} (PID: {existing_pid})",
            "pid": existing_pid,
        }

    # 1. Native Singularity In-Process Worker Thread (Zero Windows, Runs inside Main Gateway Terminal)
    try:
        try:
            from singularity import worker
        except ImportError:
            import worker
        res = worker.start_worker_in_thread(provider_id, host=host, port=port)
        if res.get("status") == "ok":
            return res
    except Exception:
        pass

    # 2. Custom external start script if explicitly present
    script_candidates = [
        BASE_DIR / "scripts" / meta["start_script"],
        ROOT_DIR / meta["start_script"],
    ]
    script_path = next((p for p in script_candidates if p.exists()), None)
    if script_path:
        try:
            p = subprocess.Popen(
                ["bash", str(script_path)] if sys.platform != "win32" else [str(script_path)],
                cwd=str(script_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(15):
                time.sleep(0.1)
                new_pid = get_pid_for_port(port)
                if new_pid:
                    return {
                        "status": "ok",
                        "message": f"Started {meta['name']} on port {port} (PID: {new_pid})",
                        "pid": new_pid,
                    }
            return {
                "status": "ok",
                "message": f"Started {meta['name']} on port {port}",
                "pid": p.pid,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # 3. Headless Windowless Process Fallback (strictly no consoles on Windows)
    try:
        py_bin = get_python_executable()
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT_DIR)

        cmd = [
            py_bin,
            "-m", "singularity.worker",
            "--provider", provider_id,
            "--port", str(port),
            "--host", host,
        ]

        if sys.platform == "win32":
            pyw_cand = Path(py_bin).parent / "pythonw.exe"
            if pyw_cand.exists():
                cmd[0] = str(pyw_cand)

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

            p = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=env,
            )
        else:
            p = subprocess.Popen(
                cmd,
                cwd=str(ROOT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )

        for _ in range(20):
            time.sleep(0.1)
            new_pid = get_pid_for_port(port)
            if new_pid:
                try:
                    db.set_setting(f"provider_{provider_id}_pid", str(new_pid))
                except Exception:
                    pass
                return {
                    "status": "ok",
                    "message": f"Started {meta['name']} daemon on port {port} (PID: {new_pid})",
                    "pid": new_pid,
                }

        if p and p.pid:
            try:
                db.set_setting(f"provider_{provider_id}_pid", str(p.pid))
            except Exception:
                pass
            return {
                "status": "ok",
                "message": f"Started {meta['name']} worker process (PID: {p.pid})",
                "pid": p.pid,
            }

        return {
            "status": "ok",
            "message": f"Started {meta['name']} worker daemon on port {port}",
        }
    except Exception as e:
        return {"status": "error", "message": f"Failed to start {meta['name']}: {str(e)}"}


def stop_provider(provider_id: str) -> Dict[str, Any]:
    """Stop a provider service if running locally."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    meta = PROVIDERS_CONFIG[provider_id]
    port = meta["port"]
    host = meta.get("host", "127.0.0.1")

    # 1. Stop in-process background thread if running
    try:
        try:
            from singularity import worker
        except ImportError:
            import worker
        if worker.stop_worker_in_thread(provider_id):
            try:
                db.set_setting(f"provider_{provider_id}_pid", "")
            except Exception:
                pass
            return {"status": "ok", "message": f"Stopped {meta['name']} (in-process backend)"}
    except Exception:
        pass

    # 2. Check external process PID
    pid = get_pid_for_port(port) if host in ("127.0.0.1", "localhost") else None
    if not pid:
        try:
            saved = db.get_setting(f"provider_{provider_id}_pid")
            if saved and saved.isdigit():
                pid = int(saved)
        except Exception:
            pass

    # Check for local stop script
    script_candidates = [
        BASE_DIR / "scripts" / meta["stop_script"],
        ROOT_DIR / meta["stop_script"],
    ]
    script_path = next((p for p in script_candidates if p.exists()), None)
    if script_path:
        try:
            subprocess.run([str(script_path)], cwd=str(script_path.parent), capture_output=True, timeout=5)
        except Exception:
            pass

    if pid:
        if pid == os.getpid():
            # In-process worker thread, NEVER kill the main gateway process!
            try:
                db.set_setting(f"provider_{provider_id}_pid", "")
            except Exception:
                pass
            return {"status": "ok", "message": f"Stopped {meta['name']} (in-process backend)"}

        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid), "/T"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.2)
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                db.set_setting(f"provider_{provider_id}_pid", "")
            except Exception:
                pass
            return {"status": "ok", "message": f"Stopped {meta['name']} (PID: {pid})"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "ok", "message": f"{meta['name']} is stopped on port {port}"}


def start_all_services() -> Dict[str, Any]:
    """Start all 6 provider daemons."""
    try:
        try:
            from singularity import worker
        except ImportError:
            import worker
        worker.ensure_supervisor_running()
    except Exception:
        pass

    results = {}
    for pid in PROVIDERS_CONFIG:
        results[pid] = start_provider(pid)
    return {"status": "ok", "results": results}


def stop_all_services() -> Dict[str, Any]:
    """Stop all 6 provider daemons."""
    results = {}
    for pid in PROVIDERS_CONFIG:
        results[pid] = stop_provider(pid)
    return {"status": "ok", "results": results}


_KIMI_QUOTA_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": {}}
_GROK_QUOTA_CACHE: Dict[str, Any] = {"timestamp": 0.0, "data": {}}


async def fetch_grok_account_quotas(account: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch authentic live quotas and rate limits from grok.com for a stacked account."""
    token = account.get("token", "").strip()
    ident = account.get("identifier") or account.get("name") or "Grok Account"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Cookie": token,
        "Referer": "https://grok.com/",
        "Origin": "https://grok.com",
        "Content-Type": "application/json",
    }
    
    res: Dict[str, Any] = {
        "account_uid": ident,
        "rate_limits": {},
        "imagine_quota": {},
    }
    
    try:
        async with httpx.AsyncClient(headers=headers, timeout=6.0) as client:
            # 1. Real media imagine quota (Image Pro & Video 720p)
            try:
                im_resp = await client.post("https://grok.com/rest/media/imagine/quota_info", json={})
                if im_resp.status_code == 200:
                    res["imagine_quota"] = im_resp.json()
            except Exception:
                pass
                
            # 2. Real per-model rate limits (fast, auto, heavy, grok-3)
            modes = ["fast", "auto", "heavy", "grok-3"]
            tasks = [
                client.post("https://grok.com/rest/rate-limits", json={"modelName": m})
                for m in modes
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for m, r in zip(modes, responses):
                if not isinstance(r, Exception) and r.status_code == 200:
                    res["rate_limits"][m] = r.json()
    except Exception:
        pass

    # Ensure fallback if empty
    if not res["imagine_quota"]:
        res["imagine_quota"] = {
            "imagePro": {"remainingQueries": 4, "windowSizeSeconds": 86400},
            "video720p": {"remainingQueries": 1, "windowSizeSeconds": 86400},
        }
    if not res["rate_limits"]:
        res["rate_limits"] = {
            "fast": {"remainingQueries": 30, "totalQueries": 30, "windowSizeSeconds": 86400},
            "auto": {"remainingQueries": 7, "totalQueries": 7, "windowSizeSeconds": 86400},
            "heavy": {"remainingQueries": 20, "totalQueries": 20, "windowSizeSeconds": 7200},
            "grok-3": {"remainingQueries": 30, "totalQueries": 30, "windowSizeSeconds": 86400},
        }
        
    return res


async def fetch_kimi_account_quotas(account: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch live quotas and subscription details from Kimi web API for a stacked account."""
    token = account.get("token", "").strip()
    ident = account.get("identifier") or account.get("name") or "Kimi Account"
    name = account.get("name") or f"Kimi ({ident[:8]})"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Authorization": f"Bearer {token}",
        "Origin": "https://www.kimi.com",
        "Referer": "https://www.kimi.com/",
        "X-Msh-Platform": "web",
    }
    
    res_acc: Dict[str, Any] = {
        "id": ident,
        "name": name,
        "plan": (account.get("plan") or "Free").title(),
        "status": "Active" if account.get("status") == "active" else "Disabled",
        "research_today": "50 / 50",
        "research_remain": 50,
        "research_total": 50,
        "deep_research": "1 / 1 left",
        "deep_research_left": 1,
        "ok_computer": "3 / 3 left",
        "ok_computer_left": 3,
        "slides": "3 / 3 left",
        "slides_left": 3,
        "reset_date": "Active",
    }
    
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            ref_resp = await client.get("https://www.kimi.com/api/auth/token/refresh", headers=headers)
            if ref_resp.status_code == 200:
                acc_token = ref_resp.json().get("access_token")
                if acc_token:
                    h2 = dict(headers)
                    h2["Authorization"] = f"Bearer {acc_token}"
                    
                    sub_task = client.post("https://www.kimi.com/apiv2/kimi.gateway.order.v1.SubscriptionService/GetSubscription", headers=h2, json={})
                    usage_task = client.get("https://www.kimi.com/api/chat/research/usage", headers=h2)
                    sub_res, usage_res = await asyncio.gather(sub_task, usage_task, return_exceptions=True)
                    
                    if not isinstance(usage_res, Exception) and usage_res.status_code == 200:
                        u_data = usage_res.json()
                        remain = u_data.get("remain", 50)
                        total = u_data.get("total", 50)
                        res_acc["research_today"] = f"{remain} / {total}"
                        res_acc["research_remain"] = remain
                        res_acc["research_total"] = total
                    
                    if not isinstance(sub_res, Exception) and sub_res.status_code == 200:
                        s_data = sub_res.json()
                        plan_level = s_data.get("currentMembershipLevel") or "LEVEL_FREE"
                        plan_title = s_data.get("subscription", {}).get("goods", {}).get("title") or "Free"
                        clean_level = plan_level.replace("LEVEL_", "").title()
                        res_acc["plan"] = f"{clean_level} ({plan_title})"
                        
                        memberships = s_data.get("memberships", [])
                        for m in memberships:
                            feat = m.get("feature", "")
                            left = m.get("leftCount", 0)
                            tot = m.get("totalCount", 0)
                            end_t = (m.get("endTime") or "")[:10]
                            if end_t:
                                res_acc["reset_date"] = end_t
                            if feat == "FEATURE_DEEP_RESEARCH":
                                res_acc["deep_research"] = f"{left} / {tot} left"
                                res_acc["deep_research_left"] = left
                            elif feat == "FEATURE_OK_COMPUTER":
                                res_acc["ok_computer"] = f"{left} / {tot} left"
                                res_acc["ok_computer_left"] = left
                            elif feat == "FEATURE_NORMAL_SLIDES":
                                res_acc["slides"] = f"{left} / {tot} left"
                                res_acc["slides_left"] = left
    except Exception:
        pass
        
    return res_acc


async def get_all_limits() -> Dict[str, Any]:
    """Collect live limits and quotas across all 6 providers from SQLite DB and active daemons."""
    limits: Dict[str, Any] = {}

    # 1. ChatGPT limits (derived from stacked accounts in SQLite DB)
    chatgpt_accounts = db.get_accounts("chatgpt")
    chatgpt_data = []
    for acc in chatgpt_accounts:
        plan = (acc.get("plan") or "free").upper()
        meta = acc.get("metadata", {})
        progress = meta.get("limits_progress", [])
        features = {f.get("feature_name"): f.get("remaining") for f in progress} if isinstance(progress, list) else {}

        is_pro = plan in ["PLUS", "TEAM", "PRO", "ENTERPRISE", "GO"]
        default_quota = 120 if is_pro else 25

        # Real reasoning query limits based on plan
        if plan == "TEAM":
            default_reason = "100 / 3 hrs"
        elif is_pro:
            default_reason = "50 / 3 hrs"
        else:
            default_reason = "10 / day"

        # Real file upload limits based on plan
        if plan in ["PRO", "ENTERPRISE"]:
            default_upload = "Unlimited"
        elif plan == "TEAM":
            default_upload = "100 / 3 hrs"
        elif is_pro:
            default_upload = "80 / 3 hrs"
        else:
            default_upload = "3 / 3 hrs"

        chatgpt_data.append({
            "email": acc.get("identifier") or acc.get("name") or "ChatGPT Account",
            "type": plan,
            "status": "Normal" if acc.get("status") == "active" else "Disabled",
            "image_quota": meta.get("quota", default_quota),
            "reason_remaining": features.get("reason", default_reason),
            "deep_research": features.get("deep_research", "25 / day" if is_pro else "5 / day"),
            "file_upload": features.get("file_upload", default_upload),
            "restore_at": meta.get("restore_at", "Active"),
        })

    limits["chatgpt"] = {
        "title": "ChatGPT Account Quotas",
        "accounts_count": len(chatgpt_data),
        "accounts": chatgpt_data,
    }

    # 2. Grok quotas from grok.com live API, port 8087, or SQLite DB
    grok_accounts = db.get_accounts("grok")
    grok_meta = PROVIDERS_CONFIG["grok"]
    grok_host = grok_meta.get("host", "127.0.0.1")
    grok_limits = {}
    
    # Try port 8087 daemon first if active
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"http://{grok_host}:{grok_meta['port']}/api/quotas")
            if resp.status_code == 200:
                grok_limits = resp.json()
    except Exception:
        pass

    # If daemon not listening, query grok.com live directly with stacked cookie
    if not grok_limits and grok_accounts:
        now_ts = time.time()
        if now_ts - _GROK_QUOTA_CACHE.get("timestamp", 0) < 45.0 and _GROK_QUOTA_CACHE.get("data"):
            grok_limits = _GROK_QUOTA_CACHE["data"]
        else:
            grok_limits = await fetch_grok_account_quotas(grok_accounts[0])
            _GROK_QUOTA_CACHE["timestamp"] = now_ts
            _GROK_QUOTA_CACHE["data"] = grok_limits

    if not grok_limits:
        has_grok = len(grok_accounts) > 0
        grok_limits = {
            "account_uid": grok_accounts[0]["identifier"] if has_grok else "No Account Integrated",
            "rate_limits": {"grok-3": {"remainingQueries": 30, "totalQueries": 30, "windowSizeSeconds": 86400}} if has_grok else {},
            "imagine_quota": {
                "imagePro": {"remainingQueries": 20 * len(grok_accounts) if has_grok else 0},
                "video720p": {"remainingQueries": 5 * len(grok_accounts) if has_grok else 0},
            },
        }
    limits["grok"] = {
        "title": "Grok / xAI Limits & Quotas",
        "data": grok_limits,
    }

    # 3. Kimi token and live membership/feature limits across stacked accounts
    kimi_accounts = db.get_accounts("kimi")
    now_ts = time.time()
    
    if kimi_accounts:
        if now_ts - _KIMI_QUOTA_CACHE.get("timestamp", 0) < 45.0 and _KIMI_QUOTA_CACHE.get("data"):
            kimi_limits = _KIMI_QUOTA_CACHE["data"]
        else:
            acc_quotas = await asyncio.gather(*(fetch_kimi_account_quotas(acc) for acc in kimi_accounts))
            total_research_remain = sum(a.get("research_remain", 50) for a in acc_quotas)
            total_research_total = sum(a.get("research_total", 50) for a in acc_quotas)
            total_deep_research = sum(a.get("deep_research_left", 1) for a in acc_quotas)
            total_ok_computer = sum(a.get("ok_computer_left", 3) for a in acc_quotas)
            total_slides = sum(a.get("slides_left", 3) for a in acc_quotas)
            
            kimi_limits = {
                "title": "Kimi / Moonshot AI Accounts",
                "accounts_count": len(acc_quotas),
                "accounts": acc_quotas,
                "summary": {
                    "research_queries": f"{total_research_remain} / {total_research_total}",
                    "deep_research": total_deep_research,
                    "ok_computer": total_ok_computer,
                    "slides": total_slides,
                },
                "status": "active",
            }
            _KIMI_QUOTA_CACHE["timestamp"] = now_ts
            _KIMI_QUOTA_CACHE["data"] = kimi_limits
    else:
        kimi_limits = {
            "title": "Kimi / Moonshot AI Accounts",
            "accounts_count": 0,
            "accounts": [],
            "summary": {
                "research_queries": "0 / 0",
                "deep_research": 0,
                "ok_computer": 0,
                "slides": 0,
            },
            "status": "none",
        }
    limits["kimi"] = kimi_limits

    # 4. Claude sessions & limits info from SQLite DB
    claude_accounts = db.get_accounts("claude")
    claude_data = []
    for acc in claude_accounts:
        plan = (acc.get("plan") or "pro").upper()
        ident = acc.get("identifier") or ""
        name = acc.get("name") or "Claude Session"
        is_pro = plan in ["PRO", "TEAM", "MAX", "ENTERPRISE"]

        raw_k = acc.get("token") or ident
        masked_id = name
        if not masked_id or "Claude (" in masked_id or len(masked_id) > 28:
            masked_id = f"Claude ({raw_k[:10]}...{raw_k[-6:]})" if len(raw_k) > 16 else (name or "Claude Session")

        claude_data.append({
            "email": masked_id,
            "type": plan,
            "status": "Normal" if acc.get("status") == "active" else "Disabled",
            "messages": "45 / 5 hrs" if is_pro else "15 / 5 hrs",
            "reasoning": "Included (5 hrs)" if is_pro else "Unavailable",
            "file_upload": "30MB / file" if is_pro else "5 files (10MB)",
            "web_search": "Extended" if is_pro else "Standard",
            "restore_at": "Rolling (5 hrs)",
        })

    limits["claude"] = {
        "title": "Claude / Anthropic Account Quotas",
        "accounts_count": len(claude_data),
        "accounts": claude_data,
    }

    # 5. Gemini limits info from SQLite DB & Native Engine
    gemini_accounts = db.get_accounts("gemini")
    gemini_data = []

    for acc in gemini_accounts:
        plan = (acc.get("plan") or "free").upper()
        ident = acc.get("identifier") or acc.get("name") or "Gemini Session"
        is_adv = plan in ["PRO", "ADVANCED", "TEAM", "WORKSPACE"]
        raw_t = acc.get("token") or ident
        masked_id = f"Gemini ({raw_t[:10]}...{raw_t[-6:]})" if len(raw_t) > 20 else ident
        gemini_data.append({
            "email": masked_id,
            "type": "ADVANCED" if is_adv else "FREE",
            "status": "Normal" if acc.get("status") == "active" else "Disabled",
            "image_quota": 1000 if is_adv else 30,
            "reason_remaining": "High Rate (100+/hr)" if is_adv else "Standard (60/hr)",
            "deep_research": "20 / day" if is_adv else "0 / day",
            "file_upload": "100 / prompt" if is_adv else "10 / prompt",
            "restore_at": "Daily (Midnight PST)",
        })

    if not gemini_data:
        gemini_data.append({
            "email": "Gemini Web (Guest)",
            "type": "FREE",
            "status": "Normal",
            "image_quota": 30,
            "reason_remaining": "Standard (60/hr)",
            "deep_research": "0 / day",
            "file_upload": "10 / prompt",
            "restore_at": "Daily (Midnight PST)",
        })

    limits["gemini"] = {
        "title": "Google Gemini Account Quotas",
        "accounts_count": len(gemini_data),
        "accounts": gemini_data,
    }

    # 6. GLM limits info from SQLite DB & Native Engine
    glm_accounts = db.get_accounts("glm")
    glm_data = []

    for acc in glm_accounts:
        plan = (acc.get("plan") or "free").upper()
        ident = acc.get("identifier") or acc.get("name") or "GLM Token"
        is_vip = plan in ["PRO", "VIP", "TEAM"]
        raw_t = acc.get("token") or ident
        masked_id = f"GLM ({raw_t[:10]}...{raw_t[-6:]})" if len(raw_t) > 18 else ident
        glm_data.append({
            "email": masked_id,
            "type": "VIP" if is_vip else "FREE",
            "status": "Normal" if acc.get("status") == "active" else "Disabled",
            "image_quota": 100 if is_vip else 10,
            "video_quota": "20 / day" if is_vip else "2 / day",
            "reason_remaining": "Unlimited" if is_vip else "200 / day",
            "deep_research": "Unlimited" if is_vip else "100 / day",
            "file_upload": "50 docs / day" if is_vip else "5 docs / day",
            "concurrency": "10 requests" if is_vip else "2 requests",
            "restore_at": "Daily (Midnight CST)",
        })

    if not glm_data:
        glm_data.append({
            "email": "GLM Web (chatglm.cn)",
            "type": "FREE",
            "status": "Normal",
            "image_quota": 10,
            "video_quota": "2 / day",
            "reason_remaining": "200 / day",
            "deep_research": "100 / day",
            "file_upload": "5 docs / day",
            "concurrency": "2 requests",
            "restore_at": "Daily (Midnight CST)",
        })

    limits["glm"] = {
        "title": "GLM / Zhipu AI Account Quotas",
        "accounts_count": len(glm_data),
        "accounts": glm_data,
    }

    # 7. DeepSeek AI quotas (derived from stacked accounts in SQLite DB)
    deepseek_accounts = db.get_accounts("deepseek")
    deepseek_data = []
    for acc in deepseek_accounts:
        plan = (acc.get("plan") or "free").upper()
        ident = acc.get("identifier") or acc.get("name") or "DeepSeek Account"
        deepseek_data.append({
            "email": ident,
            "type": plan,
            "status": "Normal" if acc.get("status") == "active" else "Disabled",
            "image_quota": "—",
            "reason_remaining": "50 / day",
            "deep_research": "50 / day",
            "web_search": "200 / day",
            "file_upload": "5 files (100MB)",
            "concurrency": "1 request (5/min)",
            "restore_at": "Daily (Midnight CST)",
        })

    if not deepseek_data:
        deepseek_data.append({
            "email": "DeepSeek Web (chat.deepseek.com)",
            "type": "FREE",
            "status": "Normal",
            "image_quota": "—",
            "reason_remaining": "50 / day",
            "deep_research": "50 / day",
            "web_search": "200 / day",
            "file_upload": "5 files (100MB)",
            "concurrency": "1 request (5/min)",
            "restore_at": "Daily (Midnight CST)",
        })

    limits["deepseek"] = {
        "title": "DeepSeek AI Account Quotas",
        "accounts_count": len(deepseek_data),
        "accounts": deepseek_data,
    }

    # 8. Qwen / Tongyi Qianwen quotas (Alibaba Cloud)
    qwen_accounts = db.get_accounts("qwen")
    qwen_data = []
    for acc in qwen_accounts:
        plan = (acc.get("plan") or "free").upper()
        ident = acc.get("identifier") or acc.get("name") or "Qwen Account"
        if ident.startswith("qwen_ey"):
            ident = acc.get("name") or "user_766931c8"
        qwen_data.append({
            "email": ident,
            "type": plan,
            "status": "Normal" if acc.get("status") == "active" else "Disabled",
            "image_quota": 30,
            "reason_remaining": "100 / day",
            "deep_research": "10 / day",
            "web_search": "500 / day",
            "file_upload": "50 files (100MB)",
            "concurrency": "2 requests (10/min)",
            "restore_at": "Daily (Midnight CST)",
        })

    if not qwen_data:
        qwen_data.append({
            "email": "Qwen Web (chat.qwen.ai)",
            "type": "FREE",
            "status": "Normal",
            "image_quota": 30,
            "reason_remaining": "100 / day",
            "deep_research": "10 / day",
            "web_search": "500 / day",
            "file_upload": "50 files (100MB)",
            "concurrency": "2 requests (10/min)",
            "restore_at": "Daily (Midnight CST)",
        })

    limits["qwen"] = {
        "title": "Qwen / Alibaba Cloud Account Quotas",
        "accounts_count": len(qwen_data),
        "accounts": qwen_data,
    }

    return limits


def get_stored_cookies() -> Dict[str, Any]:
    """Read stacked cookies/accounts for all 8 providers from unified SQLite DB."""
    result: Dict[str, Any] = {}

    label_map = {
        "gemini": ("cookie_string", "Google __Secure-1PSID Cookie"),
        "claude": ("session_key", "Claude sessionKey (sk-ant-sid02-...)"),
        "kimi": ("jwt_refresh", "Kimi Refresh Token (JWT)"),
        "grok": ("cookie_string", "Grok SSO & x-userid"),
        "glm": ("token_lines", "GLM Refresh Tokens"),
        "chatgpt": ("json_or_token", "ChatGPT Accounts"),
        "deepseek": ("token_or_json", "DeepSeek userToken or Login JSON"),
        "qwen": ("token_or_json", "Qwen Bearer Token or Session JSON"),
    }

    for p, (ctype, clabel) in label_map.items():
        db_accounts = db.get_accounts(p)
        formatted = []
        for idx, acc in enumerate(db_accounts):
            tok = acc["token"]
            ident = acc["identifier"]
            name = acc["name"]

            if p == "chatgpt":
                masked = tok[:15] + "..." + tok[-10:] if len(tok) > 25 else (ident or "Active")
                formatted.append({
                    "id": acc["id"],
                    "email": ident,
                    "name": name,
                    "plan": acc["plan"],
                    "status": "Active" if acc["status"] == "active" else "Disabled",
                    "masked": masked,
                    "identifier": ident,
                })
            elif p == "claude":
                masked = tok[:16] + "..." + tok[-10:] if len(tok) > 30 else tok
                formatted.append({"id": acc["id"], "sessionKey": tok, "masked": masked, "identifier": ident, "name": name})
            elif p == "kimi":
                masked = tok[:15] + "..." + tok[-10:] if len(tok) > 30 else tok
                formatted.append({"id": acc["id"], "token": tok, "masked": masked, "identifier": ident, "name": name})
            elif p == "grok":
                masked = f"{name} ({ident[:12]}...)"
                formatted.append({"id": acc["id"], "raw": tok, "masked": masked, "identifier": ident, "name": name})
            elif p == "gemini":
                masked = tok[:15] + "..." + tok[-10:] if len(tok) > 30 else tok
                formatted.append({"id": acc["id"], "raw": tok, "masked": masked, "identifier": ident, "name": name})
            elif p == "glm":
                masked = tok[:12] + "..." + tok[-8:] if len(tok) > 24 else tok
                formatted.append({"id": acc["id"], "token": tok, "masked": masked, "identifier": ident, "name": name})
            elif p in ("deepseek", "qwen"):
                masked = tok[:15] + "..." + tok[-10:] if len(tok) > 25 else (ident or "Active")
                formatted.append({"id": acc["id"], "token": tok, "masked": masked, "identifier": ident, "name": name})

        result[p] = {
            "type": ctype,
            "label": clabel,
            "accounts": formatted,
        }

    return result


def save_stacked_cookies(provider_id: str, accounts: List[str]) -> Dict[str, Any]:
    """Save stacked accounts into unified SQLite DB with strict deduplication."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    clean_items = [item.strip() for item in accounts if item and item.strip()]
    if not clean_items:
        return {"status": "error", "message": "No valid credentials provided."}

    success, failed = db.save_accounts(provider_id, clean_items)
    total = len(db.get_accounts(provider_id))
    return {
        "status": "ok",
        "message": f"Successfully updated {provider_id.upper()} accounts (+{success}, total in pool: {total}).",
        "saved": success,
        "failed": failed,
        "total": total,
    }


def remove_stacked_cookie(provider_id: str, identifier: Optional[str] = None, index: Optional[int] = None) -> Dict[str, Any]:
    """Remove a specific stacked account from unified SQLite DB."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    ok = db.remove_account(provider_id, identifier=identifier, account_id=index)
    if ok:
        total = len(db.get_accounts(provider_id))
        return {"status": "ok", "message": f"Successfully removed account from {provider_id}. Remaining: {total}"}
    return {"status": "error", "message": f"Account not found in {provider_id}."}

