from core.context import TestContext
from core.state import TestState
from core.network import Allocator
from core.executor import Executor
from tunnels.registry import load_all

class Orchestrator:
    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.alloc = Allocator(
            pool=cfg.get("network", "tunnel_pool", default="10.250.0.0/16"),
            prefix=30,
        )
        self.dry = cfg.get("tests", "dry_run", default=False)
        self.exec = Executor(dry_run=self.dry, logger=log)
        self.modules = load_all()

    def list_modules(self):
        return sorted(self.modules.keys())

    def run_test(self, tunnel_id):
        mod = self.modules.get(tunnel_id)
        if not mod:
            self.log.error(f"unknown tunnel: {tunnel_id}")
            return {"tunnel": tunnel_id, "status": "FAIL", "reason": "UNKNOWN"}

        ctx = TestContext(
            test_id=f"{tunnel_id.upper()}-TEST",
            tunnel_id=tunnel_id,
            interface_name=f"{self.cfg.get('network','interface_prefix',default='tl-')}{tunnel_id}0",
            dry_run=self.dry,
        )
        try:
            local, remote = self.alloc.next_pair()
            ctx.tunnel_local_ip = local
            ctx.tunnel_remote_ip = remote
        except Exception as e:
            self.log.error(f"alloc failed: {e}")

        result = {"tunnel": tunnel_id, "status": "FAIL", "stages": {}}
        try:
            mod.check_dependencies(ctx, self.exec)
            mod.prepare(ctx, self.exec)
            mod.configure_server_a(ctx, self.exec)
            mod.configure_server_b(ctx, self.exec)
            ok_v = mod.verify(ctx, self.exec)
            ok_t = mod.test_traffic(ctx, self.exec)
            result["stages"] = {"verify": ok_v, "traffic": ok_t}
            result["status"] = "PASS" if (ok_v and ok_t) else "FAIL"
        except Exception as e:
            result["reason"] = str(e)
            self.log.error(f"{tunnel_id} failed: {e}")
        finally:
            try:
                mod.cleanup(ctx, self.exec)
            except Exception as e:
                self.log.warn(f"cleanup error: {e}")
        return result