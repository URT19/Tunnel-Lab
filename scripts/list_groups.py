#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tunnels.registry import load_all


def main():
    mods = load_all()
    groups = {}
    for tid, mod in mods.items():
        g = getattr(mod, "group", None) or tid
        groups.setdefault(g, []).append(tid)

    for g, members in sorted(groups.items()):
        members = sorted(members)
        if len(members) == 1:
            display = members[0]
        else:
            labels = []
            for m in members:
                lbl = getattr(mods[m], "label", "") or m
                labels.append(lbl)
            display = f"{g} ({', '.join(labels)})"
        print(f"{g}|{','.join(members)}|{display}")


if __name__ == "__main__":
    main()
