"""Persistent settings stored as JSON in the user's config directory."""
import json
import os
import platform
import secrets
import socket
import sys
import threading
import uuid

DEFAULTS = {
    "role": "server",            # "server" (owns the mouse) or "client"
    "name": socket.gethostname().split(".")[0],
    "id": None,                  # stable machine id
    "code": None,                # pairing code shared by all machines
    "server_host": "",           # client: address of the server
    "port": 24800,
    "layout": {},                # server: machine_id -> {"x": int, "y": int}
    "known": {},                 # server: machine_id -> {"name", "w", "h", "os"}
    "clipboard": True,
    "swap_ctrl_cmd": True,       # map Ctrl <-> Cmd when crossing Windows <-> Mac
    "speed": 1.0,                # remote pointer speed multiplier
    "autostart": False,
    "theme": "auto",             # "auto" (system), "light" or "dark"
    "language": "auto",          # "auto" (system language), "fr" or "en"
}


def config_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    path = os.path.join(base, "MultiMouse")
    os.makedirs(path, exist_ok=True)
    return path


def os_kind():
    s = platform.system()
    return {"Windows": "windows", "Darwin": "mac"}.get(s, "linux")


class Config:
    def __init__(self):
        self._path = os.path.join(config_dir(), "settings.json")
        self._lock = threading.Lock()
        self.data = dict(DEFAULTS)
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass
        if not self.data.get("id"):
            self.data["id"] = uuid.uuid4().hex[:12]
        if not self.data.get("code"):
            self.data["code"] = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        self.save()

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, **kwargs):
        with self._lock:
            self.data.update(kwargs)
        self.save()

    def save(self):
        with self._lock:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self._path)
