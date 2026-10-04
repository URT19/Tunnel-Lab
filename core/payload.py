import socket
import struct


PAYLOAD_SIZE = 64
MAGIC = b"TLAB"


def make_payload(tunnel: str, direction: str, seq: int) -> bytes:
    head = f"{tunnel}|{direction}|SEQ={seq}|".encode("utf-8")
    pad = b"x" * max(0, PAYLOAD_SIZE - len(head))
    return MAGIC + head + pad


def parse_payload(data: bytes) -> dict:
    if not data.startswith(MAGIC):
        return {"ok": False, "reason": "BAD_MAGIC"}
    body = data[len(MAGIC):].decode("utf-8", "ignore")
    return {"ok": True, "raw": body}


def tcp_send(host: str, port: int, data: bytes, timeout: float = 5.0) -> dict:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.sendall(struct.pack("!I", len(data)) + data)
        ack = s.recv(16)
        s.close()
        return {"ok": ack == b"OK", "ack": ack.decode("utf-8", "ignore")}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def tcp_receiver(port: int, timeout: float = 60.0) -> dict:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(1)
    s.settimeout(timeout)
    try:
        conn, addr = s.accept()
        conn.settimeout(timeout)
        hdr = conn.recv(4)
        if len(hdr) < 4:
            conn.close()
            return {"ok": False, "reason": "SHORT_HEADER"}
        n = struct.unpack("!I", hdr)[0]
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        conn.sendall(b"OK")
        conn.close()
        return {"ok": True, "from": addr[0], "size": len(data)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    finally:
        s.close()


def udp_send(host: str, port: int, data: bytes, timeout: float = 5.0) -> dict:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(data, (host, port))
        ack, _ = s.recvfrom(16)
        s.close()
        return {"ok": ack == b"OK", "ack": ack.decode("utf-8", "ignore")}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def udp_receiver(port: int, timeout: float = 60.0) -> dict:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.settimeout(timeout)
    try:
        data, addr = s.recvfrom(2048)
        s.sendto(b"OK", addr)
        return {"ok": True, "from": addr[0], "size": len(data)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    finally:
        s.close()


# ---------------- IPv6 ----------------
def tcp6_send(host: str, port: int, data: bytes, timeout: float = 5.0) -> dict:
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port, 0, 0))
        s.sendall(struct.pack("!I", len(data)) + data)
        ack = s.recv(16)
        s.close()
        return {"ok": ack == b"OK", "ack": ack.decode("utf-8", "ignore")}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def tcp6_receiver(port: int, timeout: float = 60.0) -> dict:
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("::", port))
    s.listen(1)
    s.settimeout(timeout)
    try:
        conn, addr = s.accept()
        conn.settimeout(timeout)
        hdr = conn.recv(4)
        if len(hdr) < 4:
            conn.close()
            return {"ok": False, "reason": "SHORT_HEADER"}
        n = struct.unpack("!I", hdr)[0]
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        conn.sendall(b"OK")
        conn.close()
        return {"ok": True, "from": addr[0], "size": len(data)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    finally:
        s.close()


def udp6_send(host: str, port: int, data: bytes, timeout: float = 5.0) -> dict:
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(data, (host, port, 0, 0))
        ack, _ = s.recvfrom(16)
        s.close()
        return {"ok": ack == b"OK", "ack": ack.decode("utf-8", "ignore")}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def udp6_receiver(port: int, timeout: float = 60.0) -> dict:
    s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("::", port))
    s.settimeout(timeout)
    try:
        data, addr = s.recvfrom(2048)
        s.sendto(b"OK", addr)
        return {"ok": True, "from": addr[0], "size": len(data)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}
    finally:
        s.close()
