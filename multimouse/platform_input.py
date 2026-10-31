"""Native input capture and injection for Windows and macOS.

Capture (machine that owns the mouse):
  * local mode  -> reports absolute cursor positions so the engine can detect edges
  * remote mode -> swallows every mouse/keyboard event and reports relative deltas

Injection (machine being controlled): absolute moves, buttons, wheel and keys.
"""
import ctypes
import sys
import threading
import time

from .config import os_kind

OS = os_kind()

if OS == "windows":
    try:  # physical pixels everywhere, must run before any window exists
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    from ctypes import wintypes

    user32 = ctypes.windll.user32

if OS == "mac":
    import AppKit  # shipped with pynput on macOS (pyobjc-framework-Cocoa / Quartz)
    import Quartz

    def _mac_allow_background_cursor():
        """Let CGDisplayHideCursor work while another app is in front (same trick as Synergy)."""
        try:
            cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            cg._CGSDefaultConnection.restype = ctypes.c_int
            cg.CGSSetConnectionProperty.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
            cf.CFStringCreateWithCString.restype = ctypes.c_void_p
            cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
            conn = cg._CGSDefaultConnection()
            key = cf.CFStringCreateWithCString(None, b"SetsCursorInBackground", 0x08000100)
            cg.CGSSetConnectionProperty(conn, conn, key, ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue"))
        except Exception:
            pass

    _mac_allow_background_cursor()
    try:  # warping the cursor would otherwise freeze local events for 0.25 s
        Quartz.CGSetLocalEventsSuppressionInterval(0.0)
    except Exception:
        pass

from pynput import keyboard, mouse
from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button


# --------------------------------------------------------------------------- #
#  Screens
# --------------------------------------------------------------------------- #
def get_screens():
    """Return {"x","y","w","h","monitors":[...]}: desktop bounding box in input coordinates."""
    mons = []
    if OS == "windows":
        proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                  ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

        def cb(_h, _dc, rect, _lp):
            r = rect.contents
            mons.append({"x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top})
            return 1

        user32.EnumDisplayMonitors(None, None, proc(cb), 0)
    elif OS == "mac":
        err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
        for did in ids[:count]:
            b = Quartz.CGDisplayBounds(did)
            mons.append({"x": int(b.origin.x), "y": int(b.origin.y),
                         "w": int(b.size.width), "h": int(b.size.height)})
    if not mons:
        try:
            import tkinter
            root = tkinter.Tk()
            mons.append({"x": 0, "y": 0, "w": root.winfo_screenwidth(), "h": root.winfo_screenheight()})
            root.destroy()
        except Exception:
            mons.append({"x": 0, "y": 0, "w": 1920, "h": 1080})
    x0 = min(m["x"] for m in mons)
    y0 = min(m["y"] for m in mons)
    x1 = max(m["x"] + m["w"] for m in mons)
    y1 = max(m["y"] + m["h"] for m in mons)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
            "monitors": [{**m, "x": m["x"] - x0, "y": m["y"] - y0} for m in mons]}


def buttons_down():
    """True while a physical mouse button is held (we never switch machines mid-drag)."""
    if OS == "windows":
        return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x01, 0x02, 0x04))
    if OS == "mac":
        st = Quartz.kCGEventSourceStateCombinedSessionState
        return any(Quartz.CGEventSourceButtonState(st, b) for b in (0, 1, 2))
    return False


def cursor_pos():
    if OS == "mac":
        p = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        return int(p.x), int(p.y)
    return mouse.Controller().position


# --------------------------------------------------------------------------- #
#  Key description shared across platforms
# --------------------------------------------------------------------------- #
_NAME_BY_VK = {}
for _k in Key:
    try:
        # macOS media keys use NX codes (0, 1, 7, 14, 16-18) that collide with letter keycodes
        if _k.value.vk is not None and not getattr(_k.value, "_is_media", False):
            _NAME_BY_VK.setdefault(_k.value.vk, _k.name)
    except AttributeError:
        pass

_WIN_NUMPAD = {**{0x60 + i: str(i) for i in range(10)},
               0x6A: "*", 0x6B: "+", 0x6D: "-", 0x6E: ".", 0x6F: "/"}

_MAC_ANSI = {0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c", 9: "v",
             11: "b", 12: "q", 13: "w", 14: "e", 15: "r", 16: "y", 17: "t", 18: "1", 19: "2",
             20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8",
             29: "0", 30: "]", 31: "o", 32: "u", 33: "[", 34: "i", 35: "p", 37: "l", 38: "j",
             39: "'", 40: "k", 41: ";", 42: "\\", 43: ",", 44: "/", 45: "n", 46: "m", 47: ".",
             50: "`", 65: ".", 67: "*", 69: "+", 75: "/", 78: "-", 82: "0", 83: "1", 84: "2",
             85: "3", 86: "4", 87: "5", 88: "6", 89: "7", 91: "8", 92: "9"}


def _mac_layout_table():
    """keycode -> unshifted char for the active keyboard layout (falls back to US ANSI)."""
    table = dict(_MAC_ANSI)
    try:
        from pynput._util.darwin import keycode_context, keycode_to_string
        with keycode_context() as ctx:
            for kc in range(128):
                if kc in (36, 48, 49, 51, 53) or kc in _NAME_BY_VK:
                    continue
                s = keycode_to_string(ctx, kc)
                if s and s.isprintable() and s.strip():
                    table[kc] = s.lower()
    except Exception:
        pass
    return table


_MAC_CHARS = _mac_layout_table() if OS == "mac" else {}
_MAC_CHAR_TO_KC = {}
for _kc, _ch in _MAC_CHARS.items():
    _MAC_CHAR_TO_KC.setdefault(_ch, _kc)

# Typed characters travel as text between Windows and macOS: the AZERTY layouts of the two
# systems place @ # { [ | \ _ - and others on different keys, so each side retypes the
# character with its own layout instead of replaying a key position.
_UC_SHIFT, _UC_CAPS, _UC_OPT = 0x02, 0x04, 0x08            # UCKeyTranslate modifier bits
_CG_SHIFT, _CG_CTRL, _CG_OPT, _CG_CMD = 0x20000, 0x40000, 0x80000, 0x100000
_CG_CAPS, _CG_NUMPAD, _CG_FN = 0x10000, 0x200000, 0x800000
_MAC_MODS = {56: _CG_SHIFT | 0x2, 60: _CG_SHIFT | 0x4, 59: _CG_CTRL | 0x1, 62: _CG_CTRL | 0x2000,
             58: _CG_OPT | 0x20, 61: _CG_OPT | 0x40, 55: _CG_CMD | 0x8, 54: _CG_CMD | 0x10, 63: _CG_FN}
_MAC_CAPS_KC = 57
_MAC_KEYPAD = {65, 67, 69, 75, 78, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92}


def _mac_text_tables():
    """(keycode, UC modifiers) -> (char, dead) and char -> (keycode, CG flags, dead)."""
    fwd, rev = {}, {}
    try:
        from pynput._util.darwin import CarbonExtra, keycode_context
        with keycode_context() as (kbd_type, layout):
            if not layout:
                return fwd, rev

            def translate(kc, mods, no_dead):
                dead, n, buf = ctypes.c_uint32(), ctypes.c_uint8(), (ctypes.c_uint16 * 4)()
                CarbonExtra.UCKeyTranslate(layout, kc, 0, mods, kbd_type, 1 if no_dead else 0,
                                           ctypes.byref(dead), 4, ctypes.byref(n), buf)
                return "".join(chr(buf[i]) for i in range(n.value)), dead.value

            for mods, flags in ((0, 0), (_UC_SHIFT, _CG_SHIFT), (_UC_OPT, _CG_OPT),
                                (_UC_SHIFT | _UC_OPT, _CG_SHIFT | _CG_OPT),
                                (_UC_CAPS, None), (_UC_CAPS | _UC_SHIFT, None),
                                (_UC_CAPS | _UC_OPT, None), (_UC_CAPS | _UC_SHIFT | _UC_OPT, None)):
                for kc in range(128):
                    if kc in _NAME_BY_VK or kc in _MAC_MODS or kc == _MAC_CAPS_KC:
                        continue
                    s, dead_state = translate(kc, mods, False)
                    dead = not s and dead_state != 0
                    if dead:
                        s = translate(kc, mods, True)[0]
                    if len(s) != 1 or not s.isprintable() or not s.strip():
                        continue
                    fwd[(kc, mods)] = (s, dead)
                    cur = rev.get(s)  # prefer the main block over the keypad
                    if flags is not None and (cur is None or (cur[0] in _MAC_KEYPAD and kc not in _MAC_KEYPAD)):
                        rev[s] = (kc, flags, dead)
    except Exception:
        pass
    return fwd, rev


_MAC_TEXT, _MAC_TYPE = _mac_text_tables() if OS == "mac" else ({}, {})


def describe_key(vk):
    """Turn a native key code into a portable description."""
    name = _NAME_BY_VK.get(vk)
    char = None
    if name is None:
        if OS == "windows":
            char = _WIN_NUMPAD.get(vk)
            if char is None:
                c = user32.MapVirtualKeyW(vk, 2) & 0xFFFF
                if c & 0x7FFF:  # the top bit only flags a dead key (^ ¨ on AZERTY)
                    char = chr(c & 0x7FFF).lower()
        elif OS == "mac":
            char = _MAC_CHARS.get(vk)
    return {"vk": vk, "name": name, "char": char, "os": OS}


# --------------------------------------------------------------------------- #
#  Capture
# --------------------------------------------------------------------------- #
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x200, 0x201, 0x202
WM_RBUTTONDOWN, WM_RBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP = 0x204, 0x205, 0x207, 0x208
WM_MOUSEWHEEL, WM_XBUTTONDOWN, WM_XBUTTONUP, WM_MOUSEHWHEEL = 0x20A, 0x20B, 0x20C, 0x20E
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
LLMHF_INJECTED = 0x01

_WIN_BUTTONS = {WM_LBUTTONDOWN: ("left", True), WM_LBUTTONUP: ("left", False),
                WM_RBUTTONDOWN: ("right", True), WM_RBUTTONUP: ("right", False),
                WM_MBUTTONDOWN: ("middle", True), WM_MBUTTONUP: ("middle", False)}


def _signed16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def _win_layout():
    """Keyboard layout of the foreground window (each window can have its own)."""
    tid = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    return user32.GetKeyboardLayout(tid)


if OS == "windows":
    user32.GetKeyboardLayout.restype = ctypes.c_void_p
    user32.ToUnicodeEx.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_ubyte),
                                   ctypes.c_wchar_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
    user32.VkKeyScanExW.argtypes = [ctypes.c_wchar, ctypes.c_void_p]
    user32.VkKeyScanExW.restype = ctypes.c_short

_NX_MEDIA = {0: "media_volume_up", 1: "media_volume_down", 7: "media_volume_mute", 16: "media_play_pause",
             17: "media_next", 18: "media_previous", 19: "media_next", 20: "media_previous"}


def _mac_guard(listener):
    """macOS disables an event tap whose callback was slow once; pynput never re-enables it."""
    create, handle = listener._create_event_tap, listener._handle_message
    disabled = (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput)

    def create_tap():
        listener._mm_tap = create()
        return listener._mm_tap

    def handle_message(proxy, etype, event, refcon, injected):
        if etype in disabled:
            if getattr(listener, "_mm_tap", None) is not None:
                Quartz.CGEventTapEnable(listener._mm_tap, True)
            return
        try:
            handle(proxy, etype, event, refcon, injected)
        except Exception:
            pass

    listener._create_event_tap = create_tap
    listener._handle_message = handle_message
    return listener


class Capture:
    """Global hooks. Callbacks run on the hook thread and must stay fast."""

    def __init__(self, on_move, on_delta, on_button, on_scroll, on_key):
        self.on_move, self.on_delta = on_move, on_delta
        self.on_button, self.on_scroll, self.on_key = on_button, on_scroll, on_key
        self.remote = False
        self.center = (0, 0)
        self._ml = self._kl = None
        self._held = set()        # Windows: modifier vks held while remote
        self._caps = False        # Windows: caps lock as seen by the remote machine
        self._hidden = False      # macOS: cursor hidden by us

    # -- lifecycle ---------------------------------------------------------
    def start(self):
        if OS == "windows":
            self._ml = mouse.Listener(win32_event_filter=self._win_mouse)
            self._kl = keyboard.Listener(win32_event_filter=self._win_key)
        elif OS == "mac":
            self._ml = _mac_guard(mouse.Listener(darwin_intercept=self._mac_mouse))
            self._kl = _mac_guard(keyboard.Listener(darwin_intercept=self._mac_key))
        else:
            self._ml = mouse.Listener(on_move=self.on_move)
            self._kl = keyboard.Listener()
        self._ml.start()
        self._kl.start()

    def stop(self):
        self.set_remote(False)
        for l in (self._ml, self._kl):
            if l:
                l.stop()
        self._ml = self._kl = None

    def set_remote(self, remote, park_at=None):
        """Enter/leave remote mode. In remote mode the local cursor is frozen at screen center."""
        if remote == self.remote and park_at is None:
            return
        self.remote = remote
        if remote:
            s = get_screens()
            prim = s["monitors"][0]
            self.center = (s["x"] + prim["x"] + prim["w"] // 2, s["y"] + prim["y"] + prim["h"] // 2)
            self._warp(*self.center)
            if OS == "windows":
                self._held.clear()
                self._caps = bool(user32.GetKeyState(0x14) & 1)
            elif OS == "mac":
                Quartz.CGAssociateMouseAndMouseCursorPosition(False)
                if not self._hidden:  # hide/show calls are counted, keep them balanced
                    Quartz.CGDisplayHideCursor(Quartz.CGMainDisplayID())
                    self._hidden = True
        else:
            if OS == "mac":
                Quartz.CGAssociateMouseAndMouseCursorPosition(True)
                if self._hidden:
                    Quartz.CGDisplayShowCursor(Quartz.CGMainDisplayID())
                    self._hidden = False
            if park_at:
                self._warp(*park_at)

    @staticmethod
    def _warp(x, y):
        if OS == "windows":
            user32.SetCursorPos(int(x), int(y))
        elif OS == "mac":
            Quartz.CGWarpMouseCursorPosition((x, y))
        else:
            mouse.Controller().position = (x, y)

    # -- Windows -----------------------------------------------------------
    def _win_mouse(self, msg, data):
        if data.flags & LLMHF_INJECTED:
            return False
        if not self.remote:
            if msg == WM_MOUSEMOVE:
                self.on_move(data.pt.x, data.pt.y)
            return False
        if msg == WM_MOUSEMOVE:
            # Measure against the real cursor position: the move that crossed the edge was
            # not suppressed, so the cursor may sit on the border instead of the center.
            cur = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cur))
            dx, dy = data.pt.x - cur.x, data.pt.y - cur.y
            if abs(cur.x - self.center[0]) > 50 or abs(cur.y - self.center[1]) > 50:
                user32.SetCursorPos(*self.center)  # sticks: this event is suppressed below
            if dx or dy:
                self.on_delta(dx, dy)
        elif msg in _WIN_BUTTONS:
            self.on_button(*_WIN_BUTTONS[msg])
        elif msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            which = "x1" if (data.mouseData >> 16) == 1 else "x2"
            self.on_button(which, msg == WM_XBUTTONDOWN)
        elif msg == WM_MOUSEWHEEL:
            self.on_scroll(0, _signed16(data.mouseData >> 16) / 120.0)
        elif msg == WM_MOUSEHWHEEL:
            self.on_scroll(_signed16(data.mouseData >> 16) / 120.0, 0)
        self._ml.suppress_event()

    def _win_key(self, msg, data):
        if not self.remote or data.flags & 0x10:  # LLKHF_INJECTED
            return False
        vk, pressed = data.vkCode, msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
        desc = describe_key(vk)
        if vk == 0xA2 and data.scanCode == 0x21D:
            desc["altgr_ctrl"] = True  # the fake Ctrl Windows sends with AltGr
        elif vk in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C):
            (self._held.add if pressed else self._held.discard)(vk)
        elif vk == 0x14 and pressed:
            self._caps = not self._caps
        elif pressed and desc["name"] is None:
            text = self._win_text(vk, data.scanCode)
            if text:
                desc["text"], desc["dead"] = text
        self.on_key(desc, pressed)
        self._kl.suppress_event()

    def _win_text(self, vk, scan):
        """Character this key types with the current Shift/AltGr/Caps state, or None for shortcuts."""
        held = self._held
        if held & {0xA2, 0xA3, 0xA4, 0x5B, 0x5C}:  # Ctrl, left Alt or Win: a shortcut, not text
            return None
        state = (ctypes.c_ubyte * 256)()
        if held & {0xA0, 0xA1}:
            state[0x10] = state[0xA0] = 0x80
        if 0xA5 in held:  # AltGr = Ctrl + Alt
            state[0x11] = state[0xA2] = state[0x12] = state[0xA5] = 0x80
        if self._caps:
            state[0x14] = 0x01
        buf = ctypes.create_unicode_buffer(8)
        # flag 4: leave the kernel dead-key state alone (Windows 10 1607+)
        n = user32.ToUnicodeEx(vk, scan, state, buf, 8, 4, _win_layout())
        ch = buf.value[:1]
        if n == 0 or not ch or not ch.isprintable() or not ch.strip() or n > 1:
            return None
        return ch, n < 0

    # -- macOS -------------------------------------------------------------
    def _mac_mouse(self, etype, event):
        if not self.remote:
            if etype in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDragged,
                         Quartz.kCGEventRightMouseDragged, Quartz.kCGEventOtherMouseDragged):
                p = Quartz.CGEventGetLocation(event)
                self.on_move(int(p.x), int(p.y))
            return event
        f = Quartz.CGEventGetIntegerValueField
        if etype in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDragged,
                     Quartz.kCGEventRightMouseDragged, Quartz.kCGEventOtherMouseDragged):
            dx, dy = f(event, Quartz.kCGMouseEventDeltaX), f(event, Quartz.kCGMouseEventDeltaY)
            p = Quartz.CGEventGetLocation(event)
            if abs(p.x - self.center[0]) > 50 or abs(p.y - self.center[1]) > 50:
                self._warp(*self.center)  # the cursor got loose (e.g. association refused)
            if dx or dy:
                self.on_delta(dx, dy)
        elif etype == Quartz.kCGEventLeftMouseDown:
            self.on_button("left", True)
        elif etype == Quartz.kCGEventLeftMouseUp:
            self.on_button("left", False)
        elif etype == Quartz.kCGEventRightMouseDown:
            self.on_button("right", True)
        elif etype == Quartz.kCGEventRightMouseUp:
            self.on_button("right", False)
        elif etype in (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp):
            n = f(event, Quartz.kCGMouseEventButtonNumber)
            self.on_button({2: "middle", 3: "x1", 4: "x2"}.get(n, "middle"),
                           etype == Quartz.kCGEventOtherMouseDown)
        elif etype == Quartz.kCGEventScrollWheel:
            gf = Quartz.CGEventGetDoubleValueField
            dy = gf(event, Quartz.kCGScrollWheelEventFixedPtDeltaAxis1)
            dx = gf(event, Quartz.kCGScrollWheelEventFixedPtDeltaAxis2)
            if dx or dy:
                self.on_scroll(-dx, dy)
        return None

    def _mac_key(self, etype, event):
        if not self.remote:
            return event
        if etype not in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp, Quartz.kCGEventFlagsChanged):
            return self._mac_system_key(event)
        kc = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        flags = Quartz.CGEventGetFlags(event)
        desc = describe_key(kc)
        if etype == Quartz.kCGEventFlagsChanged:
            if kc == _MAC_CAPS_KC:  # one event per toggle, never a release: send both
                self.on_key(desc, True)
                self.on_key(desc, False)
                return None
            if kc not in _MAC_MODS:
                return None
            dev, gen = _MAC_MODS[kc] & 0xFFFF, _MAC_MODS[kc] & ~0xFFFF
            # left/right device bits when the keyboard reports them, otherwise the generic mask
            pressed = bool(flags & dev) if dev and flags & 0x217F else bool(flags & gen)
        else:
            pressed = etype == Quartz.kCGEventKeyDown
            if pressed and not flags & (_CG_CMD | _CG_CTRL):
                mods = ((_UC_SHIFT if flags & _CG_SHIFT else 0) | (_UC_CAPS if flags & _CG_CAPS else 0)
                        | (_UC_OPT if flags & _CG_OPT else 0))
                text = _MAC_TEXT.get((kc, mods))
                if text:
                    desc["text"], desc["dead"] = text
        self.on_key(desc, pressed)
        return None

    def _mac_system_key(self, event):
        """Media keys arrive as NSSystemDefined events; forward them, keep brightness etc. local."""
        try:
            ns = AppKit.NSEvent.eventWithCGEvent_(event)
            if ns is None or ns.subtype() != 8:
                return event
            data = ns.data1()
            name = _NX_MEDIA.get((data & 0xFFFF0000) >> 16)
            if name is None:
                return event
            if not data & 0x1:  # ignore auto-repeat
                self.on_key({"vk": None, "name": name, "char": None, "os": OS}, ((data & 0xFF00) >> 8) == 0x0A)
            return None
        except Exception:
            return event


# --------------------------------------------------------------------------- #
#  Injection
# --------------------------------------------------------------------------- #
_BUTTONS = {"left": Button.left, "right": Button.right, "middle": Button.middle}
for _n in ("x1", "x2"):
    if hasattr(Button, _n):
        _BUTTONS[_n] = getattr(Button, _n)


_MAC_KC_BY_NAME = {}
if OS == "mac":
    for _n, _k in Key.__members__.items():
        if not getattr(_k.value, "_is_media", False) and _k.value.vk is not None:
            _MAC_KC_BY_NAME[_n] = _k.value.vk
# real keyboards flag these keys as keypad / fn keys; some apps (and shortcuts) look at it
_MAC_ARROWS = {123, 124, 125, 126}
_MAC_FN_KEYS = {114, 115, 116, 117, 119, 121} | {_v for _n, _v in _MAC_KC_BY_NAME.items() if _n[0] == "f" and _n[1:].isdigit()}


class Injector:
    def __init__(self):
        self.mouse = mouse.Controller()
        self.kb = keyboard.Controller()
        self.pressed_keys = set()
        self.pressed_buttons = set()
        self._typed = set()       # keys of the other machine that were retyped as text
        self._scroll_acc = [0.0, 0.0]
        self._last_click = (0.0, None, 0, (0, 0))  # time, button, count, position
        self._mac_flags = 0       # modifiers we hold down on macOS
        self._mac_caps = False
        self._lock = threading.Lock()

    def move(self, x, y):
        if OS == "mac":
            btn = next(iter(self.pressed_buttons), None)
            etype, cgb = {
                None: (Quartz.kCGEventMouseMoved, Quartz.kCGMouseButtonLeft),
                "left": (Quartz.kCGEventLeftMouseDragged, Quartz.kCGMouseButtonLeft),
                "right": (Quartz.kCGEventRightMouseDragged, Quartz.kCGMouseButtonRight),
            }.get(btn, (Quartz.kCGEventOtherMouseDragged, Quartz.kCGMouseButtonCenter))
            ev = Quartz.CGEventCreateMouseEvent(None, etype, (x, y), cgb)
            Quartz.CGEventSetFlags(ev, self._mac_flags_now())
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        elif OS == "windows":
            user32.SetCursorPos(int(x), int(y))
        else:
            self.mouse.position = (x, y)

    def button(self, name, pressed):
        (self.pressed_buttons.add if pressed else self.pressed_buttons.discard)(name)
        if OS == "mac":
            self._mac_button(name, pressed)
            return
        b = _BUTTONS.get(name)
        if b is None:
            return
        (self.mouse.press if pressed else self.mouse.release)(b)

    def _mac_button(self, name, pressed):
        """Synthetic clicks carry their own click count: macOS does not detect double-clicks for us."""
        now = time.monotonic()
        pos = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
        t, last, count, lpos = self._last_click
        if pressed:
            near = abs(pos.x - lpos[0]) <= 4 and abs(pos.y - lpos[1]) <= 4
            same = last == name and near and now - t <= AppKit.NSEvent.doubleClickInterval()
            count = count + 1 if same else 1
            self._last_click = (now, name, count, (pos.x, pos.y))
        types = {"left": (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp, Quartz.kCGMouseButtonLeft),
                 "right": (Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp, Quartz.kCGMouseButtonRight)}
        down, up, cgb = types.get(name, (Quartz.kCGEventOtherMouseDown, Quartz.kCGEventOtherMouseUp,
                                         {"middle": 2, "x1": 3, "x2": 4}.get(name, 2)))
        ev = Quartz.CGEventCreateMouseEvent(None, down if pressed else up, pos, cgb)
        Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventButtonNumber, cgb)
        Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, max(1, count))
        Quartz.CGEventSetFlags(ev, self._mac_flags_now())  # Cmd-click, Shift-click, Option-click
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    def scroll(self, dx, dy):
        if OS == "windows":
            if dy:
                user32.mouse_event(0x0800, 0, 0, ctypes.c_uint32(int(round(dy * 120))).value, 0)
            if dx:
                user32.mouse_event(0x01000, 0, 0, ctypes.c_uint32(int(round(dx * 120))).value, 0)
            return
        acc = self._scroll_acc
        acc[0] += dx
        acc[1] += dy
        ix, iy = int(acc[0]), int(acc[1])
        acc[0] -= ix
        acc[1] -= iy
        if not (ix or iy):
            return
        if OS == "mac":
            ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 2, iy, -ix)
            Quartz.CGEventSetFlags(ev, self._mac_flags_now())
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
        else:
            self.mouse.scroll(ix, iy)

    # -- keyboard ------------------------------------------------------------
    def _resolve(self, desc):
        if desc.get("os") == OS and desc.get("vk") is not None:
            return KeyCode.from_vk(desc["vk"])
        name = desc.get("name")
        if name and hasattr(Key, name):
            return getattr(Key, name)
        ch = desc.get("char")
        if ch:
            if OS == "mac" and ch in _MAC_CHAR_TO_KC:
                return KeyCode.from_vk(_MAC_CHAR_TO_KC[ch])
            return KeyCode.from_char(ch)
        return None

    def key(self, desc, pressed):
        with self._lock:
            tid = (desc.get("os"), desc.get("vk"))
            if desc.get("os") != OS and desc.get("text"):
                if pressed:
                    self._typed.add(tid)
                    self._type_text(desc["text"], desc.get("dead", False))
                return
            if not pressed and tid in self._typed:  # release of a key we retyped as text
                self._typed.discard(tid)
                return
            if OS == "mac" and not (desc.get("name") or "").startswith("media_"):
                self._mac_key(desc, pressed)
                return
            k = self._resolve(desc)
            if k is None:
                return
            try:
                if pressed:
                    self.kb.press(k)
                    self.pressed_keys.add(k)
                else:
                    self.kb.release(k)
                    self.pressed_keys.discard(k)
            except Exception:
                pass

    def _type_text(self, ch, dead):
        if OS == "mac":
            self._mac_type(ch, dead)
        elif OS == "windows":
            self._win_type(ch, dead)
        else:
            try:
                self.kb.type(ch)
            except Exception:
                pass

    # macOS: our own events, so every key carries the modifiers we hold (pynput would drop
    # them for keys resolved by keycode, breaking Cmd+C & co.)
    def _mac_flags_now(self):
        return self._mac_flags | (_CG_CAPS if self._mac_caps else 0)

    def _mac_post(self, kc, down, flags, etype=None, text=None):
        ev = Quartz.CGEventCreateKeyboardEvent(None, kc, down)
        if etype is not None:
            Quartz.CGEventSetType(ev, etype)
        if text:
            Quartz.CGEventKeyboardSetUnicodeString(ev, len(text), text)
        Quartz.CGEventSetFlags(ev, flags)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    def _mac_key(self, desc, pressed):
        if desc.get("os") == OS and desc.get("vk") is not None:
            kc = desc["vk"]
        else:
            kc = _MAC_KC_BY_NAME.get(desc.get("name"))
            ch = desc.get("char")
            if kc is None and ch:
                kc = _MAC_CHAR_TO_KC.get(ch)
                if kc is None and ch in _MAC_TYPE:
                    kc = _MAC_TYPE[ch][0]
        if kc is None:
            return
        if kc == _MAC_CAPS_KC:
            if pressed:
                self._mac_caps = not self._mac_caps
                self._mac_post(kc, True, self._mac_flags_now(), Quartz.kCGEventFlagsChanged)
            return
        if kc in _MAC_MODS:
            mask = _MAC_MODS[kc]
            if pressed:
                self._mac_flags |= mask
            else:
                self._mac_flags &= ~(mask & 0xFFFF)
                # drop the generic bit only once no key of that kind is held anymore
                for other, m in _MAC_MODS.items():
                    if m & ~0xFFFF == mask & ~0xFFFF and self._mac_flags & m & 0xFFFF:
                        break
                else:
                    self._mac_flags &= ~mask
            (self.pressed_keys.add if pressed else self.pressed_keys.discard)(("mac", kc))
            self._mac_post(kc, pressed, self._mac_flags_now(), Quartz.kCGEventFlagsChanged)
            return
        flags = self._mac_flags_now()
        if kc in _MAC_ARROWS:
            flags |= _CG_NUMPAD | _CG_FN
        elif kc in _MAC_FN_KEYS:
            flags |= _CG_FN
        (self.pressed_keys.add if pressed else self.pressed_keys.discard)(("mac", kc))
        self._mac_post(kc, pressed, flags)

    def _mac_type(self, ch, dead):
        entry = _MAC_TYPE.get(ch)
        if entry and entry[2] == dead:
            kc, flags, _ = entry
            self._mac_post(kc, True, flags)  # exact modifiers for this character, nothing else
            self._mac_post(kc, False, flags)
        else:  # not on this layout: send the character itself
            self._mac_post(0, True, 0, text=ch)
            self._mac_post(0, False, 0, text=ch)

    # Windows: retype the character with the local layout, adjusting Shift / AltGr around it
    def _win_type(self, ch, dead):
        r = user32.VkKeyScanExW(ch, _win_layout())
        vk, shift_state = r & 0xFF, (r >> 8) & 0xFF
        if r == -1 or vk == 0xFF or shift_state & ~0x07:
            try:  # not on this layout: Unicode input
                self.kb.press(KeyCode.from_char(ch))
                self.kb.release(KeyCode.from_char(ch))
            except Exception:
                pass
            return
        down = lambda v: bool(user32.GetAsyncKeyState(v) & 0x8000)
        need_shift, need_altgr = bool(shift_state & 1), (shift_state & 6) == 6
        released, pressed = [], []
        if not need_shift:
            released += [v for v in (0xA0, 0xA1) if down(v)]
        elif not down(0xA0) and not down(0xA1):
            pressed.append(0xA0)
        if need_altgr:
            pressed += [v for v in (0xA2, 0xA4) if not down(v)]  # Ctrl + Alt acts as AltGr
        elif shift_state & 6:  # Ctrl or Alt alone: not text, give up on the layout
            released, pressed = [], []
        try:
            for v in released:
                self.kb.release(KeyCode.from_vk(v))
            for v in pressed:
                self.kb.press(KeyCode.from_vk(v))
            self.kb.press(KeyCode.from_vk(vk))
            self.kb.release(KeyCode.from_vk(vk))
            for v in reversed(pressed):
                self.kb.release(KeyCode.from_vk(v))
            for v in released:
                self.kb.press(KeyCode.from_vk(v))
        except Exception:
            pass

    def release_all(self):
        """Never leave a stuck modifier or button behind when control moves away."""
        with self._lock:
            for k in list(self.pressed_keys):
                try:
                    if isinstance(k, tuple):
                        self._mac_post(k[1], False, 0, Quartz.kCGEventFlagsChanged if k[1] in _MAC_MODS else None)
                    else:
                        self.kb.release(k)
                except Exception:
                    pass
            self.pressed_keys.clear()
            self._typed.clear()
            self._mac_flags = 0
        for b in list(self.pressed_buttons):
            self.button(b, False)
