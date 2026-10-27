import { createAvatar } from "./avatar.js";
import { VoicePlayer } from "./voice.js";

const $ = (s) => document.querySelector(s);
const app = $(".app");
const log = $("#log");
const input = $("#input");
const sendBtn = $("#send-btn");
const subtitle = $("#subtitle");

const STATES = {
  idle: ["ΗΡΕΜΙΑ", "พร้อมรับคำสั่ง"],
  thinking: ["ΥΠΟΛΟΓΙΣΜΟΣ", "กำลังประมวลผล"],
  speaking: ["ΛΟΓΟΣ", "กำลังตอบ"],
};

let ws = null;
let busy = false;
let current = null; // the Ciel entry currently streaming
let pending = []; // streamed text not yet painted, see flush()
let flushQueued = false;
let retry = 0;
let connectedBefore = false;
let userName = "มาสเตอร์";
let running = null; // {version, commit} the page was loaded with
let ttsAvailable = false;
let turnSpeaks = false; // is the current reply being voiced?
let subs = new Map(); // anime style: seq → translation of that Japanese line
let jpLines = new Map(); // seq → Japanese line
let noAudio = new Set(); // segments whose audio failed
let subSeq = -2; // which segment the subtitle is showing (-1 = a line with no voice)
let anime = false; // persona speaking style: Japanese voice + translated text

const prefs = loadPrefs();
const avatar = await createAvatar($("#stage"));
const voice = new VoicePlayer({
  onLevel: (level, low, high) => avatar.setLevel(level, low, high),
  onSegment: (seg) => {
    setAvatar("speaking");
    if (seg.emotion) avatar.setEmotion(seg.emotion);
    showSegmentSubtitle(seg.seq);
  },
  onIdle: () => {
    if (!busy) setAvatar("idle");
    avatar.setEmotion("calm");
    // the last line stays on screen until the next one replaces it
  },
});

// ── prefs (per device) ────────────────────────────────

function loadPrefs() {
  try {
    return { voiceOut: true, voiceMode: false, subtitles: true, ...JSON.parse(localStorage.getItem("ciel.prefs") || "{}") };
  } catch {
    return { voiceOut: true, voiceMode: false, subtitles: true };
  }
}

function savePrefs() {
  try {
    localStorage.setItem("ciel.prefs", JSON.stringify(prefs));
  } catch {}
}

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
  app.dataset.state = state;
  const [greek, thai] = STATES[state];
  $("#state-greek").textContent = greek;
  $("#state-thai").textContent = thai;
}

function showVersion(v) {
  $("#sl-version").textContent = `v${v.version}${v.commit ? ` · ${v.commit}` : ""}`;
}

// ── voice mode & toggles ──────────────────────────────

const speakNow = () => ttsAvailable && (prefs.voiceMode || prefs.voiceOut);

function renderToggles() {
  app.classList.toggle("voice-mode", prefs.voiceMode);
  app.classList.toggle("no-subs", !prefs.subtitles);
  $("#voice-btn").textContent = prefs.voiceOut ? "[เสียง●]" : "[เสียง○]";
  $("#voice-btn").hidden = !ttsAvailable || prefs.voiceMode;
  $("#subs-btn").textContent = prefs.subtitles ? "[ซับ●]" : "[ซับ○]";
  $("#subs-btn").hidden = !prefs.voiceMode;
  $("#stage").setAttribute("aria-label", prefs.voiceMode ? "ออกจากโหมดเสียง" : "เข้าโหมดเสียง");
}

function setVoiceMode(on) {
  const apply = () => {
    prefs.voiceMode = on;
    savePrefs();
    renderToggles();
    if (!on) scrollDown();
  };
  // morph smoothly where supported (Chrome / Android)
  if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.startViewTransition(apply);
  } else {
    apply();
  }
}

// Tap the circle: interrupt Ciel if she is talking, otherwise switch modes
$("#stage").addEventListener("click", () => {
  voice.unlock();
  if (voice.playing) {
    voice.stop();
    addEntry("note", "หยุดพูดแล้ว");
    return;
  }
  setVoiceMode(!prefs.voiceMode);
});
$("#stage").addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    $("#stage").click();
  }
});

$("#voice-btn").addEventListener("click", () => {
  voice.unlock();
  prefs.voiceOut = !prefs.voiceOut;
  if (!prefs.voiceOut) voice.stop();
  savePrefs();
  renderToggles();
});

$("#subs-btn").addEventListener("click", () => {
  prefs.subtitles = !prefs.subtitles;
  savePrefs();
  renderToggles();
});

function showSubtitle(text, jp = "") {
  $("#sub-main").textContent = text;
  $("#sub-jp").textContent = jp;
  subtitle.classList.add("on");
}

function clearSubtitle() {
  subSeq = -2;
  subtitle.classList.remove("on");
}

// Subtitle for segment `seq`: in anime style the Japanese line on top and its
// translation below. The translation is generated after the Japanese line, so it
// often arrives while — or after — that line is spoken; `sub` fills it in later.
function showSegmentSubtitle(seq) {
  subSeq = seq;
  if (anime) showSubtitle(subs.get(seq) || "…", jpLines.get(seq) || "");
  else showSubtitle(jpLines.get(seq) || "");
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
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    retry = 0;
    setBusy(false);
  };

  ws.onmessage = (e) => {
    if (e.data instanceof ArrayBuffer) voice.addAudio(e.data);
    else handle(JSON.parse(e.data));
  };

  ws.onclose = (e) => {
    if (e.code === 4401) return showLogin();
    setStatus("offline", "ΑΠΟΣΥΝΔΕΣΗ");
    voice.stop();
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
      ttsAvailable = !!msg.tts;
      anime = msg.style === "anime";
      renderToggles();
      if (ttsAvailable && anime && !voice.acks) voice.loadAcks([0, 1, 2].map((i) => `/api/voice/ack/${i}`));
      if (checkVersion(msg)) return;
      if (connectedBefore && log.children.length) {
        addEntry("note", "เชื่อมต่อใหม่แล้ว — บทสนทนาก่อนหน้าจะไม่ถูกจำ");
      } else if (anime && msg.greeting_ja) {
        const entry = addEntry("ciel");
        appendLine(entry, "jp", msg.greeting_ja);
        appendLine(entry, "sub", msg.greeting);
      } else if (msg.greeting) {
        addEntry("ciel", msg.greeting);
      }
      connectedBefore = true;
      break;

    case "start":
      turnSpeaks = !!msg.speak;
      anime = msg.style === "anime";
      subs = new Map();
      jpLines = new Map();
      noAudio = new Set();
      subSeq = -2; // the previous answer's subtitle stays until this one has a line
      if (turnSpeaks) voice.beginTurn();
      current = addEntry("ciel");
      current.classList.add("streaming");
      setAvatar("thinking");
      break;

    case "delta":
      if (!current) current = addEntry("ciel");
      // voiced replies switch to "speaking" when the audio actually starts
      if (!turnSpeaks && !pending.length && !current.body.textContent) setAvatar("speaking");
      pending.push([msg.kind || null, msg.text]);
      if (!flushQueued) {
        flushQueued = true;
        requestAnimationFrame(flush);
      }
      break;

    case "line_end":
      pending.push(["end", msg.kind || ""]); // kind may correct how the line was streamed
      if (!flushQueued) {
        flushQueued = true;
        requestAnimationFrame(flush);
      }
      break;

    case "segment":
      jpLines.set(msg.seq, msg.text);
      if (msg.audio) voice.addSegment(msg);
      else {
        avatar.setEmotion(msg.emotion);
        if (!anime) showSegmentSubtitle(msg.seq); // anime: wait for its translation
      }
      break;

    case "sub":
      subs.set(msg.seq, msg.text);
      if (msg.seq < 0) {
        // a line Ciel wrote without Japanese: nothing to say, just show it
        subSeq = -1;
        showSubtitle(msg.text);
      } else if (msg.seq === subSeq || !turnSpeaks || noAudio.has(msg.seq)) {
        // fill in the line on screen (even if its audio already finished),
        // or follow the text when there is no voice for it
        showSegmentSubtitle(msg.seq);
      }
      break;

    case "audio_error":
      voice.failed(msg.seq);
      noAudio.add(msg.seq);
      if (!voice.playing) showSegmentSubtitle(msg.seq);
      break;

    case "audio_end":
      voice.end();
      break;

    case "end":
      flush();
      if (current && !msg.structured) current.body.textContent = msg.text;
      finish();
      break;

    case "error":
      if (current && !current.body.textContent) current.remove();
      voice.stop();
      finish();
      addEntry("error", msg.message);
      break;
  }
}

// Tokens arrive many times per frame; paint them at most once per frame.
// pending = [[kind, text], …]; kind null = plain text, "jp"/"sub" = anime lines, "end" = close line
function flush() {
  flushQueued = false;
  if (!pending.length || !current) return;
  for (const [kind, text] of pending) {
    if (kind === "end") {
      if (text && current.line && current.line.dataset.kind !== text) {
        current.line.className = `ln ${text}`;
        current.line.dataset.kind = text;
      }
      current.line = null;
    }
    else if (kind) appendLine(current, kind, text, true);
    else {
      if (!current.stream) current.body.append((current.stream = document.createTextNode("")));
      current.stream.appendData(text);
    }
  }
  pending = [];
  scrollDown();
}

// anime style: the entry body holds alternating Japanese / translation lines
function appendLine(entry, kind, text, streaming = false) {
  let line = streaming ? entry.line : null;
  if (!line || line.dataset.kind !== kind) {
    line = document.createElement("span");
    line.className = `ln ${kind}`;
    line.dataset.kind = kind;
    line.append(document.createTextNode(""));
    entry.body.append(line);
    if (streaming) entry.line = line;
  }
  line.firstChild.appendData(text);
}

function finish() {
  pending = [];
  current?.classList.remove("streaming");
  current = null;
  // a voiced reply stays "thinking" until its audio starts, then the player takes over
  if (!voice.active) {
    setAvatar("idle");
    avatar.setEmotion("calm");
  }
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
  if (busy || voice.playing) return false; // try again after this reply
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
  voice.unlock(); // we're inside a user gesture: allowed to start audio
  voice.stop(); // a new question interrupts the old answer
  addEntry("user", text);
  const speak = speakNow();
  ws.send(JSON.stringify({ type: "chat", text, speak }));
  if (speak && anime) voice.playAck(); // "ん。" right away while the model thinks
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
  voice.stop();
  log.replaceChildren();
  clearSubtitle();
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

renderToggles();
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
