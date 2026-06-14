#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WPHAWK_PY="$SCRIPT_DIR/wphawk.py"

echo ""
echo " ╔══════════════════════════════════════╗"
echo " ║   WPHawk  —  Linux/macOS Installer   ║"
echo " ╚══════════════════════════════════════╝"
echo ""

# ── Locate Python ─────────────────────────────────────────────────────────────
PYTHON=""
for candidate in python3 python3.11 python3.10 python3.9 python; do
    if command -v "$candidate" &>/dev/null; then
        VER=$("$candidate" -c "import sys; print(sys.version_info.major * 10 + sys.version_info.minor)" 2>/dev/null || echo 0)
        if [ "$VER" -ge 39 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo " [ERROR] Python 3.9+ not found."
    echo "         Install via your package manager:"
    echo "           sudo apt install python3   # Debian/Ubuntu"
    echo "           brew install python        # macOS"
    exit 1
fi

echo " Python : $(command -v $PYTHON)"
echo " Version: $($PYTHON --version)"
echo ""

# ── Install dependencies ───────────────────────────────────────────────────────
echo " Installing dependencies..."
"$PYTHON" -m pip install --upgrade pip --quiet --disable-pip-version-check
"$PYTHON" -m pip install aiohttp aiosqlite pyyaml --quiet --disable-pip-version-check
echo " Dependencies OK."
echo ""

# ── Create wphawk wrapper ──────────────────────────────────────────────────────
WRAPPER=""
for dir in /usr/local/bin "$HOME/.local/bin" "$HOME/bin"; do
    if [ -d "$dir" ] && [ -w "$dir" ]; then
        WRAPPER="$dir/wphawk"
        break
    fi
done

if [ -z "$WRAPPER" ]; then
    mkdir -p "$HOME/.local/bin"
    WRAPPER="$HOME/.local/bin/wphawk"
fi

cat > "$WRAPPER" << EOF
#!/usr/bin/env bash
exec "$PYTHON" "$WPHAWK_PY" "\$@"
EOF
chmod +x "$WRAPPER"

echo " Created : $WRAPPER"
echo ""
echo " ─────────────────────────────────────────"
echo "  Done!  Run:"
echo ""
echo "    wphawk -u https://target.com"
echo ""
echo "  Full scan (all modules):"
echo ""
echo "    wphawk -u https://target.com --full-scan"
echo " ─────────────────────────────────────────"
echo ""

# Remind about PATH if $HOME/.local/bin or $HOME/bin was used
if [[ "$WRAPPER" == "$HOME"* ]]; then
    WDIR="$(dirname $WRAPPER)"
    if [[ ":$PATH:" != *":$WDIR:"* ]]; then
        echo " NOTE: Add this to your ~/.bashrc or ~/.zshrc:"
        echo "   export PATH=\"\$PATH:$WDIR\""
        echo ""
    fi
fi
