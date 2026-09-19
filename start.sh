#!/usr/bin/env bash
# Singularity Gateway Launcher

# Resolve real directory even when called through a symlink (e.g. $PREFIX/bin/singular)
if command -v realpath >/dev/null 2>&1; then
    SCRIPT_PATH="$(realpath "${BASH_SOURCE[0]}")"
    DIR="$(dirname "$SCRIPT_PATH")"
else
    SOURCE="${BASH_SOURCE[0]}"
    while [ -L "$SOURCE" ]; do
        DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
        SOURCE="$(readlink "$SOURCE")"
        [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
    done
    DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
fi

# Fallback path search if DIR/singularity is missing (handles complex Termux symlinks)
if [ ! -d "$DIR/singularity" ]; then
    if [ -d "$HOME/Singularity/singularity" ]; then
        DIR="$HOME/Singularity"
    elif [ -n "$PREFIX" ] && [ -d "$PREFIX/../home/Singularity/singularity" ]; then
        DIR="$PREFIX/../home/Singularity"
    fi
fi

# Auto-link 'singular' binary into PATH if in Termux
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ] && [ ! -e "$PREFIX/bin/singular" ]; then
    ln -sf "$DIR/start.sh" "$PREFIX/bin/singular" 2>/dev/null || true
fi

# Detect Python across Linux, macOS, Termux, and Windows (Git Bash/MSYS2/WSL)
PYTHON_BIN=""
if [ -x "$DIR/singularity/.venv/bin/python3" ]; then
    PYTHON_BIN="$DIR/singularity/.venv/bin/python3"
elif [ -x "$DIR/singularity/.venv/Scripts/python.exe" ]; then
    PYTHON_BIN="$DIR/singularity/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
elif command -v py >/dev/null 2>&1; then
    PYTHON_BIN="py"
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "============================================================"
    echo "  [ERROR] Python was not found on your system!"
    echo "  Please install Python 3.10+ from https://www.python.org"
    echo "  On Windows: Ensure 'Add python.exe to PATH' is checked."
    echo "============================================================"
    read -p "Press Enter to close..." _ 2>/dev/null || sleep 5
    exit 1
fi

# Prevent instant terminal window closure on crash/error (common on Windows Git Bash)
trap 'EXIT_CODE=$?; if [ $EXIT_CODE -ne 0 ]; then echo ""; echo "Singularity exited with code $EXIT_CODE."; read -p "Press Enter to close..." _ 2>/dev/null || sleep 5; fi' EXIT

cd "$DIR/singularity" || exit 1

# Check basic dependencies (uvicorn, httpx, starlette)
if ! "$PYTHON_BIN" -c "import starlette, uvicorn, httpx" 2>/dev/null; then
    echo "  [*] Installing required dependencies from requirements.txt..."
    "$PYTHON_BIN" -m pip install -r "$DIR/requirements.txt" || true
fi

# Route CLI commands vs server launch
case "$1" in
    status|limits|accounts|import|export|simulate|host|chat|service|-h|--help)
        exec "$PYTHON_BIN" cli.py "$@"
        ;;
    server|"")
        [ "$1" == "server" ] && shift
        exec "$PYTHON_BIN" server.py "$@"
        ;;
    *)
        exec "$PYTHON_BIN" server.py "$@"
        ;;
esac

