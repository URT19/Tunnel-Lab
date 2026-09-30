import json
from pathlib import Path

from textual.app import App as TApp, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static, ListView, ListItem, Label, Input, RichLog
from textual.screen import Screen
from textual.binding import Binding


class ServerPanel(Static):
    def __init__(self, label, cfg, key):
        super().__init__()
        self.label = label
        self.cfg = cfg
        self.key = key

    def render(self):
        host = self.cfg.get(self.key, "host", default="") or "-"
        user = self.cfg.get(self.key, "user", default="") or "-"
        port = self.cfg.get(self.key, "ssh_port", default=22)
        return (
            f"[bold green]{self.label}[/bold green]\n"
            f"Host: {host}\nUser: {user}\nSSH Port: {port}"
        )


class MainMenu(Screen):
    BINDINGS = [
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select", "Select", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left"):
                yield ServerPanel("SERVER A", self.app_ref.cfg, "server_a")
                yield ServerPanel("SERVER B", self.app_ref.cfg, "server_b")
            with Vertical(id="right"):
                yield Label("[bold cyan]TUNNEL LAB v" + self.app_ref.version + "[/bold cyan]")
                yield Label("Two-Server Tunnel Compatibility Framework")
                yield Static("", id="spacer")
                yield ListView(
                    ListItem(Label("1) Configure servers"), id="cfg"),
                    ListItem(Label("2) Setup A <-> B channel"), id="setup"),
                    ListItem(Label("3) Select tunnels"), id="sel"),
                    ListItem(Label("4) Run tests"), id="run"),
                    ListItem(Label("5) Exit"), id="exit"),
                    id="menu",
                )
        yield Footer()

    def on_mount(self):
        self.query_one("#menu", ListView).focus()

    def on_list_view_selected(self, event):
        i = event.item.id
        if i == "cfg":
            self.app_ref.push_screen(ConfigScreen(self.app_ref))
        elif i == "setup":
            self.app_ref.push_screen(SetupScreen(self.app_ref))
        elif i == "sel":
            self.app_ref.push_screen(TunnelSelectScreen(self.app_ref))
        elif i == "run":
            self.app_ref.push_screen(RunScreen(self.app_ref))
        elif i == "exit":
            self.app_ref.exit()


class ConfigScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", show=True)]

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Label("[bold]Configure Servers[/bold]  (Tab=next, Enter=save, Esc=back)")
            for key in ("server_a", "server_b"):
                for field in ("host", "user", "ssh_port", "auth", "password", "key_path"):
                    cur = str(self.app_ref.cfg.get(key, field, default="") or "")
                    yield Label(f"{key}.{field}")
                    yield Input(value=cur, id=f"{key}__{field}")
        yield Footer()

    def on_mount(self):
        inputs = self.query(Input)
        if inputs:
            inputs[0].focus()

    def on_input_submitted(self, event):
        inputs = list(self.query(Input))
        idx = inputs.index(event.input)
        if idx + 1 < len(inputs):
            inputs[idx + 1].focus()
        else:
            self._save()

    def action_back(self):
        self._save()

    def _save(self):
        for inp in self.query(Input):
            key, field = inp.id.split("__", 1)
            self.app_ref.cfg.set(inp.value, key, field)
        self.app_ref.pop_screen()


class SetupScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", show=True)]

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Label("[bold]Setup A <-> B control channel[/bold]  (Esc=back)")
            yield RichLog(id="log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self):
        self.run_worker(self._do_setup, thread=True)

    def _do_setup(self):
        log = self.query_one("#log", RichLog)
        try:
            self.app.call_from_thread(log.write, "[cyan]deploying agent to server B...[/cyan]")
            self.app_ref.orch.setup_servers()
            self.app.call_from_thread(log.write, "[green]channel ready[/green]")
        except Exception as e:
            self.app.call_from_thread(log.write, f"[red]setup failed: {e}[/red]")

    def action_back(self):
        self.app_ref.pop_screen()


class TunnelSelectScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", show=True)]

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Label("[bold]Select Tunnels[/bold]  (Space=toggle, A=all, N=none, Esc=back)")
            yield ListView(id="tlist")
        yield Footer()

    def on_mount(self):
        enabled = set(self.app_ref.cfg.get("tests", "enabled", default=[]) or [])
        lv = self.query_one("#tlist", ListView)
        for m in self.app_ref.orch.list_modules():
            mark = "[x]" if m in enabled else "[ ]"
            lv.append(ListItem(Label(f"{mark} {m}"), id=m))
        lv.focus()

    def on_key(self, event):
        lv = self.query_one("#tlist", ListView)
        if event.key == "space":
            item = lv.highlighted_child
            if item is not None:
                cur = self.app_ref.cfg.get("tests", "enabled", default=[]) or []
                tid = item.id
                if tid in cur:
                    cur.remove(tid)
                else:
                    cur.append(tid)
                self.app_ref.cfg.set(cur, "tests", "enabled")
                item.query_one(Label).update(f"{'[x]' if tid in cur else '[ ]'} {tid}")
            event.stop()
        elif event.key == "a":
            all_ids = self.app_ref.orch.list_modules()
            self.app_ref.cfg.set(all_ids, "tests", "enabled")
            for item in lv.children:
                item.query_one(Label).update(f"[x] {item.id}")
            event.stop()
        elif event.key == "n":
            self.app_ref.cfg.set([], "tests", "enabled")
            for item in lv.children:
                item.query_one(Label).update(f"[ ] {item.id}")
            event.stop()

    def action_back(self):
        self.app_ref.pop_screen()


class RunScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", show=True)]

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Label("[bold]Running Tests[/bold]  (Esc=back)")
            yield RichLog(id="log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self):
        self.run_worker(self._run_all, thread=True)

    def _line_for(self, name, stages):
        if not stages:
            return f"    {name}: (not run)"
        parts = []
        for k, v in stages.items():
            parts.append(f"{k}={'OK' if v else 'FAIL'}")
        return f"    {name}: " + "  ".join(parts)

    def _run_all(self):
        log = self.query_one("#log", RichLog)
        selected = self.app_ref.cfg.get("tests", "enabled", default=[]) or []
        if not selected:
            self.app.call_from_thread(log.write, "[yellow]nothing selected[/yellow]")
            return
        results = []
        for tid in selected:
            self.app.call_from_thread(log.write, f"[cyan]>>> {tid} ...[/cyan]")
            r = self.app_ref.orch.run_test(tid)
            results.append(r)
            color = "green" if r.get("status") == "PASS" else "red"
            self.app.call_from_thread(log.write, f"[{color}][{r['tunnel']}] {r['status']}[/{color}]")
            self.app.call_from_thread(log.write, "  DIRECT  (A -> B):")
            self.app.call_from_thread(log.write, self._line_for("direct", r.get("direct", {})))
            self.app.call_from_thread(log.write, "  REVERSE (B -> A):")
            self.app.call_from_thread(log.write, self._line_for("reverse", r.get("reverse", {})))
            if r.get("reason"):
                self.app.call_from_thread(log.write, f"  reason: {r['reason']}")

        summary = self.app_ref.orch.advisor.summary(results)
        for line in summary.splitlines():
            self.app.call_from_thread(log.write, line)

        outdir = Path(__file__).resolve().parent.parent / "results"
        outdir.mkdir(parents=True, exist_ok=True)
        fname = outdir / f"summary-{self.app_ref.orch.log.session}.json"
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        self.app.call_from_thread(log.write, f"saved: {fname}")

    def action_back(self):
        self.app_ref.pop_screen()
        
class TunnelLabApp(TApp):
    CSS = """
    Screen { layout: vertical; }
    #left { width: 40%; border: round green; padding: 1; }
    #right { width: 60%; border: round cyan; padding: 1; }
    ListView { height: 100%; }
    Input { margin: 0 0 1 0; }
    #log { height: 100%; border: round cyan; }
    """
    BINDINGS = [Binding("ctrl+c", "quit", "Quit", show=True)]

    def __init__(self, orch, cfg, version):
        super().__init__()
        self.orch = orch
        self.cfg = cfg
        self.version = version

    def on_mount(self):
        self.push_screen(MainMenu(self))