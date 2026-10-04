"""Pretty-print tunnel test results using rich tables."""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED


console = Console()


def _mark(v):
    if v is True:
        return Text("\u2713", style="bold green")
    if v is False:
        return Text("\u2717", style="bold red")
    return Text("\u00b7", style="dim")


def _phase_ok(stages):
    if not stages:
        return False
    return all(stages.get(k, False) for k in ("iface_a", "iface_b", "tcp", "udp"))


def render_tunnel(result, elapsed=None):
    """Return a rich Panel for one tunnel result."""
    name = result.get("tunnel", "?").upper()
    status = result.get("status", "?")
    reason = result.get("reason", "")
    direct = result.get("direct", {}) or {}
    reverse = result.get("reverse", {}) or {}

    # title with timing
    if elapsed is not None:
        title_text = f"{name}   ({elapsed:.1f}s)"
    else:
        title_text = name

    table = Table(
        show_header=True,
        header_style="bold cyan",
        box=ROUNDED,
        border_style="cyan",
        pad_edge=False,
    )
    table.add_column("Direction", style="bold", no_wrap=True)
    table.add_column("Interface A", justify="center", no_wrap=True)
    table.add_column("Interface B", justify="center", no_wrap=True)
    table.add_column("ICMP", justify="center", no_wrap=True)
    table.add_column("TCP", justify="center", no_wrap=True)
    table.add_column("UDP", justify="center", no_wrap=True)
    table.add_column("Result", justify="center", no_wrap=True)

    def add_row(label, stages):
        ok = _phase_ok(stages)
        res = Text("PASS", style="bold green") if ok else Text("FAIL", style="bold red")
        table.add_row(
            label,
            _mark(stages.get("iface_a")),
            _mark(stages.get("iface_b")),
            _mark(stages.get("icmp")),
            _mark(stages.get("tcp")),
            _mark(stages.get("udp")),
            res,
        )

    add_row("DIRECT", direct)
    add_row("REVERSE", reverse)

    # color the panel border by final status
    border = "green" if status == "PASS" else "red"

    # subtitle for reason if failed
    subtitle = None
    if status != "PASS" and reason:
        subtitle = Text(f"reason: {reason}", style="bold red")

    panel = Panel(
        table,
        title=Text(title_text, style="bold cyan"),
        subtitle=subtitle,
        border_style=border,
        padding=(0, 1),
    )
    return panel


def render_summary(results):
    """Print the final summary table."""
    console.print()
    console.rule("[bold cyan]Test Summary[/bold cyan]")
    console.print()

    for r in results:
        name = r.get("tunnel", "?").upper()
        status = r.get("status", "?")
        if status == "PASS":
            console.print(f"    [bold green]{name:<10}[/bold green] "
                          f"[green]\u2713 PASS[/green]")
        else:
            console.print(f"    [bold red]{name:<10}[/bold red] "
                          f"[red]\u2717 FAIL[/red]")

    tested = len(results)
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = tested - passed

    console.print()
    console.rule(style="dim")
    console.print()
    console.print(f"    Tested : [bold]{tested}[/bold]")
    console.print(f"    Passed : [bold green]{passed}[/bold green]")
    console.print(f"    Failed : [bold red]{failed}[/bold red]")
    console.print()


def print_tunnel(result, elapsed=None):
    """Print a single tunnel result immediately."""
    console.print(render_tunnel(result, elapsed=elapsed))
