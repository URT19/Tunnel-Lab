# Tunnel-Lab

Test which tunneling protocols actually work between two Ubuntu 24.04
servers, especially useful for servers behind restrictive networks.

Version: 9.2.0

## What it does

- You give it two servers (A and B) via SSH.
- It deploys a small agent on B.
- For each selected tunnel it:
  1. configures the tunnel on both sides,
  2. verifies interface and routing,
  3. sends ICMP, TCP and UDP payload A -> B (DIRECT),
  4. tears down, configures again with B initiating,
  5. sends ICMP, TCP and UDP payload B -> A (REVERSE),
  6. reports per-side, per-tunnel results with hints.

## Requirements

- Two Ubuntu 24.04 servers with root SSH access.
- Server A: the machine you run the app on.
- Server B: reachable from A via SSH.
- Both servers must be able to reach each other on their public IPs.

## Install

    git clone https://github.com/URT19/Tunnel-Lab.git
    cd Tunnel-Lab
    ./install.sh

The installer:
- installs system packages (iproute2, wireguard-tools, paramiko, etc.),
- creates a .venv if system python packages are too old,
- generates run.sh.

## Run

Preferred (menu-based, arrow keys, paste-friendly):

    ./menu.sh

Alternative (Textual UI):

    ./run.sh


## First-time setup (in the UI)

1. "Configure servers"
   - Two columns: SERVER A and SERVER B.
   - Fields: host, user, ssh_port, auth, password, key_path.
   - Use the "Detect public IP" button for Server A (works even on
     filtered servers, because it reads the local interface, not an
     external service).
   - Tab between fields. Ctrl+S to save. Esc to save and go back.

2. "SYNC Servers channel"
   - Deploys the agent to Server B, starts it, opens the Control Channel.
   - You should see "channel ready" in the log.

3. "Select tunnels"
   - Move with up/down arrows.
   - Space to toggle, A = all, N = none.
   - Esc to go back.

4. "Run tests"
   - Runs each selected tunnel in DIRECT and REVERSE mode.
   - Shows per-stage results and hints for failures.

Results are saved to results/summary-<session>.json
Logs are in logs/session-<session>.log

## Navigation keys

- Main menu: up/down, Enter, Q to quit
- Config: Tab between fields, Enter save, Esc back
- Tunnel select: up/down, Space toggle, A all, N none, Esc back
- Run screen: Esc back, Ctrl+C exit

## Adding a new tunnel

See ARCHITECTURE.md section 6.

Short version:
1. Create tunnels/mytunnel.py with class MyTunnel(TunnelModule).
2. Implement commands_for_a, commands_for_b, cleanup_commands_a/b.
3. Run. It appears in the list automatically.

## Troubleshooting

- "externally-managed-environment" from pip:
  use ./install.sh which handles it automatically.
- Textual import error:
  rerun ./install.sh, it will rebuild the venv with textual >= 0.60.
- Agent not reachable:
  check that Server B allows incoming on the agent port (default random).
  check /root/tunnel-lab/agent.log on Server B.

## Versioning

See CHANGELOG.md. Current: 0.4.1.
