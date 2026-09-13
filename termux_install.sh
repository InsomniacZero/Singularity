#!/usr/bin/env bash

# ==============================================================================
# Universal-Gift - 1-Click Installer for Android Termux & Linux
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "\033[1;36m═══════════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;36m      🎁 Universal-Gift - Free Gemini Web2API Proxy Setup 🎁        \033[0m"
echo -e "\033[1;36m═══════════════════════════════════════════════════════════════════\033[0m"

# 1. Update packages & install Python
echo -e "\033[1;33m[1/3] Checking & Installing Python...\033[0m"
if command -v pkg >/dev/null 2>&1; then
    pkg update -y && pkg install -y python git
elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y && sudo apt-get install -y python3 python3-pip git
fi

# 2. Install optional httpx for high-performance HTTP/2 streaming
echo -e "\033[1;33m[2/3] Installing Python httpx library...\033[0m"
pip install httpx 2>/dev/null || pip3 install --break-system-packages httpx 2>/dev/null || true

# 3. Create shortcut commands 'gift' and 'insom'
chmod +x "$SCRIPT_DIR/termux_start.sh"
echo -e "\033[1;33m[3/3] Creating shortcut command 'gift'...\033[0m"

if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ]; then
    cat << EOF > "$PREFIX/bin/gift"
#!/usr/bin/env bash
cd "$SCRIPT_DIR" && exec ./termux_start.sh "\$@"
EOF
    chmod +x "$PREFIX/bin/gift"
elif [ -d "/usr/local/bin" ] && [ -w "/usr/local/bin" ]; then
    cat << EOF > "/usr/local/bin/gift"
#!/usr/bin/env bash
cd "$SCRIPT_DIR" && exec ./termux_start.sh "\$@"
EOF
    chmod +x "/usr/local/bin/gift"
fi

# Add alias to ~/.bashrc for seamless global execution
if ! grep -q "alias gift=" "$HOME/.bashrc" 2>/dev/null; then
    echo "alias gift='$SCRIPT_DIR/termux_start.sh'" >> "$HOME/.bashrc"
fi

echo ""
echo -e "\033[1;32m═══════════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;32m   🎉 INSTALLATION COMPLETE! READY TO USE GEMINI ANYWHERE! 🎉   \033[0m"
echo -e "\033[1;32m═══════════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;37mFrom now on, whenever you want to start the API proxy, just type:\033[0m"
echo ""
echo -e "      \033[1;33mgift\033[0m"
echo ""
echo -e "\033[1;37mand press Enter!\033[0m"
echo -e "\033[1;32m═══════════════════════════════════════════════════════════════════\033[0m"
echo ""
read -p "Would you like to start the server right now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    exec "$SCRIPT_DIR/termux_start.sh"
fi
