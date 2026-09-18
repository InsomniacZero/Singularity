#!/usr/bin/env python3
"""
Singularity Provider Engine
Manages status, lifecycle, limits, models, and cookie storage for all 6 providers:
ChatGPT (8000), Claude (8080), Gemini (8084), GLM (8085), Kimi (8086), Grok (8087).
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

ROOT_DIR = Path(__file__).resolve().parent.parent
PYTHON_VENV = ROOT_DIR / "kimi2api" / ".venv" / "bin" / "python3"
SYSTEM_PYTHON = "python3"

PROVIDERS_CONFIG = {
    "gemini": {
        "id": "gemini",
        "name": "Gemini",
        "port": 8084,
        "badge": "Google DeepMind",
        "color": "#4285F4",
        "start_script": "start_gemini.sh",
        "stop_script": "stop_gemini.sh",
        "health_path": "/v1/models",
        "cookie_file": ROOT_DIR / "cookie.txt",
        "cookie_type": "cookie_string",
        "cookie_label": "Google __Secure-1PSID Cookie",
        "cookie_placeholder": "Paste raw cookie string containing __Secure-1PSID=... and __Secure-1PSIDTS=...",
        "auth_header": None,
    },
    "chatgpt": {
        "id": "chatgpt",
        "name": "ChatGPT",
        "port": 8000,
        "badge": "OpenAI Pool",
        "color": "#10A37F",
        "start_script": "start_chatgpt2api.sh",
        "stop_script": "stop_chatgpt2api.sh",
        "health_path": "/healthz",
        "cookie_file": ROOT_DIR / "chatgpt2api" / "data" / "accounts.json",
        "cookie_type": "json_or_token",
        "cookie_label": "Next-Auth Session JSON or Access Token",
        "cookie_placeholder": "Paste JSON session dump or access token (one per account card)...",
        "auth_header": "Bearer chatgpt2api",
    },
    "claude": {
        "id": "claude",
        "name": "Claude",
        "port": 8080,
        "badge": "Anthropic",
        "color": "#D97757",
        "start_script": "start_claude2api.sh",
        "stop_script": "stop_claude2api.sh",
        "health_path": "/v1/models",
        "cookie_file": ROOT_DIR / "claude2api" / "config.yaml",
        "cookie_type": "session_key",
        "cookie_label": "Claude sessionKey (sk-ant-sid02-...)",
        "cookie_placeholder": "sk-ant-sid02-...",
        "auth_header": "Bearer sk-claude-local",
    },
    "kimi": {
        "id": "kimi",
        "name": "Kimi",
        "port": 8086,
        "badge": "Moonshot AI",
        "color": "#00C389",
        "start_script": "start_kimi2api.sh",
        "stop_script": "stop_kimi2api.sh",
        "health_path": "/healthz",
        "cookie_file": ROOT_DIR / "kimi2api" / ".env",
        "cookie_type": "jwt_refresh",
        "cookie_label": "Kimi Refresh Token (JWT)",
        "cookie_placeholder": "eyJhbGciOiJIUzUxMiIsInR5cCI6IkpXVCJ9...",
        "auth_header": "Bearer sk-kimi-local",
    },
    "glm": {
        "id": "glm",
        "name": "GLM",
        "port": 8085,
        "badge": "Zhipu AI",
        "color": "#4A72FF",
        "start_script": "start_glm2api.sh",
        "stop_script": "stop_glm2api.sh",
        "health_path": "/v1/models",
        "cookie_file": ROOT_DIR / "glm2api" / "token.txt",
        "cookie_type": "token_lines",
        "cookie_label": "GLM Refresh Token",
        "cookie_placeholder": "Paste Zhipu refresh token (one account per line or card)...",
        "auth_header": "Bearer sk-glm-local",
    },
    "grok": {
        "id": "grok",
        "name": "Grok",
        "port": 8087,
        "badge": "xAI",
        "color": "#E5E5E5",
        "start_script": "start_grok2api.sh",
        "stop_script": "stop_grok2api.sh",
        "health_path": "/healthz",
        "cookie_file": ROOT_DIR / "grok2api" / "cookies.txt",
        "cookie_type": "cookie_string",
        "cookie_label": "Grok SSO Cookie & UserID",
        "cookie_placeholder": "sso=...; sso-rw=...; x-userid=...",
        "auth_header": None,
    },
}

# Dynamic Comprehensive Catalog (206 models across 6 providers)
MODELS_CATALOG = [   {   'capabilities': ['chat', 'vision', 'code', 'streaming'],
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

    # 1. Check ChatGPT accounts from accounts.json
    chatgpt_file = PROVIDERS_CONFIG["chatgpt"]["cookie_file"]
    if chatgpt_file.exists():
        try:
            with open(chatgpt_file, "r", encoding="utf-8") as f:
                accounts = json.load(f)
            if isinstance(accounts, list):
                for acc in accounts:
                    acc_type = str(acc.get("type") or "").strip().lower()
                    plan_type = ""
                    auth_meta = acc.get("https://api.openai.com/auth") or {}
                    if isinstance(auth_meta, dict):
                        plan_type = str(auth_meta.get("chatgpt_plan_type") or "").strip().lower()
                    if acc_type in ["plus", "team", "pro", "enterprise"] or plan_type in ["plus", "team", "pro", "enterprise"]:
                        tiers["chatgpt_plus"] = True
                        break
        except Exception:
            pass

    # 2. Check Claude cookies from config.yaml
    claude_file = PROVIDERS_CONFIG["claude"]["cookie_file"]
    if claude_file.exists():
        try:
            import yaml
            with open(claude_file, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            if isinstance(cfg, dict):
                for s in cfg.get("sessions", []):
                    if isinstance(s, dict):
                        plan = str(s.get("plan") or s.get("tier") or s.get("type") or "").strip().lower()
                        if plan in ["pro", "max", "team", "enterprise"]:
                            tiers["claude_pro"] = True
                            break
                        notes = str(s.get("notes") or s.get("name") or "").strip().lower()
                        if any(k in notes for k in ["pro", "max", "team", "enterprise"]):
                            tiers["claude_pro"] = True
                            break
            if not tiers["claude_pro"]:
                raw_text = claude_file.read_text(encoding="utf-8")
                if re.search(r'(?i)(?:plan|tier|account_type|subscription)\s*:\s*[\'\"]?(?:pro|max|team|enterprise)', raw_text):
                    tiers["claude_pro"] = True
        except Exception:
            pass

    # 3. Check Grok cookies from cookies.txt
    grok_file = PROVIDERS_CONFIG["grok"]["cookie_file"]
    if grok_file.exists():
        try:
            content = grok_file.read_text(encoding="utf-8").lower()
            if "supergrok" in content or "premium" in content:
                tiers["grok_premium"] = True
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
            if "opus" in mid or "fable" in mid or "pro" in mid or "max" in mid:
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
    """Find PID listening on a given port."""
    try:
        res = subprocess.run(["lsof", f"-ti:{port}"], capture_output=True, text=True, timeout=2)
        pids = [int(p.strip()) for p in res.stdout.strip().splitlines() if p.strip().isdigit()]
        return pids[0] if pids else None
    except Exception:
        return None


async def ping_service(port: int, health_path: str, auth_header: Optional[str] = None) -> tuple[bool, float]:
    """Check if service is responding on HTTP and return latency in ms."""
    url = f"http://127.0.0.1:{port}{health_path}"
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
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
    for pid, meta in PROVIDERS_CONFIG.items():
        port = meta["port"]
        process_pid = get_pid_for_port(port)
        alive, latency = await ping_service(port, meta["health_path"], meta["auth_header"])

        results.append({
            "id": meta["id"],
            "name": meta["name"],
            "badge": meta["badge"],
            "port": port,
            "color": meta["color"],
            "pid": process_pid,
            "running": bool(process_pid) or alive,
            "latency_ms": latency if alive else None,
            "health_path": meta["health_path"],
            "cookie_label": meta["cookie_label"],
        })
    return results


def start_provider(provider_id: str) -> Dict[str, Any]:
    """Execute start script for a provider."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    meta = PROVIDERS_CONFIG[provider_id]
    port = meta["port"]
    current_pid = get_pid_for_port(port)
    if current_pid:
        return {"status": "ok", "message": f"{meta['name']} is already running (PID: {current_pid})", "pid": current_pid}

    script_path = ROOT_DIR / meta["start_script"]
    if not script_path.exists():
        return {"status": "error", "message": f"{meta['name']} runner script '{meta['start_script']}' not found in {ROOT_DIR.name}. Start provider on port {port} or configure proxy."}

    try:
        # Use subprocess with nohup / detached process
        subprocess.Popen(
            [str(script_path)],
            cwd=str(ROOT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setpgrp,
        )
        time.sleep(1.2)
        new_pid = get_pid_for_port(port)
        return {
            "status": "ok",
            "message": f"Started {meta['name']} on port {port}",
            "pid": new_pid,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def stop_provider(provider_id: str) -> Dict[str, Any]:
    """Stop a provider service."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    meta = PROVIDERS_CONFIG[provider_id]
    port = meta["port"]
    pid = get_pid_for_port(port)
    if not pid:
        # Also run stop script if any (e.g. systemctl for chatgpt)
        script_path = ROOT_DIR / meta["stop_script"]
        if script_path.exists():
            subprocess.run([str(script_path)], cwd=str(ROOT_DIR), capture_output=True)
        return {"status": "ok", "message": f"{meta['name']} is not running"}

    try:
        # Call stop script first
        script_path = ROOT_DIR / meta["stop_script"]
        if script_path.exists():
            subprocess.run([str(script_path)], cwd=str(ROOT_DIR), capture_output=True, timeout=5)

        # Force kill if still on port
        time.sleep(0.5)
        rem_pid = get_pid_for_port(port)
        if rem_pid:
            os.kill(rem_pid, signal.SIGKILL)

        return {"status": "ok", "message": f"Stopped {meta['name']} (PID: {pid})"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def start_all_services() -> Dict[str, Any]:
    """Start all 6 provider daemons."""
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


async def get_all_limits() -> Dict[str, Any]:
    """Collect live limits and quotas across all 6 providers."""
    limits: Dict[str, Any] = {}

    # 1. ChatGPT limits via c2a CLI (with accounts.json direct fallback)
    chatgpt_data = []
    try:
        cli_path = ROOT_DIR / "chatgpt2api" / "c2a"
        if cli_path.exists():
            proc = await asyncio.create_subprocess_exec(
                str(cli_path), "status", "--json",
                cwd=str(ROOT_DIR / "chatgpt2api"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                raw_json = json.loads(stdout.decode("utf-8"))
                for acc in raw_json.get("accounts", []):
                    features = {f.get("feature_name"): f.get("remaining") for f in acc.get("limits_progress", [])}
                    chatgpt_data.append({
                        "email": acc.get("email"),
                        "type": acc.get("type", "free").upper(),
                        "status": acc.get("status", "Normal"),
                        "image_quota": acc.get("quota", 0),
                        "reason_remaining": features.get("reason", "N/A"),
                        "deep_research": features.get("deep_research", "N/A"),
                        "file_upload": features.get("file_upload", "N/A"),
                        "restore_at": acc.get("restore_at"),
                    })
    except Exception:
        chatgpt_data = []

    # Direct fallback: if c2a wasn't available (e.g. running on Termux / standalone), read accounts.json directly
    if not chatgpt_data:
        accounts_file = PROVIDERS_CONFIG["chatgpt"]["cookie_file"]
        if accounts_file.exists():
            try:
                loaded = json.loads(accounts_file.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    for acc in loaded:
                        limits_progress = acc.get("limits_progress", [])
                        features = {f.get("feature_name"): f.get("remaining") for f in limits_progress} if isinstance(limits_progress, list) else {}
                        chatgpt_data.append({
                            "email": acc.get("email") or acc.get("name") or "Account",
                            "type": (acc.get("type") or "free").upper(),
                            "status": acc.get("status", "Active"),
                            "image_quota": acc.get("quota", "—"),
                            "reason_remaining": features.get("reason", "—"),
                            "deep_research": features.get("deep_research", "—"),
                            "file_upload": features.get("file_upload", "—"),
                            "restore_at": acc.get("restore_at", "Active"),
                        })
            except Exception:
                pass

    limits["chatgpt"] = {
        "title": "ChatGPT Account Pool",
        "accounts_count": len(chatgpt_data),
        "accounts": chatgpt_data,
    }

    # 2. Grok quotas from port 8087
    grok_limits = {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("http://127.0.0.1:8087/api/quotas")
            if resp.status_code == 200:
                grok_limits = resp.json()
    except Exception:
        pass

    cookie_path = ROOT_DIR / "grok2api" / "cookies.txt"
    has_grok_cookie = cookie_path.exists() and bool(cookie_path.read_text(encoding="utf-8").strip())
    if not grok_limits:
        grok_limits = {
            "account_uid": "Connected" if has_grok_cookie else "No Account Integrated",
            "rate_limits": {},
            "imagine_quota": {
                "imagePro": {"remainingQueries": 0},
                "video720p": {"remainingQueries": 0}
            }
        }
    limits["grok"] = {
        "title": "Grok / xAI Limits",
        "data": grok_limits,
    }

    # 3. Kimi token and membership info
    kimi_limits = {"status": "none", "membership_level": "No Token Configured", "daily_research_quota": "—", "context_window": "—", "expires_at": "Not Configured"}
    try:
        kimi_env = ROOT_DIR / "kimi2api" / ".env"
        if kimi_env.exists():
            content = kimi_env.read_text(encoding="utf-8")
            m = re.search(r"KIMI_TOKEN=([^\s]+)", content)
            if m and m.group(1).strip():
                jwt_str = m.group(1).strip()
                parts = jwt_str.split(".")
                if len(parts) >= 2:
                    import base64
                    payload_b64 = parts[1] + "=="
                    payload_str = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
                    payload = json.loads(payload_str)
                    exp = payload.get("exp", 0)
                    exp_date = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(exp)) if exp else "Unknown"
                    membership = payload.get("membership", {}).get("level", 10)
                    kimi_limits = {
                        "membership_level": f"Level {membership}",
                        "expires_at": exp_date,
                        "daily_research_quota": "50 queries / day",
                        "context_window": "200k / 500k tokens",
                        "status": "active",
                    }
    except Exception as e:
        kimi_limits = {"error": str(e), "membership_level": "Error Reading Token", "daily_research_quota": "—", "context_window": "—", "expires_at": "Error"}
    limits["kimi"] = {
        "title": "Kimi / Moonshot AI Limits",
        "data": kimi_limits,
    }

    # 4. Claude sessions limit info
    claude_limits = {"active_sessions": 0, "rolling_window": "None", "free_tier_status": "No Session Connected", "pro_tier_models": "Locked"}
    try:
        yaml_path = ROOT_DIR / "claude2api" / "config.yaml"
        if yaml_path.exists():
            content = yaml_path.read_text(encoding="utf-8")
            keys = re.findall(r'sessionKey:\s*"([^"]+)"', content)
            session_count = len(keys)
            claude_limits = {
                "active_sessions": session_count,
                "rolling_window": "5-hour dynamic context window" if session_count > 0 else "None",
                "free_tier_status": "Active (Standard Claude 5 Sonnet & Haiku)" if session_count > 0 else "No Session Connected",
                "pro_tier_models": "Locked (Opus 5 requires Pro cookie)",
            }
    except Exception as e:
        claude_limits = {"error": str(e), "active_sessions": 0, "rolling_window": "Error", "free_tier_status": "Error", "pro_tier_models": "Locked"}
    limits["claude"] = {
        "title": "Claude / Anthropic Limits",
        "data": claude_limits,
    }

    # 5. Gemini limits info
    gemini_limits = {
        "rpm_limit": "15 Requests / Minute (Free Tier)",
        "rpd_limit": "1,500 Requests / Day",
        "context_window": "1,000,000 Tokens (1M)",
        "portrait_pipeline": "Portrait Conditioning & Auto-Cropping Enabled",
    }
    limits["gemini"] = {
        "title": "Gemini Limits",
        "data": gemini_limits,
    }

    # 6. GLM limits info
    glm_limits = {
        "concurrency_slots": "50 Concurrent Requests",
        "guest_mode": "Auto-Guest Token Rotation Enabled",
        "refresh_frequency": "Dynamic on token expiration",
    }
    limits["glm"] = {
        "title": "GLM Zhipu AI Limits",
        "data": glm_limits,
    }

    return limits


def get_stored_cookies() -> Dict[str, Any]:
    """Read stacked cookies/accounts for all 6 providers with index and identifiers."""
    result: Dict[str, Any] = {}

    # Gemini
    gemini_file = PROVIDERS_CONFIG["gemini"]["cookie_file"]
    gemini_cookies = []
    if gemini_file.exists():
        lines = [l.strip() for l in gemini_file.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        for idx, line in enumerate(lines):
            masked = line[:15] + "..." + line[-10:] if len(line) > 30 else line
            gemini_cookies.append({"id": idx, "raw": line, "masked": masked, "identifier": line})
    result["gemini"] = {
        "type": "cookie_string",
        "label": "Google __Secure-1PSID Cookie",
        "accounts": gemini_cookies,
    }

    # Claude
    claude_file = PROVIDERS_CONFIG["claude"]["cookie_file"]
    claude_accounts = []
    if claude_file.exists():
        content = claude_file.read_text(encoding="utf-8")
        keys = re.findall(r'sessionKey:\s*"([^"]+)"', content)
        for idx, k in enumerate(keys):
            masked = k[:16] + "..." + k[-10:] if len(k) > 30 else k
            claude_accounts.append({"id": idx, "sessionKey": k, "masked": masked, "identifier": k})
    result["claude"] = {
        "type": "session_key",
        "label": "Claude sessionKey (sk-ant-sid02-...)",
        "accounts": claude_accounts,
    }

    # Kimi
    kimi_file = PROVIDERS_CONFIG["kimi"]["cookie_file"]
    kimi_accounts = []
    if kimi_file.exists():
        content = kimi_file.read_text(encoding="utf-8")
        tokens = re.findall(r'KIMI_TOKEN=([^\s]+)', content)
        for idx, t in enumerate(tokens):
            if t.strip():
                masked = t[:15] + "..." + t[-10:] if len(t) > 30 else t
                kimi_accounts.append({"id": idx, "token": t, "masked": masked, "identifier": t})
    result["kimi"] = {
        "type": "jwt_refresh",
        "label": "Kimi Refresh Token (JWT)",
        "accounts": kimi_accounts,
    }

    # Grok
    grok_file = PROVIDERS_CONFIG["grok"]["cookie_file"]
    grok_accounts = []
    if grok_file.exists():
        lines = [l.strip() for l in grok_file.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        for idx, line in enumerate(lines):
            uid_m = re.search(r"x-userid=([^;]+)", line)
            uid = uid_m.group(1).strip() if uid_m else "default"
            masked = f"x-userid={uid[:8]}...; sso={line[:12]}..."
            grok_accounts.append({"id": idx, "raw": line, "masked": masked, "identifier": uid if uid != "default" else line})
    result["grok"] = {
        "type": "cookie_string",
        "label": "Grok SSO & x-userid",
        "accounts": grok_accounts,
    }

    # GLM
    glm_file = PROVIDERS_CONFIG["glm"]["cookie_file"]
    glm_tokens = []
    if glm_file.exists():
        lines = [l.strip() for l in glm_file.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        for idx, line in enumerate(lines):
            masked = line[:12] + "..." + line[-8:] if len(line) > 24 else line
            glm_tokens.append({"id": idx, "token": line, "masked": masked, "identifier": line})
    result["glm"] = {
        "type": "token_lines",
        "label": "GLM Refresh Tokens",
        "accounts": glm_tokens,
    }

    # ChatGPT
    chatgpt_file = PROVIDERS_CONFIG["chatgpt"]["cookie_file"]
    chatgpt_accounts = []
    if chatgpt_file.exists():
        try:
            acc_data = json.loads(chatgpt_file.read_text(encoding="utf-8"))
            if isinstance(acc_data, list):
                for idx, acc in enumerate(acc_data):
                    email = acc.get("email")
                    name = acc.get("name") or (email.split("@")[0] if email else f"Account #{idx + 1}")
                    token = acc.get("access_token") or ""
                    masked = token[:15] + "..." + token[-10:] if len(token) > 25 else (email or "Active")
                    chatgpt_accounts.append({
                        "id": idx,
                        "email": email or name,
                        "name": name,
                        "plan": acc.get("type") or "free",
                        "status": acc.get("status") or "Active",
                        "masked": masked,
                        "identifier": email or token or str(idx),
                    })
        except Exception:
            pass
    result["chatgpt"] = {
        "type": "json_or_token",
        "label": "ChatGPT Accounts",
        "accounts": chatgpt_accounts,
    }

    return result


def parse_chatgpt_account_input(raw: str) -> Optional[Dict[str, Any]]:
    """Parse Next-Auth session JSON dumps, access tokens, or raw JWT dumps."""
    raw = raw.strip()
    if not raw:
        return None

    # 1. Try parsing JSON
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            user = data.get("user", {}) if isinstance(data.get("user"), dict) else {}
            email = user.get("email") or data.get("email")
            name = user.get("name") or data.get("name")
            access_token = data.get("accessToken") or data.get("access_token")
            session_token = data.get("sessionToken") or data.get("session_token")
            plan = data.get("account", {}).get("planType") or data.get("plan_type") or data.get("type") or "free"

            if not access_token and "token" in data:
                access_token = data["token"]

            if not email and access_token and access_token.startswith("eyJ"):
                try:
                    import base64
                    payload_b64 = access_token.split(".")[1]
                    payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
                    email = payload.get("https://api.openai.com/profile", {}).get("email") or payload.get("email")
                    if not name:
                        name = payload.get("https://api.openai.com/profile", {}).get("name")
                except Exception:
                    pass

            if access_token or session_token or email:
                if not email:
                    email = f"user_{access_token[:8]}" if access_token else "chatgpt_user"
                if not name:
                    name = email.split("@")[0] if "@" in email else "ChatGPT User"
                return {
                    "email": email,
                    "name": name,
                    "type": plan,
                    "status": "Active",
                    "access_token": access_token or "",
                    "session_token": session_token or "",
                }
    except Exception:
        pass

    # 2. Raw JWT or session token string
    if raw.startswith("eyJ") or len(raw) > 40:
        email = "chatgpt_user"
        name = "ChatGPT User"
        try:
            import base64
            payload_b64 = raw.split(".")[1]
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
            email = payload.get("https://api.openai.com/profile", {}).get("email") or payload.get("email") or email
            name = payload.get("https://api.openai.com/profile", {}).get("name") or (email.split("@")[0] if "@" in email else name)
        except Exception:
            pass
        return {
            "email": email,
            "name": name,
            "type": "free",
            "status": "Active",
            "access_token": raw,
            "session_token": "",
        }

    return None


def save_stacked_cookies(provider_id: str, accounts: List[str]) -> Dict[str, Any]:
    """Save stacked accounts with strict deduplication and directory creation."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    clean_items = [item.strip() for item in accounts if item and item.strip()]

    try:
        if provider_id == "claude":
            yaml_path = PROVIDERS_CONFIG["claude"]["cookie_file"]
            yaml_path.parent.mkdir(parents=True, exist_ok=True)
            existing_keys = []
            if yaml_path.exists():
                existing_keys = re.findall(r'sessionKey:\s*"([^"]+)"', yaml_path.read_text(encoding="utf-8"))
            all_keys = existing_keys + clean_items
            unique_keys = list(dict.fromkeys(k.strip() for k in all_keys if k.strip()))

            sessions_lines = ["# Claude2API Configuration", "sessions:"]
            for key in unique_keys:
                sessions_lines.append(f'  - sessionKey: "{key}"')
                sessions_lines.append('    orgID: ""')
            sessions_lines.append("")
            sessions_lines.append('address: "0.0.0.0:8080"')
            sessions_lines.append('apiKey: "sk-claude-local"')
            sessions_lines.append('chatDelete: true')
            sessions_lines.append('maxChatHistoryLength: 10000')
            sessions_lines.append('retryCount: 1')
            yaml_path.write_text("\n".join(sessions_lines), encoding="utf-8")

        elif provider_id == "grok":
            cookie_path = PROVIDERS_CONFIG["grok"]["cookie_file"]
            cookie_path.parent.mkdir(parents=True, exist_ok=True)
            existing_lines = []
            if cookie_path.exists():
                existing_lines = [l.strip() for l in cookie_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            all_lines = existing_lines + clean_items
            # Deduplicate by x-userid or entire line
            unique_lines = []
            seen_uids = set()
            for line in all_lines:
                uid_m = re.search(r"x-userid=([^;]+)", line)
                uid = uid_m.group(1).strip() if uid_m else None
                if uid:
                    if uid in seen_uids:
                        continue
                    seen_uids.add(uid)
                elif line in unique_lines:
                    continue
                unique_lines.append(line)
            cookie_path.write_text("\n".join(unique_lines) + ("\n" if unique_lines else ""), encoding="utf-8")

        elif provider_id == "gemini":
            cookie_path = PROVIDERS_CONFIG["gemini"]["cookie_file"]
            cookie_path.parent.mkdir(parents=True, exist_ok=True)
            existing_lines = []
            if cookie_path.exists():
                existing_lines = [l.strip() for l in cookie_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            all_lines = existing_lines + clean_items
            unique_lines = []
            seen_sids = set()
            for line in all_lines:
                sid_m = re.search(r"__Secure-1PSID=([^;]+)", line)
                sid = sid_m.group(1).strip() if sid_m else None
                if sid:
                    if sid in seen_sids:
                        continue
                    seen_sids.add(sid)
                elif line in unique_lines:
                    continue
                unique_lines.append(line)
            cookie_path.write_text("\n".join(unique_lines) + ("\n" if unique_lines else ""), encoding="utf-8")

        elif provider_id == "kimi":
            env_path = PROVIDERS_CONFIG["kimi"]["cookie_file"]
            env_path.parent.mkdir(parents=True, exist_ok=True)
            if clean_items:
                primary_token = clean_items[0]
                content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
                if "KIMI_TOKEN=" in content:
                    content = re.sub(r"KIMI_TOKEN=[^\n]+", f"KIMI_TOKEN={primary_token}", content)
                else:
                    content += f"\nKIMI_TOKEN={primary_token}\n"
                env_path.write_text(content, encoding="utf-8")

        elif provider_id == "glm":
            token_path = PROVIDERS_CONFIG["glm"]["cookie_file"]
            token_path.parent.mkdir(parents=True, exist_ok=True)
            existing_lines = []
            if token_path.exists():
                existing_lines = [l.strip() for l in token_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            all_lines = existing_lines + clean_items
            unique_lines = list(dict.fromkeys(l for l in all_lines if l))
            token_path.write_text("\n".join(unique_lines) + ("\n" if unique_lines else ""), encoding="utf-8")

        elif provider_id == "chatgpt":
            chatgpt_data_dir = PROVIDERS_CONFIG["chatgpt"]["cookie_file"].parent
            chatgpt_data_dir.mkdir(parents=True, exist_ok=True)
            accounts_file = PROVIDERS_CONFIG["chatgpt"]["cookie_file"]

            c2a_path = ROOT_DIR / "chatgpt2api" / "c2a"
            can_use_c2a = c2a_path.exists() and os.access(c2a_path, os.X_OK)

            for item in clean_items:
                imported = False
                if can_use_c2a and (item.startswith("{") or item.startswith("[")):
                    try:
                        tmp_file = chatgpt_data_dir / "_import_temp.json"
                        tmp_file.write_text(item, encoding="utf-8")
                        sub_res = subprocess.run([str(c2a_path), "import", str(tmp_file)], cwd=str(ROOT_DIR / "chatgpt2api"), capture_output=True)
                        if tmp_file.exists():
                            tmp_file.unlink()
                        if sub_res.returncode == 0:
                            imported = True
                    except Exception:
                        imported = False

                if not imported:
                    # Direct json/token parsing fallback (works offline and on Termux)
                    existing_accounts = []
                    if accounts_file.exists():
                        try:
                            loaded = json.loads(accounts_file.read_text(encoding="utf-8"))
                            if isinstance(loaded, list):
                                existing_accounts = loaded
                        except Exception:
                            existing_accounts = []

                    parsed = parse_chatgpt_account_input(item)
                    if parsed:
                        p_email = (parsed.get("email") or "").strip().lower()
                        p_tok = (parsed.get("access_token") or "").strip()
                        replaced = False
                        for i, acc in enumerate(existing_accounts):
                            a_email = (acc.get("email") or "").strip().lower()
                            a_tok = (acc.get("access_token") or "").strip()
                            if (p_email and not p_email.startswith("user_") and a_email == p_email) or \
                               (p_tok and a_tok == p_tok):
                                existing_accounts[i].update(parsed)
                                replaced = True
                                break
                        if not replaced:
                            existing_accounts.append(parsed)

                        accounts_file.write_text(json.dumps(existing_accounts, indent=2, ensure_ascii=False), encoding="utf-8")

            # Final reload and strict global deduplication pass across all accounts in accounts_file
            if accounts_file.exists():
                try:
                    loaded = json.loads(accounts_file.read_text(encoding="utf-8"))
                    if isinstance(loaded, list):
                        unique_accounts = []
                        seen_emails = set()
                        seen_tokens = set()
                        for acc in loaded:
                            email = (acc.get("email") or "").strip().lower()
                            token = (acc.get("access_token") or "").strip()
                            if email and not email.startswith("user_") and email != "chatgpt_user":
                                if email in seen_emails:
                                    continue
                                seen_emails.add(email)
                            if token:
                                if token in seen_tokens:
                                    continue
                                seen_tokens.add(token)
                            unique_accounts.append(acc)
                        accounts_file.write_text(json.dumps(unique_accounts, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass

        return {"status": "ok", "message": f"Successfully updated accounts for {provider_id}."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def remove_stacked_cookie(provider_id: str, identifier: Optional[str] = None, index: Optional[int] = None) -> Dict[str, Any]:
    """Remove a specific stacked account from a provider's configuration."""
    if provider_id not in PROVIDERS_CONFIG:
        return {"status": "error", "message": f"Unknown provider: {provider_id}"}

    try:
        if provider_id == "chatgpt":
            accounts_file = PROVIDERS_CONFIG["chatgpt"]["cookie_file"]
            if not accounts_file.exists():
                return {"status": "error", "message": "No ChatGPT accounts file found."}

            loaded = json.loads(accounts_file.read_text(encoding="utf-8"))
            if not isinstance(loaded, list):
                return {"status": "error", "message": "Invalid accounts format."}

            initial_len = len(loaded)
            new_accounts = []

            if index is not None and 0 <= index < len(loaded):
                new_accounts = [acc for i, acc in enumerate(loaded) if i != index]
            elif identifier:
                ident = identifier.strip().lower()
                for acc in loaded:
                    email = (acc.get("email") or "").strip().lower()
                    name = (acc.get("name") or "").strip().lower()
                    token = (acc.get("access_token") or "").strip()
                    if email == ident or name == ident or token == identifier.strip() or token.startswith(identifier.strip()):
                        continue
                    new_accounts.append(acc)
            else:
                return {"status": "error", "message": "Neither index nor identifier provided."}

            if len(new_accounts) == initial_len:
                return {"status": "error", "message": "Account not found to remove."}

            accounts_file.write_text(json.dumps(new_accounts, indent=2, ensure_ascii=False), encoding="utf-8")
            return {"status": "ok", "message": "Successfully removed ChatGPT account."}

        elif provider_id == "claude":
            yaml_path = PROVIDERS_CONFIG["claude"]["cookie_file"]
            if not yaml_path.exists():
                return {"status": "error", "message": "Claude config file not found."}
            content = yaml_path.read_text(encoding="utf-8")
            keys = re.findall(r'sessionKey:\s*"([^"]+)"', content)
            initial_len = len(keys)

            if index is not None and 0 <= index < len(keys):
                keys = [k for i, k in enumerate(keys) if i != index]
            elif identifier:
                keys = [k for k in keys if k != identifier.strip()]

            if len(keys) == initial_len:
                return {"status": "error", "message": "Session key not found to remove."}

            sessions_lines = ["# Claude2API Configuration", "sessions:"]
            for key in keys:
                sessions_lines.append(f'  - sessionKey: "{key}"')
                sessions_lines.append('    orgID: ""')
            sessions_lines.append("")
            sessions_lines.append('address: "0.0.0.0:8080"')
            sessions_lines.append('apiKey: "sk-claude-local"')
            sessions_lines.append('chatDelete: true')
            sessions_lines.append('maxChatHistoryLength: 10000')
            sessions_lines.append('retryCount: 1')
            yaml_path.write_text("\n".join(sessions_lines), encoding="utf-8")
            return {"status": "ok", "message": "Successfully removed Claude session."}

        elif provider_id == "grok":
            cookie_path = PROVIDERS_CONFIG["grok"]["cookie_file"]
            if not cookie_path.exists():
                return {"status": "error", "message": "Grok cookies file not found."}
            lines = [l.strip() for l in cookie_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            initial_len = len(lines)

            if index is not None and 0 <= index < len(lines):
                lines = [l for i, l in enumerate(lines) if i != index]
            elif identifier:
                lines = [l for l in lines if identifier.strip() not in l]

            if len(lines) == initial_len:
                return {"status": "error", "message": "Grok cookie not found to remove."}

            cookie_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            return {"status": "ok", "message": "Successfully removed Grok cookie."}

        elif provider_id == "gemini":
            cookie_path = PROVIDERS_CONFIG["gemini"]["cookie_file"]
            if not cookie_path.exists():
                return {"status": "error", "message": "Gemini cookies file not found."}
            lines = [l.strip() for l in cookie_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            initial_len = len(lines)

            if index is not None and 0 <= index < len(lines):
                lines = [l for i, l in enumerate(lines) if i != index]
            elif identifier:
                lines = [l for l in lines if identifier.strip() not in l]

            if len(lines) == initial_len:
                return {"status": "error", "message": "Gemini cookie not found to remove."}

            cookie_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            return {"status": "ok", "message": "Successfully removed Gemini cookie."}

        elif provider_id == "glm":
            token_path = PROVIDERS_CONFIG["glm"]["cookie_file"]
            if not token_path.exists():
                return {"status": "error", "message": "GLM tokens file not found."}
            lines = [l.strip() for l in token_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            initial_len = len(lines)

            if index is not None and 0 <= index < len(lines):
                lines = [l for i, l in enumerate(lines) if i != index]
            elif identifier:
                lines = [l for l in lines if l != identifier.strip()]

            if len(lines) == initial_len:
                return {"status": "error", "message": "GLM token not found to remove."}

            token_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            return {"status": "ok", "message": "Successfully removed GLM token."}

        elif provider_id == "kimi":
            env_path = PROVIDERS_CONFIG["kimi"]["cookie_file"]
            if env_path.exists():
                content = env_path.read_text(encoding="utf-8")
                content = re.sub(r"KIMI_TOKEN=[^\n]+", "KIMI_TOKEN=", content)
                env_path.write_text(content, encoding="utf-8")
            return {"status": "ok", "message": "Successfully cleared Kimi token."}

    except Exception as e:
        return {"status": "error", "message": str(e)}

