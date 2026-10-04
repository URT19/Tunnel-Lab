from tunnels.base import TunnelModule

class WireGuard(TunnelModule):
    id = "wireguard"
    name = "WireGuard"
    category = "VPN"
    description = "Modern UDP VPN"

    def commands_for_a(self, ctx):
        i = ctx.interface_name
        return [
            f"mkdir -p /etc/wireguard && chmod 700 /etc/wireguard",
            f"[ -f /etc/wireguard/{i}.key ] || (wg genkey | tee /etc/wireguard/{i}.key | wg pubkey > /etc/wireguard/{i}.pub)",
            f"ip link del {i} 2>/dev/null || true",
            f"ip link add dev {i} type wireguard",
            f"wg set {i} private-key /etc/wireguard/{i}.key listen-port 51820",
            f"ip addr add {ctx.tunnel_local_ip}/30 dev {i}",
            f"ip link set {i} up",
        ]

    def commands_for_b(self, ctx):
        i = ctx.interface_name
        return [
            f"mkdir -p /etc/wireguard && chmod 700 /etc/wireguard",
            f"[ -f /etc/wireguard/{i}.key ] || (wg genkey | tee /etc/wireguard/{i}.key | wg pubkey > /etc/wireguard/{i}.pub)",
            f"ip link del {i} 2>/dev/null || true",
            f"ip link add dev {i} type wireguard",
            f"wg set {i} private-key /etc/wireguard/{i}.key listen-port 51820",
            f"ip addr add {ctx.tunnel_remote_ip}/30 dev {i}",
            f"ip link set {i} up",
        ]

    def cleanup_commands_a(self, ctx):
        return [f"ip link del {ctx.interface_name} 2>/dev/null || true"]

    def cleanup_commands_b(self, ctx):
        return [f"ip link del {ctx.interface_name} 2>/dev/null || true"]
