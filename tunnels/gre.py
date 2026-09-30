from tunnels.base import TunnelModule

class GRE(TunnelModule):
    id = "gre"
    name = "GRE"
    category = "Kernel"
    description = "IP over IP GRE tunnel"

    def check_dependencies(self, ctx, ex):
        ex.run("modprobe ip_gre || true")

    def prepare(self, ctx, ex):
        pass

    def configure_server_a(self, ctx, ex):
        iface = ctx.interface_name
        ex.run(f"ip tunnel del {iface} 2>/dev/null || true")
        ex.run(f"ip tunnel add {iface} mode gre local {ctx.server_a_ip} remote {ctx.server_b_ip} ttl 64")
        ex.run(f"ip addr add {ctx.tunnel_local_ip}/30 dev {iface}")
        ex.run(f"ip link set {iface} up")

    def configure_server_b(self, ctx, ex):
        iface = ctx.interface_name
        ex.run(f"ip tunnel del {iface} 2>/dev/null || true")
        ex.run(f"ip tunnel add {iface} mode gre local {ctx.server_b_ip} remote {ctx.server_a_ip} ttl 64")
        ex.run(f"ip addr add {ctx.tunnel_remote_ip}/30 dev {iface}")
        ex.run(f"ip link set {iface} up")

    def verify(self, ctx, ex):
        rc, out, _ = ex.run(f"ip link show {ctx.interface_name}")
        return rc == 0 and "UP" in out

    def test_traffic(self, ctx, ex):
        rc, _, _ = ex.run(f"ping -c 2 -W 2 {ctx.tunnel_remote_ip}")
        return rc == 0

    def cleanup(self, ctx, ex):
        ex.run(f"ip tunnel del {ctx.interface_name} 2>/dev/null || true")