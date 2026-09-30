from tunnels.base import TunnelModule

class SSHTun(TunnelModule):
    id = "ssh_tun"
    name = "SSH TUN"
    category = "SSH"
    description = "SSH -w tun device"

    def check_dependencies(self, ctx, ex):
        ex.run("command -v ssh >/dev/null 2>&1")

    def prepare(self, ctx, ex): pass

    def configure_server_a(self, ctx, ex):
        i = ctx.interface_name
        ex.run(f"ip tuntap add dev {i} mode tun 2>/dev/null || true")
        ex.run(f"ip addr add {ctx.tunnel_local_ip}/30 dev {i}")
        ex.run(f"ip link set {i} up")

    def configure_server_b(self, ctx, ex):
        i = ctx.interface_name
        ex.run(f"ip tuntap add dev {i} mode tun 2>/dev/null || true")
        ex.run(f"ip addr add {ctx.tunnel_remote_ip}/30 dev {i}")
        ex.run(f"ip link set {i} up")

    def verify(self, ctx, ex):
        rc, out, _ = ex.run(f"ip link show {ctx.interface_name}")
        return rc == 0 and "UP" in out

    def test_traffic(self, ctx, ex):
        return self.verify(ctx, ex)

    def cleanup(self, ctx, ex):
        ex.run(f"ip link del {ctx.interface_name} 2>/dev/null || true")