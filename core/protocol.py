import json, struct

HEADER = "!I"

def pack(msg: dict) -> bytes:
    body = json.dumps(msg).encode("utf-8")
    return struct.pack(HEADER, len(body)) + body

def unpack_header(buf: bytes):
    if len(buf) < 4:
        return None
    return struct.unpack(HEADER, buf[:4])[0]