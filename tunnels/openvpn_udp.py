from tunnels._ovpn_base import OpenVPNBase


class OpenVPNUDP(OpenVPNBase):
    id = "openvpn_udp"
    name = "OpenVPN UDP"
    description = "OpenVPN over UDP (static key, ping-only test)"
    label = "UDP"
    PROTO = "udp"
    DCO = False
    DIRECT_PORT = 53787
    REVERSE_PORT = 53797
