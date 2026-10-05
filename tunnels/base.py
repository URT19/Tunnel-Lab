from abc import ABC, abstractmethod


class TunnelModule(ABC):
    id = ""
    name = ""
    category = ""
    description = ""
    family = "ipv4"
    applicable_stages = ("iface_a", "iface_b", "icmp", "tcp", "udp")
    group = None
    label = ""

    def setup(self, ctx, orch):
        pass

    def teardown(self, ctx, orch):
        pass

    def run_direct(self, ctx, orch):
        return self._default_phase(ctx, orch, reverse=False)

    def run_reverse(self, ctx, orch):
        return self._default_phase(ctx, orch, reverse=True)

    def _default_phase(self, ctx, orch, reverse=False):
        stages = {}
        if not reverse:
            orch.local_many(self.commands_for_a(ctx))
            orch.remote_many(self.commands_for_b(ctx))
        else:
            orch.remote_many(self.reverse_commands_for_b(ctx))
            orch.local_many(self.reverse_commands_for_a(ctx))
        orch.sleep(1.2)

        if ctx.interface_name:
            rc_a, _, _ = orch.local(f"ip link show {ctx.interface_name}")
            stages["iface_a"] = (rc_a == 0)
            rb = orch.remote(
                {"type": "RUN", "command": f"ip link show {ctx.interface_name}"},
                expect="RESULT", timeout=20,
            )
            stages["iface_b"] = (rb.get("rc", 1) == 0)
        else:
            stages["iface_a"] = True
            stages["iface_b"] = True

        if not (stages["iface_a"] and stages["iface_b"]):
            return stages

        if self.family == "ipv6":
            addr_a = getattr(self, "ADDR_A", "").split("/")[0]
            addr_b = getattr(self, "ADDR_B", "").split("/")[0]
            if "icmp" in self.applicable_stages:
                stages["icmp"] = (orch.icmp6_from_a(addr_b) if not reverse
                                  else orch.icmp6_from_b(addr_a))
            if "tcp" in self.applicable_stages:
                stages["tcp"] = (orch.tcp6_a_to_b(addr_b, self.id, "direct") if not reverse
                                 else orch.tcp6_b_to_a(addr_a, self.id, "reverse"))
            if "udp" in self.applicable_stages:
                stages["udp"] = (orch.udp6_a_to_b(addr_b, self.id, "direct") if not reverse
                                 else orch.udp6_b_to_a(addr_a, self.id, "reverse"))
            return stages

        if "icmp" in self.applicable_stages:
            stages["icmp"] = (orch.icmp_from_a(ctx.tunnel_remote_ip) if not reverse
                              else orch.icmp_from_b(ctx.tunnel_local_ip))
        if "tcp" in self.applicable_stages:
            stages["tcp"] = (orch.tcp_a_to_b(ctx.tunnel_remote_ip, self.id, "direct") if not reverse
                             else orch.tcp_b_to_a(ctx.tunnel_local_ip, self.id, "reverse"))
        if "udp" in self.applicable_stages:
            stages["udp"] = (orch.udp_a_to_b(ctx.tunnel_remote_ip, self.id, "direct") if not reverse
                             else orch.udp_b_to_a(ctx.tunnel_local_ip, self.id, "reverse"))
        return stages

    def commands_for_a(self, ctx):          return []
    def commands_for_b(self, ctx):          return []
    def reverse_commands_for_a(self, ctx):  return self.commands_for_a(ctx)
    def reverse_commands_for_b(self, ctx):  return self.commands_for_b(ctx)
    def cleanup_commands_a(self, ctx):      return []
    def cleanup_commands_b(self, ctx):      return []
