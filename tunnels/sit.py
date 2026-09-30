from tunnels.base import TunnelModule

class SIT(TunnelModule):
    id = "sit"
    name = "SIT / 6in4"
    category = "Kernel"
    description = "IPv6 over IPv4"

    def check_dependencies(self, ctx, ex):
        ex.run("modprobe sit || true")

    def prepare(self, ctx, ex): pass

    def configure_server_a(self, ctx, ex):
        i = ctx.interface_name
        ex.run(f"ip tunnel del {i} 2>/dev/null || true")
        ex.run(f"ip tunnel add {i} mode sit local {ctx.server_a_ip} remote {ctx.server_b_ip} ttl 64")
        ex.run(f"ip link set {i} up")

    def configure_server_b(self, ctx, ex):
        i = ctx.interface_name
        ex.run(f"ip tunnel del {i} 2>/dev/null || true")
        ex.run(f"ip tunnel add {i} mode sit local {ctx.server_b_ip} remote {ctx.server_a_ip} ttl 64")
        ex.run(f"ip link set {i} up")

    def verify(self, ctx, ex):
        rc, out, _ = ex.run(f"ip link show {ctx.interface_name}")
        return rc == 0 and "UP" in out

    def test_traffic(self, ctx, ex):
        return self.verify(ctx, ex)

    def cleanup(self, ctx, ex):
        ex.run(f"ip tunnel del {ctx.interface_name} 2>/dev/null || true")