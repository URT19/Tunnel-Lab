import subprocess
import base64
from pathlib import Path

from tunnels.base import TunnelModule


class OpenVPNDCO(TunnelModule):
    """OpenVPN DCO with auto-generated PKI (easy-rsa).

    DCO requires TLS mode with certificates (not static key).
    DIRECT  : A is server, B is client, port 53789/udp.
    REVERSE : B is server, A is client, port 53799/udp.
    Tunnel IPs: server 10.67.11.1, client 10.67.11.2.
    """

    id = "openvpn_dco"
    label = "DCO"
    name = "OpenVPN DCO"
    category = "VPN"
    description = "OpenVPN DCO (TLS + PKI, auto-generated certs)"
    family = "ipv4"
    applicable_stages = ("iface_a", "iface_b", "icmp")

    IFACE = "tlab-ovpn0"
    DIR = "/etc/openvpn/tlab-ovpn-dco"
    DIRECT_PORT = 53789
    REVERSE_PORT = 53799
    SERVER_IP = "10.67.11.1"
    CLIENT_IP = "10.67.11.2"

    # ---------- cleanup ----------
    def _cleanup(self, orch):
        # DCO devices need to be released by killing openvpn first,
        # then removing the module, then reloading it. Plain ip link del
        # often fails silently for a stale DCO device.
        cmd = (
            f"pkill -9 -f 'openvpn.*' 2>/dev/null; "
            f"sleep 1; "
            f"for d in $(ip link show 2>/dev/null | grep -oE '(dco[0-9]+|tlab-dco[a-zA-Z0-9_-]*|tlab-ovpn[0-9]*)' | sort -u); do "
            f"  ip link del dev $d 2>/dev/null || true; "
            f"done; "
            f"rm -rf {self.DIR}; "
            f"rm -f /tmp/dco-*.log /tmp/dco-*.pid; "
            f"echo done"
        )
        subprocess.run(cmd, shell=True, capture_output=True)
        try:
            orch.remote_run(cmd, timeout=20)
        except Exception:
            pass


    def _force_clean_dco(self, orch, side):
        """Remove every stale dco-* device."""
        cmd = (
            "pkill -9 -f 'openvpn.*' 2>/dev/null; "
            "sleep 1; "
            "for d in $(ip link show 2>/dev/null | grep -oE '(dco[0-9]+|tlab-dco[a-zA-Z0-9_-]*|tlab-ovpn[0-9]*)' | sort -u); do "
            "  ip link del dev $d 2>/dev/null || true; "
            "done; "
            "echo clean-ok"
        )
        if side == "a":
            subprocess.run(cmd, shell=True, capture_output=True)
        else:
            try:
                orch.remote_run(cmd, timeout=20)
            except Exception:
                pass

    def setup(self, ctx, orch):
        # load DCO kernel module
        subprocess.run(
            "modprobe ovpn_dco_v2 2>/dev/null || modprobe ovpn-dco-v2 2>/dev/null || true",
            shell=True, capture_output=True)
        try:
            orch.remote_run(
                "modprobe ovpn_dco_v2 2>/dev/null || modprobe ovpn-dco-v2 2>/dev/null || true; echo ok",
                timeout=15)
        except Exception:
            pass
        # open DCO ports
        for p_ in (self.DIRECT_PORT, self.REVERSE_PORT):
            subprocess.run(
                f"iptables -C INPUT -p udp --dport {p_} -j ACCEPT 2>/dev/null || "
                f"iptables -I INPUT -p udp --dport {p_} -j ACCEPT",
                shell=True, capture_output=True)
            subprocess.run(f"ufw allow {p_}/udp 2>/dev/null || true",
                           shell=True, capture_output=True)
            try:
                orch.remote_run(
                    f"iptables -C INPUT -p udp --dport {p_} -j ACCEPT 2>/dev/null || "
                    f"iptables -I INPUT -p udp --dport {p_} -j ACCEPT; "
                    f"ufw allow {p_}/udp 2>/dev/null || true; echo ok",
                    timeout=15)
            except Exception:
                pass
        self._cleanup(orch)

    def teardown(self, ctx, orch):
        self._cleanup(orch)

    # ---------- PKI ----------
    def _build_pki(self, orch):
        d = self.DIR
        cmd = (
            f"rm -rf {d}; mkdir -p {d}; chmod 700 {d}; "
            f"if [ -d /usr/share/easy-rsa ]; then "
            f"  cp -r /usr/share/easy-rsa/* {d}/ 2>/dev/null; "
            f"elif command -v make-cadir >/dev/null 2>&1; then "
            f"  make-cadir {d} 2>/dev/null; "
            f"fi; "
            f"if [ ! -f {d}/easyrsa ]; then echo easyrsa-not-found; exit 1; fi; "
            f"cd {d}; "
            f"./easyrsa init-pki >/dev/null 2>&1; "
            f"EASYRSA_BATCH=1 EASYRSA_REQ_CN=TLAB ./easyrsa build-ca nopass >/dev/null 2>&1; "
            f"EASYRSA_BATCH=1 ./easyrsa build-server-full server nopass >/dev/null 2>&1; "
            f"EASYRSA_BATCH=1 ./easyrsa build-client-full client nopass >/dev/null 2>&1; "
            f"test -f {d}/pki/ca.crt && test -f {d}/pki/issued/server.crt && "
            f"test -f {d}/pki/private/server.key && test -f {d}/pki/issued/client.crt && "
            f"test -f {d}/pki/private/client.key && echo pki-ok"
        )
        rc, out, err = orch.local(cmd, timeout=180)
        if "pki-ok" not in out:
            return False
        # flatten cert/key paths on A so they match B and server_cmd
        flat = (
            f"cp {d}/pki/ca.crt {d}/ca.crt; "
            f"cp {d}/pki/issued/server.crt {d}/server.crt; "
            f"cp {d}/pki/private/server.key {d}/server.key; "
            f"cp {d}/pki/issued/client.crt {d}/client.crt; "
            f"cp {d}/pki/private/client.key {d}/client.key; "
            f"chmod 600 {d}/server.key {d}/client.key; "
            f"echo flat-ok"
        )
        rc2, out2, _ = orch.local(flat, timeout=15)
        return "flat-ok" in out2

    def _push_pki_to_b(self, orch):
        files = [
            (f"{self.DIR}/pki/ca.crt", f"{self.DIR}/ca.crt"),
            (f"{self.DIR}/pki/issued/server.crt", f"{self.DIR}/server.crt"),
            (f"{self.DIR}/pki/private/server.key", f"{self.DIR}/server.key"),
            (f"{self.DIR}/pki/issued/client.crt", f"{self.DIR}/client.crt"),
            (f"{self.DIR}/pki/private/client.key", f"{self.DIR}/client.key"),
        ]
        r = orch.remote_run(f"mkdir -p {self.DIR}; chmod 700 {self.DIR}; echo ok", timeout=15)
        if "ok" not in (r.get("stdout") or ""):
            return False
        for local_path, remote_path in files:
            try:
                data = Path(local_path).read_bytes()
            except Exception:
                return False
            b64 = base64.b64encode(data).decode()
            cmd = f"echo {b64} | base64 -d > {remote_path}; chmod 600 {remote_path}; echo ok"
            r = orch.remote_run(cmd, timeout=15)
            if "ok" not in (r.get("stdout") or ""):
                return False
        return True

    # ---------- commands ----------
    def _common_opts(self):
        return (
            "--cipher AES-256-GCM "
            "--data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305 "
            "--dh none "
            "--ping 10 --ping-restart 60 "
            "--persist-tun --persist-key "
            "--route-noexec "
        )

    def _server_cmd(self, port, side):
        return (
            f"openvpn --dev-type tun --dev {self.IFACE} "
            f"--ifconfig {self.SERVER_IP} {self.CLIENT_IP} "
            f"--ca {self.DIR}/ca.crt --cert {self.DIR}/server.crt "
            f"--key {self.DIR}/server.key "
            f"--tls-server "
            f"{self._common_opts()}"
            f"--proto udp --port {port} "
            f"--writepid /tmp/dco-{side}.pid "
            f"--log /tmp/dco-{side}.log "
            f"--daemon"
        )

    def _client_cmd(self, remote_ip, port, side):
        return (
            f"openvpn --dev-type tun --dev {self.IFACE} "
            f"--ifconfig {self.CLIENT_IP} {self.SERVER_IP} "
            f"--ca {self.DIR}/ca.crt --cert {self.DIR}/client.crt "
            f"--key {self.DIR}/client.key "
            f"--tls-client "
            f"{self._common_opts()}"
            f"--remote {remote_ip} {port} --nobind "
            f"--proto udp "
            f"--writepid /tmp/dco-{side}.pid "
            f"--log /tmp/dco-{side}.log "
            f"--daemon"
        )

    # ---------- phase ----------
    def _wait_iface(self, orch, side, timeout=15):
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
        import time
        # unique device name per run to avoid stale DCO devices
        # Linux interface name max = 15 chars
        self.IFACE = f"dco{port % 10000}{int(time.time()) % 1000}"
        stages = {"iface_a": False, "iface_b": False, "icmp": False}

        # 1) port free
        if server_side == "a":
            rc, out, _ = orch.local(
                f"ss -uln | grep -qE ':{port}$' && echo BUSY || echo FREE")
            if "FREE" not in out:
                orch.log.warn(f"step1 FAIL: port {port}/udp busy on A")
                return stages
        else:
            try:
                r = orch.remote_run(
                    f"ss -uln | grep -qE ':{port}$' && echo BUSY || echo FREE",
                    timeout=10)
                if "FREE" not in (r.get("stdout") or ""):
                    orch.log.warn(f"step1 FAIL: port {port}/udp busy on B")
                    return stages
            except Exception:
                pass
        orch.log.info(f"step1 OK: port {port}/udp free")

        # 2) PKI
        if not self._build_pki(orch):
            orch.log.warn("step2 FAIL: PKI gen on A")
            return stages
        if not self._push_pki_to_b(orch):
            orch.log.warn("step2 FAIL: push PKI to B")
            return stages
        orch.log.info("step2 OK: PKI generated + distributed")

        # 2b) force clean DCO devices on both sides right before start
        self._force_clean_dco(orch, "a")
        self._force_clean_dco(orch, "b")
        orch.log.info("step2b OK: DCO devices cleaned")

        # 3) start
        if server_side == "a":
            subprocess.run(self._server_cmd(port, "a"), shell=True,
                           capture_output=True, timeout=20)
            orch.sleep(1)
            try:
                orch.remote_run(self._client_cmd(ctx.server_a_ip, port, "b"),
                                timeout=20)
            except Exception as e:
                orch.log.warn(f"step3 client B: {e}")
        else:
            try:
                orch.remote_run(self._server_cmd(port, "b"), timeout=20)
            except Exception as e:
                orch.log.warn(f"step3 server B: {e}")
            orch.sleep(1)
            subprocess.run(self._client_cmd(ctx.server_b_ip, port, "a"),
                           shell=True, capture_output=True, timeout=20)
        orch.log.info(f"step3 OK: started (server={server_side.upper()})")

        # 4) wait iface
        ok_a = self._wait_iface(orch, "a")
        ok_b = self._wait_iface(orch, "b")
        stages["iface_a"] = ok_a
        stages["iface_b"] = ok_b
        if not (ok_a and ok_b):
            orch.log.warn(f"step4 FAIL: iface a={ok_a} b={ok_b}")
            rc, out, _ = orch.local("tail -25 /tmp/dco-a.log 2>/dev/null")
            if out.strip():
                orch.log.info(f"A log:\n{out[-900:]}")
            try:
                r = orch.remote_run("tail -25 /tmp/dco-b.log 2>/dev/null",
                                    timeout=10)
                if r.get("stdout"):
                    orch.log.info(f"B log:\n{r['stdout'][-900:]}")
            except Exception:
                pass
            return stages
        orch.log.info("step4 OK: ifaces up")

        # 5) ping
        if server_side == "a":
            rc, out, _ = orch.local(f"ping -c 3 -W 3 {self.CLIENT_IP}")
            stages["icmp"] = (rc == 0)
        else:
            try:
                r = orch.remote_run(f"ping -c 3 -W 3 {self.CLIENT_IP}", timeout=20)
                stages["icmp"] = (r.get("rc", 1) == 0)
            except Exception:
                pass
        if stages["icmp"]:
            orch.log.info("step5 OK: ping over tunnel works")
        else:
            orch.log.warn("step5 FAIL: ping over tunnel")
        return stages

    def run_direct(self, ctx, orch):
        return self._run_phase(ctx, orch, "a", self.DIRECT_PORT)

    def run_reverse(self, ctx, orch):
        return self._run_phase(ctx, orch, "b", self.REVERSE_PORT)
