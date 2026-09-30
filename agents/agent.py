import socket, threading, json
from core.protocol import pack, unpack_header

class Agent:
    def __init__(self, host="0.0.0.0", port=0, token="", logger=None):
        self.host = host
        self.port = port
        self.token = token
        self.log = logger

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(1)
        self.port = s.getsockname()[1]
        if self.log:
            self.log.info(f"agent listening on {self.port}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()

    def _handle(self, conn, addr):
        buf = b""
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                n = unpack_header(buf)
                if n is None:
                    continue
                if len(buf) < 4 + n:
                    continue
                body = buf[4:4+n].decode("utf-8")
                buf = buf[4+n:]
                try:
                    msg = json.loads(body)
                except Exception:
                    continue
                if self.log:
                    self.log.event("agent.msg", msg)
                resp = {"type": "ACK", "echo": msg.get("type", "")}
                conn.sendall(pack(resp))
        finally:
            conn.close()