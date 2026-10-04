#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import Config
from ui.dashboard import DashboardApp

VERSION = "9.2.0"


def main():
    base = Path(__file__).parent
    cfg = Config(base / "config.yaml")
    DashboardApp(cfg, VERSION).run()


if __name__ == "__main__":
    main()
