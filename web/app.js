import { createAvatar } from "./avatar.js";

const $ = (s) => document.querySelector(s);
const log = $("#log");
const input = $("#input");
const sendBtn = $("#send-btn");

let ws = null;
let busy = false;
let bubble = null; // the Ciel message currently streaming
let retry = 0;
let connectedBefore = false;
const avatar = await createAvatar($("#stage"));

// ── status ────────────────────────────────────────────

function setStatus(kind, text) {
  $("#status-dot").className = `status-dot ${kind}`;
  $("#status-text").textContent = text;
}

function setBusy(v) {
  busy = v;
  sendBtn.disabled = v;
  setStatus(v ? "busy" : "online", v ? "กำลังประมวลผล…" : "ออนไลน์");
}

// ── messages ──────────────────────────────────────────

function addMessage(role, text = "") {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  log.append(el);
  scrollDown();
  return el;
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
    setStatus("offline", "ขาดการเชื่อมต่อ กำลังลองใหม่…");
    avatar.setState("idle");
    if (bubble) finishBubble();
    busy = false;
    setTimeout(connect, Math.min(1000 * 2 ** retry++, 15000));
  };
}

function handle(msg) {
  switch (msg.type) {
    case "hello":
      $("#brand-name").textContent = msg.name;
      document.title = msg.name;
      if (connectedBefore && log.children.length) {
        addMessage("note", "เชื่อมต่อใหม่แล้ว — บทสนทนาก่อนหน้าจะไม่ถูกจำ");
      } else if (msg.greeting) {
        addMessage("ciel", msg.greeting);
      }
      connectedBefore = true;
      break;

    case "start":
      bubble = addMessage("ciel typing");
      avatar.setState("thinking");
      break;

    case "delta":
      if (!bubble) bubble = addMessage("ciel");
      if (!bubble.textContent) avatar.setState("speaking");
      bubble.textContent += msg.text;
      scrollDown();
      break;

    case "end":
      if (bubble) bubble.textContent = msg.text;
      finishBubble();
      break;

    case "error":
      if (bubble && !bubble.textContent) bubble.remove();
      finishBubble();
      addMessage("error", msg.message);
      break;
  }
}

function finishBubble() {
  bubble?.classList.remove("typing");
  bubble = null;
  avatar.setState("idle");
  setBusy(false);
}

// ── input ─────────────────────────────────────────────

function send() {
  const text = input.value.trim();
  if (!text || busy || ws?.readyState !== WebSocket.OPEN) return;
  addMessage("user", text);
  ws.send(JSON.stringify({ type: "chat", text }));
  input.value = "";
  autosize();
  setBusy(true);
}

function autosize() {
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight + 2}px`;
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
  setStatus("offline", "ต้องเข้าสู่ระบบ");
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

try {
  const me = await fetch("/api/me").then((r) => r.json());
  if (me.authed) connect();
  else showLogin();
} catch {
  setStatus("offline", "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้");
}
