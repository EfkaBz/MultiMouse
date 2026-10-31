"""Render the README screenshots with headless Chrome or Edge.

    python tools/screenshots.py     # English interface -> docs/captures/en (README.md)
                                    # French interface  -> docs/captures/fr (README.fr.md)
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
CAPTURES = os.path.join(ROOT, "docs", "captures")

PAGES = {  # file prefix -> query string for tools/shot.html
    "screens": "view=screens",
    "devices": "view=devices",
    "settings": "view=settings",
    "client": "role=client&os=mac&view=screens",
}
SHOTS = [(os.path.join(lang, f"{page}-{theme}.png"), f"{query}&theme={theme}&lang={lang}", theme == "dark")
         for lang in ("en", "fr") for page, query in PAGES.items() for theme in ("light", "dark")]


def browser():
    candidates = [shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("msedge"),
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    return next(c for c in candidates if c and os.path.isfile(c))


def main():
    for lang in ("en", "fr"):
        os.makedirs(os.path.join(CAPTURES, lang), exist_ok=True)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    exe = browser()
    for name, query, dark in SHOTS:
        path = os.path.join(CAPTURES, name)
        profile = tempfile.mkdtemp(prefix="mm-shot-")  # a fresh profile: no hand-off to a running browser
        args = [exe, "--headless=new", f"--user-data-dir={profile}", "--no-first-run", "--disable-gpu",
                "--hide-scrollbars", "--force-device-scale-factor=2",
                "--window-size=1300,860", "--virtual-time-budget=8000", f"--screenshot={path}",
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
