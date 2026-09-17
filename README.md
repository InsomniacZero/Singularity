# ⚡ Singularity — Universal AI Gateway & Hub

> **One localhost endpoint. Six AI providers. 186+ models. Zero API keys needed.**

Singularity is a unified AI gateway that aggregates **ChatGPT, Claude, Gemini, Grok, Kimi, and GLM** into a single OpenAI-compatible API endpoint at `http://localhost:9000/v1`. Stack multiple accounts per provider, monitor live quotas, and control everything from a premium dark-mode dashboard.

---

## 🌟 Key Highlights

- **Universal `/v1` Endpoint** — Drop-in OpenAI-compatible API serving 186+ models from 6 providers through one URL
- **Cookie Stacker** — Stack multiple free accounts per provider and rotate them automatically for higher throughput
- **Live Quotas & Limits** — Real-time monitoring of remaining image gens, reasoning tokens, and message caps per provider
- **Singularity-Access (ngrok)** — One-click tunnel to expose your local gateway to the internet for mobile & remote access
- **Interactive Playground** — Test any model with live streaming directly in the dashboard
- **Full Streaming & Vision** — SSE streaming, multimodal image input, tool calling, and image generation across all providers
- **Dynamic Model Catalog** — Models auto-lock/unlock based on which accounts you've stacked

---

## 📱 Dashboard Preview

The Singularity dashboard runs at `http://localhost:9000` and provides:

| Tab | What It Does |
|---|---|
| **Control Center** | Start/stop provider daemons, view fleet status, copy API endpoint |
| **Limits & Quotas** | Live remaining queries, image gens, and reasoning budgets per provider |
| **Available Models** | Browse all 186+ models with lock/unlock status and provider filters |
| **Cookie Stacker** | Add accounts per provider with built-in token extraction guides |
| **Playground** | Interactive chat with model selector, temperature control, and streaming |
| **Singularity-Access** | ngrok tunnel for remote/mobile access with one click |

---

## ⚡ Quick Start

### 💻 Linux / macOS / Windows (Desktop)

```bash
# Clone the repo
git clone https://github.com/InsomniacZero/Singularity.git
cd Singularity

# Install dependencies
pip install -r requirements.txt

# Start the gateway
python3 singularity/server.py
```

The dashboard opens at **`http://localhost:9000`** and the API is live at **`http://localhost:9000/v1`**.

---

### 📱 Android (Termux)

Open **[Termux](https://f-droid.org/en/packages/com.termux/)** and paste:

```bash
# Install prerequisites (rust is needed to build pydantic-core)
pkg update -y && pkg install -y python git rust

# Clone & install
git clone https://github.com/InsomniacZero/Singularity.git
cd Singularity
pip install -r requirements.txt

# Start the gateway
python3 singularity/server.py
```

> **⚠️ `rust` is required** — Termux builds pydantic-core from source on Android. `pkg install rust` takes ~2 min but only needs to be done once.
>
> **Access from same phone:** Open `http://localhost:9000` in your phone browser.
> **Access from PC on same Wi-Fi:** Use `http://<PHONE_IP>:9000/v1` (run `ifconfig` in Termux to find your IP).

---

## 🔌 How to Connect

Once running, point any OpenAI-compatible client to:

| Setting | Value |
|---|---|
| **Base URL** | `http://localhost:9000/v1` |
| **API Key** | `sk-singularity-local` (or any string) |

### SillyTavern
- **API Type:** Chat Completion (OpenAI)
- **Server URL:** `http://localhost:9000/v1/chat/completions`
- **API Key:** `sk-singularity-local`

### Cursor / VS Code / Continue / Cline
- **Provider:** OpenAI Compatible
- **Base URL:** `http://localhost:9000/v1`
- **Model:** Pick any from the catalog (e.g. `gpt-5-6-mini`, `claude-3-7-sonnet`, `gemini-3.8-flash`)

### Python SDK
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:9000/v1",
    api_key="sk-singularity-local"
)

response = client.chat.completions.create(
    model="gpt-5-6-mini",
    messages=[{"role": "user", "content": "Hello from Singularity!"}],
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
    "model": "gemini-3.8-flash",
    "messages": [{"role": "user", "content": "What is Singularity?"}],
    "stream": true
  }'
```

---

## 🎯 Provider Fleet

Singularity orchestrates six provider backends:

| Provider | Port | Models | Highlights |
|---|---|---|---|
| **ChatGPT** | 8000 | 20 | GPT-5.6-Mini/Sol/Terra, GPT-6-Astra, GPT-Image-2.5 |
| **Claude** | 8080 | 20 | Claude 3.7 Sonnet, Claude 4 Opus/Sonnet, Claude Fable |
| **Gemini** | 8084 | 21 | Gemini 3.8 Flash, 3.1 Pro, Nano Banana image models |
| **Grok** | 8087 | 8 | Grok 3, Grok 3 Mini, Grok Imagine |
| **Kimi** | 8086 | 31 | Kimi K2, K2 Math, K2 Vision (200k/500k context) |
| **GLM** | 8085 | 86 | GLM-4 Plus, CogView, Video Gen, Music Gen |

---

## 🍪 Cookie Stacker

The **Cookie Stacker** tab lets you add multiple free accounts per provider to increase throughput and avoid rate limits. Each provider has a built-in guide showing exactly how to extract your session tokens:

- **ChatGPT** → `chatgpt.com/api/auth/session` (use separate Chrome profiles)
- **Claude** → Session key from `claude.ai` cookies
- **Grok** → `x.com` auth cookies
- **Kimi** → `kimi.com` refresh token
- **Gemini** → Google `__Secure-1PSID` cookie
- **GLM** → No credentials needed (free tier)

> ⚠️ Always use **separate Chrome profiles** per account. Never log out of accounts you're using for stacking.

---

## 🌐 Singularity-Access (Remote / Mobile)

The **Singularity-Access** tab lets you expose your local server to the internet via ngrok:

1. Click **Start ngrok Tunnel**
2. Get a public URL like `https://your-subdomain.ngrok-free.dev`
3. Use this URL on your phone, tablet, or any remote device
4. SillyTavern mobile → paste the public URL + `/v1/chat/completions`

> Requires [ngrok](https://ngrok.com/) installed. Free tier works out of the box.

---

## 📁 Project Structure

```
Singularity/
├── singularity/
│   ├── server.py          # FastAPI gateway (port 9000)
│   ├── providers.py       # Provider engine, model catalog, cookie management
│   ├── tunnel.py          # ngrok tunnel manager
│   └── static/
│       ├── index.html     # Dashboard UI
│       ├── app.js         # Frontend logic
│       ├── style.css      # Styles
│       ├── tokens.css     # Design tokens
│       ├── logo.svg       # Singularity logo
│       └── icons/         # Provider SVG icons
├── requirements.txt
├── .gitignore
└── README.md
```

---

## ⚙️ API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/models` | List all available models (OpenAI format) |
| `POST` | `/v1/chat/completions` | Chat completion (streaming & non-streaming) |
| `GET` | `/api/services` | Provider fleet status |
| `POST` | `/api/services/{id}/start` | Start a specific provider |
| `POST` | `/api/services/{id}/stop` | Stop a specific provider |
| `GET` | `/api/limits` | Live quota data for all providers |
| `GET` | `/api/models` | Full model catalog with lock/unlock status |
| `GET` | `/api/cookies` | View stacked accounts per provider |
| `POST` | `/api/cookies` | Add/stack new account credentials |
| `GET` | `/api/tunnel/status` | ngrok tunnel status |
| `POST` | `/api/tunnel/start` | Start ngrok tunnel |
| `POST` | `/api/tunnel/stop` | Stop ngrok tunnel |

---

## 📄 License

MIT License. Built by **InsomniacZero**.
