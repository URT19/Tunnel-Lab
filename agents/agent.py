import os
import signal
import socket
import subprocess
import threading
import time
import json

from core.protocol import pack, unpack_header
from agents.commands import WHITELIST, is_safe_raw


class Agent:
    def __init__(self, host="0.0.0.0", port=0, logger=None, port_file="agent.port"):
        self.host = host
        self.port = port
        self.log = logger
        self.port_file = port_file
        self.running = True

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.host, self.port))
        s.listen(8)
        self.port = s.getsockname()[1]
        with open(self.port_file, "w") as f:
            f.write(str(self.port))
        if self.log:
            self.log.info(f"agent listening on {self.port}")
        while self.running:
            conn, addr = s.accept()
            threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()

    def _handle(self, conn, addr):
        buf = b""
        if self.log:
            self.log.info(f"agent: connection from {addr}")
        try:
            while True:
                data = conn.recv(8192)
                if not data:
                    break
                buf += data
                while True:
                    n = unpack_header(buf)
                    if n is None or len(buf) < 4 + n:
                        break
                    body = buf[4:4 + n].decode("utf-8")
                    buf = buf[4 + n:]
                    try:
                        msg = json.loads(body)
                    except Exception:
                        continue
                    if self.log:
                        self.log.event("agent.recv", msg)
                    threading.Thread(
                        target=self._dispatch_and_reply,
                        args=(conn, msg),
                        daemon=True,
                    ).start()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _dispatch_and_reply(self, conn, msg):
        try:
            resp = self._dispatch(msg)
            conn.sendall(pack(resp))
            if self.log:
                self.log.event("agent.send", resp)
        except Exception as e:
            try:
                conn.sendall(pack({"type": "ERROR", "reason": str(e)}))
            except Exception:
                pass

    def _dispatch(self, msg):
        t = msg.get("type", "")
        if t == "PING":
            return {"type": "PONG", "ts": time.time()}

        if t == "RUN":
            cmd = msg.get("command", "")
            if not is_safe_raw(cmd):
                return {"type": "ERROR", "reason": "NOT_WHITELISTED", "cmd": cmd}
            rc, out, err = self._run(cmd)
            return {"type": "RESULT", "rc": rc, "stdout": out, "stderr": err}

        if t == "RUN_MANY":
            results = []
            for cmd in msg.get("commands", []):
                if not is_safe_raw(cmd):
                    results.append({"cmd": cmd, "rc": 1, "error": "NOT_WHITELISTED"})
                    continue
                rc, out, err = self._run(cmd)
                results.append({"cmd": cmd, "rc": rc, "stdout": out, "stderr": err})
            return {"type": "RESULTS", "results": results}

        if t == "PROBE":
            ip = msg.get("ip", "")
            rc, out, err = self._run(f"ping -c 2 -W 2 {ip}")
            return {"type": "PROBE_RESULT", "ok": rc == 0, "ip": ip}

        if t == "RECV_TCP":
            from core.payload import tcp_receiver
            port = int(msg.get("port", 0))
            timeout = float(msg.get("timeout", 20))
            res = tcp_receiver(port, timeout=timeout)
            return {"type": "RECV_TCP_RESULT", **res}

        if t == "RECV_UDP":
            from core.payload import udp_receiver
            port = int(msg.get("port", 0))
            timeout = float(msg.get("timeout", 20))
            res = udp_receiver(port, timeout=timeout)
            return {"type": "RECV_UDP_RESULT", **res}

        if t == "SEND_TCP":
            from core.payload import tcp_send, make_payload
            host = msg.get("host", "")
            port = int(msg.get("port", 0))
            tunnel = msg.get("tunnel", "x")
            direction = msg.get("direction", "rev")
            data = make_payload(tunnel, direction, 1)
            res = tcp_send(host, port, data, timeout=float(msg.get("timeout", 5)))
            return {"type": "SEND_TCP_RESULT", **res}

        if t == "SEND_UDP":
            from core.payload import udp_send, make_payload
            host = msg.get("host", "")
            port = int(msg.get("port", 0))
            tunnel = msg.get("tunnel", "x")
            direction = msg.get("direction", "rev")
            data = make_payload(tunnel, direction, 1)
            res = udp_send(host, port, data, timeout=float(msg.get("timeout", 5)))
            return {"type": "SEND_UDP_RESULT", **res}

        if t == "RECV_TCP6":
            from core.payload import tcp6_receiver
            port = int(msg.get("port", 0))
            timeout = float(msg.get("timeout", 20))
            res = tcp6_receiver(port, timeout=timeout)
            return {"type": "RECV_TCP6_RESULT", **res}

        if t == "RECV_UDP6":
            from core.payload import udp6_receiver
            port = int(msg.get("port", 0))
            timeout = float(msg.get("timeout", 20))
            res = udp6_receiver(port, timeout=timeout)
            return {"type": "RECV_UDP6_RESULT", **res}

        if t == "SEND_TCP6":
            from core.payload import tcp6_send, make_payload
            host = msg.get("host", "")
            port = int(msg.get("port", 0))
            tunnel = msg.get("tunnel", "x")
            direction = msg.get("direction", "rev")
            data = make_payload(tunnel, direction, 1)
            res = tcp6_send(host, port, data, timeout=float(msg.get("timeout", 5)))
            return {"type": "SEND_TCP6_RESULT", **res}

        if t == "SEND_UDP6":
            from core.payload import udp6_send, make_payload
            host = msg.get("host", "")
            port = int(msg.get("port", 0))
            tunnel = msg.get("tunnel", "x")
            direction = msg.get("direction", "rev")
            data = make_payload(tunnel, direction, 1)
            res = udp6_send(host, port, data, timeout=float(msg.get("timeout", 5)))
            return {"type": "SEND_UDP6_RESULT", **res}

        return {"type": "ERROR", "reason": "UNKNOWN_TYPE", "type": t}

    def _run(self, cmd, timeout=30):
        """Run cmd in its own process group. Kill the WHOLE group on timeout."""
        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                text=True,
            )
        except Exception as e:
            return 1, "", str(e)

        try:
            out, err = proc.communicate(timeout=timeout)
            return proc.returncode, out or "", err or ""
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
            try:
                out, err = proc.communicate(timeout=2)
            except Exception:
                out, err = "", ""
            return 124, out or "", (err or "") + "\n[TIMEOUT]"
