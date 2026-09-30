import shutil, datetime
from pathlib import Path

class Backup:
    def __init__(self, backup_dir: Path):
        self.dir = Path(backup_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def backup_file(self, path: Path):
        p = Path(path)
        if not p.exists():
            return None
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        dst = self.dir / f"{p.name}.{ts}.bak"
        shutil.copy2(p, dst)
        return dst