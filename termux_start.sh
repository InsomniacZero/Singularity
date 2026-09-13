#!/usr/bin/env bash

# ==============================================================================
# Universal-Gift - Server Launch Script
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Prevent Android Termux sleep/killing in background
if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock
fi

clear 2>/dev/null || true

# Get local Wi-Fi / LAN IP for connecting other devices on same network
LOCAL_IP="127.0.0.1"
if command -v ip >/dev/null 2>&1; then
    LAN_IP=$(ip -4 addr show scope global 2>/dev/null | grep inet | awk '{print $2}' | cut -d/ -f1 | head -n 1)
    if [ -n "$LAN_IP" ]; then
        LOCAL_IP="$LAN_IP"
    fi
elif command -v ifconfig >/dev/null 2>&1; then
    LAN_IP=$(ifconfig 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | head -n 1)
    if [ -n "$LAN_IP" ]; then
        LOCAL_IP="$LAN_IP"
    fi
fi

echo -e "\033[1;36m═════════════════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;36m      🎁 Universal-Gift - Free Gemini Web2API Proxy 🎁                  \033[0m"
echo -e "\033[1;36m═════════════════════════════════════════════════════════════════════════\033[0m"
echo -e "  \033[1;32m● Status:\033[0m          Active (Online)"
echo -e "  \033[1;37m• Local URL:\033[0m        \033[1;33mhttp://localhost:8045/v1\033[0m"
echo -e "  \033[1;37m• Network URL:\033[0m      \033[1;33mhttp://${LOCAL_IP}:8045/v1\033[0m"
echo -e "  \033[1;37m• Default Model:\033[0m    \033[1;32mgemini-3.8-flash\033[0m"
echo -e "  \033[1;37m• Flagship Pro:\033[0m     \033[1;35mgemini-3.1-pro\033[0m or \033[1;35mgemini-3.1-pro-extended\033[0m"
echo -e "  \033[1;37m• API Key:\033[0m          Leave blank or enter any string (e.g. \033[1;37mgift\033[0m)"
echo -e "\033[1;36m═════════════════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;37m  HOW TO CONNECT IN YOUR FAVORITE APPS:\033[0m"
echo -e "  \033[1;33m1. Cursor / VS Code (Continue/Cline/Roo/Aider):\033[0m"
echo -e "     Base URL: \033[1;32mhttp://localhost:8045/v1\033[0m  |  Model: \033[1;32mgemini-3.1-pro\033[0m"
echo -e "  \033[1;33m2. Open WebUI / LibreChat / Chatbox:\033[0m"
echo -e "     API URL:  \033[1;32mhttp://localhost:8045/v1\033[0m  |  API Key: \033[1;32many\033[0m"
echo -e "  \033[1;33m3. Python openai SDK:\033[0m"
echo -e "     client = OpenAI(base_url='\033[1;32mhttp://localhost:8045/v1\033[0m', api_key='\033[1;32many\033[0m')"
echo -e "  \033[1;33m4. Janitor AI / SillyTavern:\033[0m"
echo -e "     Proxy URL: \033[1;32mhttp://localhost:8045/v1/chat/completions\033[0m"
echo -e "\033[1;36m═════════════════════════════════════════════════════════════════════════\033[0m"
echo -e "  \033[1;31mPress Ctrl+C at any time to stop.\033[0m\n"

exec python3 "$SCRIPT_DIR/gemini_web2api.py" --port 8045 "$@"
