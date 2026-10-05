#!/usr/bin/env python3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import Config
from core.logger import Logger
from core.ssh_setup import SSHSetup
from core.channel import ping_channel


AGENT_PORT = 51888


def log(msg):
    print(f"    {msg}", flush=True)


def _local_version():
    try:
        return (ROOT / "VERSION").read_text().strip()
    except Exception:
        return "?"


def _remote_version(ssh):
    try:
        rc, out, err = ssh.run("cat /root/tunnel-lab/VERSION 2>/dev/null || echo ?",
                               which="server_b", timeout=10)
        return out.strip() or "?"
    except Exception:
        return "?"


# Required apt packages on B
APT_PKGS = [
    "python3", "python3-pip",
    "iproute2", "iputils-ping", "netcat-openbsd",
    "wireguard-tools", "wireguard",
    "whiptail",
    "curl", "wget",
    "sshpass",
    "tcpdump",
    "strongswan", "strongswan-pki",
    "libcharon-extra-plugins", "libcharon-extauth-plugins",
    "openvpn",
    "nftables", "iptables",
    "resolvconf",
]

# Required commands (binary name -> apt pkg)
REQUIRED_CMDS = {
    "python3": "python3",
    "pip3": "python3-pip",
    "ip": "iproute2",
    "ping": "iputils-ping",
    "nc": "netcat-openbsd",
    "wg": "wireguard-tools",
    "whiptail": "whiptail",
    "curl": "curl",
    "wget": "wget",
    "sshpass": "sshpass",
    "tcpdump": "tcpdump",
    "ipsec": "strongswan",
    "openvpn": "openvpn",
    "iptables": "iptables",
    "nft": "nftables",
}


def _ensure_remote_pkgs(ssh):
    """Install all required apt packages on B."""
    pkg_list = " ".join(APT_PKGS)
    log(f"  ensuring apt packages on B ({len(APT_PKGS)} pkgs)")
    cmd = (
        "export DEBIAN_FRONTEND=noninteractive; "
        "apt-get update -qq; "
        f"apt-get install -y -qq {pkg_list} "
        "> /tmp/tlab-apt.log 2>&1; "
        "rc=$?; "
        "modprobe wireguard 2>/dev/null || true; "
        "exit $rc"
    )
    rc, out, err = ssh.run(cmd, which="server_b", timeout=600)
    if rc != 0:
        log(f"  apt-get returned rc={rc} (check /tmp/tlab-apt.log on B)")
        return False
    log("  apt packages installed")
    return True


def _verify_remote_cmds(ssh):
    """Verify all required commands exist on B."""
    checks = " ; ".join(
        f"command -v {cmd} >/dev/null 2>&1 || echo MISSING:{cmd}"
        for cmd in REQUIRED_CMDS.keys()
    )
    rc, out, err = ssh.run(checks, which="server_b", timeout=30)
    missing = [ln.split("MISSING:")[1]
               for ln in (out or "").splitlines() if ln.startswith("MISSING:")]
    if missing:
        log(f"  missing commands on B: {missing}")
        return False
    log("  all required commands present on B")
    return True


def _ensure_remote_dirs(ssh):
    cmd = "mkdir -p /root/tunnel-lab /root/tunnel-lab/logs /root/tunnel-lab/core /root/tunnel-lab/agents"
    ssh.run(cmd, which="server_b", timeout=15)


def _verify_kernel_modules(ssh):
    """Load tunnel-related kernel modules on B."""
    mods = ["wireguard", "ip_gre", "ipip", "sit", "vxlan", "tun"]
    cmd = "; ".join(f"modprobe {m} 2>/dev/null || true" for m in mods)
    ssh.run(cmd, which="server_b", timeout=30)
    rc, out, err = ssh.run("awk '{print $1}' /proc/modules", which="server_b", timeout=15)
    loaded = set((out or "").split())
    log(f"  modules loaded on B: {sorted(m for m in mods if m in loaded)}")


def main():
    base = ROOT
    cfg = Config(base / "config.yaml")
    log_ = Logger(base / "logs")
    ssh = SSHSetup(cfg, log_)

    a_host = cfg.get("server_a", "host", default="?")
    b_host = cfg.get("server_b", "host", default="?")

    ver_local = _local_version()
    ver_remote_before = _remote_version(ssh)

    print()
    print("    " + "=" * 60)
    print(f"    SYNC SERVERS")
    print(f"    Server A : {a_host}")
    print(f"    Server B : {b_host}")
    print(f"    Local version  (A) : {ver_local}")
    print(f"    Remote version (B) : {ver_remote_before}   (before sync)")
    print("    " + "=" * 60)
    print()

    # 1) basic SSH check
    log("step 1/8  checking SSH to Server B")
    try:
        rc, out, err = ssh.run("echo ok && hostname && python3 --version",
                               which="server_b", timeout=15)
        lines = out.strip().splitlines()
        log(f"           ssh      : OK")
        log(f"           hostname : {lines[1] if len(lines) > 1 else '?'}")
        log(f"           python   : {lines[2] if len(lines) > 2 else '?'}")
    except Exception as e:
        log(f"           FAILED: {e}")
        return 1

    # 2) ensure python3 (bootstrap; may be needed before apt big install)
    log("step 2/8  ensuring python3 on Server B")
    try:
        v = ssh.ensure_python()
        log(f"           ok: {v}")
    except Exception as e:
        log(f"           FAILED: {e}")
        return 2

    # 3) install apt packages on B
    log("step 3/8  installing required apt packages on Server B")
    try:
        _ensure_remote_pkgs(ssh)
    except Exception as e:
        log(f"           WARN: {e}")

    # 4) verify commands exist on B
    log("step 4/8  verifying required commands on Server B")
    try:
        _verify_remote_cmds(ssh)
    except Exception as e:
        log(f"           WARN: {e}")

    # 5) load kernel modules on B
    log("step 5/8  loading kernel modules on Server B")
    try:
        _verify_kernel_modules(ssh)
    except Exception as e:
        log(f"           WARN: {e}")

    # 6) create directories on B
    log("step 6/8  ensuring directories on Server B")
    _ensure_remote_dirs(ssh)
    log("           ok")

    # 7) pack + deploy bundle
    log("step 7/8  packing agent bundle (core + agents + VERSION)")
    try:
        bundle_path = ssh._build_bundle(base)
        log(f"           bundle: {bundle_path} ({bundle_path.stat().st_size} bytes)")
    except Exception as e:
        log(f"           FAILED: {e}")
        return 7

    log("           opening firewall on A and B")
    try:
        ssh.open_firewall_local(AGENT_PORT)
        ssh.open_firewall(AGENT_PORT)
        log("           firewall opened")
    except Exception as e:
        log(f"           WARN: {e}")

    log("           uploading and extracting bundle to B")
    try:
        ssh.deploy_agent(base)
        log("           ok")
    except Exception as e:
        log(f"           FAILED: {e}")
        log(ssh.tail_agent_log(20))
        return 7

    # 8) start agent + channel
    log("step 8/8  starting agent on B and opening channel")
    ssh.stop_agent()
    time.sleep(0.5)
    try:
        pid = ssh.start_agent(port=AGENT_PORT)
        time.sleep(2.0)
        log(f"           pid = {pid}")
    except Exception as e:
        log(f"           FAILED: {e}")
        log(ssh.tail_agent_log(20))
        return 8

    port = ssh.get_agent_port() or str(AGENT_PORT)
    log(f"           agent port = {port}")

    res = ping_channel(b_host, int(port), logger=log_, timeout=8)
    if res["ok"]:
        log(f"           PONG: {res['pong']}")
    else:
        log(f"           FAILED: {res['error']}")
        log(ssh.tail_agent_log(30))
        return 8

    ver_remote_after = _remote_version(ssh)

    print()
    print("    " + "=" * 60)
    print(f"    Local version  (A) : {ver_local}")
    print(f"    Remote version (B) : {ver_remote_after}   (after sync)")
    if ver_local == ver_remote_after:
        print(f"    VERSIONS MATCH")
    else:
        print(f"    WARNING: versions differ (A={ver_local}, B={ver_remote_after})")
    print("    " + "=" * 60)
    print()
    print("OK: channel ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
