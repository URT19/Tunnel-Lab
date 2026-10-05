import os
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
import paramiko


REMOTE_DIR = "/root/tunnel-lab"


class SSHSetup:
    """Deploys agent bundle to Server B and starts it."""

    def __init__(self, cfg, logger=None):
        self.cfg = cfg
        self.log = logger
        self.remote_dir = REMOTE_DIR

    # ---------------- connection ----------------
    def _client(self, which="server_b"):
        host = self.cfg.get(which, "host", default="")
        port = int(self.cfg.get(which, "ssh_port", default=22))
        user = self.cfg.get(which, "user", default="root")
        password = self.cfg.get(which, "password", default="") or None
        key_path = self.cfg.get(which, "key_path", default="") or None

        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if key_path:
            cli.connect(host, port=port, username=user,
                        key_filename=key_path, timeout=15)
        else:
            cli.connect(host, port=port, username=user,
                        password=password, timeout=15)
        return cli

    # ---------------- run over ssh ----------------
    def run(self, cmd, which="server_b", check=False, timeout=120):
        if self.log:
            self.log.info(f"SSH[{which}] RUN: {cmd}")
        cli = self._client(which)
        try:
            stdin, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
            out = stdout.read().decode("utf-8", "ignore")
            err = stderr.read().decode("utf-8", "ignore")
            rc = stdout.channel.recv_exit_status()
            if check and rc != 0:
                raise RuntimeError(f"ssh cmd failed: {cmd}\nSTDERR: {err}")
            return rc, out, err
        finally:
            cli.close()

    # ---------------- build bundle ----------------
    def _build_bundle(self, local_root: Path) -> Path:
        """Create a tar.gz with only what B needs."""
        tmp = Path(tempfile.gettempdir()) / "agent-bundle.tar.gz"
        if tmp.exists():
            tmp.unlink()
        local_root = Path(local_root)

        include = [
            "VERSION",
            "core/__init__.py",
            "core/protocol.py",
            "core/logger.py",
            "core/payload.py",
            "core/netinfo.py",
            "core/config.py",
            "agents/__init__.py",
            "agents/commands.py",
            "agents/agent.py",
            "agents/runner.py",
        ]
        with tarfile.open(tmp, "w:gz") as tar:
            for rel in include:
                src = local_root / rel
                if src.exists():
                    tar.add(str(src), arcname=rel)
        return tmp

    # ---------------- deploy ----------------
    def deploy_agent(self, local_root: Path, remote_dir=None):
        remote_dir = remote_dir or self.remote_dir
        bundle = self._build_bundle(local_root)
        if self.log:
            self.log.info(f"bundle size: {bundle.stat().st_size} bytes")

        cli = self._client("server_b")
        try:
            sftp = cli.open_sftp()

            # mkdir -p remote_dir
            def mkdirs(path):
                parts = path.strip("/").split("/")
                cur = ""
                for p in parts:
                    cur += "/" + p
                    try:
                        sftp.stat(cur)
                    except IOError:
                        sftp.mkdir(cur)

            mkdirs(remote_dir)
            mkdirs(remote_dir + "/core")
            mkdirs(remote_dir + "/agents")
            mkdirs(remote_dir + "/logs")

            remote_bundle = f"{remote_dir}/agent-bundle.tar.gz"
            sftp.put(str(bundle), remote_bundle)
            sftp.close()

            # extract on B
            rc, out, err = self.run(
                f"cd {remote_dir} && tar -xzf agent-bundle.tar.gz && rm -f agent-bundle.tar.gz && ls -la",
                which="server_b",
            )
            if rc != 0:
                raise RuntimeError(f"tar extract failed: {err}")

            if self.log:
                self.log.info(f"agent deployed: {out}")
        finally:
            cli.close()

    # ---------------- python check ----------------
    def ensure_python(self):
        rc, out, err = self.run("command -v python3 || echo MISSING",
                                which="server_b")
        if "MISSING" in out:
            if self.log:
                self.log.info("installing python3 on server B")
            self.run("apt-get update && apt-get install -y python3",
                     which="server_b", timeout=300)
        rc, out, err = self.run("python3 --version", which="server_b")
        if self.log:
            self.log.info(f"server B python: {out.strip()}")
        return out.strip()

    # ---------------- agent control ----------------
    def start_agent(self, port=51888, remote_dir=None):
        remote_dir = remote_dir or self.remote_dir
        # Run through setsid + full detach so SSH channel closes immediately.
        cmd = (
            f"cd {remote_dir} && "
            f"rm -f agent.port agent.log && "
            f"setsid python3 -u -m agents.runner --port {port} "
            f"< /dev/null > {remote_dir}/agent.log 2>&1 & "
            f"echo started"
        )
        try:
            rc, out, err = self.run(cmd, which="server_b", timeout=15)
        except Exception as e:
            if self.log:
                self.log.warn(f"start_agent ssh timeout/err: {e}")
            rc, out, err = 0, "started", ""
        if self.log:
            self.log.info(f"start_agent out: {out.strip()}")
        return out.strip()


    def open_firewall(self, port=51888, remote_dir=None):
        """Open control port + common tunnel ports on B (ufw + iptables + firewalld)."""
        tcp_ports = [port, 9991, 53788, 53798]
        udp_ports = [4789, 51820, 500, 4500, 8472, 9992, 53787, 53789, 53797, 53799]
        ips = ["47"]  # GRE (proto 47)
        cmds = []
        for p_ in tcp_ports:
            cmds.append(f"ufw allow {p_}/tcp 2>/dev/null || true")
            cmds.append(f"iptables -C INPUT -p tcp --dport {p_} -j ACCEPT 2>/dev/null || "
                        f"iptables -I INPUT -p tcp --dport {p_} -j ACCEPT 2>/dev/null || true")
        for p_ in udp_ports:
            cmds.append(f"ufw allow {p_}/udp 2>/dev/null || true")
            cmds.append(f"iptables -C INPUT -p udp --dport {p_} -j ACCEPT 2>/dev/null || "
                        f"iptables -I INPUT -p udp --dport {p_} -j ACCEPT 2>/dev/null || true")
        # GRE/IPIP are IP protocols, not ports
        for proto in ("gre", "ipip", "esp", "ah"):
            cmds.append(f"iptables -C INPUT -p {proto} -j ACCEPT 2>/dev/null || "
                        f"iptables -I INPUT -p {proto} -j ACCEPT 2>/dev/null || true")
        # firewalld (RHEL family)
        cmds.append("command -v firewall-cmd >/dev/null 2>&1 && "
                    "firewall-cmd --permanent --add-port=51888/tcp && "
                    "firewall-cmd --permanent --add-port=4789/udp && "
                    "firewall-cmd --permanent --add-port=51820/udp && "
                    "firewall-cmd --reload || true")
        for c in cmds:
            try:
                self.run(c, which="server_b", timeout=20)
            except Exception:
                pass
        return True


    def open_firewall_local(self, port=51888):
        """Open control port + tunnel/payload ports on Server A (local)."""
        import subprocess
        tcp_ports = [port, 9991, 53788, 53798]
        udp_ports = [4789, 51820, 500, 4500, 8472, 9992, 53787, 53789, 53797, 53799]
        cmds = []
        for p_ in tcp_ports:
            cmds.append(f"ufw allow {p_}/tcp 2>/dev/null || true")
            cmds.append(f"iptables -C INPUT -p tcp --dport {p_} -j ACCEPT 2>/dev/null || "
                        f"iptables -I INPUT -p tcp --dport {p_} -j ACCEPT 2>/dev/null || true")
        for p_ in udp_ports:
            cmds.append(f"ufw allow {p_}/udp 2>/dev/null || true")
            cmds.append(f"iptables -C INPUT -p udp --dport {p_} -j ACCEPT 2>/dev/null || "
                        f"iptables -I INPUT -p udp --dport {p_} -j ACCEPT 2>/dev/null || true")
        for proto in ("gre", "ipip", "esp", "ah"):
            cmds.append(f"iptables -C INPUT -p {proto} -j ACCEPT 2>/dev/null || "
                        f"iptables -I INPUT -p {proto} -j ACCEPT 2>/dev/null || true")
        for c in cmds:
            try:
                subprocess.run(c, shell=True, capture_output=True, timeout=20)
            except Exception:
                pass
        return True

    def get_agent_port(self, remote_dir=None):
        remote_dir = remote_dir or self.remote_dir
        rc, out, err = self.run(
            f"cat {remote_dir}/agent.port 2>/dev/null || true",
            which="server_b",
        )
        return out.strip()

    def stop_agent(self):
        # kill all agents and wait for the port to free up
        self.run(
            "pkill -9 -f 'agents.runner' 2>/dev/null || true; "
            "sleep 1; "
            "for i in 1 2 3 4 5; do "
            "  ss -tlnp 2>/dev/null | grep -q ':51888 ' || break; "
            "  sleep 1; "
            "done; echo stopped",
            which="server_b",
            timeout=15,
        )

    def tail_agent_log(self, n=30, remote_dir=None):
        remote_dir = remote_dir or self.remote_dir
        rc, out, err = self.run(
            f"tail -n {n} {remote_dir}/agent.log 2>/dev/null || echo '(no log)'",
            which="server_b",
        )
        return out


    # ---------------- status helpers ----------------
    def agent_status(self):
        """Return dict describing the agent on B."""
        info = {
            "pid": "",
            "port": "",
            "python": "",
            "uptime": "",
            "alive": False,
        }
        rc, out, err = self.run("pgrep -f 'agents.runner' || true", which="server_b")
        info["pid"] = out.strip().splitlines()[0] if out.strip() else ""
        info["alive"] = bool(info["pid"])

        rc, out, err = self.run(
            f"cat {self.remote_dir}/agent.port 2>/dev/null || true",
            which="server_b",
        )
        info["port"] = out.strip()

        rc, out, err = self.run("python3 --version 2>&1 || true", which="server_b")
        info["python"] = out.strip()

        rc, out, err = self.run(
            f"ps -o etime= -p {info['pid']} 2>/dev/null || true", which="server_b"
        )
        info["uptime"] = out.strip()

        return info
