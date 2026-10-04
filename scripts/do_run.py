#!/usr/bin/env python3
import sys
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import Config
from core.logger import Logger
from core.orchestrator import Orchestrator
from core.channel import bus_emit
from core.formatter import print_tunnel, render_summary, console


STATUS_FILE = ROOT / "logs" / "tunnels_status.json"


def write_status(results):
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
    except Exception:
        pass


def main():
    base = ROOT
    cfg = Config(base / "config.yaml")
    log = Logger(base / "logs")
    orch = Orchestrator(cfg, log)

    selected = cfg.get("tests", "enabled", default=[]) or []
    a = cfg.get("server_a", "host", default="?")
    b = cfg.get("server_b", "host", default="?")

    console.print()
    console.print(f"    [cyan]Tunnels :[/cyan] [bold]{', '.join(t.upper() for t in selected)}[/bold]")
    console.print(f"    [cyan]A       :[/cyan] {a}")
    console.print(f"    [cyan]B       :[/cyan] {b}")
    console.print()

    init = [{"tunnel": t, "status": "PENDING"} for t in selected]
    write_status(init)

    console.print("    [dim][setup] opening channel to B ...[/dim]")
    try:
        orch.setup_servers()
        console.print("    [green][setup] channel ready[/green]")
    except Exception as e:
        console.print(f"    [red][setup] FAILED: {e}[/red]")
        for item in init:
            item["status"] = "FAIL"
            item["reason"] = "SETUP_FAILED"
        write_status(init)
        return 2

    results = []
    for i, tid in enumerate(selected):
        bus_emit({"dir": "SYS", "type": "TUNNEL_START", "tunnel": tid})
        print()
        console.print(f"    [cyan]>>> testing [bold]{tid.upper()}[/bold] ...[/cyan]")

        init[i]["status"] = "RUNNING"
        write_status(init)

        t0 = time.time()
        r = orch.run_test(tid)
        dt = time.time() - t0
        results.append(r)

        init[i]["status"] = r.get("status", "FAIL")
        init[i]["reason"] = r.get("reason", "")
        init[i]["direct"] = r.get("direct", {})
        init[i]["reverse"] = r.get("reverse", {})
        write_status(init)

        bus_emit({"dir": "SYS", "type": "TUNNEL_DONE", "tunnel": tid,
                  "status": r.get("status"), "reason": r.get("reason", "")})

        # render box
        print()
        print_tunnel(r, elapsed=dt)

    render_summary(results)

    outdir = base / "results"
    outdir.mkdir(exist_ok=True)
    fname = outdir / f"summary-{log.session}.json"
    with open(fname, "w") as f:
        json.dump(results, f, indent=2)
    console.print(f"    [dim]Saved: {fname}[/dim]")
    console.print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
