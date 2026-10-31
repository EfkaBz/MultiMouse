"""Render the README screenshots (docs/captures) with headless Chrome or Edge.

    python tools/screenshots.py
"""
import functools
import http.server
import os
import shutil
import subprocess
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "captures")

PAGES = {  # file prefix -> query string for tools/shot.html
    "screens": "view=screens",
    "devices": "view=devices",
    "settings": "view=settings",
    "client": "role=client&os=mac&view=screens",
}
SHOTS = [(f"{page}-{theme}.png", f"{query}&theme={theme}", theme == "dark")
         for page, query in PAGES.items() for theme in ("light", "dark")]


def browser():
    candidates = [shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("msedge"),
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    return next(c for c in candidates if c and os.path.isfile(c))


def main():
    os.makedirs(OUT, exist_ok=True)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    exe = browser()
    for name, query, dark in SHOTS:
        path = os.path.join(OUT, name)
        profile = tempfile.mkdtemp(prefix="mm-shot-")  # a fresh profile: no hand-off to a running browser
        args = [exe, "--headless=new", f"--user-data-dir={profile}", "--no-first-run", "--disable-gpu",
                "--hide-scrollbars", "--force-device-scale-factor=2",
                "--window-size=1300,860", "--virtual-time-budget=4000", f"--screenshot={path}",
                f"http://127.0.0.1:{port}/tools/shot.html?{query}"]
        if dark:
            args.insert(1, "--force-dark-mode")
        if os.path.exists(path):
            os.remove(path)
        for _ in range(3):  # headless Chrome sometimes exits before writing: retry
            subprocess.run(args, capture_output=True, timeout=90)
            for _ in range(50):
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    break
                time.sleep(0.2)
            if os.path.exists(path):
                break
        else:
            raise SystemExit(f"capture impossible : {name}")
        shutil.rmtree(profile, ignore_errors=True)
        print("wrote", os.path.relpath(path, ROOT))
    srv.shutdown()


if __name__ == "__main__":
    main()
