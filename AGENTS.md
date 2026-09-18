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
