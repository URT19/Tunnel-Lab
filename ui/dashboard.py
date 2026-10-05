import json
import os
import subprocess
import threading
import time
from pathlib import Path

from textual.app import App as TApp, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, RichLog
from textual.screen import Screen
from textual.binding import Binding

from core.channel import bus_tail

def shutil_which(cmd):
    import shutil
    return shutil.which(cmd)




STATUS_FILE = Path.cwd() / "logs" / "tunnels_status.json"

MENU_ITEMS = [
    ("1", "Config Server A",     "cfg_a"),
    ("2", "Config Server B",     "cfg_b"),
    ("3", "SYNC Servers",        "setup"),
    ("4", "Select tunnels",      "select"),
    ("5", "Run tests",           "run"),
    ("6", "Channel status",      "status"),
    ("7", "Agent log on B",      "agent_log"),
    ("8", "View config.yaml",    "view_cfg"),
    ("9", "Edit config (nano)",  "nano"),
    ("0", "Quit",                "quit"),
]

CHECK = "[green]✓[/green]"
CROSS = "[red]✗[/red]"
DOT   = "[dim]·[/dim]"


def _stage_mark(v):
    if v is True:
        return CHECK
    if v is False:
        return CROSS
    return DOT


class VersionBar(Static):
    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def render(self):
        import time
        a_v = self.app_ref.status.get("a_version", "?")
        b_v = self.app_ref.status.get("b_version", "?")
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"[bold cyan]Tunnel Lab v{self.app_ref.version}[/bold cyan]"
            f"   [dim]A: v{a_v}[/dim]"
            f"   [dim]B: v{b_v}[/dim]"
            f"   [dim]{now}[/dim]"
        )


class LogoBox(Static):
    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def render(self):
        a_v = self.app_ref.status.get("a_version", "?")
        b_v = self.app_ref.status.get("b_version", "?")
        return (
            "[bold cyan]"
            "  ████████ ██    ██ ███    ██ ███    ██ ███████ ██      \n"
            "     ██    ██    ██ ████   ██ ████   ██ ██      ██      \n"
            "     ██    ██    ██ ██ ██  ██ ██ ██  ██ █████   ██      \n"
            "     ██    ██    ██ ██  ██ ██ ██  ██ ██ ██      ██      \n"
            "     ██     ██████  ██   ████ ██   ████ ███████ ███████ \n"
            "                    L   A   B                            \n"
            "[/bold cyan]"
            f"[dim]Tunnel Compatibility Framework[/dim]   "
            f"[yellow]v{self.app_ref.version}[/yellow]\n"
            f"[green]Server A Version:[/green] {a_v}    "
            f"[green]Server B Version:[/green] {b_v}"
        )


class BoxServerA(Static):
    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def render(self):
        s = self.app_ref.status
        host = s.get("a_host", "-")
        mark = "[green]● ONLINE[/green]" if s.get("a_connected") else "[red]○ OFFLINE[/red]"
        return (
            f"[bold]SERVER A  (controller)[/bold]\n"
            f"{mark}   {host}\n"
            f"[dim]local machine[/dim]"
        )


class BoxServerB(Static):
    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def render(self):
        s = self.app_ref.status
        host = s.get("b_host", "-")
        pid = s.get("b_pid", "-") or "-"
        port = s.get("b_port", "-") or "-"
        mark = "[green]● ONLINE[/green]" if s.get("b_connected") else "[red]○ OFFLINE[/red]"
        return (
            f"[bold]SERVER B  (agent)[/bold]\n"
            f"{mark}   {host}\n"
            f"[dim]pid[/dim] {pid}   [dim]port[/dim] {port}"
        )


class BoxAgent(Static):
    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref
        self.lines = []

    def update_lines(self, lines):
        self.lines = lines
        self.refresh()

    def _fmt(self, item):
        ts = time.strftime("%H:%M:%S", time.localtime(item["ts"]))
        msg = item["msg"]
        d = msg.get("dir", "?")
        t = msg.get("type", "?")
        tun = msg.get("tunnel", "")
        reason = msg.get("reason", "")

        if d == "SYS":
            if t == "TUNNEL_START":
                return f"[dim]{ts}[/dim] [yellow]>>> testing {tun}[/yellow]"
            if t == "TUNNEL_DONE":
                icon = CHECK if msg.get("status") == "PASS" else CROSS
                r = f" [red]{reason}[/red]" if reason else ""
                return f"[dim]{ts}[/dim] [yellow]<<< {tun}[/yellow] {icon}{r}"
            return f"[dim]{ts}[/dim] {t}"

        if d == "A->B":
            return f"[dim]{ts}[/dim] [cyan]A→B[/cyan] {t}"
        if d == "B->A":
            return f"[dim]{ts}[/dim] [green]B→A[/green] {t}"
        return f"[dim]{ts}[/dim] {d} {t}"

    def render(self):
        head = "[bold magenta]AGENT  (A <-> B live)[/bold magenta]"
        if not self.lines:
            body = "[dim]no messages yet[/dim]"
        else:
            # show last 4, with newest at bottom
            out = [self._fmt(item) for item in self.lines[-4:]]
            body = "\n".join(out)
        return head + "\n" + body


class MenuPanel(Static):
    def render(self):
        left = MENU_ITEMS[:5]
        right = MENU_ITEMS[5:]
        lines = [
            "[bold yellow]MENU[/bold yellow]  [dim](press a key)[/dim]",
            "",
        ]
        for i in range(5):
            lk, lt, _ = left[i]
            rk, rt, _ = right[i]
            lines.append(
                f"  [bold]{lk}[/bold] {lt:<24}   [bold]{rk}[/bold] {rt}"
            )
        return "\n".join(lines)


class BoxTunnels(Static):
    """Tunnel status board: one row per selected tunnel."""
    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref
        self.items = []

    def update_items(self, items):
        self.items = items
        self.refresh()

    def _line(self, it):
        name = it.get("tunnel", "?")
        status = it.get("status", "PENDING")
        direct = it.get("direct", {}) or {}
        reverse = it.get("reverse", {}) or {}

        if status == "PENDING":
            return f"  [dim]… {name:<12} pending[/dim]"
        if status == "RUNNING":
            return f"  [yellow]⟳ {name:<12} running...[/yellow]"

        icon = CHECK if status == "PASS" else CROSS
        def marks(d):
            keys = ["iface_a", "iface_b", "icmp", "tcp", "udp"]
            return " ".join(_stage_mark(d.get(k)) for k in keys)

        d_str = marks(direct) if direct else DOT + " " + DOT + " " + DOT + " " + DOT + " " + DOT
        r_str = marks(reverse) if reverse else DOT + " " + DOT + " " + DOT + " " + DOT + " " + DOT
        reason = it.get("reason", "")
        tail = f" [red]{reason}[/red]" if (reason and status != "PASS") else ""
        return f"  {icon} {name:<12}  D {d_str}   R {r_str}{tail}"

    def render(self):
        head = (
            "[bold cyan]TUNNEL STATUS[/bold cyan]   "
            "[dim]D=direct (iface_a iface_b icmp tcp udp)   "
            "R=reverse[/dim]"
        )
        if not self.items:
            return head + "\n  [dim]no tunnel selected[/dim]"
        lines = [self._line(it) for it in self.items]
        return head + "\n" + "\n".join(lines)


# ---------------------------------------------------------------- picker
class PickRow(Static):
    def __init__(self, tunnel_name, screen_ref):
        super().__init__(id=f"row_{tunnel_name}")
        self.tunnel_name = tunnel_name
        self.screen_ref = screen_ref

    def render(self):
        mark = "[x]" if self.tunnel_name in self.screen_ref.selected else "[ ]"
        is_cur = (self.screen_ref.items[self.screen_ref.cursor] == self.tunnel_name)
        if is_cur:
            return f"[bold black on cyan] > {mark} {self.tunnel_name} [/bold black on cyan]"
        return f"   {mark} {self.tunnel_name}"


class TunnelPickerScreen(Screen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("space", "toggle", "Toggle", show=True),
        Binding("enter", "save", "Save", show=True),
        Binding("a", "all", "All", show=True),
        Binding("n", "none", "None", show=True),
    ]

    def __init__(self, app_ref, parent):
        super().__init__()
        self.app_ref = app_ref
        self.parent_screen = parent
        self.items = []
        self.selected = set()
        self.cursor = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="pickbox"):
            yield Static(
                "[bold cyan]Select tunnels[/bold cyan]   "
                "[dim]up/down move  Space toggle  A all  N none  "
                "Enter save  Esc cancel[/dim]",
                id="pickhint",
            )
            with Vertical(id="picklist"):
                pass
        yield Footer()

    def on_mount(self):
        base = Path.cwd()
        selected_cfg = set(self.app_ref.cfg.get("tests", "enabled", default=[]) or [])
        self.selected = set(selected_cfg)
        for f in sorted((base / "tunnels").glob("*.py")):
            name = f.stem
            if name in ("__init__", "base", "registry"):
                continue
            self.items.append(name)
        container = self.query_one("#picklist", Vertical)
        for name in self.items:
            container.mount(PickRow(name, self))

    def refresh_list(self):
        for row in self.query(PickRow):
            row.refresh()

    def on_key(self, event):
        if event.key == "up":
            if self.cursor > 0:
                self.cursor -= 1
                self.refresh_list()
            event.stop()
        elif event.key == "down":
            if self.cursor < len(self.items) - 1:
                self.cursor += 1
                self.refresh_list()
            event.stop()
        elif event.key == "space":
            self.action_toggle()
            event.stop()
        elif event.key == "enter":
            self.action_save()
            event.stop()
        elif event.key == "a":
            self.action_all()
            event.stop()
        elif event.key == "n":
            self.action_none()
            event.stop()
        elif event.key == "escape":
            self.action_cancel()
            event.stop()

    def action_toggle(self):
        if not self.items:
            return
        name = self.items[self.cursor]
        if name in self.selected:
            self.selected.discard(name)
        else:
            self.selected.add(name)
        self.refresh_list()

    def action_all(self):
        self.selected = set(self.items)
        self.refresh_list()

    def action_none(self):
        self.selected = set()
        self.refresh_list()

    def action_save(self):
        items = sorted(self.selected)
        self.app_ref.cfg.set(items, "tests", "enabled")
        try:
            self.parent_screen.wlog(f"[green]selected tunnels: {items}[/green]")
            self.parent_screen.refresh_tunnels()
        except Exception:
            pass
        self.app.pop_screen()

    def action_cancel(self):
        self.app.pop_screen()


# ---------------------------------------------------------------- dashboard
class Dashboard(Screen):
    BINDINGS = [
        Binding("1", "cfg_a", "1", show=False),
        Binding("2", "cfg_b", "2", show=False),
        Binding("3", "setup", "3", show=False),
        Binding("4", "select", "4", show=False),
        Binding("5", "run", "5", show=False),
        Binding("6", "status", "6", show=False),
        Binding("7", "agent_log", "7", show=False),
        Binding("8", "view_cfg", "8", show=False),
        Binding("9", "nano", "9", show=False),
        Binding("0", "quit", "0", show=False),
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("l", "toggle_log", "Toggle log", show=True),
        Binding("y", "copy_log", "Copy log", show=True),
    ]

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="rowversion"):
            yield VersionBar(self.app_ref)
        with Vertical(id="rowlogo"):
            yield LogoBox(self.app_ref)
        with Horizontal(id="row1"):
            with Vertical(id="sa"):
                yield BoxServerA(self.app_ref)
            with Vertical(id="sb"):
                yield BoxServerB(self.app_ref)
        with Vertical(id="row2"):
            yield BoxAgent(self.app_ref)
        with Vertical(id="row3"):
            yield MenuPanel()
        with Vertical(id="row3b"):
            yield BoxTunnels(self.app_ref)
        with Vertical(id="row4"):
            yield RichLog(id="log", highlight=True, markup=True)
        yield Footer()

    # ---------- helpers ----------
    def wlog(self, msg):
        try:
            self.query_one("#log", RichLog).write(msg)
        except Exception:
            pass

    def _py(self):
        base = Path.cwd()
        v = base / ".venv" / "bin" / "python"
        return str(v) if v.exists() else "python3"

    def _spawn(self, script, label):
        self.wlog(f"[cyan]>>> {label}[/cyan]")
        def worker():
            try:
                proc = subprocess.Popen(
                    [self._py(), "-u", str(Path.cwd() / "scripts" / script)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                )
                for line in proc.stdout:
                    self.app.call_from_thread(self.wlog, line.rstrip())
                proc.wait()
                self.app.call_from_thread(self.wlog, f"[green]{label} done[/green]")
                self.app.call_from_thread(self.refresh_status)
                self.app.call_from_thread(self.refresh_tunnels)
            except Exception as e:
                self.app.call_from_thread(self.wlog, f"[red]{label} error: {e}[/red]")
        threading.Thread(target=worker, daemon=True).start()

    # ---------- actions ----------
    def action_cfg_a(self): self._nano_edit("server_a")
    def action_cfg_b(self): self._nano_edit("server_b")


    def action_cfg_a(self):
        self.wlog("[yellow]use ./menu.sh (option 1) for config[/yellow]")

    def action_cfg_b(self):
        self.wlog("[yellow]use ./menu.sh (option 2) for config[/yellow]")

    def action_setup(self): self._spawn("do_setup.py", "setup")
    def action_run(self): self._spawn("do_run.py", "run tests")
    def action_status(self): self._spawn("do_status.py", "status")

    def action_select(self):
        self.app.push_screen(TunnelPickerScreen(self.app_ref, self))

    def action_agent_log(self):
        self.wlog("[cyan]>>> agent log on B[/cyan]")
        def worker():
            try:
                from core.config import Config
                from core.ssh_setup import SSHSetup
                from core.logger import Logger
                base = Path.cwd()
                cfg = Config(base / "config.yaml")
                log = Logger(base / "logs")
                ssh = SSHSetup(cfg, log)
                out = ssh.tail_agent_log(40)
                for line in out.splitlines():
                    self.app.call_from_thread(self.wlog, line)
            except Exception as e:
                self.app.call_from_thread(self.wlog, f"[red]{e}[/red]")
        threading.Thread(target=worker, daemon=True).start()

    def action_view_cfg(self):
        try:
            txt = (Path.cwd() / "config.yaml").read_text()
            self.wlog("[bold]config.yaml:[/bold]")
            for line in txt.splitlines():
                self.wlog("  " + line)
        except Exception as e:
            self.wlog(f"[red]{e}[/red]")

    def action_nano(self):
        base = Path.cwd()
        self.app.exit()
        subprocess.call([os.environ.get("EDITOR", "nano"), str(base / "config.yaml")])
        print("[i] restart with ./run.sh")

    def action_refresh(self):
        self.wlog("[cyan]refresh[/cyan]")
        self.refresh_status()
        self.refresh_tunnels()

    def action_toggle_log(self):
        w = self.query_one("#log", RichLog)
        w.display = not w.display

    def action_copy_log(self):
        """Copy the whole bus + status to a file and try OSC 52."""
        try:
            bus_path = Path.cwd() / "logs" / "bus.jsonl"
            out_path = Path.cwd() / "logs" / "agent_copy.txt"
            lines = []
            if bus_path.exists():
                for line in bus_path.read_text().splitlines()[-200:]:
                    try:
                        item = json.loads(line)
                        ts = time.strftime("%H:%M:%S", time.localtime(item["ts"]))
                        m = item["msg"]
                        lines.append(f"{ts} {m.get('dir','?')} {m.get('type','?')}")
                    except Exception:
                        pass
            out_path.write_text("\n".join(lines))
            self.wlog(f"[green]copied to {out_path}[/green]")
            self.wlog("[dim]use: cat logs/agent_copy.txt[/dim]")
        except Exception as e:
            self.wlog(f"[red]copy failed: {e}[/red]")

    def action_quit(self):
        self.app.exit()

    # ---------- mount ----------
    def on_mount(self):
        self.wlog("[cyan]dashboard ready[/cyan]")
        self.wlog("[dim]press 1-9 for actions, 0 to quit[/dim]")
        self.refresh_status()
        self.refresh_tunnels()
        self.set_interval(2.0, self.refresh_status)
        self.set_interval(1.0, self.refresh_agent)
        self.set_interval(2.0, self.refresh_tunnels)

    def refresh_agent(self):
        try:
            self.query_one(BoxAgent).update_lines(bus_tail(50))
        except Exception:
            pass

    def refresh_tunnels(self):
        try:
            selected = self.app_ref.cfg.get("tests", "enabled", default=[]) or []
            items = []
            if STATUS_FILE.exists():
                try:
                    data = json.loads(STATUS_FILE.read_text())
                except Exception:
                    data = []
                by_name = {it.get("tunnel"): it for it in data}
                for t in selected:
                    items.append(by_name.get(t, {"tunnel": t, "status": "PENDING"}))
            else:
                for t in selected:
                    items.append({"tunnel": t, "status": "PENDING"})
            self.query_one(BoxTunnels).update_items(items)
        except Exception:
            pass

    def refresh_status(self):
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        try:
            from core.config import Config
            from core.ssh_setup import SSHSetup
            from core.logger import Logger
            base = Path.cwd()
            cfg = Config(base / "config.yaml")
            log = Logger(base / "logs")
            ssh = SSHSetup(cfg, log)

            a = cfg.get("server_a", "host", default="") or "-"
            b = cfg.get("server_b", "host", default="") or "-"
            self.app_ref.status["a_host"] = a
            self.app_ref.status["b_host"] = b
            self.app_ref.status["a_connected"] = bool(a and a != "-")

            try:
                st = ssh.agent_status()
                self.app_ref.status["b_pid"] = st.get("pid", "-") or "-"
                self.app_ref.status["b_port"] = st.get("port", "-") or "-"
                self.app_ref.status["b_connected"] = bool(st.get("alive"))
            except Exception:
                self.app_ref.status["b_connected"] = False
                self.app_ref.status["b_pid"] = "-"
                self.app_ref.status["b_port"] = "-"

            # local + remote versions
            try:
                self.app_ref.status["a_version"] = (
                    (Path.cwd() / "VERSION").read_text().strip() or "?"
                )
            except Exception:
                self.app_ref.status["a_version"] = "?"
            try:
                rc, out, err = ssh.run("cat /root/tunnel-lab/VERSION 2>/dev/null || echo ?",
                                       which="server_b", timeout=10)
                self.app_ref.status["b_version"] = out.strip() or "?"
            except Exception:
                self.app_ref.status["b_version"] = "?"

            self.app.call_from_thread(self._repaint)
        except Exception as e:
            try:
                self.app.call_from_thread(self.wlog, f"[red]status error: {e}[/red]")
            except Exception:
                pass

    def _repaint(self):
        try:
            self.query_one(VersionBar).refresh()
            self.query_one(LogoBox).refresh()
            self.query_one(BoxServerA).refresh()
            self.query_one(BoxServerB).refresh()
        except Exception:
            pass


class DashboardApp(TApp):
    CSS = """
    Screen { layout: vertical; }
    #rowversion { height: 1; padding: 0 1; }
    #rowlogo { height: 9; border: round cyan; padding: 0 1; }
    #row1 { height: 5; }
    #sa { width: 50%; border: round green; padding: 0 1; }
    #sb { width: 50%; border: round yellow; padding: 0 1; }
    #row2 { height: 6; border: round magenta; padding: 0 1; }
    #row3 { height: 9; border: round yellow; padding: 0 1; }
    #row3b { height: 5; border: round cyan; padding: 0 1; }
    #row4 { height: 1fr; border: round blue; padding: 0 1; }
    #log { height: 100%; }
    #pickbox { border: round cyan; padding: 1; height: 100%; }
    #picklist { height: 1fr; padding: 0 1; }
    PickRow { height: 1; }
    """
    BINDINGS = [Binding("ctrl+c", "quit", "Quit", show=True)]

    def __init__(self, cfg, version):
        super().__init__()
        self.cfg = cfg
        self.version = version
        self.status = {
            "a_host": "-", "a_connected": False,
            "b_host": "-", "b_connected": False,
            "b_pid": "-", "b_port": "-",
            "a_version": "?", "b_version": "?",
        }

    def on_mount(self):
        self.push_screen(Dashboard(self))
