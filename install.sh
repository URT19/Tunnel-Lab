#!/usr/bin/env bash
set -euo pipefail

R="\033[0m"; G="\033[1;32m"; Y="\033[1;33m"; C="\033[1;36m"; RE="\033[1;31m"; B="\033[1m"

echo -e "${C}=========================================${R}"
echo -e "${C}   Tunnel-Lab Installer v9.2.0${R}"
echo -e "${C}=========================================${R}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# ---------- distro info ----------
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO="${ID:-unknown}"; VER="${VERSION_ID:-unknown}"
else
    DISTRO="unknown"; VER="unknown"
fi
echo -e "${G}[+]${R} distro: $DISTRO $VER"

SUDO=""
if [ "$(id -u)" != "0" ]; then
    SUDO="sudo"
    if ! command -v sudo >/dev/null 2>&1; then
        echo -e "${RE}[!]${R} not root and no sudo. Please run as root."
        exit 1
    fi
fi

# ---------- apt packages ----------
echo -e "${C}[*]${R} installing system packages (apt)..."
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq \
    python3 python3-pip python3-venv python3-full \
    python3-paramiko python3-yaml \
    iproute2 iputils-ping netcat-openbsd \
    wireguard-tools \
    whiptail \
    curl wget \
    sshpass \
    tcpdump \
    strongswan strongswan-pki libcharon-extra-plugins libcharon-extauth-plugins \
    openvpn \
    nftables iptables \
    >/dev/null 2>&1 || true

# ---------- check python3 ----------
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RE}[!]${R} python3 still missing."
    exit 1
fi
PYV=$(python3 --version | awk '{print $2}')
echo -e "${G}[+]${R} python3 version: $PYV"

# ---------- textual version check ----------
TEXTUAL_OK=0
if python3 -c "import textual, sys; from importlib.metadata import version; v=version('textual'); parts=tuple(int(x) for x in v.split('.')[:2]); sys.exit(0 if parts >= (0,60) else 1)" 2>/dev/null; then
    TEXTUAL_OK=1
fi

NEED_VENV=0
python3 -c "import paramiko" 2>/dev/null || NEED_VENV=1
python3 -c "import yaml"     2>/dev/null || NEED_VENV=1
python3 -c "import rich"     2>/dev/null || NEED_VENV=1
[ "$TEXTUAL_OK" = "0" ] && NEED_VENV=1

# ---------- venv if needed ----------
if [ "$NEED_VENV" = "1" ]; then
    echo -e "${C}[*]${R} creating venv at .venv ..."
    rm -rf .venv
    python3 -m venv .venv
    ./.venv/bin/pip install --upgrade pip >/dev/null
    ./.venv/bin/pip install \
        "textual>=0.60" \
        "rich>=13.7" \
        "pyyaml>=6.0" \
        "paramiko>=3.4"
    echo -e "${G}[+]${R} venv ready"
    RUNNER="./.venv/bin/python"
else
    echo -e "${G}[+]${R} system packages are new enough"
    RUNNER="python3"
fi

# ---------- sshd tun options on B are handled by tunnel-lab itself ----------
# (do_setup.py adds PermitTunnel and reloads sshd when needed)

# ---------- helpers ----------
cat > "$ROOT/run.sh" <<EOF
#!/usr/bin/env bash
cd "\$(dirname "\$0")"
$RUNNER main.py "\$@"
stty sane 2>/dev/null || true
EOF
chmod +x "$ROOT/run.sh"

chmod +x "$ROOT/menu.sh" 2>/dev/null || true
chmod +x "$ROOT/export.sh" 2>/dev/null || true
chmod +x "$ROOT/install.sh"

# ---------- verify ----------
echo -e "${C}[*]${R} verifying imports and tools..."
$RUNNER - <<'PYEOF2'
import sys

mods = ["paramiko", "yaml", "rich", "textual"]
missing = []
for m in mods:
    try:
        mod = __import__(m)
        v = getattr(mod, "__version__", "?")
        print(f"  OK  {m} ({v})")
    except Exception as e:
        print(f"  ERR {m}: {e}")
        missing.append(m)

try:
    from textual.app import ComposeResult
    print("  OK  textual.app.ComposeResult")
except Exception as e:
    print(f"  ERR textual.app.ComposeResult: {e}")
    missing.append("textual-compose")

if missing:
    print(f"missing python modules: {missing}")
    sys.exit(1)
PYEOF2

# ---------- system tools check ----------
TOOLS="ip ping nc whiptail curl sshpass tcpdump"
MISSING_TOOLS=""
for t in $TOOLS; do
    if ! command -v "$t" >/dev/null 2>&1; then
        MISSING_TOOLS="$MISSING_TOOLS $t"
    else
        echo -e "  ${G}OK${R}  $t"
    fi
done

# optional tools (not fatal)
for t in wg ipsec openvpn; do
    if command -v "$t" >/dev/null 2>&1; then
        echo -e "  ${G}OK${R}  $t"
    else
        echo -e "  ${Y}--${R}  $t (optional, not installed)"
    fi
done

if [ -n "$MISSING_TOOLS" ]; then
    echo -e "${Y}[!]${R} missing tools:$MISSING_TOOLS"
    echo -e "${Y}    install manually if you need them${R}"
fi

echo
echo -e "${G}=========================================${R}"
echo -e "${G}  Install complete${R}"
echo -e "${G}=========================================${R}"
echo -e "  Run menu:  ${C}./menu.sh${R}"
echo -e "  Dashboard: ${C}./run.sh${R}"
echo -e "  Export:    ${C}./export.sh${R}"
