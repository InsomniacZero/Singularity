# <img src="singularity/static/logo.svg" width="36" height="36" alt="Singularity Logo" style="vertical-align: middle; margin-right: 8px;" /> Singularity

> **One localhost endpoint. Eight AI providers. 216+ models. Zero API keys needed.**

Singularity is a unified AI gateway and playground that aggregates **ChatGPT, Claude, Gemini, Grok, Kimi, GLM, DeepSeek, and Qwen** into a single OpenAI-compatible API endpoint at `http://localhost:9000/v1`. Stack multiple accounts per provider, monitor live quotas, test models in a Claude-inspired playground with interactive artifacts, and launch an integrated character visual-novel suite with **Tavern Studio**.

---

## 🌟 Key Highlights

- **Universal `/v1` Endpoint** — Drop-in OpenAI-compatible API serving 216+ models across 8 providers through one URL.
- **🏰 Integrated Tavern Studio** — Bundled character roleplay, visual novel stage, and storytelling studio running on ports `5173`/`3001` alongside Singularity.
- **🎨 Interactive Code Artifacts** — Real-time interactive previews for React components, HTML/CSS, SVGs, and formatted Markdown with version tracking.
- **🍪 Cookie Stacker & Vault** — Stack multiple free accounts per provider with automatic round-robin rotation, session persistence, and token extraction guides.
- **📊 Live Quotas & Limits** — Real-time tracking of remaining image gens, reasoning budgets, context limits, and hourly rate limits.
- **🧠 Thinking / Reasoning Controls** — Inspect and set custom thinking budget caps per model with real-time thought-process disclosure.
- **🎭 Persona System** — Switch between customized agent personas and custom instructions directly within the playground.
- **🧪 Device Simulation Mode** — Test and develop against all 216 models locally without requiring live network sessions (`./singular simulate on`).
- **🌐 Singularity-Access** — Remote and mobile access via ngrok or cloud tunnels with one click.
- **✨ Sleek Glass UI** — Claude-inspired dark mode interface with official Anthropic typography, responsive sidebar, and floating glass dock.

---

## 📱 Dashboard & Features

The Singularity dashboard runs at `http://localhost:9000` and provides:

| View | What It Does |
|---|---|
| **Control Center** | Monitor provider fleet daemons, launch Tavern Studio, view gateway status, and copy API URLs |
| **Limits & Quotas** | Inspect real-time queries, image generation credits, and reasoning budgets per provider |
| **Available Models** | Browse all 216+ models with capability badges (Vision, CoT, Search, Web) and active lock/unlock status |
| **Cookie Stacker** | Stack multiple credentials per provider with step-by-step token extraction guides |
| **Playground** | Claude-style chat interface with streaming, thinking toggles, temperature control, and persona selector |
| **Artifacts Workbench**| Multi-view interactive code previewer supporting React, HTML/JS, SVG, and Markdown |
| **Tavern Studio** | Visual novel stage, reactive character portraits, lorebooks, and multi-character storytelling (`:5173`) |
| **Singularity-Access** | One-click ngrok tunnel for mobile and remote access |

---

## ⚡ Quick Start

### 🪟 Windows (1-Click or CLI)

1. **Prerequisite:** Ensure [Python 3.10+](https://www.python.org/downloads/) and [Node.js 18+](https://nodejs.org/) are installed.
   > ⚠️ **Important:** During Python setup, ensure **"Add python.exe to PATH"** is checked.

2. **Download & Run:**
   - **Option A (Git):**
     ```cmd
     git clone https://github.com/InsomniacZero/Singularity.git
     cd Singularity
     start.bat
     ```
   - **Option B (Zip):**
     Download and extract the ZIP, then double-click **`start.bat`**.

3. **What happens on boot:**
   - Auto-creates Python virtualenv and installs backend dependencies.
   - Automatically spins up **Singularity Gateway** on `http://localhost:9000`.
   - Automatically spins up **Tavern Studio** on `http://localhost:5173` (backend `:3001`).

4. **Windows CLI:**
   You can run all Singularity commands directly with `start.bat`:
   ```cmd
   start.bat status               :: Inspect fleet health and account count
   start.bat limits               :: Live quotas for ChatGPT, Claude, Grok, etc.
   start.bat accounts             :: List stacked accounts in SQLite vault
   start.bat chat "Hello world"   :: Quick terminal streaming chat test
   start.bat simulate on          :: Enable offline simulation mode
   ```

---

### 🐧 Linux / macOS

```bash
# 1. Clone the repository
git clone https://github.com/InsomniacZero/Singularity.git
cd Singularity

# 2. Launch (boots Singularity :9000 + Tavern Studio :5173)
./start.sh
```

> **Tip:** You can also run CLI commands or chat using `./start.sh` or the built-in symlink `./singular`:
> ```bash
> ./singular status
> ./singular limits
> ./singular chat "Explain quantum computing" -m gpt-5-6-mini
> ```

---

### 📱 Android (Termux)

Open **[Termux](https://f-droid.org/en/packages/com.termux/)** and run:

```bash
pkg update -y && pkg install -y python git nodejs-lts && git clone https://github.com/InsomniacZero/Singularity.git && cd Singularity && chmod +x start.sh && ./start.sh
```

- **Next time:** Type **`singular`** from anywhere in Termux to launch.
- **Access locally:** Open `http://localhost:9000` in your mobile browser.
- **Access over local Wi-Fi:** Open `http://<PHONE_IP>:9000` from your PC or tablet.

---

## 🎯 Provider Fleet (8 Providers / 216+ Models)

Singularity manages 8 native reverse-proxy worker engines:

| Provider | Port | Models | Flagship Models & Capabilities |
|---|---|---|---|
| **ChatGPT** | 8000 | 20 | GPT-5.6-Mini/Sol/Terra, GPT-6-Astra, GPT-Image-2.5, Multimodal Vision |
| **Claude** | 8080 | 20 | Claude 3.7 Sonnet (Thinking), Claude 4 Opus/Sonnet, Claude Fable |
| **Gemini** | 8084 | 21 | Gemini 3.8 Flash, 3.1 Pro, Imagen 3, Nano Banana vision models |
| **Grok** | 8087 | 8 | Grok 3, Grok 3 Mini, Grok Imagine, Real-time X search |
| **Kimi** | 8086 | 31 | Kimi K3 Flagship, K3 Thinking/Search, K2.8 (200k context) |
| **GLM** | 8085 | 86 | GLM 5.3, GLM 5.3 Thinking/Search, CogView 4, GLM-5 Turbo |
| **DeepSeek** | 8088 | 12 | DeepSeek V3, R1 Reasoner, DeepSeek V4, V4-Pro, V4.1-Flash |
| **Qwen** | 8089 | 18 | Qwen 2.5 (72B), Qwen Max, Qwen Plus, Qwen Coder (128k context) |

---

## 🏰 Tavern Studio Integration

Singularity bundles **Tavern Studio**, an immersive visual novel storytelling and character chat client:
- **Zero Config:** Automatically launches alongside Singularity on `http://localhost:5173`.
- **Direct Pipeline:** Connects out-of-the-box to `http://localhost:9000/v1` with all 216 models ready to generate text and expressions.
- **Features:** Reactive 2D portraits, dynamic background stages, audio/BGM channels, world lorebooks, day planners, and Singularity image generation.
- **Fast Access:** Launch Tavern with one click from the dashboard sidebar or the floating Glass Dock.

---

## 🎨 Interactive Artifacts Sandbox

When testing models in the Playground, Singularity automatically detects and isolates executable code blocks into live interactive artifacts:
- **React Apps:** Render live JSX/React components directly in the browser via Babel & React 18.
- **HTML / CSS / JS:** Live interactive websites, games, and web apps with instant hot reloading.
- **Vector Graphics:** Render and inspect raw SVG diagrams and vector illustrations.
- **Version History:** Track iterations and switch back and forth between generated artifact versions.
- **Exporting:** One-click code copying or raw artifact file downloads.

---

## 🔌 Connecting Clients

Once running, point any OpenAI-compatible client to:

| Setting | Value |
|---|---|
| **Base URL** | `http://localhost:9000/v1` |
| **API Key** | `sk-singularity-local` (or any string) |

### SillyTavern / Third-Party Frontends
- **API Type:** Chat Completion (OpenAI)
- **Server URL:** `http://localhost:9000/v1/chat/completions`
- **API Key:** `sk-singularity-local`

### Cursor / VS Code / Cline / Continue
- **Provider:** OpenAI Compatible
- **Base URL:** `http://localhost:9000/v1`
- **Model:** Any model from the catalog (e.g. `claude-3-7-sonnet`, `deepseek-v4`, `gpt-5-6-mini`, `gemini-3.8-flash`)

### Python SDK
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:9000/v1",
    api_key="sk-singularity-local"
)

response = client.chat.completions.create(
    model="claude-3-7-sonnet",
    messages=[{"role": "user", "content": "Explain quantum teleportation."}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### cURL
```bash
curl http://localhost:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-singularity-local" \
  -d '{
    "model": "deepseek-v4",
    "messages": [{"role": "user", "content": "Hello Singularity!"}],
    "stream": true
  }'
```

---

## 🛠️ CLI Cheatsheet (`./singular` / `start.bat`)

Singularity features a unified CLI engine accessible via `./singular` (Linux/macOS) or `start.bat` (Windows):

```bash
# 1. Fleet & System Status
./singular status                    # Live status of all 8 providers & stacked accounts
./singular status --json             # Compact JSON output for scripts

# 2. Live Limits & Quotas Across All Providers
./singular limits                    # Real-time limits (ChatGPT, Claude, Gemini, Grok, Kimi, GLM, etc.)

# 3. Account Vault Management (SQLite)
./singular accounts                  # List all stacked accounts across providers
./singular accounts chatgpt          # Filter accounts by provider
./singular import <path_or_json>     # Import credentials dump into SQLite vault
./singular export [backup.json]      # Export portable credential vault to JSON

# 4. Device Simulation Mode (Portable / Offline Testing)
./singular simulate on               # Test all 216 models locally without upstream network
./singular simulate off              # Reconnect to live backend sessions
./singular simulate status           # Inspect simulation status

# 5. Fast Model Inference & Testing
./singular chat "Hello" -m claude-3-7-sonnet          # Quick terminal streaming completion
./singular chat "Write code" -m deepseek-v4           # Test DeepSeek
./singular chat "Hello" --simulate                    # Force simulated completion
```

---

## 📁 Repository Structure

```
Singularity/
├── singularity/                         # Core Python package & UI
│   ├── engines/                         # Provider Web2API engines
│   │   ├── chatgpt.py                   # ChatGPT Sentinel PoW & reverse proxy
│   │   ├── claude.py                    # Claude session & stream driver
│   │   ├── deepseek.py                  # DeepSeek native solver & driver
│   │   ├── gemini.py                    # Gemini SNlM0e & Google session driver
│   │   ├── glm.py                       # Zhipu GLM guest & session driver
│   │   ├── grok.py                      # Grok xAI websocket & REST driver
│   │   ├── kimi.py                      # Kimi Moonshot driver
│   │   ├── qwen.py                      # Qwen Alibaba Cloud driver
│   │   └── __init__.py
│   ├── static/                          # Control Center Web UI
│   │   ├── index.html                   # Dashboard & Playground HTML
│   │   ├── style.css                    # Sleek Claude-style design system
│   │   ├── app.js                       # Frontend logic & WebSocket streaming
│   │   ├── glass-dock.css / .js         # Floating Glass Dock navigation
│   │   ├── fonts/                       # Official Anthropic Sans & Serif typography
│   │   ├── icons/                       # Provider & UI SVGs
│   │   └── vendor/                      # Offline Prism & React compilers
│   ├── artifacts.py                     # Artifact sandbox & preview runner
│   ├── personas.py                      # Persona system & system prompts
│   ├── cli.py                           # Singularity unified CLI engine
│   ├── db.py                            # SQLite credential vault
│   ├── providers.py                     # Model catalog & live limit aggregators
│   ├── server.py                        # FastAPI / ASGI Universal Gateway
│   ├── tunnel.py                        # Cloudflare / ngrok tunnel engine
│   └── worker.py                        # Provider daemon supervisor
│
├── TAVERN/                              # Integrated Tavern Studio
│   ├── src/                             # React / Vite visual novel frontend
│   ├── server/                          # Fast SQLite character & world backend
│   └── package.json
│
├── start.sh                             # Linux / macOS / Termux unified launcher
├── start.bat                            # Windows native batch launcher
├── singular -> start.sh                 # Linux / Termux CLI symlink
├── requirements.txt                     # Python dependencies
├── logo.svg                             # Singularity branding
├── ARCHITECTURE.md                     # Comprehensive technical architecture & agent manual
├── AGENTS.md                            # Agent instructions & CLI cheat sheet
├── MISTAKES.md                          # Lessons learned & post-mortem log
└── README.md                            # Documentation
```

---

## 📄 License

MIT License. Built by **[InsomniacZero](https://github.com/InsomniacZero)**.
