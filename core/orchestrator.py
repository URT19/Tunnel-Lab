import time
import threading
import subprocess
import shlex
from pathlib import Path

from core.context import TestContext
from core.network import Allocator
from core.executor import Executor
from core.channel import ChannelClient
from core.ssh_setup import SSHSetup
from core.advisor import Advisor
from core.payload import (
    tcp_receiver, udp_receiver, tcp_send, udp_send,
    tcp6_receiver, udp6_receiver, tcp6_send, udp6_send,
)
from tunnels.registry import load_all


TCP_PORT = 9991
UDP_PORT = 9992
AGENT_PORT = 51888


class Orchestrator:
    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.alloc = Allocator(
            pool=cfg.get("network", "tunnel_pool", default="10.250.0.0/16"),
            prefix=30,
        )
        self.dry = cfg.get("tests", "dry_run", default=False)
        self.exec = Executor(dry_run=self.dry, logger=log)
        self.modules = load_all()
        self.advisor = Advisor()
        self.ssh = SSHSetup(cfg, log)
        self.channel = None
        self.agent_port = None
        self.base_dir = Path(__file__).resolve().parent.parent

    def setup_servers(self):
        self.log.info("setup: deploying agent on server B")
        self.ssh.open_firewall_local(AGENT_PORT)
        self.ssh.open_firewall(AGENT_PORT)
        self.ssh.deploy_agent(self.base_dir, remote_dir="/root/tunnel-lab")
        self.ssh.stop_agent()
        time.sleep(0.5)
        self.ssh.start_agent(port=AGENT_PORT)
        time.sleep(2.0)
        port = self.ssh.get_agent_port() or str(AGENT_PORT)
        self.agent_port = int(port)
        host_b = self.cfg.get("server_b", "host", default="")
        self.channel = ChannelClient(host_b, self.agent_port, logger=self.log)
        pong = self.channel.request({"type": "PING"}, expect="PONG", timeout=10)
        self.log.info(f"channel ready: {pong}")
        return True

    def teardown_servers(self):
        if self.channel:
            self.channel.close()
        self.ssh.stop_agent()

    def list_modules(self):
        return sorted(self.modules.keys())

    def sleep(self, s):
        time.sleep(s)

    def local(self, cmd, timeout=60):
        return self.exec.run(cmd)

    def local_many(self, cmds):
        for c in cmds:
            self.exec.run(c)

    def remote(self, msg, expect, timeout=60):
        return self.channel.request(msg, expect=expect, timeout=timeout)

    def remote_many(self, cmds):
        return self.remote({"type": "RUN_MANY", "commands": cmds},
                           expect="RESULTS", timeout=120)

    def remote_run(self, cmd, timeout=60):
        return self.remote({"type": "RUN", "command": cmd},
                           expect="RESULT", timeout=timeout)

    def icmp_from_a(self, target):
        for cmd in (f"ping -c 3 -W 3 {target}", f"ping -c 1 -W 2 {target}"):
            rc, _, _ = self.local(cmd)
            if rc == 0:
                return True
        return False

    def icmp_from_b(self, target):
        for cmd in (f"ping -c 3 -W 3 {target}", f"ping -c 1 -W 2 {target}"):
            try:
                r = self.remote_run(cmd, timeout=25)
                if r.get("rc", 1) == 0:
                    return True
            except Exception:
                continue
        return False

    def icmp6_from_a(self, target):
        for cmd in (f"ping -6 -c 3 -W 5 {target}",
                    f"ping6 -c 3 -W 5 {target}",
                    f"ping -6 -c 1 -W 3 {target}"):
            rc, _, _ = self.local(cmd)
            if rc == 0:
                return True
        return False

    def icmp6_from_b(self, target):
        for cmd in (f"ping -6 -c 3 -W 5 {target}",
                    f"ping6 -c 3 -W 5 {target}",
                    f"ping -6 -c 1 -W 3 {target}"):
            try:
                r = self.remote_run(cmd, timeout=25)
                if r.get("rc", 1) == 0:
                    return True
            except Exception:
                continue
        return False

    def tcp_a_to_b(self, target, tunnel, direction):
        try:
            self.remote({"type": "RECV_TCP", "port": TCP_PORT, "timeout": 15},
                        expect="RECV_TCP_RESULT", timeout=20)
            return True
        except Exception as e:
            self.log.warn(f"tcp_a_to_b: {e}")
            return False

    def tcp_b_to_a(self, target, tunnel, direction):
        res = {"ok": False}
        def listener():
            r = tcp_receiver(TCP_PORT, timeout=20)
            res["ok"] = r.get("ok", False)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.8)
        try:
            r = self.remote(
                {"type": "SEND_TCP", "host": target, "port": TCP_PORT,
                 "tunnel": tunnel, "direction": direction, "timeout": 5},
                expect="SEND_TCP_RESULT", timeout=15)
            sent_ok = r.get("ok", False)
        except Exception as e:
            self.log.warn(f"tcp_b_to_a send: {e}")
            sent_ok = False
        th.join(timeout=5)
        return sent_ok and res.get("ok", False)

    def udp_a_to_b(self, target, tunnel, direction):
        try:
            self.remote({"type": "RECV_UDP", "port": UDP_PORT, "timeout": 15},
                        expect="RECV_UDP_RESULT", timeout=20)
            return True
        except Exception as e:
            self.log.warn(f"udp_a_to_b: {e}")
            return False

    def udp_b_to_a(self, target, tunnel, direction):
        res = {"ok": False}
        def listener():
            r = udp_receiver(UDP_PORT, timeout=20)
            res["ok"] = r.get("ok", False)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.8)
        try:
            r = self.remote(
                {"type": "SEND_UDP", "host": target, "port": UDP_PORT,
                 "tunnel": tunnel, "direction": direction, "timeout": 5},
                expect="SEND_UDP_RESULT", timeout=15)
            sent_ok = r.get("ok", False)
        except Exception as e:
            self.log.warn(f"udp_b_to_a send: {e}")
            sent_ok = False
        th.join(timeout=5)
        return sent_ok and res.get("ok", False)

    def tcp6_a_to_b(self, target, tunnel, direction):
        try:
            self.remote({"type": "RECV_TCP6", "port": TCP_PORT, "timeout": 15},
                        expect="RECV_TCP6_RESULT", timeout=20)
            return True
        except Exception as e:
            self.log.warn(f"tcp6_a_to_b: {e}")
            return False

    def tcp6_b_to_a(self, target, tunnel, direction):
        res = {"ok": False}
        def listener():
            r = tcp6_receiver(TCP_PORT, timeout=20)
            res["ok"] = r.get("ok", False)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.8)
        try:
            r = self.remote(
                {"type": "SEND_TCP6", "host": target, "port": TCP_PORT,
                 "tunnel": tunnel, "direction": direction, "timeout": 5},
                expect="SEND_TCP6_RESULT", timeout=15)
            sent_ok = r.get("ok", False)
        except Exception as e:
            self.log.warn(f"tcp6_b_to_a send: {e}")
            sent_ok = False
        th.join(timeout=5)
        return sent_ok and res.get("ok", False)

    def udp6_a_to_b(self, target, tunnel, direction):
        try:
            self.remote({"type": "RECV_UDP6", "port": UDP_PORT, "timeout": 15},
                        expect="RECV_UDP6_RESULT", timeout=20)
            return True
        except Exception as e:
            self.log.warn(f"udp6_a_to_b: {e}")
            return False

    def udp6_b_to_a(self, target, tunnel, direction):
        res = {"ok": False}
        def listener():
            r = udp6_receiver(UDP_PORT, timeout=20)
            res["ok"] = r.get("ok", False)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.8)
        try:
            r = self.remote(
                {"type": "SEND_UDP6", "host": target, "port": UDP_PORT,
                 "tunnel": tunnel, "direction": direction, "timeout": 5},
                expect="SEND_UDP6_RESULT", timeout=15)
            sent_ok = r.get("ok", False)
        except Exception as e:
            self.log.warn(f"udp6_b_to_a send: {e}")
            sent_ok = False
        th.join(timeout=5)
        return sent_ok and res.get("ok", False)

    def start_local_bg(self, cmd, logfile="/tmp/tunnel-lab-bg.log"):
        wrapper = f"setsid sh -c {shlex.quote(cmd)} < /dev/null > {logfile} 2>&1 &"
        r = subprocess.run(wrapper, shell=True, capture_output=True)
        return r.returncode == 0

    def start_remote_bg(self, cmd, logfile="/tmp/tunnel-lab-bg.log"):
        full = (f"setsid sh -c {shlex.quote(cmd)} < /dev/null > {logfile} 2>&1 & "
                f"echo started")
        try:
            self.remote_run(full, timeout=15)
            return True
        except Exception:
            return False

    def ssh_l(self, which_from, which_to, local_port, remote_port,
              target_host=None, remote_user=None):
        host = self.cfg.get(which_to, "host", default="")
        port = int(self.cfg.get(which_to, "ssh_port", default=22))
        user = self.cfg.get(which_to, "user", default="root")
        pw = self.cfg.get(which_to, "password", default="") or ""
        target = target_host or "127.0.0.1"
        ssh_cmd = (f"ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                   f"-o ServerAliveInterval=15 -o ExitOnForwardFailure=yes "
                   f"-p {port} -L {local_port}:{target}:{remote_port} -N -f {user}@{host}")
        if pw:
            ssh_cmd = f"sshpass -p {shlex.quote(pw)} {ssh_cmd}"
        if which_from == "server_a":
            subprocess.run("command -v sshpass >/dev/null 2>&1 || apt-get install -y sshpass",
                           shell=True, capture_output=True, timeout=60)
            r = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True)
            return r.returncode == 0, r.stderr
        else:
            cmd = (f"command -v sshpass >/dev/null 2>&1 || "
                   f"apt-get install -y sshpass >/dev/null 2>&1 || true; "
                   f"{ssh_cmd}")
            try:
                r = self.remote_run(cmd, timeout=40)
                return r.get("rc", 1) == 0, r.get("stderr", "")
            except Exception as e:
                return False, str(e)

    def kill_port_local(self, port):
        subprocess.run(f"fuser -k {port}/tcp 2>/dev/null || true",
                       shell=True, capture_output=True)

    def kill_port_remote(self, port):
        try:
            self.remote_run(f"fuser -k {port}/tcp 2>/dev/null || true", timeout=10)
        except Exception:
            pass

    def tcp_probe_local(self, host, port, payload=b"PING", timeout=5):
        import socket
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.sendall(payload)
            s.close()
            return True
        except Exception:
            return False

    def cleanup_stale(self):
        """Kill leftover nc/ssh/tunnels on both sides before a test."""
        # local (A)
        subprocess.run("pkill -9 nc 2>/dev/null || true", shell=True,
                       capture_output=True)
        subprocess.run("pkill -9 -f 'ssh -L 199' 2>/dev/null || true",
                       shell=True, capture_output=True)
        for p_ in (19998, 19999):
            subprocess.run(f"fuser -k {p_}/tcp 2>/dev/null || true",
                           shell=True, capture_output=True)
        # remote (B) via agent
        try:
            self.remote_run(
                "pkill -9 nc 2>/dev/null || true; "
                "pkill -9 -f 'ssh -L 199' 2>/dev/null || true; "
                "fuser -k 19998/tcp 2>/dev/null || true; "
                "fuser -k 19999/tcp 2>/dev/null || true; "
                "echo cleaned",
                timeout=15,
            )
        except Exception as e:
            if self.log:
                self.log.warn(f"cleanup_stale remote: {e}")

    def run_test(self, tunnel_id):
        mod = self.modules.get(tunnel_id)
        if not mod:
            return {"tunnel": tunnel_id, "status": "FAIL", "reason": "UNKNOWN"}

        local, remote = self.alloc.next_pair()

        iface = getattr(mod, "interface_name_override", None)
        if not iface:
            prefix = self.cfg.get("network", "interface_prefix", default="tl-")
            iface = f"{prefix}{tunnel_id}0"

        ctx = TestContext(
            test_id=f"{tunnel_id.upper()}-TEST",
            tunnel_id=tunnel_id,
            server_a_ip=self.cfg.get("server_a", "host", default=""),
            server_b_ip=self.cfg.get("server_b", "host", default=""),
            tunnel_local_ip=local,
            tunnel_remote_ip=remote,
            interface_name=iface,
            dry_run=self.dry,
        )

        self.cleanup_stale()
        result = {"tunnel": tunnel_id, "status": "FAIL", "direct": {}, "reverse": {},
                  "applicable_stages": list(getattr(mod, "applicable_stages",
                                        ("iface_a","iface_b","icmp","tcp","udp")))}

        applicable = getattr(mod, "applicable_stages",
                             ("iface_a", "iface_b", "icmp", "tcp", "udp"))
        mandatory = [k for k in ("iface_a", "iface_b", "tcp", "udp") if k in applicable]

        def phase_ok(stages):
            if not stages:
                return False
            for k in mandatory:
                if not stages.get(k, False):
                    return False
            return True

        try:
            mod.setup(ctx, self)
            result["direct"] = mod.run_direct(ctx, self) or {}
            if not phase_ok(result["direct"]):
                failed = [k for k, v in result["direct"].items() if not v]
                result["reason"] = "DIRECT_" + (failed[0].upper() if failed else "UNKNOWN")
        except Exception as e:
            result["reason"] = "REMOTE_ERROR"
            result["error"] = str(e)
            self.log.error(f"direct phase failed: {e}")
        finally:
            try:
                mod.teardown(ctx, self)
                self.local_many(mod.cleanup_commands_a(ctx))
                self.remote_many(mod.cleanup_commands_b(ctx))
            except Exception as e:
                self.log.warn(f"direct cleanup: {e}")

        time.sleep(1)

        try:
            mod.setup(ctx, self)
            result["reverse"] = mod.run_reverse(ctx, self) or {}
            if not phase_ok(result["reverse"]):
                failed = [k for k, v in result["reverse"].items() if not v]
                result["reason"] = "REVERSE_" + (failed[0].upper() if failed else "UNKNOWN")
        except Exception as e:
            result["reason"] = "REMOTE_ERROR"
            result["error"] = str(e)
            self.log.error(f"reverse phase failed: {e}")
        finally:
            try:
                mod.teardown(ctx, self)
                self.local_many(mod.cleanup_commands_a(ctx))
                self.remote_many(mod.cleanup_commands_b(ctx))
            except Exception as e:
                self.log.warn(f"reverse cleanup: {e}")

        direct_ok = phase_ok(result["direct"])
        reverse_ok = phase_ok(result["reverse"])
        result["status"] = "PASS" if (direct_ok and reverse_ok) else "FAIL"
        result["direct_ok"] = direct_ok
        result["reverse_ok"] = reverse_ok
        result["explain"] = self.advisor.explain(result)
        return result
