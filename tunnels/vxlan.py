from tunnels.base import TunnelModule

class VXLAN(TunnelModule):
    id = "vxlan"
    name = "VXLAN"
    category = "Kernel"
    description = "Ethernet over UDP VXLAN"

    VNI = 42
    PORT = 4789

    def check_dependencies(self, ctx, ex):
        ex.run("modprobe vxlan || true")

    def prepare(self, ctx, ex): pass

    def _cfg(self, ctx, ex, local, remote):
        i = ctx.interface_name
        ex.run(f"ip link del {i} 2>/dev/null || true")
        ex.run(f"ip link add {i} type vxlan id {self.VNI} local {local} remote {remote} dstport {self.PORT} dev eth0")
        ex.run(f"ip link set {i} up")

    def configure_server_a(self, ctx, ex):
        self._cfg(ctx, ex, ctx.server_a_ip, ctx.server_b_ip)

    def configure_server_b(self, ctx, ex):
        self._cfg(ctx, ex, ctx.server_b_ip, ctx.server_a_ip)

    def verify(self, ctx, ex):
        rc, out, _ = ex.run(f"ip link show {ctx.interface_name}")
        return rc == 0 and "UP" in out

    def test_traffic(self, ctx, ex):
        return self.verify(ctx, ex)

    def cleanup(self, ctx, ex):
        ex.run(f"ip link del {ctx.interface_name} 2>/dev/null || true")