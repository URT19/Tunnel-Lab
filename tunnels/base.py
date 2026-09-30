from abc import ABC, abstractmethod

class TunnelModule(ABC):
    id = ""
    name = ""
    category = ""
    description = ""

    @abstractmethod
    def check_dependencies(self, ctx, ex): pass

    @abstractmethod
    def prepare(self, ctx, ex): pass

    @abstractmethod
    def configure_server_a(self, ctx, ex): pass

    @abstractmethod
    def configure_server_b(self, ctx, ex): pass

    @abstractmethod
    def verify(self, ctx, ex): return True

    @abstractmethod
    def test_traffic(self, ctx, ex): return True

    @abstractmethod
    def cleanup(self, ctx, ex): pass