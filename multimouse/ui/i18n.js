"use strict";
/* Interface texts. Static HTML uses data-i18n (text), data-i18n-html, data-i18n-ph (placeholder)
   and data-i18n-title; app.js calls t(key, vars). Vars are inserted as {name}. */

const STRINGS = {
  fr: {
    "nav.screens": "Écrans", "nav.devices": "Appareils", "nav.settings": "Réglages",
    "role.server": "Contrôleur", "role.client": "Contrôlé",
    "status.starting": "Démarrage…",

    "title.screens.server": "Disposez vos ordinateurs comme ils le sont sur votre bureau.",
    "title.screens.client": "Cet ordinateur est piloté par la souris d'un autre.",
    "title.devices.server": "Associez les ordinateurs à contrôler.",
    "title.devices.client": "Associez cet ordinateur au contrôleur.",
    "title.settings": "Ajustez le comportement de MultiMouse.",

    "empty.title": "Ajoutez un autre ordinateur",
    "empty.text": "Installez MultiMouse sur votre autre PC ou Mac, choisissez <b>Contrôlé</b>,<br>puis saisissez le code d'appairage :",
    "canvas.hint": "Glissez les écrans pour reproduire leur disposition réelle. Le pointeur passe d'un ordinateur à l'autre par les bords qui se touchent.",
    "client.found": "Contrôleurs trouvés sur le réseau",

    "pair.code": "Code d'appairage",
    "pair.code.help": "Saisissez ce code sur chaque ordinateur à contrôler. Toutes les communications sont chiffrées avec ce code.",
    "pair.copy": "Copier", "pair.new": "Nouveau code",
    "pair.address": "Adresse de cet ordinateur",
    "pair.client.group": "Connexion au contrôleur",
    "pair.client.code.sub": "Affiché sur l'ordinateur contrôleur",
    "pair.client.host": "Adresse du contrôleur",
    "pair.client.host.sub": "Laisser vide pour la détection automatique",
    "pair.client.host.ph": "Automatique",
    "devices.group": "Ordinateurs",

    "set.general": "Général", "set.name": "Nom de cet ordinateur",
    "set.language": "Langue", "set.language.auto": "Auto",
    "set.control": "Contrôle", "set.speed": "Vitesse du pointeur distant",
    "set.swap": "Inverser Ctrl et ⌘ entre Mac et PC", "set.swap.sub": "Vos raccourcis restent naturels sur chaque système",
    "set.sharing": "Partage", "set.clip": "Presse-papiers partagé", "set.clip.sub": "Copiez du texte sur un ordinateur, collez-le sur l'autre",
    "set.network": "Réseau", "set.port": "Port", "set.port.sub": "Identique sur tous les ordinateurs",
    "set.shortcut": "Raccourci", "set.home": "Revenir à l'ordinateur contrôleur", "key.esc": "Échap",
    "set.perms.group": "Autorisations macOS", "set.perms": "Accessibilité et Surveillance de l'entrée",
    "set.perms.sub": "Réglages Système › Confidentialité et sécurité : autorisez MultiMouse dans les deux rubriques.",
    "set.perms.open": "Ouvrir les réglages",
    "perms.accessibility": "Accessibilité", "perms.input": "Surveillance de l'entrée", "perms.and": " et ",
    "perms.missing": "À autoriser : {list} (Réglages Système › Confidentialité et sécurité).",
    "perms.ok": "Autorisées.",

    "st.neterror": "Erreur réseau", "st.driving": "Pilote {name}", "st.ready": "Prêt", "st.waiting": "En attente",
    "st.connected.one": "1 ordinateur connecté", "st.connected.many": "{n} ordinateurs connectés",
    "st.none": "Aucun ordinateur connecté",
    "st.piloted": "Piloté", "st.connected": "Connecté", "st.connecting": "Connexion…", "st.refused": "Connexion refusée",
    "st.lost": "Connexion perdue", "st.searching": "Recherche…",
    "st.checkcode": "Vérifiez le code", "st.noserver": "Contrôleur introuvable",
    "err.port": "Port {port} indisponible",

    "badge.offline": "Hors ligne", "badge.unlinked": "Non relié",
    "badge.unlinked.tip": "Collez cet écran contre un autre pour que le pointeur puisse y passer",
    "badge.pointer": "Pointeur", "badge.me": "Cet ordinateur",
    "forget": "Oublier", "forgotten": "{name} oublié",
    "toast.overlap": "Les écrans ne peuvent pas se chevaucher",

    "client.searching": "Recherche du contrôleur…",
    "client.searching.sub": "Le contrôleur et cet ordinateur doivent être sur le même réseau.",
    "client.connecting": "Connexion en cours…", "client.connecting.sub": "Connexion à {addr}",
    "client.piloted": "Piloté par {name}", "client.piloted.sub": "La souris et le clavier du contrôleur agissent ici.",
    "client.connected": "Connecté à {name}",
    "client.connected.sub": "Amenez le pointeur au bord de l'écran du contrôleur pour venir ici.",
    "client.refused.sub": "Vérifiez que le code d'appairage est identique sur les deux ordinateurs (onglet Appareils).",
    "client.lost.sub": "Nouvelle tentative…",
    "client.connect": "Se connecter", "client.connect.toast": "Connexion à {addr}",
    "client.none": "Aucun contrôleur détecté pour l'instant.",

    "pill.connected": "Connecté", "pill.pointer": "Pointeur ici",
    "devices.none": "Aucun ordinateur associé. Saisissez le code ci-dessus sur un autre ordinateur.",
    "toast.copied": "Code copié", "toast.newcode": "Nouveau code généré — à saisir sur les autres ordinateurs",
    "toast.invalid": "Valeur invalide", "toast.name": "Nom enregistré", "toast.port": "Port modifié",
    "toast.code": "Code enregistré",
  },

  en: {
    "nav.screens": "Screens", "nav.devices": "Devices", "nav.settings": "Settings",
    "role.server": "Controller", "role.client": "Controlled",
    "status.starting": "Starting…",

    "title.screens.server": "Arrange your computers the way they sit on your desk.",
    "title.screens.client": "This computer is driven by another computer's mouse.",
    "title.devices.server": "Pair the computers you want to control.",
    "title.devices.client": "Pair this computer with the controller.",
    "title.settings": "Adjust how MultiMouse behaves.",

    "empty.title": "Add another computer",
    "empty.text": "Install MultiMouse on your other PC or Mac, choose <b>Controlled</b>,<br>then enter the pairing code:",
    "canvas.hint": "Drag the screens to match your real setup. The pointer moves from one computer to another across the edges that touch.",
    "client.found": "Controllers found on the network",

    "pair.code": "Pairing code",
    "pair.code.help": "Enter this code on every computer you want to control. All traffic is encrypted with this code.",
    "pair.copy": "Copy", "pair.new": "New code",
    "pair.address": "This computer's address",
    "pair.client.group": "Connection to the controller",
    "pair.client.code.sub": "Shown on the controller",
    "pair.client.host": "Controller address",
    "pair.client.host.sub": "Leave empty to find it automatically",
    "pair.client.host.ph": "Automatic",
    "devices.group": "Computers",

    "set.general": "General", "set.name": "Name of this computer",
    "set.language": "Language", "set.language.auto": "Auto",
    "set.control": "Control", "set.speed": "Remote pointer speed",
    "set.swap": "Swap Ctrl and ⌘ between Mac and PC", "set.swap.sub": "Your shortcuts stay natural on each system",
    "set.sharing": "Sharing", "set.clip": "Shared clipboard", "set.clip.sub": "Copy text on one computer, paste it on another",
    "set.network": "Network", "set.port": "Port", "set.port.sub": "Same on every computer",
    "set.shortcut": "Shortcut", "set.home": "Back to the controller", "key.esc": "Esc",
    "set.perms.group": "macOS permissions", "set.perms": "Accessibility and Input Monitoring",
    "set.perms.sub": "System Settings › Privacy & Security: allow MultiMouse in both sections.",
    "set.perms.open": "Open Settings",
    "perms.accessibility": "Accessibility", "perms.input": "Input Monitoring", "perms.and": " and ",
    "perms.missing": "Still to allow: {list} (System Settings › Privacy & Security).",
    "perms.ok": "Allowed.",

    "st.neterror": "Network error", "st.driving": "Driving {name}", "st.ready": "Ready", "st.waiting": "Waiting",
    "st.connected.one": "1 computer connected", "st.connected.many": "{n} computers connected",
    "st.none": "No computer connected",
    "st.piloted": "Controlled", "st.connected": "Connected", "st.connecting": "Connecting…", "st.refused": "Connection refused",
    "st.lost": "Connection lost", "st.searching": "Searching…",
    "st.checkcode": "Check the code", "st.noserver": "Controller not found",
    "err.port": "Port {port} unavailable",

    "badge.offline": "Offline", "badge.unlinked": "Not linked",
    "badge.unlinked.tip": "Move this screen against another one so the pointer can cross over",
    "badge.pointer": "Pointer", "badge.me": "This computer",
    "forget": "Forget", "forgotten": "{name} forgotten",
    "toast.overlap": "Screens can't overlap",

    "client.searching": "Looking for the controller…",
    "client.searching.sub": "The controller and this computer must be on the same network.",
    "client.connecting": "Connecting…", "client.connecting.sub": "Connecting to {addr}",
    "client.piloted": "Controlled by {name}", "client.piloted.sub": "The controller's mouse and keyboard are working here.",
    "client.connected": "Connected to {name}",
    "client.connected.sub": "Move the pointer to the edge of the controller's screen to come here.",
    "client.refused.sub": "Make sure the pairing code is the same on both computers (Devices tab).",
    "client.lost.sub": "Retrying…",
    "client.connect": "Connect", "client.connect.toast": "Connecting to {addr}",
    "client.none": "No controller found yet.",

    "pill.connected": "Connected", "pill.pointer": "Pointer here",
    "devices.none": "No paired computer. Enter the code above on another computer.",
    "toast.copied": "Code copied", "toast.newcode": "New code created — enter it on your other computers",
    "toast.invalid": "Invalid value", "toast.name": "Name saved", "toast.port": "Port changed",
    "toast.code": "Code saved",
  },
};

let LANG = /^fr\b/i.test(navigator.language || "") ? "fr" : "en";

function t(key, vars) {
  let s = (STRINGS[LANG] && STRINGS[LANG][key]) ?? STRINGS.fr[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  return s;
}

function applyStatic() {
  document.documentElement.lang = LANG;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-html]")) el.innerHTML = t(el.dataset.i18nHtml);
  for (const el of document.querySelectorAll("[data-i18n-ph]")) el.placeholder = t(el.dataset.i18nPh);
  for (const el of document.querySelectorAll("[data-i18n-title]")) el.title = t(el.dataset.i18nTitle);
}

/* Switch language; returns true when it changed (the caller re-renders). */
function setLang(lang) {
  lang = lang === "fr" ? "fr" : "en";
  if (lang === LANG && document.documentElement.lang === lang) return false;
  LANG = lang;
  applyStatic();
  return true;
}
