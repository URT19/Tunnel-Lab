import importlib
from pathlib import Path

def load_all():
    mods = {}
    here = Path(__file__).parent
    for f in here.glob("*.py"):
        name = f.stem
        if name in ("__init__", "base", "registry"):
            continue
        if name.startswith("_"):
            continue
        try:
            m = importlib.import_module(f"tunnels.{name}")
        except Exception:
            continue
        for attr in dir(m):
            obj = getattr(m, attr)
            if isinstance(obj, type) and getattr(obj, "id", "") and obj.__module__ == m.__name__:
                try:
                    mods[obj.id] = obj()
                except Exception:
                    pass
    return mods