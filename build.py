"""Build MultiMouse.

    python -m pip install -r requirements.txt pyinstaller pillow
    python build.py                 # app only  -> dist/
    python build.py --installer     # + installer -> dist/ (Windows: needs Inno Setup 6; macOS: .dmg)
    python build.py --out <dir>     # put the results somewhere else

Windows: dist/MultiMouse.exe and dist/MultiMouse-Setup-<version>.exe
macOS:   dist/MultiMouse.app and dist/MultiMouse-<version>.dmg (build on a Mac)
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "multimouse")
ASSETS = os.path.join(PKG, "assets")


def version():
    with open(os.path.join(PKG, "__init__.py"), encoding="utf-8") as f:
        return re.search(r'__version__ = "([^"]+)"', f.read()).group(1)


def find_iscc():
    candidates = [shutil.which("iscc")] + [
        os.path.join(os.environ.get(v, ""), "Inno Setup 6", "ISCC.exe")
        for v in ("ProgramFiles(x86)", "ProgramFiles")
    ] + [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe")]
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def build_app(out, work):
    import PyInstaller.__main__

    if not os.path.isfile(os.path.join(ASSETS, "icon.ico")):
        subprocess.check_call([sys.executable, os.path.join(HERE, "tools", "make_icon.py")])
    sep = ";" if sys.platform == "win32" else ":"
    plat = "_win32" if sys.platform == "win32" else "_darwin"
    args = [
        os.path.join(PKG, "__main__.py"),
        "--name", "MultiMouse",
        "--windowed", "--noconfirm", "--clean",
        "--distpath", out, "--workpath", work, "--specpath", work,
        "--add-data", f"{os.path.join(PKG, 'ui')}{sep}multimouse/ui",
        "--add-data", f"{ASSETS}{sep}multimouse/assets",
        "--hidden-import", f"pynput.keyboard.{plat}",
        "--hidden-import", f"pynput.mouse.{plat}",
    ]
    if sys.platform == "darwin":
        args += ["--icon", os.path.join(ASSETS, "icon.png"), "--osx-bundle-identifier", "app.multimouse"]
    else:
        args += ["--onefile", "--icon", os.path.join(ASSETS, "icon.ico"),
                 "--version-file", write_version_file(work)]
    PyInstaller.__main__.run(args)
    if sys.platform == "darwin":
        shutil.rmtree(os.path.join(out, "MultiMouse"), ignore_errors=True)  # loose copy of the .app content
        finish_mac_bundle(os.path.join(out, "MultiMouse.app"))


def finish_mac_bundle(app):
    """Version, privacy strings, then re-sign: editing Info.plist breaks PyInstaller's signature."""
    import plistlib

    path = os.path.join(app, "Contents", "Info.plist")
    with open(path, "rb") as f:
        info = plistlib.load(f)
    info.update({
        "CFBundleDisplayName": "MultiMouse",
        "CFBundleShortVersionString": version(),
        "CFBundleVersion": version(),
        "LSMinimumSystemVersion": "11.0",
        "NSLocalNetworkUsageDescription": "MultiMouse se connecte aux autres ordinateurs de votre réseau local "
                                          "pour partager la souris, le clavier et le presse-papiers.",
    })
    with open(path, "wb") as f:
        plistlib.dump(info, f)
    subprocess.check_call(["codesign", "--force", "--deep", "--sign", mac_identity(), app])


MAC_IDENTITY = "MultiMouse Code Signing"  # created once by tools/make_mac_cert.sh


def mac_identity():
    """A fixed certificate keeps the privacy permissions across rebuilds; ad-hoc loses them every time."""
    found = subprocess.run(["security", "find-identity", "-p", "codesigning"],
                           capture_output=True, text=True).stdout
    if f'"{MAC_IDENTITY}"' in found:
        return MAC_IDENTITY
    print(f"Certificat « {MAC_IDENTITY} » absent : signature ad hoc. Lancez tools/make_mac_cert.sh "
          "pour que les autorisations macOS survivent aux recompilations.")
    return "-"


def write_version_file(work):
    v = version()
    nums = tuple((list(map(int, re.findall(r"\d+", v))) + [0, 0, 0, 0])[:4])
    path = os.path.join(work, "version_info.txt")
    os.makedirs(work, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[StringFileInfo([StringTable('040C04B0', [
    StringStruct('FileDescription', 'MultiMouse'),
    StringStruct('ProductName', 'MultiMouse'),
    StringStruct('FileVersion', '{v}'),
    StringStruct('ProductVersion', '{v}'),
    StringStruct('OriginalFilename', 'MultiMouse.exe')])]),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])])
""")
    return path


DMG_LAYOUT = """
tell application "Finder"
  tell disk "{vol}"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {{200, 120, 840, 548}}
    set opts to the icon view options of container window
    set arrangement of opts to not arranged
    set icon size of opts to 112
    set text size of opts to 13
    set background picture of opts to file ".background:background.tiff"
    set position of item "MultiMouse.app" of container window to {{160, 190}}
    set position of item "Applications" of container window to {{480, 190}}
    update without registering applications
    delay 1
    close
  end tell
end tell
"""


def build_dmg(out):
    """macOS installer: a disk image with the app, a link to Applications and instructions."""
    bg = os.path.join(HERE, "installer", "mac", "dmg-background.tiff")
    if not os.path.isfile(bg):
        subprocess.check_call([sys.executable, os.path.join(HERE, "tools", "make_dmg_background.py")])
    vol = f"MultiMouse {version()}"
    final = os.path.join(out, f"MultiMouse-{version()}.dmg")
    tmp = tempfile.mkdtemp(prefix="multimouse-dmg-")
    try:
        stage = os.path.join(tmp, "stage")
        os.makedirs(os.path.join(stage, ".background"))
        subprocess.check_call(["ditto", os.path.join(out, "MultiMouse.app"), os.path.join(stage, "MultiMouse.app")])
        os.symlink("/Applications", os.path.join(stage, "Applications"))
        shutil.copy(bg, os.path.join(stage, ".background", "background.tiff"))
        rw = os.path.join(tmp, "rw.dmg")
        subprocess.check_call(["hdiutil", "create", "-quiet", "-srcfolder", stage, "-volname", vol,
                               "-fs", "HFS+", "-format", "UDRW", "-size", "200m", rw])
        if os.path.isdir(f"/Volumes/{vol}"):  # an earlier image still mounted would take the name
            subprocess.run(["hdiutil", "detach", "-quiet", "-force", f"/Volumes/{vol}"])
        subprocess.check_call(["hdiutil", "attach", "-quiet", "-readwrite", "-noverify", "-noautoopen", rw])
        try:  # window layout is cosmetic: the image works without it (Finder automation may be refused)
            subprocess.run(["osascript", "-e", DMG_LAYOUT.format(vol=vol)], timeout=60, check=True)
        except (subprocess.SubprocessError, OSError) as e:
            print("Mise en page de la fenêtre du DMG ignorée :", e)
        subprocess.run(["sync"])
        subprocess.check_call(["hdiutil", "detach", "-quiet", f"/Volumes/{vol}"])
        if os.path.exists(final):
            os.remove(final)
        subprocess.check_call(["hdiutil", "convert", "-quiet", rw, "-format", "UDZO",
                               "-imagekey", "zlib-level=9", "-o", final])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_installer(out):
    iscc = find_iscc()
    if not iscc:
        sys.exit("Inno Setup 6 introuvable : https://jrsoftware.org/isdl.php (ou winget install JRSoftware.InnoSetup)")
    subprocess.check_call([iscc, f"/DAppVersion={version()}", f"/DDistDir={out}", f"/O{out}",
                           os.path.join(HERE, "installer", "MultiMouse.iss")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--installer", action="store_true", help="also build the installer (Windows setup or macOS .dmg)")
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    work = tempfile.mkdtemp(prefix="multimouse-build-")
    try:
        build_app(out, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if a.installer and sys.platform == "win32":
        build_installer(out)
    elif a.installer and sys.platform == "darwin":
        build_dmg(out)
    print("\nOK ->", out)
    for f in sorted(glob.glob(os.path.join(out, "MultiMouse*"))):
        print("  ", os.path.basename(f))


if __name__ == "__main__":
    main()
