#!/usr/bin/env bash
set -e

# Resolve directory of this script (TAVERN root)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Ensure Bun and Node paths are available
export PATH="$HOME/.bun/bin:$PATH"
export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then
  \. "$NVM_DIR/nvm.sh"
  nvm use 24 >/dev/null 2>&1 || true
fi

echo "═══════════════════════════════════════════════════════════════════"
echo "  🏰 TAVERN + ⚡ Singularity Gateway"
echo "═══════════════════════════════════════════════════════════════════"
echo "  • TAVERN Web UI:        http://localhost:5173"
echo "  • Local Backend:        http://localhost:3001"
echo "  • Singularity Gateway:  http://localhost:9000/v1"
echo "═══════════════════════════════════════════════════════════════════"

npm run dev
