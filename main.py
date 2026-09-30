#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import Config
from core.orchestrator import Orchestrator
from core.logger import Logger
from ui.app import TunnelLabApp

VERSION = "0.2.0"

def main():
    base = Path(__file__).parent
    cfg = Config(base / "config.yaml")
    log = Logger(base / "logs")
    orch = Orchestrator(cfg, log)
    TunnelLabApp(orch, cfg, VERSION).run()

if __name__ == "__main__":
    main()