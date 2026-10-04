from tunnels.base import TunnelModule


class SIT(TunnelModule):
    id = "sit"
    name = "SIT / 6in4"
    category = "Kernel"
    description = "IPv6 over IPv4 (6in4)"
    family = "ipv6"

    ADDR_A = "fd00:1::1/64"
    ADDR_B = "fd00:1::2/64"
    NETWORK = "fd00:1::/64"

    def commands_for_a(self, ctx):
        i = ctx.interface_name
        return [
            "modprobe sit 2>/dev/null || true",
            f"ip tunnel del {i} 2>/dev/null || true",
            f"ip tunnel add {i} mode sit local {ctx.server_a_ip} remote {ctx.server_b_ip} ttl 64",
            f"ip link set {i} up",
            f"ip -6 addr add {self.ADDR_A} dev {i}",
            f"ip -6 route add {self.NETWORK} dev {i}",
        ]

    def commands_for_b(self, ctx):
        i = ctx.interface_name
        return [
            "modprobe sit 2>/dev/null || true",
            f"ip tunnel del {i} 2>/dev/null || true",
            f"ip tunnel add {i} mode sit local {ctx.server_b_ip} remote {ctx.server_a_ip} ttl 64",
            f"ip link set {i} up",
            f"ip -6 addr add {self.ADDR_B} dev {i}",
            f"ip -6 route add {self.NETWORK} dev {i}",
        ]

    def cleanup_commands_a(self, ctx):
        return [
            f"ip -6 route del {self.NETWORK} dev {ctx.interface_name} 2>/dev/null || true",
            f"ip tunnel del {ctx.interface_name} 2>/dev/null || true",
        ]

    def cleanup_commands_b(self, ctx):
        return [
            f"ip -6 route del {self.NETWORK} dev {ctx.interface_name} 2>/dev/null || true",
            f"ip tunnel del {ctx.interface_name} 2>/dev/null || true",
        ]
