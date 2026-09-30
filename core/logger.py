import datetime, json
from pathlib import Path

class Logger:
    def __init__(self, log_dir: Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.file = self.log_dir / f"session-{self.session}.log"

    def info(self, msg):
        self._w(f"[INFO] {msg}")

    def warn(self, msg):
        self._w(f"[WARN] {msg}")

    def error(self, msg):
        self._w(f"[ERROR] {msg}")

    def event(self, name, data=None):
        payload = {"event": name, "data": data or {}}
        self._w("[EVENT] " + json.dumps(payload))

    def _w(self, line):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with open(self.file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {line}\n")