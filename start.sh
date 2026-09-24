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

# Phone / Termux Native ngrok setup (Android ARM64/ARM)
if [ -n "$PREFIX" ]; then
    # Verify existing ngrok actually runs without Exec format error
    NGROK_RUNNABLE=0
    if command -v ngrok >/dev/null 2>&1; then
        if ngrok version >/dev/null 2>&1; then
            NGROK_RUNNABLE=1
        else
            echo "  [⚠️] Detected broken or architecture-mismatched ngrok in Termux. Removing..."
            rm -f "$PREFIX/bin/ngrok" "$DIR/singularity/bin/ngrok" 2>/dev/null || true
        fi
    fi

    if [ "$NGROK_RUNNABLE" -eq 0 ]; then
        echo "  [📱] Android/Termux detected: installing verified native ngrok binary..."
        (
            # Accurately detect userspace architecture (dpkg) rather than just kernel (uname -m)
            DPKG_ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m)"
            NGROK_URL=""
            if [ "$DPKG_ARCH" = "aarch64" ] || [ "$DPKG_ARCH" = "arm64" ]; then
                NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz"
            elif [[ "$DPKG_ARCH" == arm* ]]; then
                NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz"
            elif [ "$DPKG_ARCH" = "x86_64" ] || [ "$DPKG_ARCH" = "amd64" ]; then
                NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz"
            else
                NGROK_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz"
            fi

            TMP_TGZ="/tmp/ngrok-termux-$$.tgz"
            if command -v curl >/dev/null 2>&1; then
                curl -sSL "$NGROK_URL" -o "$TMP_TGZ" 2>/dev/null
            elif command -v wget >/dev/null 2>&1; then
                wget -q "$NGROK_URL" -O "$TMP_TGZ" 2>/dev/null
            fi

            if [ -f "$TMP_TGZ" ]; then
                mkdir -p "$DIR/singularity/bin"
                tar -xzf "$TMP_TGZ" -C "$DIR/singularity/bin" ngrok 2>/dev/null || tar -xzf "$TMP_TGZ" -C "$DIR/singularity/bin" 2>/dev/null
                rm -f "$TMP_TGZ"
                if [ -f "$DIR/singularity/bin/ngrok" ]; then
                    chmod +x "$DIR/singularity/bin/ngrok"
                    # Test if the binary executes without Exec format error
                    if ! "$DIR/singularity/bin/ngrok" version >/dev/null 2>&1; then
                        echo "  [!] Primary binary incompatible with device. Falling back to alternative 32-bit ARM binary..."
                        ALT_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm.tgz"
                        if command -v curl >/dev/null 2>&1; then
                            curl -sSL "$ALT_URL" -o "/tmp/ngrok-alt.tgz" 2>/dev/null
                        elif command -v wget >/dev/null 2>&1; then
                            wget -q "$ALT_URL" -O "/tmp/ngrok-alt.tgz" 2>/dev/null
                        fi
                        if [ -f "/tmp/ngrok-alt.tgz" ]; then
                            tar -xzf "/tmp/ngrok-alt.tgz" -C "$DIR/singularity/bin" ngrok 2>/dev/null
                            chmod +x "$DIR/singularity/bin/ngrok"
                            rm -f "/tmp/ngrok-alt.tgz"
                        fi
                    fi

                    if "$DIR/singularity/bin/ngrok" version >/dev/null 2>&1; then
                        [ -d "$PREFIX/bin" ] && cp -f "$DIR/singularity/bin/ngrok" "$PREFIX/bin/ngrok" 2>/dev/null && chmod +x "$PREFIX/bin/ngrok" 2>/dev/null
                        echo "  [✓] Verified native ngrok successfully installed for Android!"
                    fi
                fi
            fi
        ) || true
    fi
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

# Check basic dependencies (starlette, uvicorn, httpx)
if ! "$PYTHON_BIN" -c "import starlette, uvicorn, httpx" 2>/dev/null; then
    echo "  [*] Installing required dependencies from requirements.txt..."
    "$PYTHON_BIN" -m pip install -r "$DIR/requirements.txt" || true
fi

# Route CLI commands vs server launch
case "$1" in
    status|limits|accounts|import|export|simulate|host|chat|thinking|service|tunnel|-h|--help)
        exec "$PYTHON_BIN" cli.py "$@"
        ;;
    server|"")
        [ "$1" = "server" ] && shift

        # Auto-launch Tavern Studio if TAV-TEST or TAVERN directory exists
        TAVERN_DIR=""
        if [ -d "$DIR/TAVERN" ] && [ -f "$DIR/TAVERN/package.json" ]; then
            TAVERN_DIR="$DIR/TAVERN"
        elif [ -d "$DIR/TAV-TEST" ] && [ -f "$DIR/TAV-TEST/package.json" ]; then
            TAVERN_DIR="$DIR/TAV-TEST"
        fi

        TAVERN_PID=""
        if [ -n "$TAVERN_DIR" ]; then
            if ! (echo > /dev/tcp/127.0.0.1/5173) 2>/dev/null && ! nc -z 127.0.0.1 5173 2>/dev/null && ! nc -z 127.0.0.1 3001 2>/dev/null; then
                (
                    cd "$TAVERN_DIR"
                    export PATH="$HOME/.bun/bin:$PATH"
                    export NVM_DIR="$HOME/.nvm"
                    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" && nvm use 24 >/dev/null 2>&1 || true
                    for nvm_node in "$HOME/.nvm/versions/node"/v2[0-9]*/bin; do
                        [ -d "$nvm_node" ] && export PATH="$nvm_node:$PATH"
                    done
                    [ -d "$HOME/.local/share/fnm/current/bin" ] && export PATH="$HOME/.local/share/fnm/current/bin:$PATH"
                    export API_HOST="0.0.0.0"
                    export RP_ALLOWED_ORIGINS="*"

                    # Check for node or bun
                    RUNNER=""
                    if command -v bun >/dev/null 2>&1; then
                        RUNNER="bun"
                    elif command -v npm >/dev/null 2>&1; then
                        RUNNER="npm"
                    fi

                    if [ -n "$RUNNER" ]; then
                        echo "  [🏰] Starting Tavern Studio natively alongside Singularity..."
                        if [ ! -d "node_modules" ]; then
                            echo "  [🏰] Installing Tavern dependencies (first-time setup)..."
                            if [ "$RUNNER" = "bun" ]; then
                                bun install >/dev/null 2>&1 || true
                            else
                                npm install --silent >/dev/null 2>&1 || true
                            fi
                        fi
                        if [ "$RUNNER" = "bun" ]; then
                            bun run dev >/dev/null 2>&1
                        else
                            npm run dev >/dev/null 2>&1
                        fi
                    else
                        echo "  [!] Note: Node.js (v20+) or Bun is required to launch Tavern Studio."
                        echo "      Install Node.js from https://nodejs.org or Bun from https://bun.sh"
                    fi
                ) &
                TAVERN_PID=$!
            else
                echo "  [🏰] Tavern Studio is already running."
            fi
        fi

        cleanup() {
            if [ -n "$TAVERN_PID" ]; then
                kill "$TAVERN_PID" 2>/dev/null || true
            fi
        }
        trap cleanup INT TERM EXIT

        "$PYTHON_BIN" server.py "$@"
        EXIT_CODE=$?
        cleanup
        exit $EXIT_CODE
        ;;
    *)
        exec "$PYTHON_BIN" server.py "$@"
        ;;
esac

