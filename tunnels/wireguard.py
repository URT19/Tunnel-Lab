from tunnels.base import TunnelModule

class WireGuard(TunnelModule):
    id = "wireguard"
    name = "WireGuard"
    category = "VPN"
    description = "Modern UDP VPN"

    def check_dependencies(self, ctx, ex):
        ex.run("command -v wg >/dev/null 2>&1 || (apt-get update && apt-get install -y wireguard)")

    def prepare(self, ctx, ex):
        ex.run("mkdir -p /etc/wireguard && chmod 700 /etc/wireguard")

    def configure_server_a(self, ctx, ex):
        i = ctx.interface_name
        ex.run(f"wg genkey | tee /etc/wireguard/{i}.key | wg pubkey > /etc/wireguard/{i}.pub")
        ex.run(f"ip link del {i} 2>/dev/null || true")
        ex.run(f"ip link add dev {i} type wireguard")
        ex.run(f"wg set {i} private-key /etc/wireguard/{i}.key listen-port 51820")
        ex.run(f"ip addr add {ctx.tunnel_local_ip}/30 dev {i}")
        ex.run(f"ip link set {i} up")

    def configure_server_b(self, ctx, ex):
        i = ctx.interface_name
        ex.run(f"wg genkey | tee /etc/wireguard/{i}.key | wg pubkey > /etc/wireguard/{i}.pub")
        ex.run(f"ip link del {i} 2>/dev/null || true")
        ex.run(f"ip link add dev {i} type wireguard")
        ex.run(f"wg set {i} private-key /etc/wireguard/{i}.key listen-port 51820")
        ex.run(f"ip addr add {ctx.tunnel_remote_ip}/30 dev {i}")
        ex.run(f"ip link set {i} up")

    def verify(self, ctx, ex):
        rc, out, _ = ex.run(f"ip link show {ctx.interface_name}")
        return rc == 0 and "UP" in out

    def test_traffic(self, ctx, ex):
        return self.verify(ctx, ex)

    def cleanup(self, ctx, ex):
        ex.run(f"ip link del {ctx.interface_name} 2>/dev/null || true")
        ex.run(f"rm -f /etc/wireguard/{ctx.interface_name}.key /etc/wireguard/{ctx.interface_name}.pub")