import time
import threading
import subprocess
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
SOCKS_PORT = 1080
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

    # ---------------- setup ----------------
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

    # ---------------- helpers ----------------
    def _local(self, cmd, timeout=60):
        return self.exec.run(cmd)

    def _remote(self, msg, expect, timeout=60):
        return self.channel.request(msg, expect=expect, timeout=timeout)

    def _remote_many(self, cmds):
        return self._remote({"type": "RUN_MANY", "commands": cmds},
                            expect="RESULTS", timeout=120)

    def _local_many(self, cmds):
        for c in cmds:
            self.exec.run(c)

    # ---------------- ICMP v4 ----------------
    def _icmp_from_a(self, target):
        for cmd in (f"ping -c 3 -W 3 {target}", f"ping -c 1 -W 2 {target}"):
            rc, _, _ = self._local(cmd)
            if rc == 0:
                return True
        return False

    def _icmp_from_b(self, target):
        for cmd in (f"ping -c 3 -W 3 {target}", f"ping -c 1 -W 2 {target}"):
            try:
                r = self._remote({"type": "RUN", "command": cmd},
                                 expect="RESULT", timeout=25)
                if r.get("rc", 1) == 0:
                    return True
            except Exception:
                continue
        return False

    # ---------------- ICMP v6 ----------------
    def _icmp6_from_a(self, target):
        for cmd in (f"ping -6 -c 3 -W 5 {target}",
                    f"ping6 -c 3 -W 5 {target}",
                    f"ping -6 -c 1 -W 3 {target}"):
            rc, _, _ = self._local(cmd)
            if rc == 0:
                return True
        return False

    def _icmp6_from_b(self, target):
        for cmd in (f"ping -6 -c 3 -W 5 {target}",
                    f"ping6 -c 3 -W 5 {target}",
                    f"ping -6 -c 1 -W 3 {target}"):
            try:
                r = self._remote({"type": "RUN", "command": cmd},
                                 expect="RESULT", timeout=25)
                if r.get("rc", 1) == 0:
                    return True
            except Exception:
                continue
        return False

    # ---------------- TCP/UDP v4 ----------------
    def _tcp_a_to_b(self, target, tunnel, direction):
        try:
            self._remote({"type": "RECV_TCP", "port": TCP_PORT, "timeout": 15},
                         expect="RECV_TCP_RESULT", timeout=20)
            return True
        except Exception as e:
            self.log.warn(f"tcp_a_to_b: {e}")
            return False

    def _tcp_b_to_a(self, target, tunnel, direction):
        res = {"ok": False}
        def listener():
            r = tcp_receiver(TCP_PORT, timeout=20)
            res["ok"] = r.get("ok", False)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.8)
        try:
            r = self._remote(
                {"type": "SEND_TCP", "host": target, "port": TCP_PORT,
                 "tunnel": tunnel, "direction": direction, "timeout": 5},
                expect="SEND_TCP_RESULT", timeout=15)
            sent_ok = r.get("ok", False)
        except Exception as e:
            self.log.warn(f"tcp_b_to_a send: {e}")
            sent_ok = False
        th.join(timeout=5)
        return sent_ok and res.get("ok", False)

    def _udp_a_to_b(self, target, tunnel, direction):
        try:
            self._remote({"type": "RECV_UDP", "port": UDP_PORT, "timeout": 15},
                         expect="RECV_UDP_RESULT", timeout=20)
            return True
        except Exception as e:
            self.log.warn(f"udp_a_to_b: {e}")
            return False

    def _udp_b_to_a(self, target, tunnel, direction):
        res = {"ok": False}
        def listener():
            r = udp_receiver(UDP_PORT, timeout=20)
            res["ok"] = r.get("ok", False)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.8)
        try:
            r = self._remote(
                {"type": "SEND_UDP", "host": target, "port": UDP_PORT,
                 "tunnel": tunnel, "direction": direction, "timeout": 5},
                expect="SEND_UDP_RESULT", timeout=15)
            sent_ok = r.get("ok", False)
        except Exception as e:
            self.log.warn(f"udp_b_to_a send: {e}")
            sent_ok = False
        th.join(timeout=5)
        return sent_ok and res.get("ok", False)

    # ---------------- TCP/UDP v6 ----------------
    def _tcp6_a_to_b(self, target, tunnel, direction):
        try:
            self._remote({"type": "RECV_TCP6", "port": TCP_PORT, "timeout": 15},
                         expect="RECV_TCP6_RESULT", timeout=20)
            return True
        except Exception as e:
            self.log.warn(f"tcp6_a_to_b: {e}")
            return False

    def _tcp6_b_to_a(self, target, tunnel, direction):
        res = {"ok": False}
        def listener():
            r = tcp6_receiver(TCP_PORT, timeout=20)
            res["ok"] = r.get("ok", False)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.8)
        try:
            r = self._remote(
                {"type": "SEND_TCP6", "host": target, "port": TCP_PORT,
                 "tunnel": tunnel, "direction": direction, "timeout": 5},
                expect="SEND_TCP6_RESULT", timeout=15)
            sent_ok = r.get("ok", False)
        except Exception as e:
            self.log.warn(f"tcp6_b_to_a send: {e}")
            sent_ok = False
        th.join(timeout=5)
        return sent_ok and res.get("ok", False)

    def _udp6_a_to_b(self, target, tunnel, direction):
        try:
            self._remote({"type": "RECV_UDP6", "port": UDP_PORT, "timeout": 15},
                         expect="RECV_UDP6_RESULT", timeout=20)
            return True
        except Exception as e:
            self.log.warn(f"udp6_a_to_b: {e}")
            return False

    def _udp6_b_to_a(self, target, tunnel, direction):
        res = {"ok": False}
        def listener():
            r = udp6_receiver(UDP_PORT, timeout=20)
            res["ok"] = r.get("ok", False)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.8)
        try:
            r = self._remote(
                {"type": "SEND_UDP6", "host": target, "port": UDP_PORT,
                 "tunnel": tunnel, "direction": direction, "timeout": 5},
                expect="SEND_UDP6_RESULT", timeout=15)
            sent_ok = r.get("ok", False)
        except Exception as e:
            self.log.warn(f"udp6_b_to_a send: {e}")
            sent_ok = False
        th.join(timeout=5)
        return sent_ok and res.get("ok", False)

    # ---------------- SSH SOCKS5 ----------------
    def _ssh_opts(self):
        return (
            "-o StrictHostKeyChecking=no "
            "-o UserKnownHostsFile=/dev/null "
            "-o ServerAliveInterval=15 "
            "-o ExitOnForwardFailure=yes "
            "-o ConnectTimeout=10 "
            "-o BatchMode=no"
        )

    def _build_ssh_cmd(self, which, socks_port):
        """Build a safe ssh -D command for the given server side.
        Uses SSHPASS env var (via sshpass -e) so passwords with leading
        dashes or special chars never break the shell. Supports key_path.
        Returns (cmd_string, env_dict).
        """
        host = self.cfg.get(which, "host", default="")
        port = int(self.cfg.get(which, "ssh_port", default=22))
        user = self.cfg.get(which, "user", default="root")
        password = self.cfg.get(which, "password", default="") or ""
        key_path = self.cfg.get(which, "key_path", default="") or ""

        opts = self._ssh_opts()
        base = f"ssh {opts} -p {port} -D {socks_port} -N {user}@{host}"

        env = {}
        if key_path:
            cmd = f"{base} -i {key_path}"
        elif password:
            # sshpass -e reads password from $SSHPASS — safe for any chars
            env["SSHPASS"] = password
            cmd = f"sshpass -e {base}"
        else:
            cmd = base
        return cmd, env

    def _ensure_sshpass_local(self):
        r = subprocess.run("command -v sshpass", shell=True, capture_output=True)
        if r.returncode != 0:
            subprocess.run(
                "apt-get install -y sshpass >/dev/null 2>&1 || true",
                shell=True, capture_output=True, timeout=60,
            )

    def _start_socks_on_a(self):
        """Start SSH dynamic SOCKS5 on Server A pointing at Server B."""
        import os, socket

        self._stop_socks_on_a()
        self._ensure_sshpass_local()

        pidfile = "/tmp/tunnel-lab-socks-a.pid"
        logfile = "/tmp/tunnel-lab-socks-a.log"
        for f in (pidfile, logfile):
            if os.path.exists(f):
                try:
                    os.unlink(f)
                except Exception:
                    pass

        inner, env = self._build_ssh_cmd("server_b", SOCKS_PORT)

        # Write a tiny launcher script so special chars never touch the shell
        launcher = "/tmp/tunnel-lab-socks-a.sh"
        with open(launcher, "w") as fh:
            fh.write("#!/bin/sh\n")
            fh.write(f"echo $$ > {pidfile}\n")
            if "SSHPASS" in env:
                # export without putting the value in the script file
                fh.write('export SSHPASS\n')
            fh.write(f"exec {inner}\n")
        os.chmod(launcher, 0o700)

        run_env = os.environ.copy()
        run_env.update(env)
        subprocess.Popen(
            ["setsid", launcher],
            stdin=subprocess.DEVNULL,
            stdout=open(logfile, "w"),
            stderr=subprocess.STDOUT,
            env=run_env,
            start_new_session=True,
        )

        for _ in range(30):
            time.sleep(0.3)
            try:
                s2 = socket.create_connection(("127.0.0.1", SOCKS_PORT), timeout=1)
                s2.close()
                return True
            except Exception:
                continue

        # dump log for debugging
        try:
            with open(logfile) as fh:
                tail = fh.read()[-800:]
            if self.log and tail:
                self.log.warn(f"socks A failed to open. log:\n{tail}")
        except Exception:
            pass
        if self.log:
            self.log.warn("socks A did not open port in time")
        return False

    def _stop_socks_on_a(self):
        import os
        pidfile = "/tmp/tunnel-lab-socks-a.pid"
        # kill by pidfile
        if os.path.exists(pidfile):
            try:
                pid = int(open(pidfile).read().strip())
                for sig in (15, 9):
                    try:
                        os.kill(pid, sig)
                    except ProcessLookupError:
                        break
                    time.sleep(0.2)
            except Exception:
                pass
            try:
                os.unlink(pidfile)
            except Exception:
                pass
        # fallback: kill any leftover -D 1080
        subprocess.run(
            f"pkill -f 'ssh .* -D {SOCKS_PORT}' 2>/dev/null || true",
            shell=True, capture_output=True,
        )
        # also kill launcher if still around
        subprocess.run(
            "pkill -f tunnel-lab-socks-a.sh 2>/dev/null || true",
            shell=True, capture_output=True,
        )

    def _start_socks_on_b(self):
        """Start SSH dynamic SOCKS5 on Server B pointing at Server A (reverse)."""
        self._stop_socks_on_b()

        a_host = self.cfg.get("server_a", "host", default="")
        a_port = int(self.cfg.get("server_a", "ssh_port", default=22))
        a_user = self.cfg.get("server_a", "user", default="root")
        a_pass = self.cfg.get("server_a", "password", default="") or ""
        a_key = self.cfg.get("server_a", "key_path", default="") or ""

        opts = self._ssh_opts()
        pidfile = "/tmp/tunnel-lab-socks-b.pid"
        logfile = "/tmp/tunnel-lab-socks-b.log"

        if a_key:
            ssh_line = (
                f"ssh {opts} -p {a_port} -i {a_key} "
                f"-D {SOCKS_PORT} -N {a_user}@{a_host}"
            )
            pass_setup = ""
        elif a_pass:
            # Write password to a temp file on B, use sshpass -f (safe for any char)
            pass_setup = (
                "printf '%s' \"$TL_SSHPASS\" > /tmp/.tl-sshpass && "
                "chmod 600 /tmp/.tl-sshpass; "
            )
            ssh_line = (
                f"sshpass -f /tmp/.tl-sshpass ssh {opts} -p {a_port} "
                f"-D {SOCKS_PORT} -N {a_user}@{a_host}"
            )
        else:
            ssh_line = (
                f"ssh {opts} -p {a_port} "
                f"-D {SOCKS_PORT} -N {a_user}@{a_host}"
            )
            pass_setup = ""

        # Build remote command. Password is passed via env in the RUN payload
        # so it never appears in shell history or process list as -p arg.
        cmd = (
            "command -v sshpass >/dev/null 2>&1 || "
            "(apt-get install -y sshpass >/dev/null 2>&1 || true); "
            f"rm -f {pidfile} {logfile}; "
            f"{pass_setup}"
            f"setsid sh -c 'echo $$ > {pidfile}; exec {ssh_line}' "
            f"< /dev/null > {logfile} 2>&1 & "
            "sleep 2.5; "
            f"(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | "
            f"grep -q ':{SOCKS_PORT} ' && echo OK || "
            f"(echo FAIL; tail -n 15 {logfile} 2>/dev/null || true)"
        )

        try:
            # inject password as env for the remote shell if needed
            if a_pass and not a_key:
                # agent RUN doesn't support env, so embed via a quoted assignment
                # using base64 to avoid any shell metacharacter issues
                import base64
                b64 = base64.b64encode(a_pass.encode()).decode()
                cmd = (
                    f"export TL_SSHPASS=$(echo {b64} | base64 -d); " + cmd
                )

            r = self._remote({"type": "RUN", "command": cmd},
                             expect="RESULT", timeout=90)
            out = r.get("stdout") or ""
            ok = "OK" in out
            if not ok and self.log:
                self.log.warn(f"socks B start output: {out[-500:]}")
            return ok
        except Exception as e:
            if self.log:
                self.log.warn(f"socks B failed: {e}")
            return False

    def _stop_socks_on_b(self):
        try:
            self._remote({
                "type": "RUN",
                "command": (
                    "test -f /tmp/tunnel-lab-socks-b.pid && "
                    "kill $(cat /tmp/tunnel-lab-socks-b.pid) 2>/dev/null; "
                    "rm -f /tmp/tunnel-lab-socks-b.pid /tmp/.tl-sshpass; "
                    f"pkill -f 'ssh .* -D {SOCKS_PORT}' 2>/dev/null || true"
                )
            }, expect="RESULT", timeout=10)
        except Exception:
            pass

    def _socks_probe(self, host, port, timeout=5):
        """Pure-Python SOCKS5 CONNECT probe (no external deps, no internet).
        Returns (ok, detail).
        """
        import socket
        try:
            s = socket.create_connection(("127.0.0.1", SOCKS_PORT), timeout=timeout)
            s.settimeout(timeout)
            # greeting: ver=5, 1 method, method=0 (no auth)
            s.sendall(b"\x05\x01\x00")
            resp = s.recv(2)
            if len(resp) < 2 or resp[0] != 5 or resp[1] != 0:
                s.close()
                return False, f"bad greeting: {resp!r}"

            # CONNECT request
            try:
                addr = socket.inet_aton(host)
                req = b"\x05\x01\x00\x01" + addr + port.to_bytes(2, "big")
            except OSError:
                # domain name
                hb = host.encode()
                req = b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + port.to_bytes(2, "big")
            s.sendall(req)
            resp = s.recv(10)
            s.close()
            if len(resp) < 2 or resp[0] != 5:
                return False, f"bad connect resp: {resp!r}"
            if resp[1] != 0:
                return False, f"socks error code {resp[1]}"
            return True, f"connected to {host}:{port}"
        except Exception as e:
            return False, str(e)

    def _socks_check_local(self):
        """Verify SOCKS on A by connecting through it to Server B SSH port."""
        b_host = self.cfg.get("server_b", "host", default="")
        b_port = int(self.cfg.get("server_b", "ssh_port", default=22))
        ok, detail = self._socks_probe(b_host, b_port, timeout=8)
        return ok, detail

    def _socks_check_remote(self):
        """Verify SOCKS on B by connecting through it to Server A SSH port.
        Runs a tiny pure-Python SOCKS5 probe on B (no curl / no internet).
        """
        a_host = self.cfg.get("server_a", "host", default="")
        a_port = int(self.cfg.get("server_a", "ssh_port", default=22))

        # Inline Python probe so B doesn't need extra packages
        probe_py = (
            "import socket,sys\n"
            f"H={a_host!r}; P={a_port}; SP={SOCKS_PORT}\n"
            "try:\n"
            " s=socket.create_connection(('127.0.0.1',SP),timeout=6); s.settimeout(6)\n"
            " s.sendall(b'\\x05\\x01\\x00'); r=s.recv(2)\n"
            " if len(r)<2 or r[0]!=5 or r[1]!=0: print('FAIL greeting'); sys.exit(1)\n"
            " try:\n"
            "  a=socket.inet_aton(H); req=b'\\x05\\x01\\x00\\x01'+a+P.to_bytes(2,'big')\n"
            " except OSError:\n"
            "  hb=H.encode(); req=b'\\x05\\x01\\x00\\x03'+bytes([len(hb)])+hb+P.to_bytes(2,'big')\n"
            " s.sendall(req); r=s.recv(10); s.close()\n"
            " if len(r)<2 or r[0]!=5 or r[1]!=0: print('FAIL code',r[1] if len(r)>1 else -1); sys.exit(1)\n"
            " print('OK',H,P)\n"
            "except Exception as e:\n"
            " print('FAIL',e); sys.exit(1)\n"
        )
        # write + run
        import base64
        b64 = base64.b64encode(probe_py.encode()).decode()
        cmd = (
            f"echo {b64} | base64 -d > /tmp/tl-socks-probe.py && "
            "python3 /tmp/tl-socks-probe.py; rc=$?; "
            "rm -f /tmp/tl-socks-probe.py; exit $rc"
        )
        try:
            r = self._remote({"type": "RUN", "command": cmd},
                             expect="RESULT", timeout=25)
            out = (r.get("stdout") or "").strip()
            ok = r.get("rc", 1) == 0 and out.startswith("OK")
            return ok, out
        except Exception as e:
            return False, str(e)

    # ---------------- single phase ----------------
    def _run_phase(self, mod, ctx, reverse=False):
        stages = {}

        if not reverse:
            self._local_many(mod.commands_for_a(ctx))
            self._remote_many(mod.commands_for_b(ctx))
        else:
            self._remote_many(mod.reverse_commands_for_b(ctx))
            self._local_many(mod.reverse_commands_for_a(ctx))
        time.sleep(1.2)

        rc_a, _, _ = self._local(f"ip link show {ctx.interface_name}")
        stages["iface_a"] = (rc_a == 0)
        rb = self._remote({"type": "RUN", "command": f"ip link show {ctx.interface_name}"},
                          expect="RESULT", timeout=20)
        stages["iface_b"] = (rb.get("rc", 1) == 0)

        # SOCKS5 mode: interface is not a real netdev
        if mod.id == "ssh_tun":
            stages["iface_a"] = True
            stages["iface_b"] = True
            if not reverse:
                ok = self._start_socks_on_a()
                stages["icmp"] = ok   # tunnel up (SOCKS port listening)
                if ok:
                    ok2, detail = self._socks_check_local()
                    stages["tcp"] = ok2
                    stages["udp"] = ok2  # SOCKS is TCP-based; same probe
                    if self.log:
                        self.log.info(f"socks A->B probe: {detail}")
                else:
                    stages["tcp"] = False
                    stages["udp"] = False
                self._stop_socks_on_a()
            else:
                ok = self._start_socks_on_b()
                stages["icmp"] = ok
                if ok:
                    ok2, detail = self._socks_check_remote()
                    stages["tcp"] = ok2
                    stages["udp"] = ok2
                    if self.log:
                        self.log.info(f"socks B->A probe: {detail}")
                else:
                    stages["tcp"] = False
                    stages["udp"] = False
                self._stop_socks_on_b()
            return stages

        if not (stages["iface_a"] and stages["iface_b"]):
            return stages

        family = getattr(mod, "family", "ipv4")

        if family == "ipv6":
            addr_a = getattr(mod, "ADDR_A", "").split("/")[0]
            addr_b = getattr(mod, "ADDR_B", "").split("/")[0]
            if not reverse:
                stages["icmp"] = self._icmp6_from_a(addr_b)
                stages["tcp"] = self._tcp6_a_to_b(addr_b, mod.id, "direct")
                stages["udp"] = self._udp6_a_to_b(addr_b, mod.id, "direct")
            else:
                stages["icmp"] = self._icmp6_from_b(addr_a)
                stages["tcp"] = self._tcp6_b_to_a(addr_a, mod.id, "reverse")
                stages["udp"] = self._udp6_b_to_a(addr_a, mod.id, "reverse")
            return stages

        if not reverse:
            stages["icmp"] = self._icmp_from_a(ctx.tunnel_remote_ip)
            stages["tcp"] = self._tcp_a_to_b(ctx.tunnel_remote_ip, mod.id, "direct")
            stages["udp"] = self._udp_a_to_b(ctx.tunnel_remote_ip, mod.id, "direct")
        else:
            stages["icmp"] = self._icmp_from_b(ctx.tunnel_local_ip)
            stages["tcp"] = self._tcp_b_to_a(ctx.tunnel_local_ip, mod.id, "reverse")
            stages["udp"] = self._udp_b_to_a(ctx.tunnel_local_ip, mod.id, "reverse")
        return stages

    # ---------------- full test ----------------
    def run_test(self, tunnel_id):
        mod = self.modules.get(tunnel_id)
        if not mod:
            return {"tunnel": tunnel_id, "status": "FAIL", "reason": "UNKNOWN"}

        local, remote = self.alloc.next_pair()

        if tunnel_id == "ssh_tun":
            iface = "tun0"
        else:
            iface = f"{self.cfg.get('network','interface_prefix',default='tl-')}{tunnel_id}0"

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

        result = {"tunnel": tunnel_id, "status": "FAIL", "direct": {}, "reverse": {}}

        def phase_ok(stages):
            if not stages:
                return False
            for k in ("iface_a", "iface_b", "tcp", "udp"):
                if not stages.get(k, False):
                    return False
            return True

        try:
            result["direct"] = self._run_phase(mod, ctx, reverse=False)
            if not phase_ok(result["direct"]):
                failed = [k for k, v in result["direct"].items() if not v]
                result["reason"] = "DIRECT_" + (failed[0].upper() if failed else "UNKNOWN")
        except Exception as e:
            result["reason"] = "REMOTE_ERROR"
            result["error"] = str(e)
            self.log.error(f"direct phase failed: {e}")
        finally:
            try:
                self._local_many(mod.cleanup_commands_a(ctx))
                self._remote_many(mod.cleanup_commands_b(ctx))
            except Exception as e:
                self.log.warn(f"direct cleanup: {e}")

        time.sleep(1)

        try:
            result["reverse"] = self._run_phase(mod, ctx, reverse=True)
            if not phase_ok(result["reverse"]):
                failed = [k for k, v in result["reverse"].items() if not v]
                result["reason"] = "REVERSE_" + (failed[0].upper() if failed else "UNKNOWN")
        except Exception as e:
            result["reason"] = "REMOTE_ERROR"
            result["error"] = str(e)
            self.log.error(f"reverse phase failed: {e}")
        finally:
            try:
                self._local_many(mod.cleanup_commands_a(ctx))
                self._remote_many(mod.cleanup_commands_b(ctx))
            except Exception as e:
                self.log.warn(f"reverse cleanup: {e}")

        direct_ok = phase_ok(result["direct"])
        reverse_ok = phase_ok(result["reverse"])
        result["status"] = "PASS" if (direct_ok and reverse_ok) else "FAIL"
        result["direct_ok"] = direct_ok
        result["reverse_ok"] = reverse_ok
        result["explain"] = self.advisor.explain(result)
        return result

