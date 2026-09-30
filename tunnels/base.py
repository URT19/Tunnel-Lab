from abc import ABC, abstractmethod


class TunnelModule(ABC):
    id = ""
    name = ""
    category = ""
    description = ""

    # ---- commands executed on Server A (local shell) ----
    @abstractmethod
    def commands_for_a(self, ctx): return []

    # ---- commands sent to Server B (via channel) ----
    @abstractmethod
    def commands_for_b(self, ctx): return []

    # ---- same, but for REVERSE phase (B initiates) ----
    def reverse_commands_for_a(self, ctx):
        return self.commands_for_a(ctx)

    def reverse_commands_for_b(self, ctx):
        return self.commands_for_b(ctx)

    # ---- cleanup ----
    def cleanup_commands_a(self, ctx): return []
    def cleanup_commands_b(self, ctx): return []