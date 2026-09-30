# Changelog

## 0.1.0
- Initial project skeleton.
- Core: config, logger, protocol, state, context, allocator, executor, orchestrator.
- Tunnels: gre, ipip, gretap, sit, vxlan, wireguard, ssh_tun.
- UI: rich-based console.
- Agent: minimal TCP + JSON control channel.

## 0.2.0
- UI rewritten with Textual.
- Arrow-key navigation in all menus and lists.
- Space to toggle tunnel selection, A=all, N=none.
- Config screen with Tab navigation between fields.
- Run screen with live RichLog output.