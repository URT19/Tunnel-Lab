#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VERSION="$(cat VERSION 2>/dev/null || echo 0.0.0)"
OUT_NAME="tunnel-lab-v${VERSION}-public"
OUT_DIR="/tmp/${OUT_NAME}"
TAR_PATH="${ROOT}/${OUT_NAME}.tar.gz"

# -------- clean previous --------
rm -rf "$OUT_DIR"
rm -f "$TAR_PATH"
mkdir -p "$OUT_DIR"

# -------- whitelist: only these get copied --------
FILES_TO_COPY=(
    "VERSION"
    "CHANGELOG.md"
    "ARCHITECTURE.md"
    "README.md"
    "requirements.txt"
    "main.py"
    "menu.sh"
    "run.sh"
    "install.sh"
    "export.sh"
)

DIRS_TO_COPY=(
    "core"
    "agents"
    "tunnels"
    "scripts"
    "tests"
    "ui"
)

# -------- copy files --------
for f in "${FILES_TO_COPY[@]}"; do
    [ -f "$f" ] && cp "$f" "$OUT_DIR/"
done

# -------- copy dirs, excluding sensitive/binary stuff --------
for d in "${DIRS_TO_COPY[@]}"; do
    [ -d "$d" ] || continue
    mkdir -p "$OUT_DIR/$d"
    rsync -a --quiet \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='*.pyo' \
        --exclude='.pytest_cache/' \
        --exclude='.mypy_cache/' \
        --exclude='*.bak' \
        --exclude='*.backup' \
        "$d/" "$OUT_DIR/$d/"
done

# -------- create empty placeholders (so runtime dirs exist) --------
mkdir -p "$OUT_DIR/logs" "$OUT_DIR/results" "$OUT_DIR/backups"
cat > "$OUT_DIR/logs/.gitkeep" <<'EOF'
EOF
cat > "$OUT_DIR/results/.gitkeep" <<'EOF'
EOF
cat > "$OUT_DIR/backups/.gitkeep" <<'EOF'
EOF

# -------- config.yaml: template only, no real values --------
cat > "$OUT_DIR/config.yaml" <<'YEOF'
version: REPLACE_WITH_CURRENT_VERSION
server_a:
  host: ""
  ssh_port: 22
  user: root
  password: ""
server_b:
  host: ""
  ssh_port: 22
  user: root
  password: ""
network:
  control_net: 10.254.0.0/24
  tunnel_pool: 10.250.0.0/16
  interface_prefix: tl-
tests:
  enabled: []
  timeout_sec: 20
  payload_size: 64
  dry_run: false
YEOF
# fill version placeholder
sed -i "s/REPLACE_WITH_CURRENT_VERSION/${VERSION}/" "$OUT_DIR/config.yaml"

# -------- add .gitignore --------
cat > "$OUT_DIR/.gitignore" <<'GEOF'
__pycache__/
*.pyc
*.pyo
.venv/
venv/
logs/*.log
logs/*.jsonl
logs/agent_copy.txt
logs/tunnels_status.json
results/*.json
backups/*.bak
config.yaml
.env
*.tar.gz
*.swp
.DS_Store
GEOF

# -------- safety scan: look for leaked strings --------
echo "[*] scanning for sensitive patterns..."
LEAKS=0

# collect real server IPs from the current config.yaml (before template overwrite)
REAL_IPS=""
if [ -f "$ROOT/config.yaml" ]; then
    REAL_IPS=$(grep -E '^\s*host:' "$ROOT/config.yaml" 2>/dev/null \
        | sed -E 's/.*host:\s*"?([^"]+)"?.*/\1/' \
        | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' || true)
fi

# scan for any real server IP
if [ -n "$REAL_IPS" ]; then
    for ip in $REAL_IPS; do
        if grep -rq "$ip" "$OUT_DIR" 2>/dev/null; then
            echo "[!] WARNING: found real server IP $ip in package"
            grep -rl "$ip" "$OUT_DIR" 2>/dev/null | head -5
            LEAKS=1
        fi
    done
fi

# scan for generic public IPv4 (excluding well-known / private / doc ranges)
FOUND=$(grep -rEn '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' "$OUT_DIR" 2>/dev/null \
    | grep -vE \
        '127\.0\.0\.1|0\.0\.0\.0|255\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.' \
    | grep -vE '1\.1\.1\.1|8\.8\.8\.8|1\.0\.0\.1|9\.9\.9\.9' \
    | grep -vE '\.0\.0\.(0|1)|/30|/24|/16' \
    | grep -vE 'export\.sh' \
    || true)

if [ -n "$FOUND" ]; then
    echo "[!] WARNING: possible public IPs found:"
    echo "$FOUND" | head -10
    LEAKS=1
fi

# real passwords in config.yaml (should be empty)
if grep -E 'password:\s*"[^"]+"' "$OUT_DIR/config.yaml" >/dev/null 2>&1; then
    echo "[!] WARNING: config.yaml still contains a password"
    LEAKS=1
fi

# scan for any leftover password in the tree
if grep -rEn 'password:\s*[^"\s]' "$OUT_DIR" --include='*.yaml' --include='*.yml' 2>/dev/null \
    | grep -vE 'password:\s*""' >/dev/null; then
    echo "[!] WARNING: non-empty password field found:"
    grep -rEn 'password:\s*[^"\s]' "$OUT_DIR" --include='*.yaml' --include='*.yml' 2>/dev/null | head -5
    LEAKS=1
fi

if [ "$LEAKS" = "0" ]; then
    echo "[+] no leaked IPs / passwords detected"
fi

# -------- pack --------
tar -czf "$TAR_PATH" -C "/tmp" "$OUT_NAME"
echo
echo "[+] created: $TAR_PATH"
echo "    size: $(du -h "$TAR_PATH" | awk '{print $1}')"
echo
echo "    contents preview:"
tar -tzf "$TAR_PATH" | head -40
echo
echo "[i] upload to GitHub:"
echo "    gh release create v${VERSION} \"$TAR_PATH\" --title \"v${VERSION}\" --notes-file CHANGELOG.md"
echo "    or: use web UI to create a release and upload the tarball."
