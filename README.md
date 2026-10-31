# MultiMouse

Une souris et un clavier pour piloter plusieurs PC et Mac sur le même réseau. Le pointeur passe d'un ordinateur à l'autre par les bords des écrans, selon la disposition que vous dessinez.

## Fonctionnalités

- Disposition visuelle des écrans par glisser-déposer, avec aimantation des bords et prise en charge du multi-écran
- Windows ↔ Windows, Windows ↔ macOS, macOS ↔ macOS
- Détection automatique sur le réseau local
- Communications chiffrées (AES-256-GCM) avec un code d'appairage
- Presse-papiers partagé (texte)
- Inversion automatique Ctrl ↔ ⌘ entre PC et Mac
- Compatible AZERTY / QWERTY (les touches sont transmises par caractère)
- `Ctrl` + `Alt` + `Échap` : revenir à l'ordinateur contrôleur

## Utilisation

1. Installez MultiMouse sur chaque ordinateur.
2. Sur l'ordinateur qui a la souris, choisissez **Contrôleur**.
3. Sur les autres, choisissez **Contrôlé** et saisissez le code d'appairage (onglet Appareils).
4. Dans **Écrans**, placez les ordinateurs comme sur votre bureau.

Ports utilisés : TCP 24800 (contrôle) et UDP 24801 (détection).

**macOS** : autorisez MultiMouse dans Réglages Système › Confidentialité et sécurité › **Accessibilité** et **Surveillance de l'entrée**.

## Lancer depuis les sources

Python 3.10+ requis.

```bash
python -m pip install -r requirements.txt
python -m multimouse
```

## Compiler

```bash
python -m pip install -r requirements.txt pyinstaller pillow
python build.py               # MultiMouse.exe (Windows) ou MultiMouse.app (macOS) dans dist/
python build.py --installer   # + installateur : MultiMouse-Setup-x.y.z.exe (Windows, Inno Setup 6 requis)
                              #                  ou MultiMouse-x.y.z.dmg (macOS)
python build.py --installer --out <dossier>   # résultats ailleurs que dans dist/
```

L'application macOS doit être compilée sur un Mac (Python 3.10+, dans un venv : `python3 -m venv .venv && source .venv/bin/activate`).

**macOS** : l'app n'est pas signée par un compte développeur Apple. Au premier lancement, faites clic droit › **Ouvrir**. Une fois par Mac, lancez `sh tools/make_mac_cert.sh` avant de compiler : il crée le certificat « MultiMouse Code Signing » dans le trousseau, et `build.py` signe l'app avec. macOS reconnaît alors chaque nouvelle version comme la même app, et les autorisations **Accessibilité** et **Surveillance de l'entrée** sont conservées (sans ce certificat, il faut les refaire après chaque recompilation).

## Structure

```
multimouse/
  app.py              fenêtre (pywebview) et pont JavaScript ↔ Python
  engine.py           logique contrôleur / contrôlé, disposition et passage d'un écran à l'autre
  platform_input.py   capture et injection souris / clavier (Windows, macOS)
  secure.py           canal TCP chiffré
  net.py              connexions, détection réseau
  config.py           réglages persistants
  ui/                 interface (HTML / CSS / JS)
  assets/             icônes
installer/            script Inno Setup (Windows), fond du .dmg (mac/)
tools/make_icon.py    génération des icônes
tools/make_dmg_background.py  fond de la fenêtre du .dmg
tools/make_mac_cert.sh        certificat de signature macOS (une fois par Mac)
build.py              compilation
```
