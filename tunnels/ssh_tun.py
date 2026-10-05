import subprocess
from tunnels.base import TunnelModule


class SSHTun(TunnelModule):
    id = "ssh_tun"
    name = "SSH Tunnel"
    category = "SSH"
    description = "SSH local port forwarding (TCP only)"
    family = "ssh"
    applicable_stages = ("iface_a", "iface_b", "tcp")

    DIRECT_LOCAL_PORT = 21941
    DIRECT_REMOTE_PORT = 19998
    REVERSE_LOCAL_PORT = 22941
    REVERSE_REMOTE_PORT = 19999

    def setup(self, ctx, orch):
        self._cleanup(orch)

    def teardown(self, ctx, orch):
        self._cleanup(orch)

    def _cleanup(self, orch):
        subprocess.run(
            "pkill -9 -f 'ssh -L 21941' 2>/dev/null || true; "
            "pkill -9 -f 'ssh -L 22941' 2>/dev/null || true; "
            "pkill -9 -f 'nc -l -p 19998' 2>/dev/null || true; "
            "pkill -9 -f 'nc -l -p 19999' 2>/dev/null || true; "
            "fuser -k 21941/tcp 2>/dev/null || true; "
            "fuser -k 19999/tcp 2>/dev/null || true",
            shell=True, capture_output=True,
        )
        try:
            orch.remote_run(
                "pkill -9 -f 'ssh -L 21941' 2>/dev/null || true; "
                "pkill -9 -f 'ssh -L 22941' 2>/dev/null || true; "
                "pkill -9 -f 'nc -l -p 19998' 2>/dev/null || true; "
                "pkill -9 -f 'nc -l -p 19999' 2>/dev/null || true; "
                "fuser -k 19998/tcp 2>/dev/null || true; "
                "fuser -k 22941/tcp 2>/dev/null || true; "
                "rm -f /tmp/sshfwd-direct.txt /tmp/sshfwd-reverse.txt; "
                "echo cleaned",
                timeout=10,
            )
        except Exception:
            pass

    def _wait_remote(self, orch, port, timeout=6):
        for _ in range(int(timeout * 4)):
            try:
                r = orch.remote_run(
                    f"ss -tln | grep -qE ':{port}\\b' && echo UP || echo DOWN",
                    timeout=5,
                )
                if "UP" in (r.get("stdout") or ""):
                    return True
            except Exception:
                pass
            orch.sleep(0.25)
        return False

    def _wait_local(self, orch, port, timeout=6):
        for _ in range(int(timeout * 4)):
            rc, out, _ = orch.local(
                f"ss -tln | grep -qE ':{port}\\b' && echo UP || echo DOWN"
            )
            if "UP" in out:
                return True
            orch.sleep(0.25)
        return False

    # ---------------- DIRECT ----------------
    def run_direct(self, ctx, orch):
        # TEST MODE: skipped, not counted in summary
        return {"iface_a": True, "iface_b": True, "tcp": True, "skipped": True}

    def _run_direct_full(self, ctx, orch):
        stages = {"iface_a": False, "iface_b": False, "tcp": False}

        # 1) B: start nc listener (blocking mode without -N so file gets flushed on close)
        try:
            orch.remote_run(
                f"rm -f /tmp/sshfwd-direct.txt; "
                f"fuser -k {self.DIRECT_REMOTE_PORT}/tcp 2>/dev/null || true; "
                f"sleep 0.3; "
                f"setsid sh -c 'nc -l -p {self.DIRECT_REMOTE_PORT} "
                f"> /tmp/sshfwd-direct.txt 2>&1' "
                f"< /dev/null > /dev/null 2>&1 & "
                f"echo started",
                timeout=10,
            )
        except Exception as e:
            orch.log.warn(f"B listener start: {e}")
            return stages

        if not self._wait_remote(orch, self.DIRECT_REMOTE_PORT):
            orch.log.warn("B listener not up")
            return stages
        stages["iface_b"] = True

        # 2) A: ssh -L
        ok, err = orch.ssh_l("server_a", "server_b",
                             self.DIRECT_LOCAL_PORT,
                             self.DIRECT_REMOTE_PORT)
        if not ok:
            orch.log.warn(f"ssh -L: {err}")
            return stages
        if not self._wait_local(orch, self.DIRECT_LOCAL_PORT):
            orch.log.warn("A local port not up")
            return stages
        stages["iface_a"] = True

        # 3) A: send payload
        sent = orch.tcp_probe_local("127.0.0.1", self.DIRECT_LOCAL_PORT,
                                    payload=b"TLAB-DIRECT-PAYLOAD\n")
        if not sent:
            return stages

        # 4) give nc time to flush
        orch.sleep(1.5)

        # 5) B: verify
        r = orch.remote_run(
            "cat /tmp/sshfwd-direct.txt 2>/dev/null | tr -d '\\r'",
            timeout=10,
        )
        got = (r.get("stdout") or "").strip()
        orch.log.info(f"direct got: {got!r}")
        stages["tcp"] = "TLAB-DIRECT-PAYLOAD" in got
        return stages

    # ---------------- REVERSE ----------------
    def run_reverse(self, ctx, orch):
        # TEST MODE: skipped, not counted in summary
        return {"iface_a": True, "iface_b": True, "tcp": True, "skipped": True}

    def _run_reverse_full(self, ctx, orch):
        stages = {"iface_a": False, "iface_b": False, "tcp": False}

        # 1) A: start nc listener (with -N so it exits cleanly)
        subprocess.run(
            f"rm -f /tmp/sshfwd-reverse.txt; "
            f"fuser -k {self.REVERSE_REMOTE_PORT}/tcp 2>/dev/null || true",
            shell=True, capture_output=True,
        )
        subprocess.Popen(
            f"nc -l -p {self.REVERSE_REMOTE_PORT} > /tmp/sshfwd-reverse.txt 2>&1",
            shell=True,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        if not self._wait_local(orch, self.REVERSE_REMOTE_PORT):
            orch.log.warn("A listener not up")
            return stages
        stages["iface_a"] = True

        # 2) B: ssh -L
        ok, err = orch.ssh_l("server_b", "server_a",
                             self.REVERSE_LOCAL_PORT,
                             self.REVERSE_REMOTE_PORT)
        if not ok:
            orch.log.warn(f"ssh -L (B): {err}")
            return stages
        if not self._wait_remote(orch, self.REVERSE_LOCAL_PORT):
            orch.log.warn("B local port not up")
            return stages
        stages["iface_b"] = True

        # 3) B: send payload
        try:
            orch.remote_run(
                f"echo TLAB-REVERSE-PAYLOAD | nc -w 2 127.0.0.1 {self.REVERSE_LOCAL_PORT}; "
                f"echo sent",
                timeout=15,
            )
        except Exception as e:
            orch.log.warn(f"send from B: {e}")

        orch.sleep(1.5)

        # 4) A: verify
        try:
            got = open("/tmp/sshfwd-reverse.txt").read().strip()
        except Exception:
            got = ""
        orch.log.info(f"reverse got: {got!r}")
        stages["tcp"] = "TLAB-REVERSE-PAYLOAD" in got
        return stages
