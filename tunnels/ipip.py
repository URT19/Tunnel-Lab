from tunnels.base import TunnelModule

class IPIP(TunnelModule):
    id = "ipip"
    name = "IPIP"
    category = "Kernel"
    description = "IPv4 over IPv4 tunnel"

    def check_dependencies(self, ctx, ex):
        ex.run("modprobe ipip || true")

    def prepare(self, ctx, ex): pass

    def configure_server_a(self, ctx, ex):
        i = ctx.interface_name
        ex.run(f"ip tunnel del {i} 2>/dev/null || true")
        ex.run(f"ip tunnel add {i} mode ipip local {ctx.server_a_ip} remote {ctx.server_b_ip}")
        ex.run(f"ip addr add {ctx.tunnel_local_ip}/30 dev {i}")
        ex.run(f"ip link set {i} up")

    def configure_server_b(self, ctx, ex):
        i = ctx.interface_name
        ex.run(f"ip tunnel del {i} 2>/dev/null || true")
        ex.run(f"ip tunnel add {i} mode ipip local {ctx.server_b_ip} remote {ctx.server_a_ip}")
        ex.run(f"ip addr add {ctx.tunnel_remote_ip}/30 dev {i}")
        ex.run(f"ip link set {i} up")

    def verify(self, ctx, ex):
        rc, out, _ = ex.run(f"ip link show {ctx.interface_name}")
        return rc == 0 and "UP" in out

    def test_traffic(self, ctx, ex):
        rc, _, _ = ex.run(f"ping -c 2 -W 2 {ctx.tunnel_remote_ip}")
        return rc == 0

    def cleanup(self, ctx, ex):
        ex.run(f"ip tunnel del {ctx.interface_name} 2>/dev/null || true")