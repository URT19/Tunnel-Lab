import time
import threading
from pathlib import Path

from core.context import TestContext
from core.network import Allocator
from core.executor import Executor
from core.channel import ChannelClient
from core.ssh_setup import SSHSetup
from core.advisor import Advisor
from core.payload import tcp_receiver, udp_receiver, tcp_send, udp_send
from tunnels.registry import load_all


TCP_PORT = 9991
UDP_PORT = 9992


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
        self.ssh.deploy_agent(self.base_dir, remote_dir="/root/tunnel-lab")
        self.ssh.stop_agent()
        time.sleep(0.5)
        self.ssh.start_agent(port=0)
        time.sleep(1.5)
        port = self.ssh.get_agent_port()
        if not port:
            raise RuntimeError("agent port not found")
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

    # ---------------- traffic tests ----------------
    def _icmp_from_a(self, target):
        rc, _, _ = self._local(f"ping -c 2 -W 2 {target}")
        return rc == 0

    def _icmp_from_b(self, target):
        r = self._remote({"type": "PROBE", "ip": target},
                         expect="PROBE_RESULT", timeout=20)
        return bool(r.get("ok"))

    def _tcp_a_to_b(self, target, tunnel, direction):
        # B listens, A sends
        def listener():
            self._remote({"type": "RECV_TCP", "port": TCP_PORT, "timeout": 20},
                         expect="RECV_TCP_RESULT", timeout=25)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.6)
        from core.payload import make_payload
        data = make_payload(tunnel, direction, 1)
        res = tcp_send(target, TCP_PORT, data, timeout=5)
        th.join(timeout=5)
        return bool(res.get("ok"))

    def _tcp_b_to_a(self, target, tunnel, direction):
        # A listens locally, B sends
        def listener():
            tcp_receiver(TCP_PORT, timeout=20)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.6)
        res = self._remote(
            {"type": "SEND_TCP", "host": target, "port": TCP_PORT,
             "tunnel": tunnel, "direction": direction, "timeout": 5},
            expect="SEND_TCP_RESULT", timeout=15)
        th.join(timeout=5)
        return bool(res.get("ok"))

    def _udp_a_to_b(self, target, tunnel, direction):
        def listener():
            self._remote({"type": "RECV_UDP", "port": UDP_PORT, "timeout": 20},
                         expect="RECV_UDP_RESULT", timeout=25)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.6)
        from core.payload import make_payload
        data = make_payload(tunnel, direction, 1)
        res = udp_send(target, UDP_PORT, data, timeout=5)
        th.join(timeout=5)
        return bool(res.get("ok"))

    def _udp_b_to_a(self, target, tunnel, direction):
        def listener():
            udp_receiver(UDP_PORT, timeout=20)
        th = threading.Thread(target=listener, daemon=True)
        th.start()
        time.sleep(0.6)
        res = self._remote(
            {"type": "SEND_UDP", "host": target, "port": UDP_PORT,
             "tunnel": tunnel, "direction": direction, "timeout": 5},
            expect="SEND_UDP_RESULT", timeout=15)
        th.join(timeout=5)
        return bool(res.get("ok"))

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

        # interface check
        rc_a, _, _ = self._local(f"ip link show {ctx.interface_name}")
        stages["iface_a"] = (rc_a == 0)
        rb = self._remote({"type": "RUN", "command": f"ip link show {ctx.interface_name}"},
                          expect="RESULT", timeout=20)
        stages["iface_b"] = (rb.get("rc", 1) == 0)

        if not (stages["iface_a"] and stages["iface_b"]):
            return stages

        if not reverse:
            # A -> B
            stages["icmp"] = self._icmp_from_a(ctx.tunnel_remote_ip)
            stages["tcp"] = self._tcp_a_to_b(ctx.tunnel_remote_ip, mod.id, "direct")
            stages["udp"] = self._udp_a_to_b(ctx.tunnel_remote_ip, mod.id, "direct")
        else:
            # B -> A
            stages["icmp"] = self._icmp_from_b(ctx.tunnel_local_ip)
            stages["tcp"] = self._tcp_b_to_a(ctx.tunnel_local_ip, mod.id, "reverse")
            stages["udp"] = self._udp_b_to_a(ctx.tunnel_local_ip, mod.id, "reverse")
        return stages

    def _local_many(self, cmds):
        for c in cmds:
            self.exec.run(c)

    # ---------------- full test ----------------
    def run_test(self, tunnel_id):
        mod = self.modules.get(tunnel_id)
        if not mod:
            return {"tunnel": tunnel_id, "status": "FAIL", "reason": "UNKNOWN"}

        local, remote = self.alloc.next_pair()
        ctx = TestContext(
            test_id=f"{tunnel_id.upper()}-TEST",
            tunnel_id=tunnel_id,
            server_a_ip=self.cfg.get("server_a", "host", default=""),
            server_b_ip=self.cfg.get("server_b", "host", default=""),
            tunnel_local_ip=local,
            tunnel_remote_ip=remote,
            interface_name=f"{self.cfg.get('network','interface_prefix',default='tl-')}{tunnel_id}0",
            dry_run=self.dry,
        )

        result = {
            "tunnel": tunnel_id,
            "status": "FAIL",
            "direct": {},
            "reverse": {},
        }

        # ---- DIRECT ----
        try:
            result["direct"] = self._run_phase(mod, ctx, reverse=False)
            if not all(result["direct"].values()):
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

        # ---- REVERSE ----
        try:
            result["reverse"] = self._run_phase(mod, ctx, reverse=True)
            if not all(result["reverse"].values()):
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

        direct_ok = bool(result["direct"]) and all(result["direct"].values())
        reverse_ok = bool(result["reverse"]) and all(result["reverse"].values())
        result["status"] = "PASS" if (direct_ok and reverse_ok) else "FAIL"
        result["explain"] = self.advisor.explain(result)
        return result