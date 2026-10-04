import subprocess
import socket


def _is_private(ip: str) -> bool:
    try:
        p = [int(x) for x in ip.split(".")]
        if len(p) != 4:
            return True
        if p[0] == 10:
            return True
        if p[0] == 172 and 16 <= p[1] <= 31:
            return True
        if p[0] == 192 and p[1] == 168:
            return True
        if p[0] == 127:
            return True
        if p[0] == 169 and p[1] == 254:
            return True
        if p[0] == 100 and 64 <= p[1] <= 127:
            return True
        return False
    except Exception:
        return True


def _run(cmd):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
    except Exception:
        return ""


def list_global_ips():
    """Return list of (iface, ip) for all global-scope IPv4 addresses."""
    out = _run(["ip", "-4", "-o", "addr", "show", "scope", "global"])
    res = []
    for line in out.splitlines():
        toks = line.split()
        if len(toks) >= 4:
            iface = toks[1]
            ip = toks[3].split("/")[0]
            if not _is_private(ip):
                res.append((iface, ip))
    return res


def detect_public_ip():
    """Best-effort local detection. Returns (ip, iface).

    Order:
      1. ip route get 1.1.1.1  -> src
      2. first global-scope addr
      3. hostname -I first non-private
    """
    # 1) route-based
    out = _run(["ip", "-4", "route", "get", "1.1.1.1"])
    if out:
        parts = out.split()
        src = ""
        iface = ""
        if "src" in parts:
            src = parts[parts.index("src") + 1]
        if "dev" in parts:
            iface = parts[parts.index("dev") + 1]
        if src and not _is_private(src):
            return src, iface

    # 2) global-scope addrs
    globals_ = list_global_ips()
    if globals_:
        return globals_[0][1], globals_[0][0]

    # 3) hostname -I
    out = _run(["hostname", "-I"])
    for tok in out.split():
        if not _is_private(tok):
            return tok, ""

    return "", ""


def hostname():
    try:
        return socket.gethostname()
    except Exception:
        return ""
