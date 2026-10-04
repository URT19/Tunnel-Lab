#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import Config
from core.logger import Logger
from core.ssh_setup import SSHSetup
from core.channel import ping_channel


def main():
    base = ROOT
    cfg = Config(base / "config.yaml")
    log = Logger(base / "logs")
    ssh = SSHSetup(cfg, log)

    a = cfg.get("server_a", "host", default="") or "-"
    b = cfg.get("server_b", "host", default="") or "-"

    print(f"    Server A : {a}")
    print(f"    Server B : {b}")
    print()

    # 1) SSH to A (local, so just check we're here)
    print("  [1/4] Server A (local)")
    import socket
    print(f"        hostname : {socket.gethostname()}")

    # 2) SSH to B
    print("  [2/4] Server B via SSH")
    try:
        rc, out, err = ssh.run("echo ok && hostname && python3 --version",
                               which="server_b", timeout=15)
        lines = out.strip().splitlines()
        print(f"        ssh      : OK")
        print(f"        hostname : {lines[1] if len(lines) > 1 else '?'}")
        print(f"        python   : {lines[2] if len(lines) > 2 else '?'}")
    except Exception as e:
        print(f"        ssh      : FAILED ({e})")
        return 1

    # 3) Agent on B
    print("  [3/4] Agent on B")
    try:
        st = ssh.agent_status()
        if st["alive"]:
            print(f"        pid      : {st['pid']}")
            print(f"        port     : {st['port']}")
            print(f"        uptime   : {st['uptime']}")
        else:
            print("        pid      : NOT RUNNING")
            print("        tip      : run menu 3 (Setup channel) again")
            return 2
    except Exception as e:
        print(f"        status   : FAILED ({e})")
        return 2

    # 4) Channel A <-> B
    print("  [4/4] Channel A <-> B")
    if not st["port"]:
        print("        port     : unknown (agent didn't write agent.port)")
        return 3
    res = ping_channel(b, int(st["port"]), logger=log, timeout=5)
    if res["ok"]:
        print(f"        PING     : OK")
        print(f"        PONG     : {res['pong']}")
    else:
        print(f"        PING     : FAILED ({res['error']})")
        print("        tip      : check firewall on B (port must be open)")
        return 3

    print()
    print("  STATUS: ALL GOOD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
