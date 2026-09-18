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

if [ -x "$DIR/singularity/.venv/bin/python3" ]; then
    PYTHON_BIN="$DIR/singularity/.venv/bin/python3"
else
    PYTHON_BIN="python3"
fi

cd "$DIR/singularity" || exit 1

# Route CLI commands vs background/daemon server launch
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

