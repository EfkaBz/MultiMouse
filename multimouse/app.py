"""Desktop window (pywebview) and the JS <-> Python bridge."""
import json
import os
import sys
import threading

from . import APP_NAME, __version__
from . import platform_input as pi
from .config import Config
from .engine import ClientEngine, ServerEngine


def resource(*parts):
    # PyInstaller bundles the ui folder next to this module, so __file__ works in both cases
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)


def mac_permissions():
    """macOS privacy switches: Accessibility (inject input) and Input Monitoring (capture it)."""
    if pi.OS != "mac":
        return None
    try:
        import HIServices
        import Quartz
        return {"accessibility": bool(HIServices.AXIsProcessTrusted()),
                "input": bool(Quartz.CGPreflightListenEventAccess())}
    except Exception:
        return None


def mac_request_permissions():
    """Show the system prompts and add MultiMouse to both lists in System Settings."""
    try:
        import HIServices
        import Quartz
        HIServices.AXIsProcessTrustedWithOptions({HIServices.kAXTrustedCheckOptionPrompt: True})
        Quartz.CGRequestListenEventAccess()
    except Exception:
        pass


class Api:
    """Every public method is callable from JS as window.pywebview.api.<name>()."""

    def __init__(self):
        self._cfg = Config()
        self._engine = None
        self._window = None
        self._dirty = threading.Event()
        self._lock = threading.Lock()
        self._perms = mac_permissions()
        threading.Thread(target=self._pusher, daemon=True).start()
        if self._perms is not None:
            if not all(self._perms.values()):
                mac_request_permissions()
            threading.Thread(target=self._watch_permissions, daemon=True).start()

    def _watch_permissions(self):
        """Event taps can only be created once allowed: restart the engine when that happens."""
        while True:
            threading.Event().wait(2)
            perms = mac_permissions()
            if perms != self._perms:
                gained = any(perms[k] and not self._perms[k] for k in perms)
                self._perms = perms
                if gained and self._engine is not None:
                    self._start_engine()
                self._notify()

    # -- engine ------------------------------------------------------------
    def _start_engine(self):
        with self._lock:
            if self._engine:
                self._engine.stop()
            cls = ServerEngine if self._cfg["role"] == "server" else ClientEngine
            self._engine = cls(self._cfg, self._notify)
            self._engine.start()
        self._notify()

    def _notify(self):
        self._dirty.set()

    def _pusher(self):
        while True:
            self._dirty.wait()
            self._dirty.clear()
            if self._window is not None:
                try:
                    self._window.evaluate_js(f"window.mm && window.mm.update({json.dumps(self.get_state())})")
                except Exception:
                    pass
            threading.Event().wait(0.05)  # coalesce bursts

    # -- exposed to JS -----------------------------------------------------
    def get_state(self):
        c = self._cfg
        base = {"version": __version__, "os": pi.OS, "id": c["id"], "name": c["name"], "code": c["code"],
                "port": c["port"], "server_host": c["server_host"], "clipboard": c["clipboard"],
                "swap_ctrl_cmd": c["swap_ctrl_cmd"], "speed": c["speed"], "role": c["role"],
                "permissions": self._perms}
        eng = self._engine
        if eng is not None:
            base.update(eng.state())
        return base

    def set_role(self, role):
        if role in ("server", "client") and role != self._cfg["role"]:
            self._cfg.set(role=role)
            threading.Thread(target=self._start_engine, daemon=True).start()
        return True

    def set_setting(self, key, value):
        allowed = {"clipboard": bool, "swap_ctrl_cmd": bool, "speed": float, "name": str,
                   "server_host": str, "code": str, "port": int}
        if key not in allowed:
            return False
        value = allowed[key](value)
        if key == "code":
            value = value.strip().upper()
            if len(value) < 4:
                return False
        if key == "name":
            value = value.strip()[:40] or self._cfg["name"]
        if key == "speed":
            value = min(max(value, 0.3), 3.0)
        self._cfg.set(**{key: value})
        if key in ("code", "port", "clipboard"):
            threading.Thread(target=self._start_engine, daemon=True).start()
        elif key == "server_host" and isinstance(self._engine, ClientEngine):
            self._engine.reconnect()
        elif key == "name" and self._engine:
            self._engine.rename_self(value)
        self._notify()
        return True

    def regenerate_code(self):
        import secrets
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        return self.set_setting("code", code)

    def set_layout(self, nid, x, y):
        if isinstance(self._engine, ServerEngine):
            self._engine.set_layout(nid, x, y)
        return True

    def forget(self, nid):
        if isinstance(self._engine, ServerEngine):
            self._engine.forget(nid)
        return True

    def connect_to(self, addr):
        return self.set_setting("server_host", addr)

    def copy_text(self, text):
        try:
            import pyperclip
            pyperclip.copy(text)
            return True
        except Exception:
            return False

    def open_permissions(self):
        mac_request_permissions()
        missing = "Accessibility" if self._perms and not self._perms["accessibility"] else "ListenEvent"
        os.system(f"open 'x-apple.systempreferences:com.apple.preference.security?Privacy_{missing}'")
        return True

    def shutdown(self):
        if self._engine:
            self._engine.stop()


MUTEX_NAME = "MultiMouseSingleInstance"  # also referenced by installer/MultiMouse.iss (AppMutex)


def _already_running():
    """Windows: keep one instance (it owns the network port); bring the existing window forward."""
    if pi.OS != "windows":
        return False
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.restype = ctypes.c_void_p
    _already_running.handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    if k32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
        return False
    hwnd = pi.user32.FindWindowW(None, APP_NAME)
    if hwnd:
        pi.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        pi.user32.SetForegroundWindow(hwnd)
    return True


def main():
    if _already_running():
        return
    import webview

    api = Api()
    k = 1.0
    if pi.OS == "windows":  # the process is DPI aware, so window sizes are physical pixels
        try:
            k = max(1.0, pi.user32.GetDpiForSystem() / 96)
        except Exception:
            pass
    window = webview.create_window(
        APP_NAME,
        url=resource("ui", "index.html"),
        js_api=api,
        width=int(1060 * k), height=int(700 * k), min_size=(int(880 * k), int(580 * k)),
        background_color="#F5F5F7",
        text_select=False,
        minimized="--minimized" in sys.argv,  # used by the "start with Windows" shortcut
    )
    api._window = window

    def on_loaded():
        api._start_engine() if api._engine is None else api._notify()

    window.events.loaded += on_loaded
    window.events.closed += api.shutdown
    webview.start(debug="--debug" in sys.argv)
