# AI Agent Instructions for Singularity Workspace

## ⚠️ Essential Project Rules
1. **NO GIT PUSH**: Never push code or tokens to GitHub (`git push` is forbidden unless explicitly asked by the user).
2. **NO BROWSER / CHROME AUTOMATION**: Do not open Chrome or use browser subagents unless explicitly instructed.
3. **PREFER REPO CLI (`./singular` or `./c2a`)**: When checking accounts, verifying quotas/limits, testing models, checking status, or toggling simulation mode, **DO NOT** write multi-line Python scratch scripts or raw curl commands. **Always use the built-in `./singular` (or `./c2a`) CLI tool**.
4. **NO LEGACY DEPENDENCIES**: The Singularity workspace is 100% self-contained in `singularity/`. Do not import, execute, or read files from `legacy/`.
5. **ZERO RUST BUILD TOOLCHAINS ON MOBILE**: Singularity runs on pure Python with `StarletteGateway` and `uvicorn`. Never add `pydantic` or `fastapi` to `requirements.txt`. Startup dependency checks must verify pure packages (`starlette, uvicorn, httpx`) so phone installation completes in 3–5 seconds without Cargo/Rust compilation.

---

## 🚀 Singularity Unified CLI (`./singular` / `./c2a`) Quick Cheat Sheet
The unified tool is located directly in the repository root:
`./singular` (also symlinked as `./c2a` for backward compatibility)

You can run it directly from bash in the repository root:

```bash
cd "/home/insomniac/Desktop/UNI/Apps/Gemini Web2Api/Singularity"

# 1. Inspect Fleet Status & Database Vault
./singular status                    # Live status of all 8 providers & accounts summary
./singular status --json             # Compact JSON output for scripting

# 2. Live Limits & Quotas Across All Providers
./singular limits                    # ChatGPT, Claude, Gemini, Grok, Kimi, GLM, DeepSeek, Qwen quotas
./singular limits --json             # Structured JSON limits payload

# 3. Account Vault Management (SQLite)
./singular accounts                  # List all stacked accounts across providers
./singular accounts chatgpt          # Filter accounts by provider (chatgpt, kimi, claude, deepseek, etc.)
./singular import <path_or_json>     # Import credentials dump into SQLite vault
./singular export [backup.json]      # Export portable credential vault to JSON

# 4. Device Simulation Mode (Portable / Offline Testing)
./singular simulate on               # Enable simulation mode (test all 216 models without backends)
./singular simulate off              # Disable simulation mode (connect to live backends)
./singular simulate status           # Check current simulation state

# 5. Fast Model Inference & Testing
./singular chat "What is 2+2?" -m gpt-5-6-mini       # Quick streaming chat test
./singular chat "Hello" -m gemini-3.8-flash           # Gemini test
./singular chat "Explain quantum computing" --simulate # Force simulated completion

# 6. Gateway Server Control (Dual-boots Singularity :9000 + Tavern Studio :5173)
./start.sh                           # Linux / macOS / Termux
start.bat                            # Windows (native cmd/powershell)

# 7. Cloud Tunnel & Native Remote Mobile Access (ngrok)
./singular tunnel                    # Inspect tunnel state & public HTTPS URL
./singular tunnel start              # Expose gateway securely to the internet
./singular tunnel stop               # Stop active public tunnel
./singular tunnel install            # Auto-install native ngrok binary (Phone Termux / PC)
./singular tunnel token <token>      # Set ngrok authtoken
```

---

## 🛠️ Protocol for Adding a New AI Provider to Singularity

When expanding Singularity to support a new AI provider (e.g. 8th, 9th provider):

### 1. Zero Legacy Runtime Dependencies
- If a reference repo is cloned into `legacy/` (e.g. `legacy/<repo>`), use it **only** to study API contracts, signatures, and protocols.
- **Never** import, execute, or link against `legacy/`. All runtime code must live in `singularity/`.

### 2. Strict One-File Engine Rule (`singularity/engines/`)
- Every provider must have **strictly ONE file** in `singularity/engines/`: `singularity/engines/<provider>.py`.
- **Do not scatter auxiliary scripts** (no extra `.js`, `.py`, or `.sh` files in `engines/`).
- Any sub-processes (e.g. Node.js PoW solvers, WASM execution scripts) must be embedded as inline constants within `<provider>.py`.
- Binary assets (e.g. `.wasm` modules) belong in `singularity/data/` and **must be unignored** in `.gitignore` (`!singularity/data/*.wasm`) so they are tracked by git.

### 3. Exhaustive Model Discovery & Web Research
- **Never assume legacy models are the latest.** Always run targeted web searches for:
  - Current-year model releases (e.g. V4, V4.1, Flash, Pro, Reasoner).
  - Official API aliases and web endpoints.
  - Context window capacities, vision/multimodal capabilities, and thinking/CoT features.
- Register every model in `MODELS_CATALOG` in [`singularity/providers.py`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/providers.py).
- Register all model prefixes and aliases in `resolve_model_provider()` in [`singularity/server.py`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/server.py).

### 4. Realistic & Non-Hallucinated Limits
- Do not fabricate arbitrary limits. Query the provider's live user profile / limits API (`/users/current`, etc.) using credentials if available.
- Reflect exact capabilities (Reasoning, Web Search, File Upload size/count, Concurrency, Reset Windows) in `get_all_limits()` in [`singularity/providers.py`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/providers.py).

### 5. SQLite Credential Vault Support
- Add the provider parser to `parse_credential()` in [`singularity/db.py`](file:///home/insomniac/Desktop/UNI/Apps/Gemini%20Web2Api/Singularity/singularity/db.py).
- Ensure it flexibly handles raw token strings, full JSON dumps, localStorage key-value objects (e.g. `{"value": "...", "__version": "0"}`), and JWTs.

### 6. Full Gateway & Control Center Integration
- Add provider configuration to `PROVIDERS_CONFIG` in `providers.py` (port, badge, color, host).
- Add SVG icon to `singularity/static/icons/<provider>.svg`.
- Update Control Center UI in `singularity/static/index.html` and `singularity/static/app.js` (filter pills, cookie stacker tabs, token guides).
- Test both simulated (`--simulate`) and live inference using `./singular chat`.
- Confirm fleet health via `./singular status` and `./singular limits`.

---

## 📝 Post-Mortem & Mistakes Log (Lessons Learned)

Keep these past failures in mind to avoid repeating them:

1. **Incomplete Model Discovery (Surface-Level Research)**:
   - *Mistake*: During DeepSeek integration, research stopped at the V3/R1 baseline found in the legacy reference repo, completely missing the newly released V4, V4-Pro, and V4.1-Flash models until the user pointed it out.
   - *Lesson*: Always execute thorough web searches focused specifically on the newest releases, current year changes, and active aliases before writing the model catalog.

2. **Engine Directory Clutter**:
   - *Mistake*: Created `deepseek_pow.js` and `deepseek_pow.py` in `singularity/engines/`, breaking the clean architecture where each provider has exactly one unified driver file.
   - *Lesson*: Keep `singularity/engines/` strictly one-file per provider (`<provider>.py`). Inline auxiliary Node.js or shell helpers directly in the Python module.

3. **Untracked Binary Assets in Git**:
   - *Mistake*: Placed the required WebAssembly binary in `singularity/data/` while `singularity/data/` was ignored in `.gitignore`, risking a broken deployment on fresh clones.
   - *Lesson*: Whenever placing native runtime assets in data folders, explicitly whitelist them in `.gitignore` (e.g. `!singularity/data/*.wasm`).

4. **Blindly Copying Outdated Reference Headers**:
   - *Mistake*: Copied old Android client headers (`DeepSeek/1.0.13 Android/35`) from the reference repo, causing the live API to reject requests with `CLIENT_VERSION_TOO_LOW`.
   - *Lesson*: Modern web APIs change client versions frequently. Always verify against current browser client headers (`x-client-platform: web`, modern User-Agents).

5. **Self-Recursive Worker Forwarding Loops**:
   - *Mistake*: Left an upstream check inside the engine that forwarded requests to port 8088 when the engine itself was running inside the 8088 worker, causing an infinite loop.
   - *Lesson*: Engine files are the backend implementations themselves; they must execute the native Web2API reverse-proxy logic directly.

6. **Dependency Creep & Mobile Rust Build Trap**:
   - *Mistake*: Inadvertently adding `fastapi` and `pydantic` to `requirements.txt`. On Android (Termux), `pip install` pulls `pydantic-core`, which attempts to compile Rust via `cargo`, hanging for hours on phones.
   - *Lesson*: Singularity runs on pure Python with `StarletteGateway` and `uvicorn`. Never add `pydantic` or `fastapi`. Keep `requirements.txt` strictly lightweight and pure Python so phone installations take 3–5 seconds.

7. **Termux Kernel vs Userspace Architecture Mismatch (`[Errno 8] Exec format error`)**:
   - *Mistake*: Relying solely on `uname -m` to select native binaries (e.g. ngrok) on Android Termux. On many phones, a 64-bit kernel (`aarch64`) runs a 32-bit Termux userspace (`arm` / `armhf`). Attempting to execute a 64-bit ELF binary on a 32-bit userland crashes with `[Errno 8] Exec format error`. Furthermore, checking `os.access(..., os.X_OK)` returns `True` even for mismatched ELF architectures.
   - *Lesson*: Detect userspace architecture using `dpkg --print-architecture` and pointer width (`sys.maxsize > 2**32`). Always test execution via `is_binary_runnable` (`ngrok version`) before using a binary, provide automatic fallback between 64-bit and 32-bit ARM, and auto-purge broken binaries on startup.

8. **Windows Batch Parenthesis & Ampersand Traps**:
   - *Mistake*: Placing raw parentheses inside CMD `if (...)` blocks in Windows `.bat` scripts (e.g. `echo Please install Node.js (v22+)`). In `cmd.exe`, an unescaped `)` prematurely terminates the `if` block and crashes with syntax errors.
   - *Lesson*: Never use raw parentheses inside `if (...)` blocks in `.bat` files. Use square brackets `[v22+]` or escape them `^)`. Always escape ampersands `^&` in echo statements.

9. **Universal GenUI Interception (`※genui※`) & Artifact Sandboxing**:
   - *Mistake*: ChatGPT web canvas outputs raw `※genui※{"app_block":...}※` JSON payloads directly into chat bubbles, and iframe sandboxes without `allow-same-origin` or proper error boundary coordinates break React apps and push errors below the fold.
   - *Lesson*: Always route GenUI blocks through `singularity/artifacts.py` to auto-convert to `<antArtifact>`, use programmatic Babel compilation instead of DOM scanner scripts, and fix error boundaries at `top: 16px; z-index: 999999` with `allow-same-origin` on `about:srcdoc`.

10. **Canonical Dual-Launcher Invariant (`start.sh` and `start.bat`)**:
    - *Mistake*: Creating multiple ad-hoc startup scripts (`start_singularity.sh`, `singular.bat`) when users request running from arbitrary directories.
    - *Lesson*: Singularity maintains strictly two canonical launchers: `start.sh` (symlinked as `singular` for Unix/Termux) and `start.bat` for Windows. Both handle co-startup of Singularity and optional Tavern, auto-detect dependencies, and clean up child processes on exit.

11. **Module-Level Imports for Archive Extraction Handlers (`tarfile`, `zipfile`)**:
    - *Mistake*: Calling `tarfile.open()` inside an installer helper without `import tarfile` at the top of the file, causing runtime crashes (`name 'tarfile' is not defined`) when unpacking `.tgz` binaries on Android/Linux.
    - *Lesson*: Always import standard library archive tools (`tarfile`, `zipfile`) at module level and run an AST-based undefined-variable check on any newly added functions before shipping.

12. **Termux Current Directory vs. Global PATH Command Execution**:
    - *Mistake*: Typing `singular` or `singularity` directly in `~/Singularity` before initial launch fails with `command not found` because `.` is not in `$PATH`.
    - *Lesson*: First-time boot requires `./start.sh` (or `bash install.sh`). `start.sh` automatically establishes global symlinks in `$PREFIX/bin/singular`, `$PREFIX/bin/singularity`, and `$PREFIX/bin/c2a` so subsequent executions work globally without `./`.

13. **ChatGPT Web Image Generation Block in Temporary Chats & Direct Estuary CDN 403**:
    - *Mistake*: Selecting image models like `gpt-image-2.5-flare` failed with *"image generation isn't available in this temporary chat"*. This was caused by hardcoding `history_and_training_disabled: True` in OpenAI payload (OpenAI strictly disables DALL-E in temporary chats) and direct browser loading of `backend-api/estuary` URLs which return 403 without session cookies.
    - *Lesson*: For image models, dynamically toggle `history_and_training_disabled: not is_image_model`, add `system_hints: ["picture_v2"]`, download the image binary in the authenticated session, persist to `singularity/static/generated/`, stream base64 data URIs, and auto-hide the conversation via `PATCH /backend-api/conversation/{conv_id}` with `{"is_visible": False}`.

14. **Generated Image Viewport UI & Clean Floating Action Overlays**:
    - *Mistake*: Encasing AI-generated images inside bloated cards with extra border outlines and footer caption bars ("Neural Synthesis", redundant prompt text).
    - *Lesson*: Present generated images cleanly with rounded corners (`border-radius: 16px`), no caption footer, and a sleek floating top-right frosted glass overlay containing only **Copy** (with checkmark feedback) and **Download** SVG buttons with tooltips.

15. **Authentic HTML5 Canvas Fluid Simulation for Image Generation**:
    - *Mistake*: Attempting to fake fluid dynamics with CSS radial gradient spirals or SVG filters instead of running real Eulerian fluid mechanics (Navier-Stokes) like Jonas Wagner's famous `29a.ch` canvas fluid simulation.
    - *Lesson*: For image generation loading, render a real-time Navier-Stokes 2D fluid simulation on `<canvas>` with terracotta color mapping (`#d97757` on `#0d0c0b` in dark mode, and terracotta watercolor on `#fbf9f6` in light mode). Simulate authentic hydrodynamic ink drops with initial dipole vortex ring splitting, sequential plumes, interactive pointer stirring (`pointermove`), clean "Creating image" header, dynamic prompt aspect ratio, and a frosted percentage progress pill. On completion, `finish()` stops the loop and the final generated image smoothly pop-fades in.

16. **Dark Mode User Bubbles & Whitened UI Action Controls**:
    - *Mistake*: Dark mode user messages blending into generic dark gray backgrounds, with action buttons and top header settings icons being too dim (`var(--text-muted)` = `#78716c`), causing poor contrast and muddy appearance.
    - *Lesson*: In dark mode, style user message bubbles with brand terracotta `#d97757` and crisp white text. Whiten response action buttons (`.response-actions`), user message hover controls (`.user-msg-actions`), and top header settings buttons (`.claude-icon-btn`, `.claude-avatar-btn`) to `rgba(255, 255, 255, 0.85-0.92)` / `#ffffff` on hover, while keeping date timestamps subtly muted (`var(--text-muted)`).




