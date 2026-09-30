WHITELIST = {
    "CREATE_INTERFACE",
    "DELETE_INTERFACE",
    "ASSIGN_ADDRESS",
    "ADD_ROUTE",
    "DEL_ROUTE",
    "START_SERVICE",
    "STOP_SERVICE",
    "RUN_CMD_SAFE",
    "ECHO",
    "PING",
}

# commands that are allowed to be executed as raw shell on the agent
SAFE_RAW_PREFIXES = (
    "ip ", "modprobe ", "sysctl ", "wg ", "iptables ",
    "ping ", "echo ", "cat ", "ls ",
)


def is_safe_raw(cmd: str) -> bool:
    c = cmd.strip()
    return any(c.startswith(p) for p in SAFE_RAW_PREFIXES)