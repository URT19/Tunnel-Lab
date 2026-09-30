from dataclasses import dataclass, field

@dataclass
class TestContext:
    test_id: str = ""
    tunnel_id: str = ""
    server_a_ip: str = ""
    server_b_ip: str = ""
    tunnel_local_ip: str = ""
    tunnel_remote_ip: str = ""
    interface_name: str = ""
    control_port: int = 0
    session_id: str = ""
    dry_run: bool = False
    extra: dict = field(default_factory=dict)