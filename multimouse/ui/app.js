"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const call = (name, ...args) => (window.pywebview ? window.pywebview.api[name](...args) : Promise.resolve());

let S = null;               // last state from Python
let view = "screens";
let drag = null;            // active drag on the layout canvas
const tiles = new Map();    // node id -> element
let T = { scale: 0.1, ox: 0, oy: 0 }; // virtual -> canvas transform

const OS_NAME = { windows: "Windows", mac: "macOS", linux: "Linux" };
const WALLS = [
  ["#5ac8fa", "#5856d6", "#af52de"],
  ["#ffd60a", "#ff9f0a", "#ff375f"],
  ["#30d158", "#00c7be", "#0a84ff"],
  ["#ff6482", "#bf5af2", "#5e5ce6"],
  ["#64d2ff", "#30b0c7", "#34c759"],
  ["#ff9f0a", "#ff453a", "#bf5af2"],
];
const DISPLAY_ICON = '<svg class="os" viewBox="0 0 24 24"><path d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-6v2h3v1.5H7V19h3v-2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/></svg>';
const LAPTOP_ICON = '<svg viewBox="0 0 24 24"><path d="M5 5h14a1.5 1.5 0 0 1 1.5 1.5V15h-17V6.5A1.5 1.5 0 0 1 5 5Zm-3.5 11.5h21l-.6 1.3a1.5 1.5 0 0 1-1.4.9H3.5a1.5 1.5 0 0 1-1.4-.9l-.6-1.3Z"/></svg>';

function hash(s) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h; }
const wallIndex = new Map(); // id -> palette slot, kept distinct between the computers on screen
function assignWalls(ids) {
  const used = new Set();
  wallIndex.clear();
  for (const id of [...ids].sort()) {
    let i = hash(id) % WALLS.length;
    for (let k = 0; k < WALLS.length && used.has(i); k++) i = (i + 1) % WALLS.length;
    used.add(i);
    wallIndex.set(id, i);
  }
}
function wall(id) {
  const [a, b, c] = WALLS[wallIndex.get(id) ?? hash(id) % WALLS.length];
  return `linear-gradient(135deg, ${a} 0%, ${b} 55%, ${c} 100%)`;
}
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 1800);
}

/* ------------------------------------------------------------------ */
/*  Navigation & role                                                  */
/* ------------------------------------------------------------------ */
function setView(v) {
  view = v;
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
  $$(".view").forEach((s) => s.classList.toggle("active", s.id === "view-" + v));
  renderHeader();
  if (v === "screens") requestAnimationFrame(renderCanvas);
}
$$(".nav-item").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));

$$("#role-seg button").forEach((b) =>
  b.addEventListener("click", () => {
    const role = b.dataset.role;
    if (!S || S.role === role) return;
    $("#role-seg").dataset.value = role;
    S.role = role;
    document.body.dataset.role = role;
    tiles.forEach((el) => el.remove());
    tiles.clear();
    call("set_role", role);
    render();
  })
);

function renderHeader() {
  const role = S ? S.role : "server";
  $("#title").textContent = t("nav." + view);
  $("#subtitle").textContent = t(view === "settings" ? "title.settings" : `title.${view}.${role}`);
}

/* ------------------------------------------------------------------ */
/*  Status                                                             */
/* ------------------------------------------------------------------ */
function renderStatus() {
  const dot = $("#status-dot");
  let title, sub, cls;
  if (S.role === "server") {
    const n = S.connected || 0;
    const active = (S.nodes || []).find((x) => x.active);
    cls = S.error ? "err" : n ? "on" : "wait";
    title = S.error ? t("st.neterror") : n ? (active && !active.me ? t("st.driving", { name: active.name }) : t("st.ready")) : t("st.waiting");
    sub = S.error ? t("err." + S.error, { port: S.port }) : n ? t(n > 1 ? "st.connected.many" : "st.connected.one", { n }) : t("st.none");
    $("#brand-role").textContent = t("role.server");
  } else {
    const st = S.status;
    cls = st === "connected" ? "on" : st === "refused" ? "err" : "wait";
    title = { connected: t(S.active ? "st.piloted" : "st.connected"), connecting: t("st.connecting"), refused: t("st.refused"),
              connected_lost: t("st.lost"), searching: t("st.searching") }[st] || "…";
    sub = st === "connected" ? S.server_name : st === "refused" ? t("st.checkcode") : t("st.noserver");
    $("#brand-role").textContent = t("role.client");
  }
  dot.className = "dot " + cls;
  $("#status-title").textContent = title;
  $("#status-sub").textContent = sub;
}

/* ------------------------------------------------------------------ */
/*  Layout canvas (server)                                             */
/* ------------------------------------------------------------------ */
function fitTransform(nodes, W, H) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const n of nodes) { x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y); x1 = Math.max(x1, n.x + n.w); y1 = Math.max(y1, n.y + n.h); }
  const pad = 70, bottomRoom = nodes.length < 2 ? 150 : 0;
  const scale = Math.min((W - pad * 2) / (x1 - x0), (H - pad * 2 - bottomRoom) / (y1 - y0), 0.16);
  return { scale, ox: (W - (x1 - x0) * scale) / 2 - x0 * scale, oy: (H - bottomRoom - (y1 - y0) * scale) / 2 - y0 * scale };
}

const SNAP = 48; // must match engine.SNAP
function touching(a, b) {
  const overlapY = a.y < b.y + b.h && a.y + a.h > b.y;
  const overlapX = a.x < b.x + b.w && a.x + a.w > b.x;
  return (overlapY && (Math.abs(a.x + a.w - b.x) <= SNAP || Math.abs(b.x + b.w - a.x) <= SNAP)) ||
         (overlapX && (Math.abs(a.y + a.h - b.y) <= SNAP || Math.abs(b.y + b.h - a.y) <= SNAP));
}

function renderCanvas() {
  const canvas = $("#canvas");
  const isServer = S && S.role === "server";
  $("#client-panel").classList.toggle("show", !isServer);
  canvas.style.display = isServer ? "" : "none";
  $("#canvas-hint").style.visibility = isServer ? "" : "hidden";
  if (!isServer) { renderClientPanel(); $("#empty-server").classList.remove("show"); return; }

  const nodes = S.nodes || [];
  $("#empty-server").classList.toggle("show", nodes.length < 2);
  $("#empty-code").textContent = S.code;
  if (drag || !nodes.length || view !== "screens") return;

  const W = canvas.clientWidth, H = canvas.clientHeight;
  if (!W) return;
  T = fitTransform(nodes, W, H);
  assignWalls(nodes.map((n) => n.id));

  const seen = new Set();
  for (const n of nodes) {
    seen.add(n.id);
    let el = tiles.get(n.id);
    if (!el) {
      el = document.createElement("div");
      el.className = "screen";
      el.innerHTML = `<div class="wall"></div><div class="label"></div><div class="ring"></div>`;
      el.addEventListener("pointerdown", (e) => startDrag(e, el));
      canvas.appendChild(el);
      tiles.set(n.id, el);
      el.style.opacity = "0";
      requestAnimationFrame(() => (el.style.opacity = ""));
    }
    el._node = n;
    const w = n.w * T.scale, h = n.h * T.scale;
    Object.assign(el.style, { left: n.x * T.scale + T.ox + "px", top: n.y * T.scale + T.oy + "px", width: w + "px", height: h + "px" });
    el.classList.toggle("offline", !n.online);
    el.classList.toggle("active", !!n.active && S.connected > 0);
    el.classList.toggle("small", w < 120 || h < 80);
    el.querySelector(".wall").style.background = wall(n.id);
    const mons = (n.monitors || []).length > 1
      ? n.monitors.map((m) => `<div class="mon" style="left:${(m.x / n.w) * 100}%;top:${(m.y / n.h) * 100}%;width:${(m.w / n.w) * 100}%;height:${(m.h / n.h) * 100}%"></div>`).join("")
      : "";
    const linked = nodes.length < 2 || nodes.some((o) => o !== n && touching(n, o));
    const badge = !n.online ? `<span class="badge gray">${t("badge.offline")}</span>`
      : !linked ? `<span class="badge warn" title="${esc(t("badge.unlinked.tip"))}">${t("badge.unlinked")}</span>`
      : n.active && S.connected ? `<span class="badge">${t("badge.pointer")}</span>`
      : n.me ? `<span class="badge gray">${t("badge.me")}</span>` : "";
    const key = [n.name, n.w, n.h, n.os, badge, mons, n.online].join("|");
    if (el._key !== key) {
      el._key = key;
      el.querySelector(".wall").innerHTML = mons;
      el.querySelector(".label").innerHTML =
        `${DISPLAY_ICON}<div class="name">${esc(n.name)}</div><div class="res">${n.w} × ${n.h} · ${OS_NAME[n.os] || n.os}</div>`;
      el.querySelectorAll(".badge, .forget").forEach((x) => x.remove());
      if (badge) el.insertAdjacentHTML("beforeend", badge);
      if (!n.online && !n.me) {
        el.insertAdjacentHTML("beforeend", `<button class="forget" title="${esc(t("forget"))}">×</button>`);
        el.querySelector(".forget").addEventListener("pointerdown", (e) => { e.stopPropagation(); call("forget", n.id); toast(t("forgotten", { name: n.name })); });
      }
    }
  }
  for (const [id, el] of tiles) if (!seen.has(id)) { el.remove(); tiles.delete(id); }
}

function guide(cls, idx) {
  const canvas = $("#canvas");
  let g = canvas.querySelector(`.guide.${cls}[data-i="${idx}"]`);
  if (!g) { g = document.createElement("div"); g.className = "guide " + cls; g.dataset.i = idx; canvas.appendChild(g); }
  return g;
}
function hideGuides() { $$(".guide").forEach((g) => g.classList.remove("show")); }

function startDrag(e, el) {
  if (e.button !== 0) return;
  e.preventDefault();
  el.setPointerCapture(e.pointerId);
  const n = el._node;
  drag = { el, n, sx: e.clientX, sy: e.clientY, x0: n.x, y0: n.y, x: n.x, y: n.y, moved: false };
  el.classList.add("dragging");
  el.addEventListener("pointermove", onDrag);
  el.addEventListener("pointerup", endDrag, { once: true });
  el.addEventListener("pointercancel", endDrag, { once: true });
}

function onDrag(e) {
  const d = drag;
  if (!d) return;
  let x = d.x0 + (e.clientX - d.sx) / T.scale;
  let y = d.y0 + (e.clientY - d.sy) / T.scale;
  d.moved = d.moved || Math.abs(e.clientX - d.sx) + Math.abs(e.clientY - d.sy) > 3;
  const th = 16 / T.scale;
  const others = S.nodes.filter((o) => o.id !== d.n.id);
  // Touching an edge (that is what lets the pointer cross) always wins over a mere alignment,
  // and only counts against a screen that overlaps us on the other axis.
  const pick = (best, v, cur, o, touch) => {
    const dist = Math.abs(v - cur);
    if (dist >= th) return best;
    if (!best || (touch && !best.touch) || (touch === best.touch && dist < Math.abs(best.v - cur))) return { v, o, touch };
    return best;
  };
  let bx = null, by = null;
  for (const o of others) {
    const overlapY = y < o.y + o.h && y + d.n.h > o.y;
    const overlapX = x < o.x + o.w && x + d.n.w > o.x;
    for (const cx of [o.x - d.n.w, o.x + o.w]) bx = pick(bx, cx, x, o, overlapY);
    for (const cx of [o.x, o.x + o.w - d.n.w]) bx = pick(bx, cx, x, o, false);
    for (const cy of [o.y - d.n.h, o.y + o.h]) by = pick(by, cy, y, o, overlapX);
    for (const cy of [o.y, o.y + o.h - d.n.h]) by = pick(by, cy, y, o, false);
  }
  hideGuides();
  if (bx) {
    x = bx.v;
    const gx = (Math.abs(x - (bx.o.x + bx.o.w)) < 1 || Math.abs(x - bx.o.x) < 1) ? x : x + d.n.w;
    const g = guide("v", 0);
    Object.assign(g.style, { left: gx * T.scale + T.ox + "px", top: "0", bottom: "0" });
    g.classList.add("show");
  }
  if (by) {
    y = by.v;
    const gy = (Math.abs(y - (by.o.y + by.o.h)) < 1 || Math.abs(y - by.o.y) < 1) ? y : y + d.n.h;
    const g = guide("h", 0);
    Object.assign(g.style, { top: gy * T.scale + T.oy + "px", left: "0", right: "0" });
    g.classList.add("show");
  }
  d.x = Math.round(x);
  d.y = Math.round(y);
  d.el.style.left = d.x * T.scale + T.ox + "px";
  d.el.style.top = d.y * T.scale + T.oy + "px";
}

function overlaps(a, b) {
  return a.x < b.x + b.w - 1 && a.x + a.w > b.x + 1 && a.y < b.y + b.h - 1 && a.y + a.h > b.y + 1;
}

function endDrag() {
  const d = drag;
  if (!d) return;
  d.el.removeEventListener("pointermove", onDrag);
  d.el.classList.remove("dragging");
  hideGuides();
  drag = null;
  const moved = { ...d.n, x: d.x, y: d.y };
  const clash = S.nodes.some((o) => o.id !== d.n.id && overlaps(moved, o));
  if (!d.moved) { renderCanvas(); return; }
  if (clash) {
    toast(t("toast.overlap"));
  } else {
    d.n.x = d.x; d.n.y = d.y;
    call("set_layout", d.n.id, d.x, d.y);
  }
  renderCanvas();
}

window.addEventListener("resize", () => { if (view === "screens") renderCanvas(); });

/* ------------------------------------------------------------------ */
/*  Client panel                                                       */
/* ------------------------------------------------------------------ */
function renderClientPanel() {
  const st = S.status;
  const scr = $("#client-screen");
  scr.classList.toggle("active", !!S.active);
  scr.querySelector(".wall").style.background = wall(S.id || "x");
  const sp = $("#client-spinner");
  sp.className = "spinner" + (st === "connected" ? " done" : st === "refused" ? " fail" : "");
  const texts = {
    searching: [t("client.searching"), t("client.searching.sub")],
    connecting: [t("client.connecting"), t("client.connecting.sub", { addr: S.server_addr })],
    connected: S.active ? [t("client.piloted", { name: S.server_name }), t("client.piloted.sub")]
                        : [t("client.connected", { name: S.server_name }), t("client.connected.sub")],
    refused: [t("st.refused"), t("client.refused.sub")],
    connected_lost: [t("st.lost"), t("client.lost.sub")],
  };
  const [title, sub] = texts[st] || texts.searching;
  $("#client-title").textContent = title;
  $("#client-sub").textContent = sub;

  const list = $("#server-list");
  const servers = S.servers || [];
  $("#server-list-group").style.display = st === "connected" && !S.server_host ? "none" : "";
  const sig = JSON.stringify(servers) + S.server_host + S.server_addr + st + LANG;
  if (list._sig === sig) return;
  list._sig = sig;
  list.innerHTML = servers.length
    ? servers.map((sv) => {
        const current = st === "connected" && S.server_addr === sv.addr;
        return `<div class="row"><div class="lead"><div class="dev-icon" style="background:${wall(sv.addr)}">${LAPTOP_ICON}</div>
          <div class="row-text"><div class="row-title">${esc(sv.name)}</div><div class="row-sub">${esc(sv.addr)}</div></div></div>
          ${current ? `<span class="pill on">${t("pill.connected")}</span>` : `<button class="btn" data-addr="${esc(sv.addr)}">${t("client.connect")}</button>`}</div>`;
      }).join("")
    : `<div class="empty-row">${t("client.none")}</div>`;
  list.querySelectorAll("button[data-addr]").forEach((b) =>
    b.addEventListener("click", () => { call("connect_to", b.dataset.addr); toast(t("client.connect.toast", { addr: b.dataset.addr })); }));
}

/* ------------------------------------------------------------------ */
/*  Devices                                                            */
/* ------------------------------------------------------------------ */
function renderDevices() {
  const isServer = S.role === "server";
  $("#pair-server").style.display = isServer ? "" : "none";
  $("#pair-client").style.display = isServer ? "none" : "";
  $("#devices-group").style.display = isServer ? "" : "none";

  const boxes = $("#code-boxes");
  if (boxes._code !== S.code) {
    boxes._code = S.code;
    boxes.innerHTML = [...S.code].map((c, i) => `<span style="animation-delay:${i * 40}ms">${esc(c)}</span>`).join("");
  }
  $("#ips").innerHTML = (S.ips || []).map((ip) => `<div>${esc(ip)}</div>`).join("") + `<small>Port ${S.port}</small>`;
  setField("#in-code", S.code);
  setField("#in-host", S.server_host);

  if (!isServer) return;
  const list = $("#device-list");
  const others = (S.nodes || []).filter((n) => !n.me);
  const sig = JSON.stringify(others.map((n) => [n.id, n.name, n.online, n.active, n.addr])) + LANG;
  if (list._sig === sig) return;
  list._sig = sig;
  list.innerHTML = others.length
    ? others.map((n) => `<div class="row"><div class="lead"><div class="dev-icon" style="background:${n.online ? wall(n.id) : ""}">${LAPTOP_ICON}</div>
        <div class="row-text"><div class="row-title">${esc(n.name)}</div><div class="row-sub">${OS_NAME[n.os] || n.os} · ${n.w} × ${n.h}${n.addr ? " · " + esc(n.addr) : ""}</div></div></div>
        ${n.active ? `<span class="pill accent">${t("pill.pointer")}</span>` : n.online ? `<span class="pill on">${t("pill.connected")}</span>` : `<button class="btn ghost" data-forget="${n.id}">${t("forget")}</button>`}</div>`).join("")
    : `<div class="empty-row">${t("devices.none")}</div>`;
  list.querySelectorAll("[data-forget]").forEach((b) => b.addEventListener("click", () => call("forget", b.dataset.forget)));
}

$("#btn-copy-code").addEventListener("click", () => { call("copy_text", S.code); toast(t("toast.copied")); });
$("#btn-new-code").addEventListener("click", () => { call("regenerate_code"); toast(t("toast.newcode")); });

/* ------------------------------------------------------------------ */
/*  Settings                                                           */
/* ------------------------------------------------------------------ */
function setField(sel, value) {
  const el = $(sel);
  if (document.activeElement !== el) el.value = value ?? "";
}

function renderSettings() {
  setField("#in-name", S.name);
  setField("#in-port", S.port);
  $("#in-clip").checked = !!S.clipboard;
  $("#in-swap").checked = !!S.swap_ctrl_cmd;
  const sp = $("#in-speed");
  if (document.activeElement !== sp) sp.value = S.speed;
  updateSlider();
  $("#kbd-alt").textContent = S.os === "mac" ? "⌥ Option" : "Alt";
  $("#about").textContent = `MultiMouse ${S.version} · ${OS_NAME[S.os] || S.os}`;
  const p = S.permissions;
  if (p) {
    const missing = [!p.accessibility && t("perms.accessibility"), !p.input && t("perms.input")].filter(Boolean);
    $("#perm-sub").textContent = missing.length ? t("perms.missing", { list: missing.join(t("perms.and")) }) : t("perms.ok");
    $("#btn-perms").hidden = !missing.length;
  }
}
$("#btn-perms").addEventListener("click", () => call("open_permissions"));

function updateSlider() {
  const sp = $("#in-speed");
  sp.style.setProperty("--p", ((sp.value - sp.min) / (sp.max - sp.min)) * 100 + "%");
  $("#speed-val").textContent = Number(sp.value).toFixed(1) + "×";
}

function bindField(sel, key, ok) {
  const el = $(sel);
  const commit = async () => {
    if (S && String(S[key]) === el.value) return;
    const res = await call("set_setting", key, el.value);
    if (res === false) { toast(t("toast.invalid")); setField(sel, S[key]); } else if (ok) toast(t(ok));
  };
  el.addEventListener("change", commit);
  el.addEventListener("keydown", (e) => { if (e.key === "Enter") el.blur(); });
}
bindField("#in-name", "name", "toast.name");
bindField("#in-port", "port", "toast.port");
bindField("#in-code", "code", "toast.code");
bindField("#in-host", "server_host");
$("#in-clip").addEventListener("change", (e) => call("set_setting", "clipboard", e.target.checked));
$("#in-swap").addEventListener("change", (e) => call("set_setting", "swap_ctrl_cmd", e.target.checked));
$("#in-speed").addEventListener("input", updateSlider);
$("#in-speed").addEventListener("change", (e) => call("set_setting", "speed", parseFloat(e.target.value)));

/* ------------------------------------------------------------------ */
/*  Render                                                             */
/* ------------------------------------------------------------------ */
$$("#lang-seg button").forEach((b) =>
  b.addEventListener("click", () => {
    if (!S || S.language === b.dataset.lang) return;
    S.language = b.dataset.lang;
    $("#lang-seg").dataset.value = b.dataset.lang;
    call("set_setting", "language", b.dataset.lang);  // Python answers with the resolved S.lang
  })
);

function render() {
  if (!S) return;
  if (setLang(S.lang)) tiles.forEach((el) => (el._key = null));  // rebuild the translated badges
  $("#lang-seg").dataset.value = S.language || "auto";
  document.body.dataset.role = S.role;
  document.body.dataset.os = S.os;
  $("#role-seg").dataset.value = S.role;
  renderHeader();
  renderStatus();
  renderCanvas();
  renderDevices();
  renderSettings();
}

window.mm = {
  update(state) {
    S = state;
    render();
  },
};

window.addEventListener("pywebviewready", async () => {
  S = await call("get_state");
  render();
});
