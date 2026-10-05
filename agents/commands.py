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

# prefix-based allowlist for raw shell commands
SAFE_RAW_PREFIXES = (
    "ip ", "modprobe ", "sysctl ", "wg ", "wg-quick ",
    "iptables ", "ip6tables ", "nft ",
    "ping ", "ping6 ", "ping -6 ",
    "echo ", "cat ", "ls ", "which ", "command -v ", "type ",
    "mkdir ", "rm ", "chmod ", "chown ",
    "nc ", "netcat ", "ss ", "sleep ", "true", "false",
    "test ", "printf ", "date", "pwd", "hostname",
    "systemctl ", "systemd-run ",
    "fuser ", "pkill ", "killall ",
    "setsid ", "nohup ", "disown",
    "ipsec ", "swanctl ", "openvpn ",
    "apt-get ", "apt ", "dpkg ",
    "ssh ", "sshpass ", "scp ", "rsync ",
    "seq ", "awk ", "sed ", "grep ", "head ", "tail ", "tr ", "cut ",
    "wc ", "sort ", "uniq ", "xargs ",
    "ln ", "touch ", "stat ", "readlink ", "realpath ",
    "curl ", "wget ",
    "ifconfig ", "route ",
)


def is_safe_raw(cmd: str) -> bool:
    c = cmd.strip()
    if not c:
        return True
    return any(c.startswith(p) for p in SAFE_RAW_PREFIXES)
