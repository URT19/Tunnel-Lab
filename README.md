# Tunnel-Lab

Version: 9.10.3

Test which tunneling protocols actually work between two Ubuntu 24.04
servers. Built for servers behind restrictive networks (e.g. Iranian
servers where SSH/ICMP/UDP/TCP may be filtered differently).

## What it does

- You give it two servers (A and B) via SSH.
- It deploys a small agent on B.
- For each selected tunnel it:
  1. configures the tunnel on both sides,
  2. verifies interface and routing,
  3. runs DIRECT (A -> B) and REVERSE (B -> A) payload tests,
  4. reports per-direction, per-stage results with colored check marks.

Supported tunnels (v9.10.0):
- GRE, GRETAP, IPIP, SIT (kernel L3/L2)
- VXLAN (kernel L2 over UDP)
- WireGuard (L3 VPN, preshared key)
- OpenVPN UDP (static key, ports 53787/53797)
- OpenVPN TCP (static key, ports 53788/53798)
- OpenVPN DCO (TLS + auto PKI via easy-rsa, ports 53789/53799)
- SSH_TUN (SSH local port forwarding, currently in TEST MODE)

## Requirements

- Two Ubuntu 24.04 servers with root SSH access.
- Server A: the machine you run the app on.
- Server B: reachable from A via SSH.
- Both servers able to reach each other on their public IPs.

## Install
نصب پکیج ها بسته به سرعت سرور ممکنه تا چندین دقیقه طول بکشه، منتظر تایید نصب بمانید.


    git clone https://github.com/URT19/Tunnel-Lab.git
    cd Tunnel-Lab
    chmod +x install.sh
    ./install.sh

The installer:
- installs system packages (iproute2, wireguard-tools, strongswan,
  openvpn, whiptail, sshpass, tcpdump, etc.),
- creates a .venv if the system python packages are too old,
- generates run.sh.

## Run

Menu (arrow keys, paste-friendly):

    ./menu.sh

Textual live dashboard:

    ./run.sh

## First-time setup (in ./menu.sh)

1. "Configure Server A" and "Configure Server B"
   - Field by field, with defaults (user=root, ssh_port=22).
2. "SYNC Servers"
   - Provisions Server B (installs packages, loads modules,
     deploys the agent, opens firewall), then reports A/B versions.
3. "Select tunnels"
   - Space toggles, A=all, N=none.
4. "Run tests"
   - Runs each tunnel in DIRECT and REVERSE mode.
   - Colored boxes with per-stage check marks.

Results are saved to results/summary-<session>.json
Logs are in logs/session-<session>.log

## Menu keys

- Main: type the number, no Enter needed.
- Tunnel select: up/down, Space toggle, A all, N none, Enter save.
- Dashboard: 1..9 for actions, r refresh, l toggle log, q quit.

## Adding a new tunnel

Create tunnels/mytunnel.py:

    from tunnels.base import TunnelModule

    class MyTunnel(TunnelModule):
        id = "mytunnel"
        name = "My Tunnel"
        category = "Kernel"
        applicable_stages = ("iface_a", "iface_b", "icmp", "tcp", "udp")

        def commands_for_a(self, ctx):  return [...]
        def commands_for_b(self, ctx):  return [...]
        def cleanup_commands_a(self, ctx): return [...]
        def cleanup_commands_b(self, ctx): return [...]

For non-standard tunnels, override run_direct / run_reverse directly.

No changes to core/orchestrator.py are needed. See ARCHITECTURE.md.

## Versioning

See CHANGELOG.md. Current: 9.7.0.

## License

MIT (or specify your license here).
