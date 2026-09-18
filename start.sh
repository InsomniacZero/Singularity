#!/usr/bin/env bash
# Singularity Gateway Launcher
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Auto-link 'singular' binary into PATH if in Termux
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ] && [ ! -e "$PREFIX/bin/singular" ]; then
    ln -sf "$DIR/start.sh" "$PREFIX/bin/singular" 2>/dev/null || true
fi

cd "$DIR/singularity" || exit 1
exec python3 server.py "$@"
