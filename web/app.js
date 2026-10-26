import { createAvatar } from "./avatar.js";

const $ = (s) => document.querySelector(s);
const log = $("#log");
const input = $("#input");
const sendBtn = $("#send-btn");

const STATES = {
  idle: ["ΗΡΕΜΙΑ", "พร้อมรับคำสั่ง"],
  thinking: ["ΥΠΟΛΟΓΙΣΜΟΣ", "กำลังประมวลผล"],
  speaking: ["ΛΟΓΟΣ", "กำลังตอบ"],
};

let ws = null;
let busy = false;
let current = null; // the Ciel entry currently streaming
let pending = ""; // streamed text not yet painted
let flushQueued = false;
let retry = 0;
let connectedBefore = false;
let userName = "มาสเตอร์";
let running = null; // {version, commit} the page was loaded with
const avatar = await createAvatar($("#stage"));

// ── status ────────────────────────────────────────────

function setStatus(kind, text) {
  $("#status-dot").className = `dot ${kind}`;
  $("#status-text").textContent = text;
}

function setBusy(v) {
  busy = v;
  sendBtn.disabled = v;
  setStatus(v ? "busy" : "online", v ? "ΥΠΟΛΟΓΙΣΜΟΣ" : "ΣΥΝΔΕΔΕΜΕΝΟ");
}

function setAvatar(state) {
  avatar.setState(state);
  document.querySelector(".app").dataset.state = state;
  const [greek, thai] = STATES[state];
  $("#state-greek").textContent = greek;
  $("#state-thai").textContent = thai;
}

function showVersion(v) {
  $("#sl-version").textContent = `v${v.version}${v.commit ? ` · ${v.commit}` : ""}`;
}

// ── log ───────────────────────────────────────────────

const clock = () => new Date().toLocaleTimeString("en-GB", { hour12: false });

function addEntry(role, text = "") {
  const entry = document.createElement("div");
  entry.className = `entry ${role}`;
  if (role === "ciel" || role === "user") {
    const meta = document.createElement("div");
    meta.className = "meta";
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "ciel" ? "CIEL >" : `${userName} $`;
    const time = document.createElement("span");
    time.textContent = `[${clock()}] `;
    meta.append(time, who);
    entry.append(meta);
  }
  const body = document.createElement("div");
  body.className = "text";
  body.textContent = text;
  entry.append(body);
  entry.body = body;
  log.append(entry);
  scrollDown();
  return entry;
}

function scrollDown() {
  log.scrollTop = log.scrollHeight;
}

// ── connection ────────────────────────────────────────

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    retry = 0;
    setBusy(false);
  };

  ws.onmessage = (e) => handle(JSON.parse(e.data));

  ws.onclose = (e) => {
    if (e.code === 4401) return showLogin();
    setStatus("offline", "ΑΠΟΣΥΝΔΕΣΗ");
    setAvatar("idle");
    if (current) finish();
    busy = false;
    setTimeout(connect, Math.min(1000 * 2 ** retry++, 15000));
  };
}

function handle(msg) {
  switch (msg.type) {
    case "hello":
      $("#brand-name").textContent = msg.name.toUpperCase();
      document.title = msg.name;
      $("#sl-model").textContent = msg.model ?? "—";
      userName = msg.user_name || userName;
      $("#ps1").textContent = userName;
      if (checkVersion(msg)) return;
      if (connectedBefore && log.children.length) {
        addEntry("note", "เชื่อมต่อใหม่แล้ว — บทสนทนาก่อนหน้าจะไม่ถูกจำ");
      } else if (msg.greeting) {
        addEntry("ciel", msg.greeting);
      }
      connectedBefore = true;
      break;

    case "start":
      current = addEntry("ciel");
      current.classList.add("streaming");
      setAvatar("thinking");
      break;

    case "delta":
      if (!current) current = addEntry("ciel");
      if (!pending && !current.body.textContent) setAvatar("speaking");
      pending += msg.text;
      if (!flushQueued) {
        flushQueued = true;
        requestAnimationFrame(flush);
      }
      break;

    case "end":
      flush();
      if (current) current.body.textContent = msg.text;
      finish();
      break;

    case "error":
      if (current && !current.body.textContent) current.remove();
      finish();
      addEntry("error", msg.message);
      break;
  }
}

// Tokens arrive many times per frame; paint them at most once per frame
function flush() {
  flushQueued = false;
  if (!pending || !current) return;
  if (!current.stream) current.body.append((current.stream = document.createTextNode("")));
  current.stream.appendData(pending);
  pending = "";
  scrollDown();
}

function finish() {
  pending = "";
  current?.classList.remove("streaming");
  current = null;
  setAvatar("idle");
  setBusy(false);
}

// ── updates: reload when the server is running a newer build ──

function checkVersion(v) {
  if (!running) {
    running = { version: v.version, commit: v.commit };
    showVersion(running);
    return false;
  }
  if (v.version === running.version && v.commit === running.commit) return false;
  if (busy) return false; // try again after this reply
  addEntry("note", `ตรวจพบเวอร์ชันใหม่ v${v.version} · ${v.commit} — กำลังโหลดใหม่…`);
  setTimeout(() => location.reload(), 1500);
  return true;
}

async function pollVersion() {
  try {
    const v = await fetch("/api/health", { cache: "no-store" }).then((r) => r.json());
    checkVersion(v);
  } catch {
    /* server restarting — the socket will reconnect */
  }
}

// ── input ─────────────────────────────────────────────

function send() {
  const text = input.value.trim();
  if (!text || busy || ws?.readyState !== WebSocket.OPEN) return;
  addEntry("user", text);
  ws.send(JSON.stringify({ type: "chat", text }));
  input.value = "";
  autosize();
  setBusy(true);
}

function autosize() {
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight + 1}px`; // +1 for the bottom border
  input.style.overflowY = input.scrollHeight > 160 ? "auto" : "hidden";
}

$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  send();
});

input.addEventListener("keydown", (e) => {
  // Enter sends, Shift+Enter = new line. Ignore Enter while a Thai/IME composition is active.
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
});
input.addEventListener("input", autosize);

$("#reset-btn").addEventListener("click", () => {
  if (busy || ws?.readyState !== WebSocket.OPEN) return;
  log.replaceChildren();
  connectedBefore = false;
  ws.send(JSON.stringify({ type: "reset" }));
});

// ── login ─────────────────────────────────────────────

function showLogin() {
  setStatus("offline", "ΤΑΥΤΟΤΗΤΑ");
  $("#login").hidden = false;
  $("#password").focus();
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: $("#password").value }),
  });
  if (res.ok) {
    $("#login").hidden = true;
    $("#login-error").textContent = "";
    connect();
  } else {
    $("#login-error").textContent = "รหัสผ่านไม่ถูกต้องค่ะ";
  }
});

// ── boot ──────────────────────────────────────────────

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

const tick = () => ($("#sl-clock").textContent = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }));
tick();
setInterval(tick, 15000);
setInterval(pollVersion, 30000);
document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && pollVersion());

try {
  const me = await fetch("/api/me").then((r) => r.json());
  if (me.authed) connect();
  else showLogin();
} catch {
  setStatus("offline", "ΑΠΟΣΥΝΔΕΣΗ");
}
