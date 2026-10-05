from tunnels._ovpn_base import OpenVPNBase


class OpenVPNTCP(OpenVPNBase):
    id = "openvpn_tcp"
    name = "OpenVPN TCP"
    description = "OpenVPN over TCP (static key, ping-only test)"
    label = "TCP"
    PROTO = "tcp"
    DCO = False
    DIRECT_PORT = 53788
    REVERSE_PORT = 53798
