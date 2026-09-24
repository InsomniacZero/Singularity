#!/usr/bin/env bash
# Singularity Global Command Installer
# Installs 'singular' and 'singularity' CLI commands globally on Termux, Linux, and macOS.

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "⚡ Installing Singularity CLI globally..."

chmod +x "$DIR/start.sh" "$DIR/singular" "$DIR/c2a" 2>/dev/null || true

INSTALLED=0

# Termux environment
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ]; then
    ln -sf "$DIR/start.sh" "$PREFIX/bin/singular"
    ln -sf "$DIR/start.sh" "$PREFIX/bin/singularity"
    ln -sf "$DIR/start.sh" "$PREFIX/bin/c2a"
    chmod +x "$PREFIX/bin/singular" "$PREFIX/bin/singularity" "$PREFIX/bin/c2a"
    INSTALLED=1
fi

# Standard Linux/macOS user bin
if [ -d "$HOME/.local/bin" ]; then
    ln -sf "$DIR/start.sh" "$HOME/.local/bin/singular" 2>/dev/null || true
    ln -sf "$DIR/start.sh" "$HOME/.local/bin/singularity" 2>/dev/null || true
    ln -sf "$DIR/start.sh" "$HOME/.local/bin/c2a" 2>/dev/null || true
    chmod +x "$HOME/.local/bin/singular" "$HOME/.local/bin/singularity" "$HOME/.local/bin/c2a" 2>/dev/null || true
    INSTALLED=1
elif [ -w "/usr/local/bin" ]; then
    ln -sf "$DIR/start.sh" "/usr/local/bin/singular" 2>/dev/null || true
    ln -sf "$DIR/start.sh" "/usr/local/bin/singularity" 2>/dev/null || true
    ln -sf "$DIR/start.sh" "/usr/local/bin/c2a" 2>/dev/null || true
    chmod +x "/usr/local/bin/singular" "/usr/local/bin/singularity" "/usr/local/bin/c2a" 2>/dev/null || true
    INSTALLED=1
fi

# Add alias to ~/.bashrc for Termux as an extra guarantee
if [ -f "$HOME/.bashrc" ]; then
    if ! grep -q "alias singular=" "$HOME/.bashrc" 2>/dev/null; then
        echo "alias singular=\"$DIR/start.sh\"" >> "$HOME/.bashrc"
        echo "alias singularity=\"$DIR/start.sh\"" >> "$HOME/.bashrc"
    fi
fi

echo "============================================================"
echo "  [✓] Singularity CLI successfully installed globally!"
echo "  You can now run directly from anywhere:"
echo "      singular           (or ./start.sh)"
echo "      singularity status"
echo "      singular limits"
echo "============================================================"
