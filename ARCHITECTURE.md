# 🌌 Singularity Architecture Guide
> **The definitive technical manual and structural blueprint for Singularity: Universal Web2API AI Gateway, Multi-Account Stacker, and Interactive Generative UI Hub.**

---

## 📑 Table of Contents
1. [System Overview & Mission](#1-system-overview--mission)
2. [High-Level Architecture & Topology](#2-high-level-architecture--topology)
3. [Core Non-Negotiable Invariants](#3-core-non-negotiable-invariants)
4. [Repository Directory & File Anatomy](#4-repository-directory--file-anatomy)
5. [End-to-End Request & Data Flow Pipeline](#5-end-to-end-request--data-flow-pipeline)
6. [Provider Engines Deep-Dive (`singularity/engines/`)](#6-provider-engines-deep-dive-singularityengines)
7. [Credential Vault & Multi-Account Stacking (`singularity/db.py`)](#7-credential-vault--multi-account-stacking-singularitydbpy)
8. [Universal Artifacts & GenUI Sandboxing Engine](#8-universal-artifacts--genui-sandboxing-engine)
9. [Personas & Dynamic Identity Rewriter (`singularity/personas.py`)](#9-personas--dynamic-identity-rewriter-singularitypersonaspy)
10. [Cloud Tunneling & Native Mobile Access (`singularity/tunnel.py`)](#10-cloud-tunneling--native-mobile-access-singularitytunnelpy)
11. [Universal Command Line Interface (`./singular` / `./c2a`)](#11-universal-command-line-interface-singular--c2a)
12. [Frontend Architecture & Design System (`singularity/static/`)](#12-frontend-architecture--design-system-singularitystatic)
13. [Tavern Studio Integration (`TAVERN/`)](#13-tavern-studio-integration-tavern)
14. [Agent Protocols: Adding Providers & Extending Models](#14-agent-protocols-adding-providers--extending-models)

---

## 1. System Overview & Mission

**Singularity** is a high-performance, self-contained AI reverse-proxy gateway and orchestration platform. It transforms standard browser sessions and authenticated web endpoints of top frontier AI providers into a single, standardized, zero-latency **OpenAI-compatible REST and SSE streaming API** (`http://127.0.0.1:9000/v1`).

### Primary Capabilities:
- **8 Frontier AI Providers**: Full Web2API reverse-proxy drivers for **ChatGPT**, **Claude**, **Gemini**, **DeepSeek**, **Qwen**, **Kimi**, **GLM**, and **Grok**.
- **226+ Frontier Models**: Native support for GPT-5/6, Claude 3.7/4/5 Sonnet/Opus/Fable, Gemini 2.5/3.0/3.8/Omni/Veo, DeepSeek V3/R1/V4, Qwen 2.5/3.0/3.8-Max, Kimi K1.5/K2, GLM-4.5/CogView, Grok 3/Reasoner, etc.
- **Universal Multi-Account Stacking**: SQLite-backed credential vault with dynamic round-robin rotation, auto-healing, and rate-limit mitigation across unlimited accounts.
- **Universal Interactive GenUI & Artifacts**: Standalone side-by-side rendering sandbox supporting React 18, HTML5/CSS3/ES6, SVG, and Mermaid diagrams with automatic conversion of ChatGPT `※genui※` payloads into `<antArtifact>` specifications.
- **Native Cross-Platform Runtime**: Runs identically on **Linux**, **macOS**, **Windows**, and **Android (Termux)** with zero compilation overhead.
- **Authentic Upstream Inferences**: Bypasses official paid API key paywalls by authentically driving web endpoints with session tokens, handling WebAssembly/Node.js Proof-of-Work (PoW) challenges, XSRF/ALR hops, and dynamic cookie refreshes.

---

## 2. High-Level Architecture & Topology

```mermaid
graph TD
    subgraph Clients["Clients & Interfaces"]
        UI["Singularity Playground (Port 9000)<br/>Vanilla ES6 + Claude Aesthetics"]
        Tavern["Tavern Studio (Port 5173)<br/>Vite + React TSX Workbench"]
        ExtApps["External Tools & SDKs<br/>(Cursor, Open-WebUI, curl, LangChain)"]
        CLI["Singularity CLI Tool<br/>(./singular / ./c2a)"]
    end

    subgraph Gateway["Singularity Universal Gateway (:9000)"]
        Server["StarletteGateway Router<br/>(singularity/server.py)"]
        ModelRouter["resolve_model_provider()<br/>(226+ Models Routed)"]
        PersonaEng["Dynamic Persona Engine<br/>(singularity/personas.py)"]
        ArtifactsEng["Artifacts Prompt Injector<br/>(singularity/artifacts.py)"]
        ThinkingTrans["Thinking Budget Cap Translator<br/>(Claude, Gemini, OpenAI, DeepSeek)"]
    end

    subgraph DataPlane["Storage & System State"]
        DB[("SQLite WAL Vault<br/>singularity/data/singularity.db")]
        ProvidersMeta["MODELS_CATALOG & PROVIDERS_CONFIG<br/>(singularity/providers.py)"]
        TunnelMgr["Ngrok Tunnel Manager<br/>(singularity/tunnel.py)"]
    end

    subgraph InferenceEngines["Direct In-Process Engines (singularity/engines/)"]
        EngChatGPT["chatgpt.py (:8000)<br/>Sentinel PoW / DALL-E / Estuary"]
        EngClaude["claude.py (:8080)<br/>sessionKey / Org Discovery / SSE"]
        EngGemini["gemini.py (:8084)<br/>SNlM0e XSRF / SAPISIDHASH / ALR"]
        EngGLM["glm.py (:8085)<br/>Zhipu Token / CogView"]
        EngKimi["kimi.py (:8086)<br/>JWT Refresh / K2 Reasoning"]
        EngGrok["grok.py (:8087)<br/>SSO Cookies / UserID"]
        EngDeepSeek["deepseek.py (:8088)<br/>WASM PoW / Node.js Runner"]
        EngQwen["qwen.py (:8089)<br/>chat.qwen.ai Bearer / 1M Context"]
    end

    subgraph WebBackends["Upstream AI Web Platforms"]
        WebChatGPT["chatgpt.com/backend-api"]
        WebClaude["claude.ai/api"]
        WebGemini["gemini.google.com/batchexecute"]
        WebGLM["chatglm.cn/backend-api"]
        WebKimi["kimi.moonshot.cn/api"]
        WebGrok["grok.com/rest"]
        WebDeepSeek["chat.deepseek.com/api"]
        WebQwen["chat.qwen.ai/api"]
    end

    UI -->|HTTP / SSE / REST| Server
    Tavern -->|OpenAI /v1 API| Server
    ExtApps -->|OpenAI /v1 API| Server
    CLI -->|IPC / DB Query| DataPlane
    CLI -->|Inference Query| Server

    Server --> ModelRouter
    ModelRouter --> PersonaEng
    ModelRouter --> ArtifactsEng
    ModelRouter --> ThinkingTrans

    Server <-->|Query Accounts & Settings| DB
    Server <-->|Provider Metadata & Limits| ProvidersMeta
    Server <-->|Public HTTPS Exposure| TunnelMgr

    Server -->|Direct stream_chat() call| EngChatGPT
    Server -->|Direct stream_chat() call| EngClaude
    Server -->|Direct stream_chat() call| EngGemini
    Server -->|Direct stream_chat() call| EngGLM
    Server -->|Direct stream_chat() call| EngKimi
    Server -->|Direct stream_chat() call| EngGrok
    Server -->|Direct stream_chat() call| EngDeepSeek
    Server -->|Direct stream_chat() call| EngQwen

    EngChatGPT -->|TLS / curl_cffi| WebChatGPT
    EngClaude -->|TLS / httpx| WebClaude
    EngGemini -->|TLS / httpx / ALR| WebGemini
    EngGLM -->|TLS / httpx| WebGLM
    EngKimi -->|TLS / httpx| WebKimi
    EngGrok -->|TLS / httpx| WebGrok
    EngDeepSeek -->|Node PoW / curl_cffi| WebDeepSeek
    EngQwen -->|TLS / httpx| WebQwen
```

---

## 3. Core Non-Negotiable Invariants

Any AI agent modifying or expanding this codebase **must strictly follow these foundational rules**:

1. **NO GIT PUSH**: Never issue `git push` or push tokens/secrets to remote repositories.
2. **NO BROWSER / CHROME AUTOMATION**: Do not launch Playwright, Puppeteer, or Chrome subagents unless explicitly ordered by the user.
3. **ZERO RUST BUILD TOOLCHAINS ON MOBILE**:
   - The entire gateway runtime relies on pure Python: `starlette`, `uvicorn`, `httpx`, `curl_cffi`, and `websockets`.
   - **Never add `pydantic` or `fastapi` to [`requirements.txt`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/requirements.txt)**.
   - On Android Termux, compiling `pydantic-core` triggers a Rust/Cargo build that hangs mobile devices. Singularity's `StarletteGateway` provides a drop-in pure Python replacement with instant 3-second phone installations.
4. **NO LEGACY DEPENDENCIES**:
   - The Singularity workspace is 100% self-contained in `singularity/`.
   - **Never import, execute, or link against files in `legacy/`**. `legacy/` is purely an inactive reference archive.
5. **STRICT ONE-FILE ENGINE RULE (`singularity/engines/`)**:
   - Every provider driver lives in **strictly ONE file**: `singularity/engines/<provider>.py`.
   - No scattered `.js`, `.py`, or `.sh` files in `engines/`.
   - Any helper scripts (such as Node.js PoW solvers) must be embedded as inline constants within `<provider>.py`.
   - Binary assets (e.g. `.wasm` modules) reside in `singularity/data/` and must be unignored in `.gitignore` (`!singularity/data/*.wasm`).
6. **PREFER REPOSITORY CLI (`./singular` / `./c2a`)**:
   - Do not write throwaway Python test scripts to test models or check limits. Always use `./singular status`, `./singular limits`, or `./singular chat`.
7. **CANONICAL DUAL-LAUNCHER INVARIANT**:
   - Strictly two launch scripts: [`start.sh`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/start.sh) (symlinked to `singular` and `c2a` for Unix/macOS/Termux) and [`start.bat`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/start.bat) (for Windows).
8. **REAL LIVE TESTING (NO FAKE SIMULATION)**:
   - Unless specifically testing offline UI behavior with `--simulate`, all model verification must use real live upstream requests to verify tokens, cookies, and HTTP handshakes.

---

## 4. Repository Directory & File Anatomy

```
Singularity/
├── ARCHITECTURE.md              <-- This document (Comprehensive architectural blueprint)
├── AGENTS.md                    <-- Core agent operational rules, CLI quick cheat sheet & lessons
├── MISTAKES.md                  <-- Historic mistake log & post-mortem analysis (23+ recorded lessons)
├── DESIGN-SYS.md                <-- Frontend UI tokens, motion design guidelines & aesthetic rules
├── README.md                    <-- Public project documentation & quickstart guide
├── requirements.txt             <-- Minimal pure-Python dependency manifest (httpx, starlette, uvicorn...)
├── start.sh                     <-- Canonical POSIX/Termux launcher & process manager
├── start.bat                    <-- Canonical Windows CMD launcher
├── install.sh                   <-- One-line bootstrap script for fresh machines
├── singular -> start.sh         <-- Symlink to launcher & CLI
├── c2a -> start.sh              <-- Backward-compatibility symlink
├── logo.svg                     <-- Singularity brand vector mark
├── legacy/                      <-- ARCHIVE ONLY: Deprecated reference code (DO NOT IMPORT OR EXECUTE)
│
├── singularity/                 <-- CORE RUNTIME PACKAGE (100% self-contained)
│   ├── server.py                <-- Port 9000 Starlette Gateway, OpenAI REST/SSE routes & middleware
│   ├── worker.py                <-- Multi-threaded provider daemon runner (Ports 8000, 8080, 8084-8089)
│   ├── providers.py             <-- Master Catalog (226 models), provider configurations & live limits
│   ├── db.py                    <-- SQLite WAL Credential Vault, token parsers & account stacking
│   ├── cli.py                   <-- Unified CLI tool implementation (status, limits, accounts, chat)
│   ├── artifacts.py             <-- GenUI interception, <antArtifact> injector & Babel sandboxer
│   ├── personas.py              <-- Dynamic model persona mapping (Astra, Fable) & stream rewriters
│   ├── tunnel.py                <-- Native ngrok daemon manager with 32/64-bit Termux self-healing
│   │
│   ├── engines/                 <-- STRICT ONE-FILE PER PROVIDER INFERENCE DRIVERS
│   │   ├── __init__.py          <-- stream_chat() & generate_chat() universal dispatchers
│   │   ├── chatgpt.py           <-- OpenAI ChatGPT Web2API (PoW Sentinel, DALL-E, SSE)
│   │   ├── claude.py            <-- Anthropic Claude Web2API (sessionKey, Org discovery, Thinking)
│   │   ├── gemini.py            <-- Google Gemini Batchexecute (SNlM0e, SAPISIDHASH, ALR images)
│   │   ├── deepseek.py          <-- DeepSeek AI Web2API (Inline Node.js PoW, WASM runner, R1/V4)
│   │   ├── qwen.py              <-- Alibaba Qwen Web2API (chat.qwen.ai session tokens, 1M context)
│   │   ├── kimi.py              <-- Moonshot Kimi Web2API (JWT auto-refresh, K2 thinking traces)
│   │   ├── glm.py               <-- Zhipu AI GLM Web2API (Refresh tokens, CogView generation)
│   │   └── grok.py              <-- xAI Grok Web2API (SSO cookies, x-userid, conversation routing)
│   │
│   ├── data/                    <-- PERSISTENT APPLICATION STORAGE
│   │   ├── singularity.db       <-- SQLite vault (credentials, model settings, cluster state)
│   │   ├── singularity.db-wal   <-- SQLite Write-Ahead Log
│   │   └── deepseek_pow.wasm    <-- Native WebAssembly module for DeepSeek PoW solver
│   │
│   ├── bin/                     <-- Native runtime binaries (ngrok for auto-tunneling)
│   │
│   └── static/                  <-- PURE ES6 FRONTEND PLAYGROUND & CONTROL CENTER
│       ├── index.html           <-- Claude-aesthetic UI, Lightbox modals, Settings dialog, Workbench
│       ├── app.js               <-- Client orchestrator (SSE, Markdown, Model Picker, Settings sync)
│       ├── style.css            <-- Master typography, dark/light theme variables, message bubbles
│       ├── tokens.css           <-- Design tokens (Anthropic Terracotta, background tints, geometry)
│       ├── glass-dock.js        <-- Floating glass dock logic (status polling, quick modals)
│       ├── glass-dock.css       <-- Frosted glass dock styles, segmented theme switchers
│       ├── icons/               <-- High-definition SVG icons for each provider
│       └── fonts/               <-- Authentic Anthropic and typography webfonts
│
└── TAVERN/                      <-- OPTIONAL REACT TSX WORKBENCH (Vite Port 5173)
    ├── package.json             <-- React 18, Tailwind CSS, Lucide icons, Vite dependencies
    ├── vite.config.ts           <-- Vite dev server configuration (proxies to :9000)
    └── src/                     <-- Character roleplay, worldbuilding, and storytelling UI
```

---

## 5. End-to-End Request & Data Flow Pipeline

When a client sends a request to `POST http://127.0.0.1:9000/v1/chat/completions`:

```
Client Request
      │
      ▼
[server.py] StarletteGateway Handler
      │
      ├─► 1. Model Resolution: resolve_model_provider(model_name)
      │      - Catalog lookup (MODELS_CATALOG in providers.py)
      │      - Prefix/alias pattern matching
      │
      ├─► 2. Persona Engine Interception: personas.get_persona_config(model_name)
      │      - If persona (e.g. GPT-6 Astra, Claude 5 Fable): map to backend model,
      │        inject identity prompt, activate stream sanitization rewriter.
      │
      ├─► 3. Universal Artifacts Prompt Injection: artifacts.inject_artifacts_prompt()
      │      - Injects clean XML guidelines teaching the model to output <antArtifact>.
      │
      ├─► 4. User Profile Name Personalization:
      │      - Checks `user_name` or `x-singularity-user-name` header.
      │      - Injects system prompt ensuring the model knows the user's name across all providers.
      │
      ├─► 5. Thinking Budget Cap Translation:
      │      - Translates unified `thinking_budget` integer into provider-specific syntax:
      │        • Claude: {"thinking": {"type": "enabled", "budget_tokens": N}}
      │        • Gemini: {"generationConfig": {"thinkingConfig": {"thinkingBudget": N}}}
      │        • OpenAI: {"reasoning_effort": "low" | "medium" | "high"}
      │        • DeepSeek / Qwen / Kimi: {"thinking_enabled": true}
      │
      ├─► 6. Direct In-Process Dispatch: engines.stream_chat(provider_id, model, ...)
      │      - Retrieves stacked credentials from SQLite DB (`ORDER BY id DESC`).
      │      - Executes driver in `singularity/engines/<provider>.py`.
      │
      ├─► 7. Live SSE Post-Processing Stream Filter:
      │      - Strips search citation noise (`cite...turn...`, `[cite: 1]`).
      │      - Automatically converts ChatGPT `※genui※` blocks to `<antArtifact>`.
      │      - Passes tokens through PersonaStreamRewriter if persona is active.
      │
      ▼
Client Streaming Output (SSE `data: {...}`)
```

---

## 6. Provider Engines Deep-Dive (`singularity/engines/`)

Each engine in [`singularity/engines/`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/engines/) is a self-contained reverse proxy implementing the provider's native protocol.

### 1. ChatGPT (`chatgpt.py` — Port 8000)
- **Protocol**: Reverse proxies `https://chatgpt.com/backend-api/conversation`.
- **Proof-of-Work (PoW)**: Implements Sentinel / Arkose token generation and dynamic header hashing.
- **Session Types**: Accepts Next-Auth session JSON dumps (`{"accessToken": "...", "user": ...}`) or raw Bearer access tokens.
- **Image Pipeline**:
  - Detects image models (`gpt-image-2.5-flare`, DALL-E 3).
  - Toggles `history_and_training_disabled: False` (OpenAI blocks image generation in temporary chats).
  - Emits `system_hints: ["picture_v2"]`.
  - Downloads binary images from authenticated `backend-api/estuary` endpoints and streams base64 data URIs.
  - Automatically hides conversation via `PATCH /backend-api/conversation/{id}` with `{"is_visible": False}`.

### 2. Claude (`claude.py` — Port 8080)
- **Protocol**: Reverse proxies `https://claude.ai/api/organizations/{org_id}/chat_conversations/{chat_id}/completion`.
- **Authentication**: Uses `sessionKey` (`sk-ant-sid02-...`).
- **Dynamic Organization Discovery**: Automatically queries `GET /api/organizations` on startup to bind to the user's active organization UUID.
- **Streaming & Reasoning**: Parses raw Anthropic SSE streams, capturing `completion` chunks and extracting `<antThinking>` reasoning blocks.

### 3. Gemini (`gemini.py` — Port 8084)
- **Protocol**: Reverse proxies Google Gemini's Batchexecute RPC (`https://gemini.google.com/_/BardChatUi/data/batchexecute`).
- **XSRF & Build Label Dynamic Extraction**: Dynamically scrapes the active `SNlM0e` XSRF token and `bl` build label from `https://gemini.google.com/app`. If a 400 error occurs, extracts updated tokens from the response body to auto-heal.
- **SAPISIDHASH Authentication**: Derives the `Authorization: SAPISIDHASH <timestamp>_<sha1>` header from `SAPISID` / `__Secure-1PAPISID` cookies.
- **High-Definition Media Pipeline**: Resolves generated image candidates through authenticated App Layer Redirection (ALR) hops (`=d-I?alr=yes`) to download full-resolution binaries and stream base64 images.

### 4. DeepSeek (`deepseek.py` — Port 8088)
- **Protocol**: Reverse proxies `https://chat.deepseek.com/api/v0/chat/completion`.
- **Inline WebAssembly PoW Solver**: Contains an inline Node.js runner script that executes against the tracked binary [`singularity/data/deepseek_pow.wasm`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/data/deepseek_pow.wasm) to solve cryptographic PoW challenges in ~15ms.
- **Authentication**: DeepSeek userToken (JWT Bearer).
- **Reasoning**: Streams native `reasoning_content` deltas for DeepSeek-R1 and V4 models.

### 5. Alibaba Qwen (`qwen.py` — Port 8089)
- **Protocol**: Reverse proxies `https://chat.qwen.ai/api/v1/chat/completions`.
- **Authentication**: Accepts Bearer tokens, cookie strings, or localStorage objects.
- **Features**: Supports Qwen 2.5, Qwen 3.0, and Qwen 3.8 Max with full 1M token context windows, streaming reasoning traces, and search citations.

### 6. Moonshot Kimi (`kimi.py` — Port 8086)
- **Protocol**: Reverse proxies `https://kimi.moonshot.cn/api/chat/stream`.
- **Token Refresh**: Uses persistent JWT refresh tokens to dynamically fetch short-lived access tokens via `POST /api/auth/token/refresh`.
- **Reasoning**: Parses K1.5 and K2 extended thinking traces and strips redundant web search citations.

### 7. Zhipu AI GLM (`glm.py` — Port 8085)
- **Protocol**: Reverse proxies `https://chatglm.cn/chatglm/backend-api/assistant/stream`.
- **Authentication**: GLM refresh tokens.
- **Multimodal**: Handles GLM-4.5 text streaming and CogView image generation requests.

### 8. xAI Grok (`grok.py` — Port 8087)
- **Protocol**: Reverse proxies `https://grok.com/rest/app-chat/conversations/new`.
- **Authentication**: Grok SSO cookie bundle (`sso=...; sso-rw=...; x-userid=...`).
- **Routing**: Routes between `grok-3`, `grok-3-deepsearch`, and `grok-3-reasoner`.

---

## 7. Credential Vault & Multi-Account Stacking (`singularity/db.py`)

Singularity stores credentials in a zero-dependency, local SQLite database operating in **Write-Ahead Logging (WAL)** mode at `singularity/data/singularity.db`.

### Database Schema
```sql
CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,         -- 'chatgpt', 'claude', 'gemini', 'deepseek', etc.
    identifier TEXT NOT NULL,       -- unique user ID, email hash, or token fingerprint
    name TEXT,                      -- optional human-readable label
    token TEXT NOT NULL,            -- sanitized token string, cookie bundle, or JSON dump
    plan TEXT DEFAULT 'free',       -- 'free', 'plus', 'pro', 'team'
    status TEXT DEFAULT 'active',   -- 'active', 'rate_limited', 'invalid'
    metadata TEXT,                  -- JSON metadata (org_id, refresh_token, expiry)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, identifier)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Stacking & Rotation Rules
- **Stacking**: Users can paste multiple accounts per provider.
- **Priority**: Database queries retrieve accounts with `ORDER BY id DESC`. Newly pasted credentials automatically take precedence.
- **Auto-Healing**: If an account encounters a rate limit (HTTP 429) or token expiration (HTTP 401), the engine flags its status in the DB and fails over to the next stacked account.
- **Universal Parser**: `parse_credential()` automatically handles raw JWT strings, Bearer tokens, browser `Cookie:` headers, and multi-line JSON dumps.

---

## 8. Universal Artifacts & GenUI Sandboxing Engine

Singularity provides first-class support for **Interactive Artifacts** across all models.

```
AI Model Stream
      │
      ├─► Normal Text / Markdown ─────────────► Chat Bubble
      │
      └─► <antArtifact identifier="..." type="...">
               │
               ▼
      Singularity Artifact Parser (app.js)
               │
               ▼
      Side-by-Side Interactive Workbench (iframe `about:srcdoc`)
         ├─ React 18 (Babel Standalone)
         ├─ Tailwind CSS Utility Classes
         ├─ Lucide React Icons & Recharts
         ├─ HTML5 / CSS3 / Vanilla JS
         ├─ Scalable Vector Graphics (SVG)
         └─ Mermaid Diagrams (mermaid.js)
```

### Supported Artifact Formats:
1. `application/vnd.ant.react`: Interactive React components rendered live via Babel Standalone in the browser.
2. `text/html`: Single-file HTML/CSS/JavaScript web applications.
3. `image/svg+xml`: Vector artwork rendered with native pan/zoom.
4. `application/vnd.ant.mermaid`: Clean architectural and process flowcharts.
5. `application/vnd.ant.code`: Standalone code snippets with syntax highlighting.
6. `text/markdown`: Structured multi-section documents.

### GenUI Interception (`※genui※`)
OpenAI ChatGPT Canvas outputs internal JSON blocks formatted as `※genui※{"app_block":...}※`. The Singularity server automatically intercepts these blocks via [`artifacts.py`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/artifacts.py) and converts them into standard `<antArtifact>` tags, ensuring full rendering compatibility across the interface.

---

## 9. Personas & Dynamic Identity Rewriter (`singularity/personas.py`)

To deliver access to unreleased frontier models while maintaining authentic behavior, Singularity uses a **Persona Engine**:

- **Model Alias Routing**: A request for `gpt-6-astra` routes internally to a high-capability backend model (`gpt-5-6-mini` or `gpt-5.6-sol`), but the persona engine injects specialized system identity rules.
- **Real-Time Stream Rewriter (`PersonaStreamRewriter`)**: Analyzes streaming SSE token buffers to replace model self-identification phrases (e.g. converting *"I am GPT-5.6"* into *"I am GPT-6 Astra"*) without breaking latency or chunk boundaries.
- **Guaranteed Isolation**: Standard vanilla models (e.g. `claude-3-7-sonnet`, `gemini-2.5-pro`) bypass the persona rewriter entirely.

---

## 10. Cloud Tunneling & Native Mobile Access (`singularity/tunnel.py`)

Singularity allows developers to access their desktop server from anywhere on a phone or tablet through an integrated ngrok tunnel manager.

### Architecture Self-Healing (Preventing `[Errno 8] Exec format error`):
On Android Termux, devices frequently run a **64-bit Linux kernel (`aarch64`)** paired with a **32-bit userspace (`arm` / `armhf`)**. A naive `uname -m` check downloads an incompatible 64-bit ELF binary, which crashes with `Exec format error`.

Singularity resolves this by:
1. Inspecting `dpkg --print-architecture` and pointer width (`sys.maxsize > 2**32`).
2. Validating execution via `is_binary_runnable()` (`ngrok version`).
3. Automatically falling back between 64-bit and 32-bit ARM binaries.
4. Auto-purging broken binaries on startup.

---

## 11. Universal Command Line Interface (`./singular` / `./c2a`)

The repository root includes a unified CLI executable.

```bash
cd "/home/insomniac/Desktop/UNI/Apps/Gemini Web2Api/Singularity"

# Inspect fleet health, gateway port, and database stats
./singular status
./singular status --json

# Query live quotas and remaining limits across all 8 providers
./singular limits
./singular limits --json

# Manage SQLite credential vault
./singular accounts                     # List all stacked accounts
./singular accounts gemini              # Filter by provider
./singular import <credentials.json>    # Bulk import credentials
./singular export [backup.json]         # Backup vault to JSON

# Toggle offline simulation mode
./singular simulate on
./singular simulate off
./singular simulate status

# Quick model inference test (streaming)
./singular chat "Hello" -m gemini-3.8-flash
./singular chat "Write a fibonacci function" -m claude-3-7-sonnet
./singular chat "Solve 2+2" -m deepseek-r1

# Manage ngrok cloud tunnel
./singular tunnel                       # Inspect active public HTTPS URL
./singular tunnel start                 # Start background tunnel
./singular tunnel stop                  # Stop active tunnel
./singular tunnel install               # Install native binary for current OS/architecture
./singular tunnel token <token>         # Save ngrok auth token
```

---

## 12. Frontend Architecture & Design System (`singularity/static/`)

The Singularity web UI is built with vanilla ES6 and CSS, adhering to Anthropic's design principles.

- **Theme Engine**: Dual-mode theme system (Light Mode / Dark Mode) powered by CSS custom properties in [`tokens.css`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/static/tokens.css) and [`style.css`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/static/style.css).
- **Floating Glass Dock (`glass-dock.js`)**: Frosted glass HUD providing quick access to Gateway status, fleet limits, cookie stacking modals, and segmented theme toggles.
- **Custom Model Selector**: Popover with instant search filtering, provider badges, checkmark indicators, and automatic catalog re-rendering.
- **Claude Settings Modal**: Profile customization (avatar upload, user display name persisted to SQLite and injected into model system prompts), temperature controls, thinking caps, and voice selection.
- **WebGL Harmonic Fluid Simulation**: When generating images, the UI renders an analytical harmonic vortex fluid simulation on an HTML5 WebGL canvas. In Light Mode, it folds terracotta streams into pure white; in Dark Mode, it streams luminous terracotta into deep `#141414`.

---

## 13. Tavern Studio Integration (`TAVERN/`)

Located in [`TAVERN/`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/TAVERN/), this optional companion application provides a character roleplay and worldbuilding workbench.

- **Tech Stack**: Vite + React 18 + TypeScript + Tailwind CSS.
- **Port**: Runs on `http://127.0.0.1:5173`.
- **API Connection**: Interacts directly with the Singularity Gateway at `http://127.0.0.1:9000/v1` using standard OpenAI completion calls.
- **Dual Boot**: Running `./start.sh` or `start.bat` automatically launches both the Singularity Gateway (:9000) and Tavern Studio (:5173) simultaneously.

---

## 14. Agent Protocols: Adding Providers & Extending Models

When instructed to add support for a new AI provider (e.g. 9th provider):

### Step 1: Create Single-File Engine
Create `singularity/engines/<provider>.py`. Ensure all logic (authentication, PoW solving, streaming SSE, and image extraction) lives in this single file.

### Step 2: Register in Engine Dispatcher
Add import and routing cases to `stream_chat()` and `generate_chat()` in [`singularity/engines/__init__.py`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/engines/__init__.py).

### Step 3: Register Provider Configuration & Models
In [`singularity/providers.py`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/providers.py):
- Add entry to `PROVIDERS_CONFIG` (ID, name, default port, badge, brand color, cookie types).
- Add models to `MODELS_CATALOG`. Search the web to identify current-year frontier releases.
- Implement live limits checking in `get_all_limits()`.

### Step 4: Add Model Resolution & Routing
In [`singularity/server.py`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/server.py):
- Update `resolve_model_provider()` with model prefix matching rules.
- Add provider-specific thinking budget translation rules.

### Step 5: Update Credential Vault
In [`singularity/db.py`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/db.py):
- Update `parse_credential()` to extract credentials from tokens, session strings, or JSON dumps.

### Step 6: Frontend & UI Assets
- Add brand SVG icon to `singularity/static/icons/<provider>.svg`.
- Add provider filter pills to the Model Picker and Cookie Stacker in [`singularity/static/index.html`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/static/index.html).

### Step 7: Verify with Authentic Live Requests
- Stack valid credentials in the database vault using `./singular accounts`.
- Execute a live test inference using `./singular chat "Hello" -m <model-id>`.
- Verify response tokens, latency, and absence of upstream errors.
