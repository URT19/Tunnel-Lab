import socket, json, threading, time
from core.protocol import pack, unpack_header


class Channel:
    """TCP + JSON control channel between Server A and Server B."""

    def __init__(self, logger=None):
        self.log = logger
        self.sock = None
        self.buf = b""
        self.on_message = None
        self.alive = False

    # ---------- client side (Server A connects to B) ----------
    def connect(self, host, port, timeout=10):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(None)
        self.alive = True
        threading.Thread(target=self._recv_loop, daemon=True).start()
        return True

    # ---------- server side (Agent on B) ----------
    def serve(self, conn):
        self.sock = conn
        self.alive = True
        self._recv_loop()

    # ---------- send ----------
    def send(self, msg: dict):
        if not self.sock:
            raise RuntimeError("channel not connected")
        if self.log:
            self.log.event("channel.send", msg)
        self.sock.sendall(pack(msg))

    # ---------- receive ----------
    def _recv_loop(self):
        while self.alive:
            try:
                data = self.sock.recv(4096)
            except Exception:
                break
            if not data:
                break
            self.buf += data
            while True:
                n = unpack_header(self.buf)
                if n is None or len(self.buf) < 4 + n:
                    break
                body = self.buf[4:4 + n].decode("utf-8")
                self.buf = self.buf[4 + n:]
                try:
                    msg = json.loads(body)
                except Exception:
                    continue
                if self.log:
                    self.log.event("channel.recv", msg)
                if self.on_message:
                    try:
                        self.on_message(msg)
                    except Exception as e:
                        if self.log:
                            self.log.warn(f"on_message error: {e}")
        self.alive = False

    def close(self):
        self.alive = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass


class ChannelClient:
    """Synchronous request/response helper for Server A."""

    def __init__(self, host, port, logger=None, timeout=30):
        self.ch = Channel(logger=logger)
        self.ch.connect(host, port)
        self.timeout = timeout
        self.inbox = []
        self._lock = threading.Lock()
        self._event = threading.Event()
        self.ch.on_message = self._on_msg

    def _on_msg(self, msg):
        with self._lock:
            self.inbox.append(msg)
        self._event.set()

    def request(self, msg, expect=None, timeout=None):
        timeout = timeout or self.timeout
        self._event.clear()
        with self._lock:
            self.inbox.clear()
        self.ch.send(msg)
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._event.wait(0.2)
            with self._lock:
                for m in list(self.inbox):
                    if expect is None or m.get("type") == expect:
                        self.inbox.remove(m)
                        return m
            self._event.clear()
        raise TimeoutError(f"no response for {msg.get('type')} (expected {expect})")

    def close(self):
        self.ch.close()