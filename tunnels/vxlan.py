from tunnels.base import TunnelModule

class VXLAN(TunnelModule):
    id = "vxlan"
    name = "VXLAN"
    category = "Kernel"
    description = "Ethernet over UDP VXLAN"

    VNI = 42
    PORT = 4789

    def commands_for_a(self, ctx):
        i = ctx.interface_name
        return [
            f"ip link del {i} 2>/dev/null || true",
            f"ip link add {i} type vxlan id {self.VNI} local {ctx.server_a_ip} "
            f"remote {ctx.server_b_ip} dstport {self.PORT} dev eth0 || "
            f"ip link add {i} type vxlan id {self.VNI} local {ctx.server_a_ip} "
            f"remote {ctx.server_b_ip} dstport {self.PORT}",
            f"ip addr add {ctx.tunnel_local_ip}/30 dev {i}",
            f"ip link set {i} up",
        ]

    def commands_for_b(self, ctx):
        i = ctx.interface_name
        return [
            f"ip link del {i} 2>/dev/null || true",
            f"ip link add {i} type vxlan id {self.VNI} local {ctx.server_b_ip} "
            f"remote {ctx.server_a_ip} dstport {self.PORT} dev eth0 || "
            f"ip link add {i} type vxlan id {self.VNI} local {ctx.server_b_ip} "
            f"remote {ctx.server_a_ip} dstport {self.PORT}",
            f"ip addr add {ctx.tunnel_remote_ip}/30 dev {i}",
            f"ip link set {i} up",
        ]

    def cleanup_commands_a(self, ctx):
        return [f"ip link del {ctx.interface_name} 2>/dev/null || true"]

    def cleanup_commands_b(self, ctx):
        return [f"ip link del {ctx.interface_name} 2>/dev/null || true"]
