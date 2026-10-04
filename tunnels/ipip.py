from tunnels.base import TunnelModule

class IPIP(TunnelModule):
    id = "ipip"
    name = "IPIP"
    category = "Kernel"
    description = "IPv4 over IPv4 tunnel"

    def commands_for_a(self, ctx):
        i = ctx.interface_name
        return [
            f"ip tunnel del {i} 2>/dev/null || true",
            f"ip tunnel add {i} mode ipip local {ctx.server_a_ip} remote {ctx.server_b_ip} ttl 64",
            f"ip addr add {ctx.tunnel_local_ip}/30 dev {i}",
            f"ip link set {i} up",
        ]

    def commands_for_b(self, ctx):
        i = ctx.interface_name
        return [
            f"ip tunnel del {i} 2>/dev/null || true",
            f"ip tunnel add {i} mode ipip local {ctx.server_b_ip} remote {ctx.server_a_ip} ttl 64",
            f"ip addr add {ctx.tunnel_remote_ip}/30 dev {i}",
            f"ip link set {i} up",
        ]

    def cleanup_commands_a(self, ctx):
        return [f"ip tunnel del {ctx.interface_name} 2>/dev/null || true"]

    def cleanup_commands_b(self, ctx):
        return [f"ip tunnel del {ctx.interface_name} 2>/dev/null || true"]
