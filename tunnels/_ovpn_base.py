import base64
import subprocess
from pathlib import Path

from tunnels.base import TunnelModule


class OpenVPNBase(TunnelModule):
    id = ""
    name = ""
    category = "VPN"
    family = "ipv4"
    applicable_stages = ("iface_a", "iface_b", "icmp")
    group = "openvpn"

    PROTO = "udp"
    DCO = False
    IFACE = "tlab-ovpn0"
    DIR = "/etc/openvpn/tlab-ovpn"
    DIRECT_PORT = 53787
    REVERSE_PORT = 53797
    SERVER_IP = "10.67.10.1"
    CLIENT_IP = "10.67.10.2"

    # ---------------- lifecycle ----------------
    def setup(self, ctx, orch):
        # if DCO, load the kernel module (ovpn_dco_v2)
        if self.DCO:
            subprocess.run(
                "modprobe ovpn_dco_v2 2>/dev/null || modprobe ovpn 2>/dev/null || "
                "modprobe ovpn-dco-v2 2>/dev/null || true",
                shell=True, capture_output=True)
            try:
                orch.remote_run(
                    "modprobe ovpn_dco_v2 2>/dev/null || modprobe ovpn 2>/dev/null || "
                    "modprobe ovpn-dco-v2 2>/dev/null || true; echo ok",
                    timeout=15)
            except Exception:
                pass
        # open all openvpn ports (udp+tcp) on both sides
        ports_udp = (53787, 53789, 53797, 53799)
        ports_tcp = (53788, 53798)
        for p_ in ports_udp:
            subprocess.run(
                f"iptables -C INPUT -p udp --dport {p_} -j ACCEPT 2>/dev/null || "
                f"iptables -I INPUT -p udp --dport {p_} -j ACCEPT",
                shell=True, capture_output=True)
            subprocess.run(f"ufw allow {p_}/udp 2>/dev/null || true",
                           shell=True, capture_output=True)
        for p_ in ports_tcp:
            subprocess.run(
                f"iptables -C INPUT -p tcp --dport {p_} -j ACCEPT 2>/dev/null || "
                f"iptables -I INPUT -p tcp --dport {p_} -j ACCEPT",
                shell=True, capture_output=True)
            subprocess.run(f"ufw allow {p_}/tcp 2>/dev/null || true",
                           shell=True, capture_output=True)
        try:
            cmds = []
            for p_ in ports_udp:
                cmds.append(f"iptables -C INPUT -p udp --dport {p_} -j ACCEPT 2>/dev/null || "
                            f"iptables -I INPUT -p udp --dport {p_} -j ACCEPT")
                cmds.append(f"ufw allow {p_}/udp 2>/dev/null || true")
            for p_ in ports_tcp:
                cmds.append(f"iptables -C INPUT -p tcp --dport {p_} -j ACCEPT 2>/dev/null || "
                            f"iptables -I INPUT -p tcp --dport {p_} -j ACCEPT")
                cmds.append(f"ufw allow {p_}/tcp 2>/dev/null || true")
            orch.remote_run("; ".join(cmds) + "; echo done", timeout=15)
        except Exception:
            pass
        self._cleanup_local(orch)
        self._cleanup_remote(orch)

    def teardown(self, ctx, orch):
        self._cleanup_local(orch)
        self._cleanup_remote(orch)

    def _cleanup_local(self, orch):
        subprocess.run(
            f"[ -f /tmp/tlab-ovpn-a.pid ] && kill $(cat /tmp/tlab-ovpn-a.pid) 2>/dev/null; "
            f"rm -f /tmp/tlab-ovpn-a.pid; "
            f"pkill -9 -f 'openvpn.*{self.IFACE}' 2>/dev/null || true; "
            f"ip link del {self.IFACE} 2>/dev/null || true; "
            f"rm -f /tmp/tlab-ovpn-a.log",
            shell=True, capture_output=True,
        )

    def _cleanup_remote(self, orch):
        try:
            orch.remote_run(
                f"[ -f /tmp/tlab-ovpn-b.pid ] && kill $(cat /tmp/tlab-ovpn-b.pid) 2>/dev/null; "
                f"rm -f /tmp/tlab-ovpn-b.pid; "
                f"pkill -9 -f 'openvpn.*{self.IFACE}' 2>/dev/null || true; "
                f"ip link del {self.IFACE} 2>/dev/null || true; "
                f"rm -f /tmp/tlab-ovpn-b.log; "
                f"echo cleaned",
                timeout=15,
            )
        except Exception:
            pass

    # ---------------- port check ----------------
    def _port_free_local(self, orch, port, proto):
        if proto == "tcp":
            cmd = f"ss -tln | awk '{{print $4}}' | grep -qE ':{port}$' && echo BUSY || echo FREE"
        else:
            cmd = f"ss -uln | awk '{{print $4}}' | grep -qE ':{port}$' && echo BUSY || echo FREE"
        rc, out, _ = orch.local(cmd)
        return "FREE" in out

    def _port_free_remote(self, orch, port, proto):
        try:
            if proto == "tcp":
                cmd = f"ss -tln | awk '{{print $4}}' | grep -qE ':{port}$' && echo BUSY || echo FREE"
            else:
                cmd = f"ss -uln | awk '{{print $4}}' | grep -qE ':{port}$' && echo BUSY || echo FREE"
            r = orch.remote_run(cmd, timeout=10)
            return "FREE" in (r.get("stdout") or "")
        except Exception:
            return False

    # ---------------- key ----------------
    def _gen_key_local(self):
        subprocess.run(f"mkdir -p {self.DIR}; chmod 700 {self.DIR}",
                       shell=True, capture_output=True)
        subprocess.run(
            f"openvpn --genkey secret {self.DIR}/static.key 2>/dev/null",
            shell=True, capture_output=True,
        )
        try:
            return Path(f"{self.DIR}/static.key").read_text()
        except Exception:
            return ""

    def _push_key_remote(self, orch, key_data):
        b64 = base64.b64encode(key_data.encode()).decode()
        cmd = (
            f"mkdir -p {self.DIR}; chmod 700 {self.DIR}; "
            f"echo {b64} | base64 -d > {self.DIR}/static.key; "
            f"chmod 600 {self.DIR}/static.key; "
            f"echo key-ok"
        )
        return orch.remote_run(cmd, timeout=15).get("stdout", "")

    # ---------------- command builders ----------------
    def _server_cmd(self, port, side):
        proto_arg = "tcp-server" if self.PROTO == "tcp" else self.PROTO
        dco_arg = "--dco" if self.DCO else ""
        if self.DCO:
            cipher_opts = (
                "--cipher AES-256-GCM "
                "--data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305 "
            )
        else:
            cipher_opts = (
                "--cipher AES-256-CBC "
                "--data-ciphers AES-256-GCM:AES-128-GCM:AES-256-CBC "
                "--data-ciphers-fallback AES-256-CBC "
                "--auth SHA256 "
            )
        return (
            f"openvpn --dev-type tun --dev {self.IFACE} "
            f"--ifconfig {self.SERVER_IP} {self.CLIENT_IP} "
            f"--secret {self.DIR}/static.key "
            f"{cipher_opts}"
            f"--proto {proto_arg} --port {port} "
            f"{dco_arg} "
            f"--ping 10 --ping-restart 60 "
            f"--persist-tun --persist-key "
            f"--route-noexec "
            f"--writepid /tmp/tlab-ovpn-{side}.pid "
            f"--log /tmp/tlab-ovpn-{side}.log "
            f"--daemon"
        )

    def _client_cmd(self, remote_ip, port, side):
        proto_arg = "tcp-client" if self.PROTO == "tcp" else self.PROTO
        dco_arg = "--dco" if self.DCO else ""
        if self.DCO:
            cipher_opts = (
                "--cipher AES-256-GCM "
                "--data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305 "
            )
        else:
            cipher_opts = (
                "--cipher AES-256-CBC "
                "--data-ciphers AES-256-GCM:AES-128-GCM:AES-256-CBC "
                "--data-ciphers-fallback AES-256-CBC "
                "--auth SHA256 "
            )
        return (
            f"openvpn --dev-type tun --dev {self.IFACE} "
            f"--ifconfig {self.CLIENT_IP} {self.SERVER_IP} "
            f"--secret {self.DIR}/static.key "
            f"{cipher_opts}"
            f"--remote {remote_ip} {port} "
            f"--nobind "
            f"--proto {proto_arg} "
            f"{dco_arg} "
            f"--ping 10 --ping-restart 60 "
            f"--persist-tun --persist-key "
            f"--route-noexec "
            f"--writepid /tmp/tlab-ovpn-{side}.pid "
            f"--log /tmp/tlab-ovpn-{side}.log "
            f"--daemon"
        )

    # ---------------- phase ----------------
    def _wait_iface(self, orch, side, timeout=12):
        for _ in range(int(timeout * 2)):
            if side == "a":
                rc, out, _ = orch.local(f"ip link show {self.IFACE} 2>/dev/null")
                if rc == 0 and "UP" in out:
                    return True
            else:
                try:
                    r = orch.remote_run(f"ip link show {self.IFACE} 2>/dev/null",
                                        timeout=5)
                    if r.get("rc", 1) == 0 and "UP" in (r.get("stdout") or ""):
                        return True
                except Exception:
                    pass
            orch.sleep(0.5)
        return False

    def _run_phase(self, ctx, orch, server_side, port):
        stages = {"iface_a": False, "iface_b": False, "icmp": False}

        # --- step 1: port free ---
        if server_side == "a":
            if not self._port_free_local(orch, port, self.PROTO):
                orch.log.warn(f"step1 FAIL: port {port}/{self.PROTO} busy on A")
                return stages
        else:
            if not self._port_free_remote(orch, port, self.PROTO):
                orch.log.warn(f"step1 FAIL: port {port}/{self.PROTO} busy on B")
                return stages
        orch.log.info(f"step1 OK: port {port}/{self.PROTO} free on {server_side.upper()}")

        # --- step 2: generate + push static key ---
        key_data = self._gen_key_local()
        if not key_data or "-----" not in key_data:
            orch.log.warn("step2 FAIL: static key generation on A")
            return stages
        pushed = self._push_key_remote(orch, key_data)
        if "key-ok" not in pushed:
            orch.log.warn(f"step2 FAIL: push key to B: {pushed[:100]}")
            return stages
        orch.log.info("step2 OK: static key generated and pushed to B")

        # --- step 3: start openvpn (server + client) ---
        if server_side == "a":
            srv = self._server_cmd(port, "a")
            subprocess.run(srv, shell=True, capture_output=True, timeout=30)
            cli = self._client_cmd(ctx.server_a_ip, port, "b")
            try:
                orch.remote_run(cli, timeout=20)
            except Exception as e:
                orch.log.warn(f"step3 client start B: {e}")
        else:
            srv = self._server_cmd(port, "b")
            try:
                orch.remote_run(srv, timeout=20)
            except Exception as e:
                orch.log.warn(f"step3 server start B: {e}")
            cli = self._client_cmd(ctx.server_b_ip, port, "a")
            subprocess.run(cli, shell=True, capture_output=True, timeout=30)
        orch.log.info(f"step3 OK: openvpn started (server={server_side.upper()})")

        # --- step 4: wait for interfaces ---
        ok_a = self._wait_iface(orch, "a")
        ok_b = self._wait_iface(orch, "b")
        stages["iface_a"] = ok_a
        stages["iface_b"] = ok_b
        if not (ok_a and ok_b):
            orch.log.warn(f"step4 FAIL: iface a={ok_a} b={ok_b}")
            # dump logs
            rc, out, _ = orch.local("tail -20 /tmp/tlab-ovpn-a.log 2>/dev/null")
            if out.strip():
                orch.log.info(f"A log:\n{out[-800:]}")
            try:
                r = orch.remote_run("tail -20 /tmp/tlab-ovpn-b.log 2>/dev/null",
                                    timeout=10)
                if r.get("stdout"):
                    orch.log.info(f"B log:\n{r['stdout'][-800:]}")
            except Exception:
                pass
            return stages
        orch.log.info("step4 OK: interfaces up on A and B")

        # --- step 5: ping over tunnel ---
        if server_side == "a":
            # A is server, B is client (10.67.10.2). A pings B.
            rc, out, _ = orch.local(f"ping -c 3 -W 3 {self.CLIENT_IP}")
            stages["icmp"] = (rc == 0)
            if rc != 0:
                orch.log.warn(f"step5 ping A->B failed: {out[:150]}")
        else:
            # B is server, A is client. B pings A (10.67.10.2).
            try:
                r = orch.remote_run(f"ping -c 3 -W 3 {self.CLIENT_IP}", timeout=20)
                stages["icmp"] = (r.get("rc", 1) == 0)
                if r.get("rc", 1) != 0:
                    orch.log.warn(f"step5 ping B->A failed: {(r.get('stdout') or '')[:150]}")
            except Exception as e:
                orch.log.warn(f"step5 remote ping error: {e}")

        if stages["icmp"]:
            orch.log.info("step5 OK: ping over tunnel works")
        return stages

    def run_direct(self, ctx, orch):
        return self._run_phase(ctx, orch, server_side="a", port=self.DIRECT_PORT)

    def run_reverse(self, ctx, orch):
        return self._run_phase(ctx, orch, server_side="b", port=self.REVERSE_PORT)
