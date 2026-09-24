# AI Agent Mistakes Log & Architectural Invariants for Singularity

This document is a persistent record of past failures, UI/UX missteps, technical lessons, and strict architectural rules for AI agents and developers working on the **Singularity** codebase.

> **Mandatory Agent Rule:** Consult this file before making changes. Whenever you encounter a bug, receive a correction from the user, or solve a tricky edge case, **you must update this file with the new mistake, rationale, and preventative rule.**

---

## 🚫 1. Absolute Workspace & Repository Boundaries

### 1.1 Never Push to GitHub Unless Explicitly Commanded
- **Mistake**: Automatically running `git push` or syncing branches to GitHub without direct instructions.
- **Rule**: `git push` is **strictly forbidden** unless the user explicitly commands it in their prompt. All commits stay local until commanded.

### 1.2 Leave the `TAVERN/` Directory Untouched
- **Mistake**: Modifying files inside `/home/insomniac/Desktop/UNI/Apps/Gemini Web2Api/Singularity/TAVERN` while implementing integration.
- **Rule**: The existing `TAVERN/` folder is sacred and must remain untouched. Any code, assets, or concepts ported to Singularity must live entirely within `singularity/`.

### 1.3 Zero Legacy Dependencies
- **Mistake**: Importing, executing, or referencing files in `legacy/` at runtime.
- **Rule**: `legacy/` is purely for read-only reference. All runtime engines, routers, and assets must be self-contained in `singularity/`.

---

## 🛡️ 2. The "Zero-Pollution" Optional Feature Rule

### 2.1 Tavern Integration Must Never Hinder or Break Base Singularity
- **Mistake**: Tightly coupling new features (like Tavern roleplay or visual novels) into core gateway routines, causing the main playground or server to crash or slow down if Tavern assets are absent.
- **Rule**: **Tavern is 100% optional.**
  - If a user only wants the Claude-style Playground, the Control Center, or the OpenAI-compatible Gateway (`:9000/v1`), they must experience **zero performance degradation, zero UI clutter, and zero breaking changes**.
  - Backend routes for Tavern must be cleanly encapsulated in an isolated module (e.g. `singularity/tavern.py`), mounted safely under `/api/tavern/...`.
  - Frontend components for Tavern must live in `singularity/static/tavern/` and only mount when the user explicitly navigates to the `🏰 Tavern` tab.
  - Failures in character card parsing or avatar storage must fail gracefully with localized error banners and never crash the main Gateway process.

---

## 🎨 3. UI, Typography & Design Invariants

### 3.1 Never Use Personal Names in Generic UI
- **Mistake**: Using the user's personal name (e.g. "Anirban") in welcome headers, dialogue prompts, or greeting cards.
- **Rule**: Always use neutral, stylish branding or customizable placeholders (e.g. "Welcome back", "How can I help you today?", or dynamic persona names).

### 3.2 Do Not Shrink Font Sizes to Fix Container Overflow
- **Mistake**: Making text smaller on long dialogue options or action chips to force them onto one line, which looked weird, unbalanced, and hard to read.
- **Rule**: Keep text sizing consistent. If text is long, widen the container or allow natural horizontal/flex breathing room instead of arbitrarily shrinking typography.

### 3.3 Eliminate Jittery Popups and Abrupt Transforms
- **Mistake**: Having sidebars or menus popup jittery from the bottom or snap without easing.
- **Rule**: Use smooth, hardware-accelerated transitions (`cubic-bezier(0.16, 1, 0.3, 1)`, `transform: translateX(...)`). The sidebar must slide smoothly from the side, with hover previews staying fluid.

### 3.4 Button & Pill Hover Clipping
- **Mistake**: Placing action buttons inside containers with `overflow: hidden` where subtle scale-ups (`transform: scale(1.02)`) or top borders get clipped at the container edge.
- **Rule**: Ensure parent containers have adequate vertical padding (`padding: 4px 0` or `overflow: visible`) so elevated or transformed buttons have full breathing room.

### 3.5 Consistent Color Tokens & Subtle Contrasts
- **Mistake**: Using mismatched backgrounds or harsh borders on dropdowns and selectors.
- **Rule**: The model selector background must match the chatbox container background (`--bg-input`), highlighting with a subtle greyish tint only on hover. Never use high-contrast outlines when a soft subtle highlight is required.

---

## ⚡ 4. Developer Velocity: Zero-Build vs. Heavy Toolchains

### 4.1 Avoiding TypeScript & Vite Build Bloat in Singularity
- **Mistake**: Pulling heavy TypeScript/Vite/npm build chains into Singularity's frontend, requiring multi-minute builds, broken typecheck barriers, and complex hot-reload configurations just to tweak a button.
- **Rule**: Keep Singularity frontend **pure vanilla ES6+ and CSS**:
  - Zero compilation step.
  - Edit a file → press F5 in browser → instantly live in 5 milliseconds.
  - Native browser `import` / `export` ES modules for clean code splitting.
  - All character parsing (SillyTavern PNG chunks, JSON schemas) implemented in lightweight, browser-native JavaScript (`DataView`, `TextDecoder`).

---

## ⚙️ 5. Gateway & Engine Technical Pitfalls

### 5.1 Incomplete Model Discovery (Surface-Level Research)
- **Mistake**: In the DeepSeek integration, research stopped at legacy V3/R1 endpoints, missing newer V4 / V4.1 releases until pointed out.
- **Rule**: Always perform targeted web searches for current-year releases, aliases, and reasoning flags before cataloging models in `singularity/providers.py`.

### 5.2 Strict One-File Engine Architecture
- **Mistake**: Adding auxiliary files (`deepseek_pow.js`, `deepseek_pow.py`) into `singularity/engines/`.
- **Rule**: Every provider must have **strictly ONE file** in `singularity/engines/<provider>.py`. Inline helper scripts, WASM loaders, or PoW routines directly within that module.

### 5.3 Git Ignore Safeguards for Binaries & Data
- **Mistake**: Placing `.wasm` or font files in directories that were globally ignored in `.gitignore`, causing deployments on fresh clones to fail.
- **Rule**: Whitelist required runtime assets explicitly in `.gitignore` (e.g. `!singularity/data/*.wasm`, `.otf` fonts), while keeping large temporary archives (`*.zip`) excluded.

### 5.4 Outdated Client Headers
- **Mistake**: Copying legacy Android client headers (`DeepSeek/1.0.13 Android/35`) causing APIs to return `CLIENT_VERSION_TOO_LOW`.
- **Rule**: Emulate modern browser client headers (`x-client-platform: web`, latest Chrome/Firefox user agents).

### 5.5 Avoid Self-Recursive Reverse-Proxy Loops
- **Mistake**: Leaving an upstream fetch inside an engine worker that forwarded back to its own listening port, causing an infinite loop.
- **Rule**: Engine files are the backend implementations themselves; they must execute native logic or forward to upstream provider domains, never to their own local port.

### 5.6 Zero Rust Toolchain & Lean Mobile Python Dependencies (No Pydantic/FastAPI)
- **Mistake**: Inadvertently adding `fastapi` and `pydantic` to `requirements.txt` or startup checks. On Android (Termux), `pip install pydantic` pulls `pydantic-core`, which requires compiling Rust with `cargo`, hanging for hours or failing entirely on phones.
- **Rule**: Singularity runs on pure Python with `StarletteGateway` and `uvicorn`. Neither `pydantic` nor `fastapi` is required. Never add `pydantic`, `fastapi`, or any package requiring a Rust/C build toolchain to `requirements.txt`. Startup checks in `start.sh` must strictly verify lightweight pure packages (`starlette, uvicorn, httpx`) so installation completes in 3–5 seconds on phones.

### 5.7 Android Termux Userspace vs. Kernel Architecture Detection for Native Binaries
- **Mistake**: Relying solely on `uname -m` or `platform.machine()` to choose native binaries (e.g. ngrok) on Android Termux. On many devices, a 64-bit kernel (`aarch64`) hosts a 32-bit Termux userspace (`arm` / `armhf`). Attempting to execute a 64-bit ELF binary on a 32-bit userspace crashes with `[Errno 8] Exec format error`. Furthermore, checking file existence or `os.access(path, os.X_OK)` returns `True` even for mismatched ELF architectures.
- **Rule**: Never trust kernel architecture or executable bits alone on Android/Termux:
  1. Detect userspace architecture via `dpkg --print-architecture` and pointer width (`sys.maxsize > 2**32`).
  2. Every candidate binary must pass `is_binary_runnable` (`ngrok version`) before being accepted or executed.
  3. Implement automatic architecture fallback (e.g. if `arm64` triggers `Exec format error`, immediately fetch and verify 32-bit `arm`).
  4. Auto-detect and purge corrupted or mismatched binaries from `$PREFIX/bin/` and `singularity/bin/` on startup.

### 5.8 Windows Batch Parenthesis & Special Character Escaping
- **Mistake**: Placing raw parentheses inside CMD `if (...)` blocks in Windows `.bat` scripts (e.g. `echo Please install Node.js (v22+)` or `echo (first-time setup)`). In `cmd.exe`, an unescaped closing parenthesis `)` prematurely closes the `if` block, throwing `... was unexpected at this time`.
- **Rule**: Never place unescaped parentheses inside `if (...)` blocks in Windows batch files. Use square brackets `[v22+]` or escape them with a caret `^)`. Always escape ampersands `^&` in echo statements so CMD does not parse them as command separators.

---

## 🔄 6. Maintenance & Error Log

Whenever an issue is identified or a user corrects a behavior, log the entry below:

- **2026-09-20 (UI Typography & Claude Parity)**: Replaced generic system sans fonts with official Anthropic webfonts (`Anthropic Sans` & `Anthropic Serif`) and aligned tokens with Claude's visual polish.
- **2026-09-20 (Dialogue Chip Overflow)**: Fixed dialogue suggestion chips by widening the prompt chip container and preventing text shrink hacks.
- **2026-09-21 (Tavern Integration Boundaries)**: Established rule that `TAVERN/` remains untouched, Tavern integration in Singularity is 100% optional, and the frontend will use pure zero-build vanilla JS/CSS to avoid Vite/TypeScript build delays.
- **2026-09-23 (Product Identity & Naming Invariant)**:
  - *Mistake*: Naming features "Claude Artifact System" or adopting 3rd-party product names.
  - *Rule*: We are building **Singularity**, not Claude or any external vendor. All features and future products must be explicitly branded as **Singularity** (e.g. **Singularity Artifacts**, **Singularity Workbench**, **Singularity Gateway**). Never brand internal features under another company's name.
- **2026-09-23 (React Artifact Sandbox Compilation & Babel DOM Scanner Avoidance)**:
  - *Mistake*: Relying on Babel Standalone's automatic in-browser DOM scanner (`<script type="text/babel">`) with `data-presets`. When Babel encountered unstripped imports, attribute strings, or redeclared variables, its internal script runner crashed with `Uncaught TypeError: "" is not a function`.
  - *Rule*: Never rely on Babel Standalone's in-browser `<script type="text/babel">` automatic scanner. Instead, always use **programmatic compilation** inside a standard `<script>` tag:
    1. Pass the sanitized source code safely via `JSON.stringify(code).replace(/<\/script/gi, '<\\/script')`.
    2. Directly invoke `Babel.transform(rawCode, { presets: ['react'] }).code` inside a `try / catch` block.
    3. Instantiate and mount the resulting component via `new Function(...)` with provided React hooks, helper utilities (`cn`, `clsx`, `twMerge`), Lucide Icon SVG proxies, and motion stubs.
- **2026-09-23 (React Artifact Sandbox `srcdoc` Iframe Opaque Origin & Error Boundary Positioning)**:
  - *Mistake*: The artifact preview `<iframe>` used `sandbox="allow-scripts allow-forms allow-modals"` without `allow-same-origin`. In Chromium/WebKit, an `about:srcdoc` document with an opaque origin (`null`) fails to resolve relative paths like `/static/vendor/react.min.js`, throwing `net::ERR_UNKNOWN_URL_SCHEME` and failing script loads. Compounding the issue, the `#error-boundary` container was placed *after* `<div id="root"></div>` with `min-height: 100vh`, pushing initialization errors completely below the fold so the user only saw a pitch-black screen.
  - *Rule*: Always include `allow-same-origin` in the sandbox iframe (`sandbox="allow-scripts allow-same-origin allow-forms allow-modals"`), inject `<base href="${window.location.origin}/"/>` into the iframe `<head>`, point scripts to absolute origin paths with CDN `onerror` fallbacks, and anchor `#error-boundary` at `position: fixed; top: 16px; left: 16px; right: 16px; z-index: 999999;` so any runtime or syntax error is immediately visible above the fold.
- **2026-09-23 (ChatGPT Canvas `※genui※` Raw Dump Conversion to Singularity Artifacts)**:
  - *Mistake*: When prompting ChatGPT models (`gpt-5.6-sol`, `chatgpt`) for interactive CSS or web applications, the model outputted OpenAI's internal Canvas format: `※genui※{"app_block":{"title":"...","content":"..."}}※`. Because neither the backend nor frontend intercepted this delimiter, the raw JSON payload was dumped into the user's chat message bubble.
  - *Rule*: Universal GenUI interceptor must always be active in `singularity/artifacts.py` and `singularity/static/app.js`: automatically extract the `app_block` JSON (or streaming partial matches), extract the title and HTML/CSS/JS content, and convert it into `<antArtifact identifier="..." type="text/html" title="...">...` so that any interactive app emitted by ChatGPT renders as a first-class Singularity Artifact with live preview and code inspection tabs.
- **2026-09-23 (Fatal Unescaped Newline in Template Literal Script Generation & Parent Globals Fallback)**:
  - *Mistake*: In `buildReactSandboxHtml`, the string `'React Component Render Error:\n'` was written inside a multiline template string literal. At runtime in `app.js`, `\n` was interpolated into the HTML string as a literal raw newline inside single quotes (`'...'`), resulting in a fatal `Uncaught SyntaxError: Invalid or unexpected token` during the browser's initial `<script>` tag parsing inside `srcdoc`. Because this happened during script parsing before execution, `waitForDependencies`, `window.onerror`, and `#error-boundary` never ran, rendering a completely blank screen.
  - *Rule*: Never place unescaped `\n` inside quoted string literals within template literal HTML/JS generators. Always use `\\n` or plain strings without newlines. Pre-load React, ReactDOM, and Babel in `index.html` so `srcdoc` iframes can immediately access `window.parent.React` / `window.parent.Babel` on tick 0, eliminating cross-origin script blocks, CDN failures, and 3MB parse delays.
- **2026-09-23 (GitHub HTTPS 100MB Packfile Timeout & HTTP 408 / Curl 22 Error)**:
  - *Mistake*: Attempting to commit bundled binary wallpaper directories (`TAVERN/seed/backgrounds/*.png` at 80MB) along with source code caused the total Git commit packfile to hit ~100MB, triggering `error: RPC failed; HTTP 408 curl 22 The requested URL returned error: 408` and connection termination on GitHub.
  - *Rule*: Never commit heavy binary wallpaper directories or media caches directly to GitHub over HTTPS. Keep repositories lean: commit only source code, config, vector icons, and essential fonts (~7MB total). Heavy visual novel backgrounds and user data (`data/`, `node_modules/`, `avatars/`) must stay excluded via `.gitignore`.
- **2026-09-23 (Git Untracking Pitfall for Already Tracked Local Docs)**:
  - *Mistake*: Expecting that simply adding previously-committed files (like `AGENTS.md` and `DESIGN-SYS.md`) to `.gitignore` would stop Git from pushing them.
  - *Rule*: `.gitignore` only applies to *untracked* files. For any file already in Git index that needs to be kept on disk for local dev use, you MUST run `git rm --cached <files>` so Git untracks them while preserving the files locally.
- **2026-09-23 (Entrypoint Proliferation & Canonical Launcher Invariant)**:
  - *Mistake*: Generating extra entrypoints (`start_singularity.sh`, `singular.bat`) when user asked to run from anywhere.
  - *Rule*: Singularity has **strictly two canonical entrypoints**:
    1. `start.sh` (symlinked as `singular` for Linux/macOS/Termux) — uses `realpath` resolution and `$PREFIX/bin` linking so it runs anywhere.
    2. `start.bat` for Windows — uses `%~dp0` to resolve the root from any current working directory.
    Never create auxiliary `.bat` or `.sh` wrapper scripts in the repository root.
- **2026-09-23 (Co-Startup Lifecycle Management for Dual Services)**:
  - *Mistake*: Relying on standalone manual launches for Tavern Studio while Singularity was running.
  - *Rule*: `start.sh` and `start.bat` handle dual co-startup automatically:
    - Checks for `TAV-TEST` first (if user is developing locally) or `TAVERN`.
    - Spawns Tavern in background on ports 5173/3001 with auto `npm install` check.
    - Sets process traps (`trap cleanup INT TERM EXIT`) on Linux/macOS/Termux so child node processes are cleanly killed when Singularity exits.
- **2026-09-23 (Cross-Device & LAN Host Binding Blocker in Integrated Web Services)**:
  - *Mistake*: When accessing Singularity from other devices on the LAN (e.g. phone or laptop on `http://192.168.1.x:9000`), clicking "Tavern" failed with connection refused because:
    1. Vite defaulted to loopback `127.0.0.1` without `server.host: '0.0.0.0'`.
    2. Express backend in `server/index.ts` listened on `127.0.0.1` without `API_HOST=0.0.0.0`.
    3. `originCheck.ts` rejected non-loopback origins with `403 Forbidden origin`.
    4. Frontend and backend hardcoded `http://localhost:5173` instead of dynamically resolving against the caller's active device hostname (`window.location.hostname`).
  - *Rule*: Whenever integrating secondary web servers (Vite/Node/FastAPI), ALWAYS:
    1. Configure `host: '0.0.0.0'` in `vite.config.ts`.
    2. Set default host to `0.0.0.0` in the backend server (`server/index.ts`).
    3. Whitelist private IPv4 subnets (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`, `.local`) in origin guards.
    4. Dynamically rewrite launcher and API URLs using the caller request's host header or `window.location.hostname`.
- **2026-09-24 (Accidental Dependency Re-introduction & Pydantic-Core Rust Build Trap on Phones)**:
  - *Mistake*: While adding DeepSeek and Qwen features, `fastapi` and `pydantic` were inadvertently added back into `requirements.txt`, and `start.sh` had `import fastapi` in its startup check. On Android (Termux), `pip install` pulled `pydantic-core`, which requires compiling Rust with `cargo`, hanging for hours on phones.
  - *Rule*: Singularity's runtime is 100% pure Python and relies on `StarletteGateway` in `singularity/server.py`. Neither `pydantic` nor `fastapi` is used. Never add `pydantic`, `fastapi`, or any package requiring a Rust toolchain to `requirements.txt`. Startup checks in `start.sh` must strictly check pure packages (`starlette, uvicorn, httpx`) so phone installation takes 3–5 seconds flat.
- **2026-09-24 (Termux Kernel vs Userspace Mismatch & `[Errno 8] Exec format error`)**:
  - *Mistake*: When downloading native ngrok binaries on Android Termux, `uname -m` reported `aarch64` (64-bit kernel), but the Termux environment on the device was a 32-bit userland (`arm` / `armhf`). Attempting to spawn the 64-bit ELF binary caused `Failed to spawn ngrok process: [Errno 8] Exec format error: '/data/data/com.termux/files/usr/bin/ngrok'`. Additionally, `get_ngrok_bin_path` assumed any file with executable bit was runnable without performing an actual execution dry-run.
  - *Rule*: Never rely solely on `uname -m` on Android/Termux.
    1. Query the actual userspace architecture via `dpkg --print-architecture` and check `sys.maxsize > 2**32`.
    2. Every candidate binary must pass `is_binary_runnable` (`ngrok version`) before being accepted or spawned.
    3. Implement automatic architecture fallback: if `arm64` triggers `Exec format error`, automatically fetch and verify the 32-bit `arm` binary.
    4. On startup, automatically detect and purge any corrupted or architecture-mismatched binaries from `$PREFIX/bin/` so the system self-heals.
- **2026-09-24 (Windows Batch Parenthesis Trap in `if (...)` Blocks)**:
  - *Mistake*: In `run_tavern.bat` and `start.bat`, `echo Please install Node.js (v22+)` and `echo (first-time setup)` were placed inside CMD `if (...)` blocks. In `cmd.exe`, raw parentheses inside an `if` block prematurely terminate the block parser, crashing with `... was unexpected at this time`.
  - *Rule*: Never use raw unescaped parentheses inside `if (...)` blocks in Windows `.bat` files. Use square brackets `[v22+]` or escape them `^)`. Never use unescaped ampersands `&` in echo statements (use `^&` so CMD doesn't treat it as a command separator).
- **2026-09-24 (Missing Standard Library Imports in Dynamic Archive Handlers)**:
  - *Mistake*: Calling `tarfile.open()` inside `singularity/tunnel.py::install_ngrok()` without `import tarfile` at the module level caused `Could not auto-install ngrok: Failed to auto-install ngrok for generic-arm64: name 'tarfile' is not defined` when extracting `.tgz` binaries on Android/Linux.
  - *Rule*: Always declare standard library extraction utilities (`tarfile`, `zipfile`, `shutil`) at module level and run an AST check across new functions to eliminate runtime `NameError` exceptions.
- **2026-09-24 (Termux Current Directory vs. Global PATH Command Execution)**:
  - *Mistake*: When in `~/Singularity`, typing `singular` or `singularity` without `./` before first boot failed with `No command singular found, did you mean: Command simulavr` because the current working directory `.` is not in `$PATH`.
  - *Rule*: On initial setup, users run `./start.sh` or `bash install.sh`. `start.sh` must immediately symlink both `singular`, `singularity`, and `c2a` into `$PREFIX/bin` (and `~/.local/bin` on Linux/macOS) and add aliases to `~/.bashrc` so that all subsequent invocations without `./` work globally from any directory.
- **2026-09-24 (ChatGPT Web Image Generation Block in Temporary Chats & Estuary CDN 403)**:
  - *Mistake*: Selecting image generation models like `gpt-image-2.5-flare` or `gpt-image-2.5-sunburst` returned a refusal: *"I can help create an apple image, but image generation isn't available in this temporary chat. Please switch to a regular ChatGPT chat and ask again..."*. This occurred because:
    1. `history_and_training_disabled: True` was unconditionally sent to the upstream OpenAI backend API, placing the session in "Temporary Chat" (incognito) mode where DALL-E / picture_v2 tools are strictly disabled by OpenAI.
    2. Model slugs (`gpt-image-2.5-flare`) were not aliased to `"auto"`, preventing proper tool binding.
    3. OpenAI estuary CDN download URLs (`sediment://` or `backend-api/estuary/content`) return HTTP 403 when loaded directly in browser `<img>` tags without session cookies.
  - *Rule*: For all image generation models:
    1. Dynamically set `history_and_training_disabled: not is_image_model` and include `"system_hints": ["picture_v2"]`.
    2. Proxy and cache all generated image assets: intercept SSE `sediment://` and `file-service://` asset pointers, download the full PNG binary using the TLS-impersonated session, persist them to `singularity/static/generated/`, and stream standard base64 data URIs (`![Generated Image](data:image/png;base64,...)`) so the frontend renders the interactive viewport immediately.
    3. Clean up the user's ChatGPT sidebar automatically post-generation by issuing `PATCH /backend-api/conversation/{conv_id}` with `{"is_visible": False}`.
- **2026-09-24 (Generated Image Viewport UI & Clean Floating Action Overlays)**:
  - *Mistake*: Encasing AI-generated images inside bloated cards with extra border outlines and footer caption bars ("Neural Synthesis", redundant prompt text). In modern conversational UI (e.g. ChatGPT), the generated image must stand clean and borderless with its natural aspect ratio and rounded corners, avoiding visual clutter.
  - *Rule*: Generated images must be presented cleanly:
    1. Render the image directly with modern rounded corners (`border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.08); box-shadow: 0 4px 24px rgba(0, 0, 0, 0.28);`).
    2. Eliminate redundant caption / prompt footers.
    3. Floating action overlay (top-right) provides dedicated, high-contrast frosted glass buttons for **Copy** and **Download** only (omitting distracting edit/share menus), with tooltips (`data-tooltip`) and immediate visual feedback (e.g. checkmark icon and "Copied!" state).
- **2026-09-25 (High-Definition WebGL Fluid Simulation & Theme Adaptive Palette)**:
  - *Mistake*: Checking `document.body.getAttribute('data-theme')` instead of `document.documentElement.getAttribute('data-theme')`, causing light mode to falsely register as dark mode and rendering black patches instead of clean white; and hardcoding pitch black instead of the UI's theme primary dark `#141414`.
  - *Rule*: For image generation loading:
    1. Check theme on `document.documentElement` (`document.documentElement.getAttribute('data-theme') || document.body.getAttribute('data-theme')`).
    2. In Light Mode: Replace all dark/black elements with pure white (`#ffffff`) and soft whitish (`#fcfbfa`). Terracotta `#d97757` streams fold and merge with whitish fluid. Zero black or dark patches!
    3. In Dark Mode: Background is the UI's dark background `#141414` (from tokens `--bg-primary`) with luminous `#d97757` terracotta streams and warm peach highlights.
    4. Render with GPU-accelerated WebGL using **analytical harmonic vortex potential flow** ($\sin, \cos, \text{atan}, \text{length}$). These are $C^\infty$ mathematically continuous, guaranteed 100% artifact-free, and impossible to produce noise or TV grain.
    5. Render at native Retina display resolution (`canvas.width = clientWidth * dpr`). Fluid motion must be strictly **autonomous** (no pointer listeners).
    6. Clean ChatGPT UI framing: "Creating image" header in top-left, aspect ratio container, and frosted glass percentage progress pill ("19%") in bottom-right corner.
    7. When inference completes, `finish()` cleanly deallocates WebGL shaders and the final image pop-fades in.
- **2026-09-25 (Dark Mode Theme Accents & High-Contrast Icon Elements)**:
  - *Mistake*: Setting user message bubbles to generic dark gray (`#242424`) and dimming response buttons and top header settings icons to muddy low-contrast gray (`#78716c`), causing poor visual hierarchy and readability on dark backdrops.
  - *Rule*: In dark mode:
    1. User message bubble background is brand terracotta (`#d97757`) with crisp white text (`#ffffff`), 16px corners, and subtle warm drop shadow.
    2. Response action buttons (copy, retry, edit, tts, feedback) in `.response-actions` and user message hover bar `.user-msg-actions` are crisp whitish (`rgba(255, 255, 255, 0.85)` / `#ffffff` on hover).
    3. Top header settings buttons (`.claude-icon-btn`, `.claude-avatar-btn`) are crisp whitish (`rgba(255, 255, 255, 0.88)` / `#ffffff` on hover).
    4. Date timestamps (`.response-date`, `.user-msg-date`) remain subtly muted (`var(--text-muted)`) so they do not compete with interactive controls.
