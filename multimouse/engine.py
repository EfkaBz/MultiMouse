"""Server (owns the mouse) and client (is controlled) logic.

Every machine is a rectangle in a shared virtual plane, sized with its real
resolution and placed by the user in the layout editor. When the pointer hits an
edge, the neighbour sharing that edge takes over at the matching position.
"""
import logging
import socket
import threading
import time

from . import platform_input as pi
from .net import Beacon, Discovery, Peer, local_ips
from .secure import Channel

log = logging.getLogger("multimouse")

SNAP = 48               # virtual px of tolerance between touching edges
SWITCH_COOLDOWN = 0.2   # s, avoids ping-pong on the border
CTRL = {"ctrl", "ctrl_l", "ctrl_r"}
ALT = {"alt", "alt_l", "alt_r", "alt_gr"}
SWAP = {"ctrl": "cmd", "ctrl_l": "cmd", "ctrl_r": "cmd_r", "cmd": "ctrl_l", "cmd_l": "ctrl_l", "cmd_r": "ctrl_r"}
MODIFIERS = CTRL | ALT | {"shift", "shift_l", "shift_r", "cmd", "cmd_l", "cmd_r", "caps_lock"}
# Keys that only pick another character on this OS (Option on a Mac, AltGr on a PC). Between
# Windows and macOS they are held back: the character itself travels, and they are sent only
# when combined with a non-text key (Option+Tab, AltGr+F4...).
TEXT_MODS = ALT if pi.OS == "mac" else {"alt_r", "alt_gr"}
SCROLL_MAC_FROM_PC = 3  # a Windows wheel notch scrolls 3 lines; a Mac line event is one line


class ClipboardWatch:
    def __init__(self, on_change):
        self.on_change = on_change
        self.last = None
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()

    def set(self, text):
        self.last = text
        try:
            import pyperclip
            pyperclip.copy(text)
        except Exception:
            pass

    def _run(self):
        try:
            import pyperclip
        except ImportError:
            return
        try:
            self.last = pyperclip.paste()
        except Exception:
            pass
        while not self._stop.wait(0.8):
            try:
                text = pyperclip.paste()
            except Exception:
                continue
            if text and text != self.last and len(text) < 1_000_000:
                self.last = text
                self.on_change(text)


# =========================================================================== #
#  Server
# =========================================================================== #
class ServerEngine:
    role = "server"

    def __init__(self, cfg, notify):
        self.cfg, self.notify = cfg, notify
        self.me = cfg["id"]
        self.lock = threading.RLock()
        self.peers = {}
        self.local = pi.get_screens()
        self.nodes = {k: dict(v) for k, v in cfg.get("known", {}).items() if k != self.me}
        self.nodes[self.me] = {"name": cfg["name"], "w": self.local["w"], "h": self.local["h"],
                               "os": pi.OS, "monitors": self.local["monitors"]}
        self.layout = dict(cfg.get("layout", {}))
        self.layout.setdefault(self.me, {"x": 0, "y": 0})
        self.active = self.me
        self.rx = self.ry = 0.0
        self.mods = set()
        self.held_text_mods = {}  # name -> already sent to the target
        self.last_switch = 0.0
        self.edge_hits = 0
        self._why_at = 0.0
        self.error = ""
        self._stop = threading.Event()
        self.capture = pi.Capture(self._on_move, self._on_delta, self._on_button, self._on_scroll, self._on_key)
        self.beacon = Beacon(lambda: {"name": cfg["name"], "id": self.me, "port": cfg["port"]})
        self.clip = ClipboardWatch(self._local_clip)
        self._sock = None

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind(("0.0.0.0", self.cfg["port"]))
            self._sock.listen(8)
            threading.Thread(target=self._accept_loop, daemon=True).start()
        except OSError as e:
            self.error = "port"  # translated by the UI
            log.error("port %s indisponible : %s", self.cfg["port"], e)
        self.beacon.start()
        if self.cfg["clipboard"]:
            self.clip.start()
        self.capture.start()
        threading.Thread(target=self._watchdog, daemon=True, name="watchdog").start()

    def _watchdog(self):
        """The mouse hook can die silently (an error, or Windows dropping a hook it found too
        slow): the pointer then never switches again. Reinstall it when the cursor moves but
        the hook stops seeing anything."""
        last_pos = None
        beat = 0
        while not self._stop.wait(1.0):
            beat += 1
            if beat % 600 == 0:
                log.info("état : %d événements souris, %d contacts de bord, curseur %s, en ligne %s, actif %s",
                         self.capture.events, self.edge_hits, pi.cursor_pos(), list(self.peers), self.active)
            try:
                if self.capture.remote:
                    last_pos = None
                    continue
                pos = pi.cursor_pos()
                quiet = time.monotonic() - self.capture.last_event > 1.5
                recent_warp = time.monotonic() - self.last_switch < 2.0
                if not self.capture.alive() or (quiet and last_pos and pos != last_pos and not recent_warp):
                    log.warning("capture de la souris inactive : réinstallation des hooks")
                    self.capture.restart()
                last_pos = pos
            except Exception:
                log.exception("watchdog")

    def stop(self):
        self._stop.set()
        self.capture.stop()
        self.beacon.stop()
        self.clip.stop()
        if self._sock:
            self._sock.close()
        for p in list(self.peers.values()):
            p.close()

    # -- network -----------------------------------------------------------
    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
            except OSError:
                break
            threading.Thread(target=self._handshake, args=(conn, addr), daemon=True).start()

    def _handshake(self, conn, addr):
        try:
            conn.settimeout(5)
            ch = Channel(conn, self.cfg["code"], is_server=True)
            conn.settimeout(None)
        except Exception:
            conn.close()
            return
        peer = Peer(ch, self._on_message, self._on_close)
        peer.info = {"addr": addr[0]}
        peer.start_reading()

    def _on_message(self, peer, msg):
        t = msg.get("t")
        if t == "hello":
            nid = msg["id"]
            with self.lock:
                old = self.peers.get(nid)
                peer.info.update(id=nid)
                self.peers[nid] = peer
                self.nodes[nid] = {"name": msg["name"], "w": msg["w"], "h": msg["h"], "os": msg["os"],
                                   "monitors": msg.get("monitors", [])}
                if nid not in self.layout:
                    right = max(self.layout[i]["x"] + self.nodes[i]["w"] for i in self.layout if i in self.nodes)
                    self.layout[nid] = {"x": right, "y": self.layout[self.me]["y"]}
                self._persist()
            if old and old is not peer:
                old.close()
            peer.send({"t": "welcome", "name": self.cfg["name"], "id": self.me, "os": pi.OS})
            log.info("connecté : %s (%s, %s)", msg["name"], msg["os"], peer.info.get("addr"))
            self.notify()
        elif t == "clip" and self.cfg["clipboard"]:
            self.clip.set(msg["text"])
            self._broadcast({"t": "clip", "text": msg["text"]}, exclude=peer)

    def _on_close(self, peer):
        nid = peer.info.get("id")
        with self.lock:
            if nid and self.peers.get(nid) is peer:
                del self.peers[nid]
                if self.active == nid:
                    self._go_home()
        self.notify()

    def _broadcast(self, msg, exclude=None):
        for p in list(self.peers.values()):
            if p is not exclude:
                p.send(msg)

    def _local_clip(self, text):
        self._broadcast({"t": "clip", "text": text})

    def _persist(self):
        known = {k: {kk: v[kk] for kk in ("name", "w", "h", "os", "monitors") if kk in v}
                 for k, v in self.nodes.items() if k != self.me}
        self.cfg.set(layout=self.layout, known=known)

    # -- geometry ----------------------------------------------------------
    def online(self, nid):
        return nid == self.me or nid in self.peers

    def rect(self, nid):
        p, n = self.layout[nid], self.nodes[nid]
        return p["x"], p["y"], n["w"], n["h"]

    def neighbor(self, src, side, v):
        sx, sy, sw, sh = self.rect(src)
        for nid in self.nodes:
            if nid == src or nid not in self.layout or not self.online(nid):
                continue
            x, y, w, h = self.rect(nid)
            if side == "left":
                ok = abs(x + w - sx) <= SNAP and y <= v < y + h
            elif side == "right":
                ok = abs(x - (sx + sw)) <= SNAP and y <= v < y + h
            elif side == "top":
                ok = abs(y + h - sy) <= SNAP and x <= v < x + w
            else:
                ok = abs(y - (sy + sh)) <= SNAP and x <= v < x + w
            if ok:
                return nid
        return None

    # -- switching ---------------------------------------------------------
    def _switch(self, nid, side, v):
        x, y, w, h = self.rect(nid)
        if side in ("left", "right"):
            px, py = (w - 2 if side == "left" else 1), v - y
        else:
            px, py = v - x, (h - 2 if side == "top" else 1)
        px, py = min(max(px, 0), w - 1), min(max(py, 0), h - 1)
        self.last_switch = time.monotonic()
        log.info("passage par le bord %s vers %s", side, self.nodes[nid]["name"])
        prev = self.active
        if prev != self.me and prev in self.peers:
            self.peers[prev].send({"t": "leave"})
        self.active = nid
        self.mods.clear()
        self.held_text_mods.clear()
        if nid == self.me:
            b = self.local
            px, py = self._on_monitor(px, py)
            self.capture.set_remote(False, park_at=(b["x"] + px, b["y"] + py))
        else:
            self.rx, self.ry = float(px), float(py)
            self.capture.set_remote(True)
            peer = self.peers[nid]
            peer.send({"t": "enter"})
            peer.send({"t": "m", "x": px, "y": py})
        self.notify()

    def _on_monitor(self, px, py):
        """Nearest point that is really on a monitor. Monitors don't fill the bounding box
        (one set lower than its neighbour leaves a gap), and Windows would push a cursor
        placed in a gap onto whichever monitor is closest to it, not the one under it."""
        def dist(m):
            cx = min(max(px, m["x"]), m["x"] + m["w"] - 1)
            cy = min(max(py, m["y"]), m["y"] + m["h"] - 1)
            return (cx - px) ** 2 + (cy - py) ** 2

        m = min(self.local["monitors"], key=dist)
        return (min(max(px, m["x"] + 1), m["x"] + m["w"] - 2),
                min(max(py, m["y"] + 1), m["y"] + m["h"] - 2))

    def _go_home(self):
        b = self.local
        if self.active != self.me and self.active in self.peers:
            self.peers[self.active].send({"t": "leave"})
        self.active = self.me
        self.mods.clear()
        self.held_text_mods.clear()
        self.capture.set_remote(False, park_at=(b["x"] + b["w"] // 2, b["y"] + b["h"] // 2))
        self.notify()

    # -- capture callbacks (hook thread) -------------------------------------
    def _outer_edge(self, lx, ly):
        """Side of the monitor under the cursor that leads out of this computer, if any.

        Edges are tested per monitor, so a monitor set lower or higher than its
        neighbours still has a usable top/bottom edge."""
        mons = self.local["monitors"]

        def inside(px, py):
            return any(m["x"] <= px < m["x"] + m["w"] and m["y"] <= py < m["y"] + m["h"] for m in mons)

        def dist(m):
            cx = min(max(lx, m["x"]), m["x"] + m["w"] - 1)
            cy = min(max(ly, m["y"]), m["y"] + m["h"] - 1)
            return (cx - lx) ** 2 + (cy - ly) ** 2

        m = min(mons, key=dist)
        lx = min(max(lx, m["x"]), m["x"] + m["w"] - 1)
        ly = min(max(ly, m["y"]), m["y"] + m["h"] - 1)
        if lx <= m["x"] and not inside(lx - 1, ly):
            return "left", lx, ly
        if lx >= m["x"] + m["w"] - 1 and not inside(lx + 1, ly):
            return "right", lx, ly
        if ly <= m["y"] and not inside(lx, ly - 1):
            return "top", lx, ly
        if ly >= m["y"] + m["h"] - 1 and not inside(lx, ly + 1):
            return "bottom", lx, ly
        return None, lx, ly

    def _on_move(self, x, y):
        b = self.local
        side, lx, ly = self._outer_edge(x - b["x"], y - b["y"])
        if side is None:
            return
        self.edge_hits += 1
        if time.monotonic() - self.last_switch < SWITCH_COOLDOWN:
            return
        if not self.peers or pi.buttons_down():
            self._why(side, x, y, f"peers={list(self.peers)} boutons={pi.buttons_down()}")
            return
        with self.lock:
            mx, my, _, _ = self.rect(self.me)
            v = my + ly if side in ("left", "right") else mx + lx
            nid = self.neighbor(self.me, side, v)
            if nid:
                self._switch(nid, side, v)
            else:
                self._why(side, x, y, f"aucun voisin à v={v} ; disposition={self.layout} "
                                      f"en ligne={list(self.peers)} écrans={self.local}")

    def _why(self, side, x, y, reason):
        """Log, at most every 2 s, why touching an edge did not switch."""
        now = time.monotonic()
        if now - self._why_at > 2:
            self._why_at = now
            log.debug("bord %s touché en (%d, %d) sans passage : %s", side, x, y, reason)

    def _on_delta(self, dx, dy):
        with self.lock:
            nid = self.active
            peer = self.peers.get(nid)
            if peer is None:
                self._go_home()
                return
            s = float(self.cfg["speed"])
            self.rx += dx * s
            self.ry += dy * s
            x, y, w, h = self.rect(nid)
            side = None
            if self.rx < 0:
                side, v = "left", y + self.ry
            elif self.rx >= w:
                side, v = "right", y + self.ry
            elif self.ry < 0:
                side, v = "top", x + self.rx
            elif self.ry >= h:
                side, v = "bottom", x + self.rx
            if side and time.monotonic() - self.last_switch >= SWITCH_COOLDOWN:
                target = self.neighbor(nid, side, int(v))
                if target:
                    self._switch(target, side, int(v))
                    return
            self.rx = min(max(self.rx, 0), w - 1)
            self.ry = min(max(self.ry, 0), h - 1)
            peer.send({"t": "m", "x": int(self.rx), "y": int(self.ry)})

    def _on_button(self, name, pressed):
        p = self.peers.get(self.active)
        if p:
            p.send({"t": "b", "b": name, "p": pressed})

    def _on_scroll(self, dx, dy):
        p = self.peers.get(self.active)
        if p:
            p.send({"t": "s", "x": dx, "y": dy})

    def _on_key(self, desc, pressed):
        name = desc.get("name")
        if name in CTRL or name in ALT:
            (self.mods.add if pressed else self.mods.discard)("ctrl" if name in CTRL else "alt")
        if pressed and name == "esc" and {"ctrl", "alt"} <= self.mods:
            with self.lock:
                self._go_home()
            return
        p = self.peers.get(self.active)
        if not p:
            return
        target_os = self.nodes.get(self.active, {}).get("os")
        if {target_os, pi.OS} == {"windows", "mac"}:
            if desc.get("altgr_ctrl"):
                return
            if name in TEXT_MODS:
                if pressed:
                    self.held_text_mods.setdefault(name, False)
                elif self.held_text_mods.pop(name, False):
                    p.send({"t": "k", "k": self._mod_desc(name, target_os), "p": False})
                return
            if pressed and not desc.get("text") and name not in MODIFIERS:
                for n, sent in self.held_text_mods.items():
                    if not sent:
                        p.send({"t": "k", "k": self._mod_desc(n, target_os), "p": True})
                        self.held_text_mods[n] = True
            if self.cfg["swap_ctrl_cmd"] and name in SWAP:
                desc = {**desc, "name": SWAP[name], "vk": None}
        p.send({"t": "k", "k": desc, "p": pressed})

    @staticmethod
    def _mod_desc(name, target_os):
        if target_os == "windows":
            name = "alt_l"  # right Alt is AltGr on many PC layouts
        return {"vk": None, "name": name, "char": None, "os": pi.OS}

    # -- UI ----------------------------------------------------------------
    def set_layout(self, nid, x, y):
        with self.lock:
            if nid in self.nodes:
                self.layout[nid] = {"x": int(x), "y": int(y)}
                self._persist()
        self.notify()

    def forget(self, nid):
        with self.lock:
            if nid == self.me or nid in self.peers:
                return
            self.nodes.pop(nid, None)
            self.layout.pop(nid, None)
            self._persist()
        self.notify()

    def rename_self(self, name):
        self.nodes[self.me]["name"] = name
        self.notify()

    def state(self):
        with self.lock:
            nodes = []
            for nid, n in self.nodes.items():
                if nid not in self.layout:
                    continue
                nodes.append({"id": nid, "name": n["name"], "w": n["w"], "h": n["h"], "os": n["os"],
                              "monitors": n.get("monitors", []), "x": self.layout[nid]["x"],
                              "y": self.layout[nid]["y"], "online": self.online(nid),
                              "me": nid == self.me, "active": nid == self.active,
                              "addr": self.peers[nid].info.get("addr") if nid in self.peers else None})
            return {"role": "server", "nodes": nodes, "ips": local_ips(), "error": self.error,
                    "connected": len(self.peers)}


# =========================================================================== #
#  Client
# =========================================================================== #
class ClientEngine:
    role = "client"

    def __init__(self, cfg, notify):
        self.cfg, self.notify = cfg, notify
        self.local = pi.get_screens()
        self.inj = pi.Injector()
        self.peer = None
        self.server_name = ""
        self.server_os = ""
        self.server_addr = ""
        self.status = "searching"     # searching | connecting | connected | refused
        self.active = False
        self._stop = threading.Event()
        self._kick = threading.Event()
        self.discovery = Discovery(self.notify)
        self.clip = ClipboardWatch(self._local_clip)

    def start(self):
        self.discovery.start()
        if self.cfg["clipboard"]:
            self.clip.start()
        threading.Thread(target=self._connect_loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._kick.set()
        self.discovery.stop()
        self.clip.stop()
        if self.peer:
            self.peer.close()
        self.inj.release_all()

    def reconnect(self):
        if self.peer:
            self.peer.close()
        self._kick.set()

    def _target(self):
        host = self.cfg["server_host"].strip()
        if host:
            port = self.cfg["port"]
            if ":" in host:
                host, port = host.rsplit(":", 1)
            return host, int(port)
        if self.discovery.servers:
            info = sorted(self.discovery.servers.values(), key=lambda i: -i["seen"])[0]
            return info["addr"], int(info.get("port", self.cfg["port"]))
        return None

    def _connect_loop(self):
        while not self._stop.is_set():
            target = self._target()
            if not target:
                self._set_status("searching")
                self._kick.wait(1.5)
                self._kick.clear()
                continue
            self._set_status("connecting")
            self.server_addr = target[0]
            welcomed = threading.Event()
            closed = threading.Event()
            try:
                sock = socket.create_connection(target, timeout=4)
                ch = Channel(sock, self.cfg["code"], is_server=False)
                sock.settimeout(None)

                def on_msg(_p, msg):
                    if msg.get("t") == "welcome":
                        self.server_name = msg.get("name", "")
                        self.server_os = msg.get("os", "")
                        welcomed.set()
                        self._set_status("connected")
                    self._on_message(msg)

                self.peer = Peer(ch, on_msg, lambda _p: closed.set())
                self.peer.start_reading()
                self.peer.send({"t": "hello", "id": self.cfg["id"], "name": self.cfg["name"], "os": pi.OS,
                                "w": self.local["w"], "h": self.local["h"], "monitors": self.local["monitors"]})
                while not closed.wait(0.5):
                    if self._stop.is_set():
                        break
            except Exception:
                pass
            self.peer = None
            self.active = False
            self.inj.release_all()
            if not self._stop.is_set():
                self._set_status("connected_lost" if welcomed.is_set() else
                                 ("refused" if self.server_addr else "searching"))
                self._kick.wait(2.5)
                self._kick.clear()

    def _set_status(self, s):
        if s != self.status:
            self.status = s
            self.notify()

    def _on_message(self, msg):
        t = msg.get("t")
        b = self.local
        if t == "m":
            self.inj.move(b["x"] + msg["x"], b["y"] + msg["y"])
        elif t == "b":
            self.inj.button(msg["b"], msg["p"])
        elif t == "s":
            k = SCROLL_MAC_FROM_PC if pi.OS == "mac" and self.server_os == "windows" else 1
            self.inj.scroll(msg["x"] * k, msg["y"] * k)
        elif t == "k":
            self.inj.key(msg["k"], msg["p"])
        elif t == "enter":
            self.active = True
            self.notify()
        elif t == "leave":
            self.active = False
            self.inj.release_all()
            self.notify()
        elif t == "clip" and self.cfg["clipboard"]:
            self.clip.set(msg["text"])

    def _local_clip(self, text):
        if self.peer:
            self.peer.send({"t": "clip", "text": text})

    def rename_self(self, name):
        if self.peer:
            self.reconnect()

    def state(self):
        servers = [{"addr": i["addr"], "name": i.get("name", i["addr"]), "port": i.get("port")}
                   for i in self.discovery.servers.values()]
        return {"role": "client", "status": self.status, "server_name": self.server_name,
                "server_addr": self.server_addr, "active": self.active, "servers": servers,
                "screen": {"w": self.local["w"], "h": self.local["h"], "monitors": self.local["monitors"]}}
