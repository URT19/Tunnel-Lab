from tunnels.base import TunnelModule


class SSHTun(TunnelModule):
    id = "ssh_tun"
    name = "SSH SOCKS5"
    category = "SSH"
    description = "SSH dynamic SOCKS5 proxy (-D)"
    family = "ipv4"

    SOCKS_PORT = 1080

    def commands_for_a(self, ctx):
        # Kill any leftover local SOCKS listeners before the test
        return [
            f"pkill -f 'ssh .* -D {self.SOCKS_PORT}' 2>/dev/null || true",
            "rm -f /tmp/tunnel-lab-socks-a.pid /tmp/tunnel-lab-socks-a.log "
            "/tmp/tunnel-lab-socks-a.sh 2>/dev/null || true",
        ]

    def commands_for_b(self, ctx):
        # Nothing to configure on B; sshd already supports -D from the client
        return []

    def reverse_commands_for_a(self, ctx):
        return self.commands_for_a(ctx)

    def reverse_commands_for_b(self, ctx):
        return [
            f"pkill -f 'ssh .* -D {self.SOCKS_PORT}' 2>/dev/null || true",
            "rm -f /tmp/tunnel-lab-socks-b.pid /tmp/tunnel-lab-socks-b.log "
            "/tmp/.tl-sshpass 2>/dev/null || true",
        ]

    def cleanup_commands_a(self, ctx):
        return [
            f"pkill -f 'ssh .* -D {self.SOCKS_PORT}' 2>/dev/null || true",
            "rm -f /tmp/tunnel-lab-socks-a.pid /tmp/tunnel-lab-socks-a.log "
            "/tmp/tunnel-lab-socks-a.sh 2>/dev/null || true",
        ]

    def cleanup_commands_b(self, ctx):
        return [
            f"pkill -f 'ssh .* -D {self.SOCKS_PORT}' 2>/dev/null || true",
            "rm -f /tmp/tunnel-lab-socks-b.pid /tmp/tunnel-lab-socks-b.log "
            "/tmp/.tl-sshpass 2>/dev/null || true",
        ]

