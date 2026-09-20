# AI Agent Instructions for Singularity Workspace

## ⚠️ Essential Project Rules
1. **NO GIT PUSH**: Never push code or tokens to GitHub (`git push` is forbidden unless explicitly asked by the user).
2. **NO BROWSER / CHROME AUTOMATION**: Do not open Chrome or use browser subagents unless explicitly instructed.
3. **PREFER REPO CLI (`./singular` or `./c2a`)**: When checking accounts, verifying quotas/limits, testing models, checking status, or toggling simulation mode, **DO NOT** write multi-line Python scratch scripts or raw curl commands. **Always use the built-in `./singular` (or `./c2a`) CLI tool**.
4. **NO LEGACY DEPENDENCIES**: The Singularity workspace is 100% self-contained in `singularity/`. Do not import, execute, or read files from `legacy/`.

---

## 🚀 Singularity Unified CLI (`./singular` / `./c2a`) Quick Cheat Sheet
The unified tool is located directly in the repository root:
`./singular` (also symlinked as `./c2a` for backward compatibility)

You can run it directly from bash in the repository root:

```bash
cd "/home/insomniac/Desktop/UNI/Apps/Gemini Web2Api/Singularity"

# 1. Inspect Fleet Status & Database Vault
./singular status                    # Live status of all 6 providers & accounts summary
./singular status --json             # Compact JSON output for scripting

# 2. Live Limits & Quotas Across All Providers
./singular limits                    # ChatGPT image/reasoning quotas, Grok, Kimi, Claude, Gemini, GLM
./singular limits --json             # Structured JSON limits payload

# 3. Account Vault Management (SQLite)
./singular accounts                  # List all stacked accounts across providers
./singular accounts chatgpt          # Filter accounts by provider (chatgpt, kimi, claude, etc.)
./singular import <path_or_json>     # Import credentials dump into SQLite vault
./singular export [backup.json]      # Export portable credential vault to JSON

# 4. Device Simulation Mode (Portable / Offline Testing)
./singular simulate on               # Enable simulation mode (test all 206 models without backends)
./singular simulate off              # Disable simulation mode (connect to live backends)
./singular simulate status           # Check current simulation state

# 5. Fast Model Inference & Testing
./singular chat "What is 2+2?" -m gpt-5-6-mini       # Quick streaming chat test
./singular chat "Hello" -m gemini-3.8-flash           # Gemini test
./singular chat "Explain quantum computing" --simulate # Force simulated completion

# 6. Gateway Server Control
./start.sh                           # Start Singularity Gateway daemon on port 9000
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

