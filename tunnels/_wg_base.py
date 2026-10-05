import subprocess
import shlex
from pathlib import Path

from tunnels.base import TunnelModule


class WireGuardBase(TunnelModule):
    """Common WireGuard logic, inspired by angristan/wireguard-install.

    Uses wg set (not wg-quick) with Table = off. Manual routes only.
    """

    id = ""
    name = ""
    family = "ipv4"
    applicable_stages = ("iface_a", "iface_b", "icmp")

    WG_PORT = 51820
    IFACE = "tlab-wg0"
    NET_A = "10.66.10.1/24"
    NET_B = "10.66.10.2/24"
    PEER_A = "10.66.10.1"
    PEER_B = "10.66.10.2"
    TARGET_PORT = 23000

    # ---------------- paths ----------------
    def _dir_a(self):
        return "/etc/wireguard/tlab-wg-a"

    def _dir_b(self):
        return "/etc/wireguard/tlab-wg-b"

    # ---------------- cleanup ----------------
    def _cleanup_local(self, orch):
        subprocess.run(
            f"wg-quick down {self.IFACE} 2>/dev/null || true; "
            f"ip link del {self.IFACE} 2>/dev/null || true; "
            f"rm -rf {self._dir_a()} {self._dir_b()}; "
            f"pkill -9 -f 'nc -l -s {self.PEER_A}' 2>/dev/null || true; "
            f"pkill -9 -f 'nc -l -p {self.TARGET_PORT}' 2>/dev/null || true; "
            f"rm -f /tmp/wg-target-a.txt",
            shell=True, capture_output=True,
        )

    def _cleanup_remote(self, orch):
        try:
            orch.remote_run(
                f"wg-quick down {self.IFACE} 2>/dev/null || true; "
                f"ip link del {self.IFACE} 2>/dev/null || true; "
                f"rm -rf {self._dir_a()} {self._dir_b()}; "
                f"pkill -9 -f 'nc -l -s {self.PEER_B}' 2>/dev/null || true; "
                f"pkill -9 -f 'nc -l -p {self.TARGET_PORT}' 2>/dev/null || true; "
                f"rm -f /tmp/wg-target-b.txt; "
                f"echo cleaned",
                timeout=15,
            )
        except Exception:
            pass

    def setup(self, ctx, orch):
        # make sure wireguard module is loaded on both sides
        subprocess.run("modprobe wireguard 2>/dev/null || true",
                       shell=True, capture_output=True)
        try:
            orch.remote_run("modprobe wireguard 2>/dev/null || true", timeout=15)
        except Exception:
            pass
        self._cleanup_local(orch)
        self._cleanup_remote(orch)

    def teardown(self, ctx, orch):
        self._cleanup_local(orch)
        self._cleanup_remote(orch)

    # ---------------- keys ----------------
    def _gen_keys_local(self):
        d = self._dir_a()
        subprocess.run(f"mkdir -p {d} && chmod 700 {d}",
                       shell=True, capture_output=True)
        subprocess.run(
            f"wg genkey | tee {d}/private.key | wg pubkey > {d}/public.key",
            shell=True, capture_output=True,
        )
        subprocess.run(f"wg genpsk > {d}/psk.key",
                       shell=True, capture_output=True)
        priv = Path(f"{d}/private.key").read_text().strip()
        pub = Path(f"{d}/public.key").read_text().strip()
        psk = Path(f"{d}/psk.key").read_text().strip()
        return priv, pub, psk

    def _gen_keys_remote(self, orch):
        d = self._dir_b()
        cmd = (
            f"mkdir -p {d} && chmod 700 {d} && "
            f"wg genkey | tee {d}/private.key | wg pubkey > {d}/public.key; "
            f"wg genpsk > {d}/psk.key; "
            f"cat {d}/private.key && echo '---' && cat {d}/public.key && echo '---' && cat {d}/psk.key"
        )
        r = orch.remote_run(cmd, timeout=15)
        out = (r.get("stdout") or "").strip().split("---")
        if len(out) != 3:
            return None, None, None
        return out[0].strip(), out[1].strip(), out[2].strip()

    # ---------------- bring up ----------------
    def _wg_up_a(self, orch, priv, peer_pub, psk, peer_ip, self_ip, endpoint):
        d = self._dir_a()
        subprocess.run(
            f""
            f"ip link del {self.IFACE} 2>/dev/null || true; "
            f"ip link add dev {self.IFACE} type wireguard; "
            f"wg set {self.IFACE} private-key {d}/private.key "
            f"listen-port {self.WG_PORT}; "
            f"wg set {self.IFACE} peer {shlex.quote(peer_pub)} "
            f"preshared-key {d}/psk.key "
            f"allowed-ips {peer_ip}/32 "
            f"endpoint {endpoint} "
            f"persistent-keepalive 25; "
            f"ip addr add {self_ip} dev {self.IFACE} 2>/dev/null || true; "
            f"ip -4 route add {peer_ip}/32 dev {self.IFACE} 2>/dev/null || true; "
            f"ip link set {self.IFACE} up",
            shell=True, capture_output=True,
        )

    def _wg_up_b(self, orch, priv, peer_pub, psk, peer_ip, self_ip, endpoint):
        d = self._dir_b()
        cmd = (
            f""
            f"mkdir -p {d}; "
            f"echo {shlex.quote(psk)} > {d}/psk.key; "
            f"chmod 600 {d}/psk.key; "
            f"ip link del {self.IFACE} 2>/dev/null || true; "
            f"ip link add dev {self.IFACE} type wireguard; "
            f"wg set {self.IFACE} private-key {d}/private.key "
            f"listen-port {self.WG_PORT}; "
            f"wg set {self.IFACE} peer {shlex.quote(peer_pub)} "
            f"preshared-key {d}/psk.key "
            f"allowed-ips {peer_ip}/32 "
            f"endpoint {endpoint} "
            f"persistent-keepalive 25; "
            f"ip addr add {self_ip} dev {self.IFACE} 2>/dev/null || true; "
            f"ip -4 route add {peer_ip}/32 dev {self.IFACE} 2>/dev/null || true; "
            f"ip link set {self.IFACE} up; "
            f"echo done"
        )
        return orch.remote_run(cmd, timeout=20).get("stdout", "")

    # ---------------- checks ----------------
    def _iface_up_a(self, orch):
        rc, out, _ = orch.local(f"ip link show {self.IFACE}")
        return rc == 0 and "UP" in out

    def _iface_up_b(self, orch):
        try:
            r = orch.remote_run(f"ip link show {self.IFACE}", timeout=10)
            return r.get("rc", 1) == 0 and "UP" in (r.get("stdout") or "")
        except Exception:
            return False

    def _handshake_a(self, orch):
        rc, out, _ = orch.local(f"wg show {self.IFACE}")
        return "handshake" in out.lower()

    def _handshake_b(self, orch):
        try:
            r = orch.remote_run(f"wg show {self.IFACE}", timeout=10)
            return "handshake" in (r.get("stdout") or "").lower()
        except Exception:
            return False

    def _ping_a_to_b(self, orch):
        for _ in range(4):
            rc, out, _ = orch.local(f"ping -c 2 -W 2 {self.PEER_B}")
            if rc == 0:
                return True
            orch.sleep(1)
        return False

    def _ping_b_to_a(self, orch):
        for _ in range(4):
            try:
                r = orch.remote_run(f"ping -c 2 -W 2 {self.PEER_A}", timeout=15)
                if r.get("rc", 1) == 0:
                    return True
            except Exception:
                pass
            orch.sleep(1)
        return False

    # ---------------- port forward over wg ----------------
    def _start_target_on_b(self, orch, payload_tag):
        try:
            orch.remote_run(
                f"pkill -9 -f 'nc -l -s {self.PEER_B}' 2>/dev/null || true; "
                f"sleep 0.3; "
                f"rm -f /tmp/wg-target-b.txt; "
                f"setsid sh -c 'nc -l -s {self.PEER_B} -p {self.TARGET_PORT} "
                f"> /tmp/wg-target-b.txt 2>&1' "
                f"< /dev/null > /dev/null 2>&1 & "
                f"echo started",
                timeout=10,
            )
            return True
        except Exception:
            return False

    def _start_target_on_a(self, orch, payload_tag):
        subprocess.run(
            f"pkill -9 -f 'nc -l -s {self.PEER_A}' 2>/dev/null || true; "
            f"rm -f /tmp/wg-target-a.txt",
            shell=True, capture_output=True,
        )
        subprocess.Popen(
            f"nc -l -s {self.PEER_A} -p {self.TARGET_PORT} > /tmp/wg-target-a.txt 2>&1",
            shell=True,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        return True

    def _send_from_a(self, orch, payload):
        try:
            import socket
            s = socket.create_connection((self.PEER_B, self.TARGET_PORT), timeout=5)
            s.sendall(payload)
            s.close()
            return True
        except Exception:
            return False

    def _send_from_b(self, orch, payload):
        try:
            orch.remote_run(
                f"printf {shlex.quote(payload.decode())} | "
                f"nc -w 2 {self.PEER_A} {self.TARGET_PORT}; echo sent",
                timeout=15,
            )
            return True
        except Exception:
            return False
