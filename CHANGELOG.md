# Changelog

## 0.1.0
- Initial project skeleton.

## 0.2.0
- UI rewritten with Textual.
- Arrow-key navigation.

## 0.3.0
- Two-server architecture: Server A (controller) + Server B (agent).
- Control Channel: pure-Python TCP + JSON between A and B.
- Agent on B executes whitelisted commands.
- SSH only used for initial agent deployment on B.
- Advisor module: turns raw results into human-readable suggestions.
- Tunnel modules now expose commands_for_a() and commands_for_b().
- Live A<->B message log in UI.
- Bidirectional payload test with ACK.


## 0.4.0
- Bidirectional test: DIRECT (A->B) and REVERSE (B->A) as separate phases.
- Three traffic layers per direction: ICMP, TCP, UDP.
- Tiny payload (64 bytes, one shot) with explicit ACK.
- Per-side, per-tunnel result report.
- New failure types: DIRECT_TCP_FAILED, REVERSE_UDP_FAILED, etc.
- New core/payload.py with TCP and UDP sender/receiver.
- Agent now handles SEND_TCP_PROBE and SEND_UDP_PROBE.