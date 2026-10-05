#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

CFG="$ROOT/config.yaml"
PY="python3"
[ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python"

R="\033[0m"; G="\033[1;32m"; Y="\033[1;33m"; C="\033[1;36m"; RE="\033[1;31m"; B="\033[1m"

# ---------------- helpers ----------------
cfg_get() {
    $PY - "$1" "$2" <<'PYEOF'
import sys, yaml
path, key = sys.argv[1], sys.argv[2]
with open(path) as f:
    d = yaml.safe_load(f) or {}
cur = d
for k in key.split("."):
    if not isinstance(cur, dict) or k not in cur:
        print(""); sys.exit(0)
    cur = cur[k]
print("" if cur is None else cur)
PYEOF
}

cfg_set() {
    $PY - "$1" "$2" "$3" <<'PYEOF'
import sys, yaml
path, key, val = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path) as f:
    d = yaml.safe_load(f) or {}
parts = key.split(".")
cur = d
for k in parts[:-1]:
    cur = cur.setdefault(k, {})
cur[parts[-1]] = val
with open(path, "w") as f:
    yaml.safe_dump(d, f, sort_keys=False, allow_unicode=False)
PYEOF
}

ask() {
    local title="$1" prompt="$2" cur="$3"
    whiptail --title "$title" --inputbox "$prompt" 10 70 "$cur" 3>&1 1>&2 2>&3
}

ask_pass() {
    local title="$1" prompt="$2"
    whiptail --title "$title" --passwordbox "$prompt" 10 70 "" 3>&1 1>&2 2>&3
}

msg() {
    whiptail --title "$1" --msgbox "$2" 12 70
}

confirm() {
    whiptail --title "$1" --yesno "$2" 10 70
}

pause() {
    echo
    read -r -p "Press Enter to continue..." _
}

banner() {
    clear
    echo -e "${C}=========================================${R}"
    echo -e "${C}   $1${R}"
    echo -e "${C}=========================================${R}"
    echo
}

# ---------------- configure one server ----------------
config_server() {
    local key="$1" label="$2"
    local host port user pw

    host=$(cfg_get "$CFG" "$key.host")
    port=$(cfg_get "$CFG" "$key.ssh_port"); [ -z "$port" ] && port="22"
    user=$(cfg_get "$CFG" "$key.user"); [ -z "$user" ] && user="root"
    pw=$(cfg_get "$CFG" "$key.password")

    local v
    v=$(ask "$label - host" "Public IP / hostname of $label:" "$host") || return
    host="$v"

    v=$(ask "$label - ssh port" "SSH port (default 22):" "$port") || return
    [ -n "$v" ] && port="$v"

    v=$(ask "$label - ssh user" "SSH user (default root):" "$user") || return
    [ -n "$v" ] && user="$v"

    v=$(ask_pass "$label - password" "SSH password for $user@$host (empty = keep current):") || return
    [ -n "$v" ] && pw="$v"

    local show_pw
    [ -n "$pw" ] && show_pw="********" || show_pw="(empty)"

    if confirm "$label - confirm" "Save this configuration?

  host:     $host
  ssh_port: $port
  user:     $user
  password: $show_pw"; then
        cfg_set "$CFG" "$key.host" "$host"
        cfg_set "$CFG" "$key.ssh_port" "$port"
        cfg_set "$CFG" "$key.user" "$user"
        cfg_set "$CFG" "$key.password" "$pw"
        msg "$label" "Saved."
    else
        msg "$label" "Cancelled."
    fi
}

# ---------------- SYNC servers ----------------
sync_servers() {
    banner "SYNC Servers"
    local a b
    a=$(cfg_get "$CFG" "server_a.host")
    b=$(cfg_get "$CFG" "server_b.host")
    if [ -z "$a" ] || [ -z "$b" ]; then
        echo -e "${RE}[!]${R} Server A or B host is empty. Configure them first."
        pause
        return
    fi
    echo -e "${G}[+]${R} A = $a"
    echo -e "${G}[+]${R} B = $b"
    echo
    set +e
    timeout 120 $PY -u "$ROOT/scripts/do_setup.py"
    rc=$?
    set -e
    echo
    if [ $rc -eq 0 ]; then
        echo -e "${G}[+]${R} SYNC done. Channel is ready."
    else
        echo -e "${RE}[!]${R} SYNC failed (exit $rc)."
    fi
    pause
}

# ---------------- select tunnels ----------------
select_tunnels() {
    local items=()
    for f in "$ROOT"/tunnels/*.py; do
        local name
        name=$(basename "$f" .py)
        case "$name" in __init__|base|registry) continue ;; esac
        case "$name" in _*) continue ;; esac
        items+=("$name" "" "off")
    done

    local selected
    selected=$(whiptail --title "Select tunnels" \
        --checklist "Space=toggle  Tab=OK  Esc=cancel" \
        25 70 15 "${items[@]}" 3>&1 1>&2 2>&3) || return

    selected=$(echo "$selected" | tr -d '"')
    $PY - "$CFG" "$selected" <<'PYEOF'
import sys, yaml
path = sys.argv[1]
items = sys.argv[2].split()
with open(path) as f:
    d = yaml.safe_load(f) or {}
d.setdefault("tests", {})["enabled"] = items
with open(path, "w") as f:
    yaml.safe_dump(d, f, sort_keys=False, allow_unicode=False)
print("saved:", items)
PYEOF
    msg "Select tunnels" "Selected: ${selected:-none}"
}

# ---------------- run tests ----------------
run_tests() {
    banner "Run tests"
    local selected
    selected=$(cfg_get "$CFG" "tests.enabled")
    if [ -z "$selected" ] || [ "$selected" = "[]" ]; then
        echo -e "${Y}[!]${R} No tunnels selected. Use option 4 first."
        pause
        return
    fi
    set +e
    timeout 600 $PY -u "$ROOT/scripts/do_run.py"
    rc=$?
    set -e
    echo
    if [ $rc -eq 0 ]; then
        echo -e "${G}[+]${R} Tests finished."
    else
        echo -e "${RE}[!]${R} Tests failed (exit $rc)."
    fi
    pause
}

# ---------------- channel status ----------------
show_status() {
    banner "Channel status"
    set +e
    timeout 30 $PY -u "$ROOT/scripts/do_status.py"
    rc=$?
    set -e
    echo
    [ $rc -eq 0 ] && echo -e "${G}[+]${R} OK." || echo -e "${RE}[!]${R} Status returned $rc."
    pause
}

# ---------------- agent log ----------------
agent_log() {
    banner "Agent log on B"
    timeout 20 $PY -u - <<'PYEOF' 2>/dev/null || echo "(failed)"
from pathlib import Path
from core.config import Config
from core.ssh_setup import SSHSetup
from core.logger import Logger
base = Path.cwd()
cfg = Config(base / "config.yaml")
log = Logger(base / "logs")
ssh = SSHSetup(cfg, log)
print(ssh.tail_agent_log(40))
PYEOF
    pause
}

view_config() {
    whiptail --title "config.yaml" --scrolltext --msgbox "$(cat "$CFG")" 25 80
}

# ---------------- main menu ----------------
while true; do
    A_HOST=$(cfg_get "$CFG" "server_a.host")
    B_HOST=$(cfg_get "$CFG" "server_b.host")
    A_SHOW="${A_HOST:-not set}"
    B_SHOW="${B_HOST:-not set}"

    CHOICE=$(whiptail --title "TUNNEL LAB" --menu \
        "A = $A_SHOW    B = $B_SHOW" 20 75 10 \
        "1" "Configure Server A" \
        "2" "Configure Server B" \
        "3" "SYNC Servers" \
        "4" "Select tunnels" \
        "5" "Run tests" \
        "6" "Channel status" \
        "7" "Agent log on B" \
        "8" "View config.yaml" \
        "9" "Launch live dashboard (Textual)" \
        "0" "Exit" \
        3>&1 1>&2 2>&3) || exit 0

    case "$CHOICE" in
        1) config_server "server_a" "Server A" ;;
        2) config_server "server_b" "Server B" ;;
        3) sync_servers ;;
        4) select_tunnels ;;
        5) run_tests ;;
        6) show_status ;;
        7) agent_log ;;
        8) view_config ;;
        9) $PY "$ROOT/main.py" ;;
        0) exit 0 ;;
    esac
done
