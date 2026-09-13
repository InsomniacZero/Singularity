# 🎁 Universal-Gift: Universal Free Gemini Web2API Proxy

> **Turn Google Gemini into a free, high-speed, OpenAI-compatible API (`http://localhost:8045/v1`) for any application — coding assistants, web UIs, agents, and custom scripts.**

---

### 🌟 Key Highlights

* **100% Free & Unlimited**: Runs via Google's web engine in anonymous Guest Mode. No credit card, no API key billing, and no Google account login required.
* **OpenAI & Google Compatible**: Exposes standard `/v1/chat/completions`, `/v1/images/generations`, `/v1/models`, and `/v1beta/models` endpoints.
* **Connect Anywhere**: Ready to drop into **Cursor**, **VS Code (Continue / Cline / Roo / Aider)**, **Open WebUI**, **LibreChat**, **LangChain**, **Python `openai` SDK**, **SillyTavern**, and more.
* **All Modern Gemini Models**: Access `gemini-3.8-flash`, `gemini-3.1-pro`, `gemini-3.1-pro-extended` (Deep Reasoning), and the **Nano Banana** image models (`nano-banana-2`, `nano-banana-pro`, `nano-banana`).
* **Full Streaming, Vision & Image Gen**: Real-time SSE streaming, multimodal image input, tool calling, and standard `/v1/images/generations` support.
* **Auto-Healing Engine**: Automatically auto-recovers XSRF tokens and build labels without requiring restarts.

---

## ⚡ Quick 1-Click Install

### 📱 Android (Termux)
Open **Termux** and paste this single command:
```bash
pkg update -y && pkg install -y git && git clone https://github.com/InsomniacZero/Universal-Gift.git && cd Universal-Gift && bash termux_install.sh
```
> **Shortcut:** From now on, simply type `gift` in Termux and press Enter to start!

---

### 💻 Windows (PowerShell)
Open **PowerShell** and paste this single command:
```powershell
irm https://raw.githubusercontent.com/InsomniacZero/Universal-Gift/main/install.ps1 | iex
```
> **Shortcut:** From now on, simply type `gift` in PowerShell or CMD to start!

---

### 🐧 Linux / macOS
Open your terminal and run:
```bash
git clone https://github.com/InsomniacZero/Universal-Gift.git
cd Universal-Gift
bash termux_install.sh
```
> **Shortcut:** Type `gift` to start!

---

## 🔌 How to Connect in Your Apps

Once the server is running, it listens at **`http://localhost:8045/v1`** (or `http://<YOUR_LAN_IP>:8045/v1` for devices on the same Wi-Fi network).

### 1. Cursor & VS Code Extensions (Continue / Cline / Roo Code / Aider)
Configure your AI provider as **OpenAI Compatible**:
* **Base URL / API Base:** `http://localhost:8045/v1`
* **API Key:** Any string (e.g. `gift`)
* **Model:** `gemini-3.1-pro` (for advanced coding) or `gemini-3.8-flash` (for fast edits)

---

### 2. Open WebUI / LibreChat / Chatbox / NextChat
* **API Host / Base URL:** `http://localhost:8045/v1`
* **API Key:** `gift`
* All models will automatically populate in the model selection list!

---

### 3. Python (`openai` Official SDK)
```python
from openai import OpenAI

# Point to your local Universal-Gift proxy
client = OpenAI(
    base_url="http://localhost:8045/v1",
    api_key="gift"  # Any non-empty string works
)

# Non-streaming
response = client.chat.completions.create(
    model="gemini-3.1-pro",
    messages=[
        {"role": "system", "content": "You are a senior systems architect."},
        {"role": "user", "content": "Design a high-throughput event processing architecture in Go."}
    ]
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="gemini-3.8-flash",
    messages=[{"role": "user", "content": "Write a quicksort in Rust with unit tests."}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

# Image Generation (Nano Banana)
image_resp = client.images.generate(
    model="nano-banana-2",
    prompt="A photorealistic 3D figurine of a cybernetic cat sitting on neon streets, octane render 8k",
    n=1,
    size="1024x1024"
)
print(image_resp.data[0].url)
```

---

### 4. cURL / Terminal
```bash
# Chat Completion
curl http://localhost:8045/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-3.8-flash",
    "messages": [
      {"role": "system", "content": "You are a concise assistant."},
      {"role": "user", "content": "Hello! What can you do?"}
    ]
  }'

# Image Generation (Nano Banana)
curl http://localhost:8045/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nano-banana-2",
    "prompt": "An astronaut riding a green horse on Mars, cinematic lighting",
    "n": 1
  }'
```

---

### 5. Chatbots & Roleplay (SillyTavern, Janitor AI, etc.)
* **API Type:** OpenAI Compatible (or Custom)
* **Proxy / Endpoint URL:** `http://localhost:8045/v1/chat/completions`
* **Model ID:** `gemini-3.1-pro-extended`, `gemini-3.8-flash`, or `nano-banana-2`
* **API Key:** `gift`

---

## 📋 Model Directory & Aliases

| Model Identifier | Mode | Description | Best For |
|---|---|---|---|
| **`gemini-3.8-flash`** *(Default)* | Fast | Google's latest high-speed, general-purpose model | Daily tasks, general chat, fast code generation |
| **`gemini-3.8-flash-thinking`** | Reasoning | Flash with Deep Reasoning mode (~20k reasoning budget) | Math, complex logic, step-by-step puzzles |
| **`gemini-3.1-pro`** | Flagship Pro | Advanced Google Pro model | Heavy programming, architecture, complex refactoring |
| **`gemini-3.1-pro-extended`** | Pro Reasoning | Gemini 3.1 Pro with Extended Thinking enabled | Maximum intelligence, hard coding problems, deep stories |
| **`gemini-3.1-pro-thinking`** | Pro Reasoning | Alias for `gemini-3.1-pro-extended` | Reasoning tokens before generation |
| **`nano-banana-2`** | Image Gen | Next-gen image synthesis (Gemini 3.1 Flash Image) | High-speed photorealistic image gen & consistent subject editing |
| **`nano-banana-pro`** | Flagship Image | Flagship high-res visual model (Gemini 3 Pro Image) | Complex prompts, legible typography, ultra-high fidelity art |
| **`nano-banana`** | Image Gen | Original viral image generator (Gemini 2.5 Flash Image) | Creative styling, 3D figurines, natural language photo manipulation |
| **`nano-banana-2-lite`** | Rapid Image | Lightweight quick generation (Gemini 3.1 Flash-Lite Image) | Ultra-fast image previews, batch concept generation |
| **`imagen-3`** | Image Gen | Alias for `nano-banana-pro` image model | Drop-in standard for Imagen / OpenAI image workflows |
| **`gemini-3.7-flash`** | Fast | Gemini 3.7 Flash | Fallback / alternative generation |
| **`gemini-3.6-flash`** | Fast | Stable 3.6 Flash | Previous stable generation |
| **`gemini-flash-lite`** | Ultra Fast | Lightweight, high-throughput model | Simple classification, extraction, summaries |
| **`gemini-auto`** | Auto | Automatic dynamic model routing | Adaptive workload handling |

> **Smart Alias Matching:** You can pass short names like `banana-2`, `banana-pro`, `nano-banana`, `imagen-3`, `3.1-pro`, `pro`, `flash`, `3.1-pro-extended`, or even standard aliases like `gpt-4o` and the proxy maps them automatically.

---

## ⚙️ Advanced Settings & Flags

Run `python3 gemini_web2api.py --help` for options:

| Flag | Default | Description |
|---|---|---|
| `--port` | `8045` | Port to bind the server on |
| `--host` | `0.0.0.0` | Host to bind on (`0.0.0.0` enables local network access) |
| `--model` | `gemini-3.8-flash` | Default model when not specified by client |
| `--cookie` | `cookie.txt` | Path to optional Google account cookie file |
| `--proxy` | `None` | Upstream HTTP/SOCKS proxy (e.g. `http://127.0.0.1:7890`) |
| `--api-key` | `""` | Require a custom API key for clients to access your server |
| `--quiet` | `False` | Disable request logging in console |

---

## 🔒 Privacy & Guest Mode

* By default, **Universal-Gift** runs in **Guest Mode**. It never requires your personal Google credentials or cookies.
* If you want to connect a specific Google account (e.g. for Gemini Advanced subscription features), simply export your `cookie.txt` using any standard cookie extension and place it in the folder.

---

## 📄 License
MIT License. Built for the open-source community by **InsomniacZero**.
