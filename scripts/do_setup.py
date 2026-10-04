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


def main():
    base = ROOT
    cfg = Config(base / "config.yaml")
    log_ = Logger(base / "logs")
    ssh = SSHSetup(cfg, log_)

    log("step 1/6  packing agent bundle (core + agents)")
    try:
        bundle_path = ssh._build_bundle(base)
        log(f"           bundle: {bundle_path} ({bundle_path.stat().st_size} bytes)")
    except Exception as e:
        log(f"           FAILED: {e}")
        return 1

    log("step 2/6  ensuring python3 on Server B")
    try:
        v = ssh.ensure_python()
        log(f"           ok: {v}")
    except Exception as e:
        log(f"           FAILED: {e}")
        return 2

    log("step 3/6  opening firewall on A and B")
    try:
        ssh.open_firewall_local(AGENT_PORT)
        log(f"           A: tcp/{AGENT_PORT}, tcp/9991, udp/9992 opened")
        ssh.open_firewall(AGENT_PORT)
        log(f"           B: tcp/{AGENT_PORT}, tcp/9991, udp/9992 opened")
    except Exception as e:
        log(f"           WARN: {e}")

    log("step 4/6  uploading and extracting bundle to B")
    try:
        ssh.deploy_agent(base)
        log("           ok")
    except Exception as e:
        log(f"           FAILED: {e}")
        log(ssh.tail_agent_log(20))
        return 4

    log("step 5/6  starting agent on B (fixed port)")
    ssh.stop_agent()
    time.sleep(0.5)
    try:
        pid = ssh.start_agent(port=AGENT_PORT)
        time.sleep(2.0)
        log(f"           pid = {pid}")
    except Exception as e:
        log(f"           FAILED: {e}")
        log(ssh.tail_agent_log(20))
        return 5

    log("step 6/6  opening control channel and sending PING")
    port = ssh.get_agent_port() or str(AGENT_PORT)
    log(f"           agent port = {port}")

    host_b = cfg.get("server_b", "host", default="")
    res = ping_channel(host_b, int(port), logger=log_, timeout=8)
    if res["ok"]:
        log(f"           PONG: {res['pong']}")
    else:
        log(f"           FAILED: {res['error']}")
        log("           --- agent.log on B ---")
        log(ssh.tail_agent_log(30))
        return 6

    print()
    print("OK: channel ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
