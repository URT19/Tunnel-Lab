from tunnels._wg_base import WireGuardBase


class WireGuard(WireGuardBase):
    id = "wireguard"
    name = "WireGuard"
    description = "WireGuard tunnel with preshared key (A and B initiate)"
    applicable_stages = ("iface_a", "iface_b", "icmp")

    def _bring_up(self, ctx, orch):
        a_priv, a_pub, a_psk = self._gen_keys_local()
        b_priv, b_pub, b_psk = self._gen_keys_remote(orch)
        if not (a_priv and b_pub and a_psk and b_psk):
            return False
        psk = a_psk
        self._wg_up_a(orch, a_priv, b_pub, psk, self.PEER_B,
                      self.NET_A, f"{ctx.server_b_ip}:{self.WG_PORT}")
        self._wg_up_b(orch, b_priv, a_pub, psk, self.PEER_A,
                      self.NET_B, f"{ctx.server_a_ip}:{self.WG_PORT}")
        orch.sleep(2.5)
        return True

    def run_direct(self, ctx, orch):
        stages = {"iface_a": False, "iface_b": False, "icmp": False}
        if not self._bring_up(ctx, orch):
            return stages

        stages["iface_a"] = self._iface_up_a(orch)
        stages["iface_b"] = self._iface_up_b(orch)
        if not (stages["iface_a"] and stages["iface_b"]):
            return stages

        stages["icmp"] = self._ping_a_to_b(orch)
        return stages

    def run_reverse(self, ctx, orch):
        stages = {"iface_a": False, "iface_b": False, "icmp": False}
        if not self._bring_up(ctx, orch):
            return stages

        stages["iface_a"] = self._iface_up_a(orch)
        stages["iface_b"] = self._iface_up_b(orch)
        if not (stages["iface_a"] and stages["iface_b"]):
            return stages

        stages["icmp"] = self._ping_b_to_a(orch)
        return stages
