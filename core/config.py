import yaml
from pathlib import Path

class Config:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = {}
        self.load()

    def load(self):
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = yaml.safe_load(f) or {}
        else:
            self.data = {}

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.data, f, allow_unicode=False, sort_keys=False)

    def get(self, *keys, default=None):
        cur = self.data
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    def set(self, value, *keys):
        cur = self.data
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        cur[keys[-1]] = value
        self.save()