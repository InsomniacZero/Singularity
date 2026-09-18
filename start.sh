#!/usr/bin/env bash
# Singularity Gateway Launcher
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR/singularity" || exit 1
exec python3 server.py "$@"
