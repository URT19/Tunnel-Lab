import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.agent import Agent
from core.logger import Logger


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    log = Logger(Path(__file__).resolve().parent.parent / "logs")
    ag = Agent(host=args.host, port=args.port, logger=log)
    ag.start()


if __name__ == "__main__":
    main()