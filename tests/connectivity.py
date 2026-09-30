def ping(ex, ip):
    rc, _, _ = ex.run(f"ping -c 2 -W 2 {ip}")
    return rc == 0