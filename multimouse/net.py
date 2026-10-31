"""Peers, LAN discovery and the TCP accept loop."""
import json
import logging
import queue
import socket
import threading
import time

from .secure import AuthError, Channel

DISCOVERY_PORT = 24801
log = logging.getLogger("multimouse")


class Peer:
    """One encrypted connection with a dedicated writer thread (hook threads never block on I/O)."""

    def __init__(self, channel: Channel, on_message, on_close):
        self.ch = channel
        self.info = {}
        self._q = queue.Queue(maxsize=4096)
        self._on_message, self._on_close = on_message, on_close
        self._closed = threading.Event()
        threading.Thread(target=self._writer, daemon=True).start()

    def start_reading(self):
        threading.Thread(target=self._reader, daemon=True).start()

    def send(self, msg):
        if self._closed.is_set():
            return
        try:
            self._q.put_nowait(msg)
        except queue.Full:
            pass

    def _writer(self):
        while not self._closed.is_set():
            try:
                msg = self._q.get(timeout=1)
            except queue.Empty:
                continue
            if msg is None:
                break
            try:
                self.ch.send(msg)
            except Exception:
                self.close()

    def _reader(self):
        try:
            while not self._closed.is_set():
                self._on_message(self, self.ch.recv())
        except AuthError:
            log.warning("%s refusé : code d'appairage différent", self.info.get("addr"))
        except (ConnectionError, OSError) as e:
            log.info("connexion %s fermée : %s", self.info.get("addr") or self.info.get("id"), e)
        except Exception:
            log.exception("erreur en traitant un message de %s", self.info)
        self.close()

    def close(self):
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._q.put_nowait(None)
        except queue.Full:
            pass
        self.ch.close()
        self._on_close(self)

    @property
    def closed(self):
        return self._closed.is_set()


class Beacon:
    """Server: broadcast our presence every 2 s (name/port only, no secret)."""

    def __init__(self, info_fn):
        self.info_fn = info_fn
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not self._stop.is_set():
            try:
                s.sendto(json.dumps({"mm": 1, **self.info_fn()}).encode(), ("255.255.255.255", DISCOVERY_PORT))
            except OSError:
                pass
            self._stop.wait(2)
        s.close()


class Discovery:
    """Client: listen for server beacons. `servers` maps address -> info."""

    def __init__(self, on_change):
        self.servers = {}
        self.on_change = on_change
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", DISCOVERY_PORT))
        except OSError:
            return
        s.settimeout(1)
        while not self._stop.is_set():
            changed = False
            try:
                data, (addr, _) = s.recvfrom(2048)
                info = json.loads(data)
                if info.get("mm") == 1:
                    changed = addr not in self.servers
                    self.servers[addr] = {**info, "addr": addr, "seen": time.time()}
            except (socket.timeout, ValueError):
                pass
            except OSError:
                break
            for a in [a for a, i in self.servers.items() if time.time() - i["seen"] > 7]:
                del self.servers[a]
                changed = True
            if changed:
                self.on_change()
        s.close()


def local_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    ips.discard("127.0.0.1")
    return sorted(ips)
