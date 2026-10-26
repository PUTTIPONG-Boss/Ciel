// Voice Lab: tune Ciel's voice per language and per emotion, preview, save.

const $ = (s) => document.querySelector(s);
const LANG_NAMES = { th: "ไทย", ja: "日本語", en: "English" };
const LANG_PREFIX = { th: "th-", ja: "ja-", en: "en-" };
const RANGES = { rate: [-50, 50, "%"], pitch: [-40, 40, "Hz"], volume: [-50, 50, "%"] };
const EMO_RANGES = { rate: [-30, 30, "%"], pitch: [-30, 30, "Hz"], volume: [-40, 40, "%"] };
const EMO_NAMES = { calm: "เย็นชา", shy: "เขิน", tease: "กวน", concern: "เป็นห่วง", pout: "หึง/งอน" };

let state = null; // the config being edited
let saved = ""; // JSON of the last saved config, to show unsaved changes
let player = null;
let ctx = null;

function setStatus(text, kind = "") {
  const el = $("#lab-status");
  el.textContent = text;
  el.className = `lab-status ${kind}`;
}

function markDirty() {
  const dirty = JSON.stringify(state) !== saved;
  $("#save-btn").textContent = dirty ? "[บันทึก*]" : "[บันทึก]";
  if (!$("#yaml").hidden) $("#yaml").textContent = toYaml();
}

function slider(label, value, [min, max, unit], onInput) {
  const row = document.createElement("label");
  row.className = "row";
  const name = document.createElement("span");
  name.className = "k";
  name.textContent = label;
  const range = document.createElement("input");
  range.type = "range";
  range.min = min;
  range.max = max;
  range.step = 1;
  range.value = value;
  const out = document.createElement("span");
  out.className = "v";
  const show = () => (out.textContent = `${range.value > 0 ? "+" : ""}${range.value}${unit}`);
  show();
  range.addEventListener("input", () => {
    show();
    onInput(Number(range.value));
    markDirty();
  });
  row.append(name, range, out);
  return row;
}

async function play(text, lang, emotion, button) {
  // create/resume audio while still inside the click — after an await it may stay suspended
  ctx ||= new AudioContext();
  if (ctx.state === "suspended") ctx.resume();
  player?.pause();
  const label = button.textContent;
  button.textContent = "[…]";
  try {
    const res = await fetch("/api/voice/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang, emotion, config: state }),
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.status);
    // play through Web Audio so volume can go above 100% (the server sends it as a gain)
    const gain = Number(res.headers.get("X-Ciel-Gain") || 1);
    const buffer = await ctx.decodeAudioData(await res.arrayBuffer());
    const src = ctx.createBufferSource();
    const amp = ctx.createGain();
    amp.gain.value = gain;
    src.buffer = buffer;
    src.connect(amp).connect(ctx.destination);
    player = { pause: () => src.stop(), set onended(fn) { src.onended = fn; } };
    src.start();
    setStatus("กำลังเล่นเสียง…");
    player.onended = () => setStatus("พร้อม");
  } catch (e) {
    setStatus(`เล่นเสียงไม่ได้: ${e.message}`, "err");
  } finally {
    button.textContent = label;
  }
}

function buildLanguage(lang, voices, sample, emotions) {
  const cfg = state.languages[lang];
  const box = document.createElement("div");
  box.className = "lang";

  const head = document.createElement("div");
  head.className = "lang-head";
  head.textContent = `── ${lang.toUpperCase()} · ${LANG_NAMES[lang]} `;
  box.append(head);

  // voice picker: this language's voices first, then multilingual ones
  const row = document.createElement("label");
  row.className = "row";
  const k = document.createElement("span");
  k.className = "k";
  k.textContent = "voice";
  const select = document.createElement("select");
  const own = voices.filter((v) => v.locale.startsWith(LANG_PREFIX[lang]) && !v.name.includes("Multilingual"));
  const multi = voices.filter((v) => v.name.includes("Multilingual"));
  for (const [title, list] of [[LANG_NAMES[lang], own], ["Multilingual (ทุกภาษา)", multi]]) {
    const group = document.createElement("optgroup");
    group.label = title;
    for (const v of list) {
      const opt = document.createElement("option");
      opt.value = v.name;
      opt.textContent = `${v.name.replace("Neural", "")} · ${v.gender === "Female" ? "♀" : "♂"} ${v.tags.join(", ")}`;
      group.append(opt);
    }
    select.append(group);
  }
  if (![...select.options].some((o) => o.value === cfg.voice)) select.add(new Option(cfg.voice, cfg.voice), 0);
  select.value = cfg.voice;
  select.addEventListener("change", () => {
    cfg.voice = select.value;
    markDirty();
  });
  row.append(k, select);
  box.append(row);

  for (const key of ["rate", "pitch", "volume"]) {
    box.append(slider(key, cfg[key] ?? 0, RANGES[key], (v) => (cfg[key] = v)));
  }

  const text = document.createElement("textarea");
  text.className = "sample";
  text.rows = 2;
  text.value = sample;
  box.append(text);

  const actions = document.createElement("div");
  actions.className = "play-row";
  const all = document.createElement("button");
  all.className = "cmd primary";
  all.textContent = "[▶ ฟัง]";
  all.title = "เล่นข้อความด้านบน (ใช้ [แท็ก] อารมณ์ในข้อความได้)";
  all.addEventListener("click", () => play(text.value, lang, "calm", all));
  actions.append(all);
  for (const emo of emotions) {
    const b = document.createElement("button");
    b.className = "cmd";
    b.textContent = `[▶ ${emo}]`;
    b.title = `เล่นทั้งข้อความด้วยอารมณ์ ${EMO_NAMES[emo] || emo}`;
    b.addEventListener("click", () => play(text.value.replace(/\[(\w+)\]/g, ""), lang, emo, b));
    actions.append(b);
  }
  box.append(actions);
  return box;
}

function buildEmotion(emo) {
  const cfg = (state.emotions[emo] ||= { rate: 0, pitch: 0, volume: 0 });
  const box = document.createElement("div");
  box.className = "lang";
  const head = document.createElement("div");
  head.className = "lang-head";
  head.textContent = `── [${emo}] ${EMO_NAMES[emo] || ""} `;
  box.append(head);
  for (const key of ["rate", "pitch", "volume"]) {
    box.append(slider(key, cfg[key] ?? 0, EMO_RANGES[key], (v) => (cfg[key] = v)));
  }
  return box;
}

function toYaml() {
  const lines = ["voice:", "  languages:"];
  for (const [lang, c] of Object.entries(state.languages)) {
    lines.push(`    ${lang}: {voice: ${c.voice}, rate: ${c.rate}, pitch: ${c.pitch}, volume: ${c.volume}}`);
  }
  lines.push("  emotions:");
  for (const [emo, c] of Object.entries(state.emotions)) {
    lines.push(`    ${emo}: {rate: ${c.rate ?? 0}, pitch: ${c.pitch ?? 0}, volume: ${c.volume ?? 0}}`);
  }
  return lines.join("\n");
}

async function load() {
  const res = await fetch("/api/voice");
  if (res.status === 401) {
    location.href = "./"; // log in on the main page first
    return;
  }
  const data = await res.json();
  if (!data.enabled) setStatus("TTS ถูกปิดอยู่ (CIEL_TTS) — ฟังตัวอย่างไม่ได้", "err");
  state = data.config;
  saved = JSON.stringify(state);

  let voices = [];
  try {
    const vr = await fetch("/api/voice/voices");
    if (vr.ok) voices = await vr.json();
  } catch {}
  if (!voices.length) setStatus("โหลดรายชื่อเสียงไม่ได้ (ต้องต่ออินเทอร์เน็ต) — ยังปรับค่าอื่นได้", "err");
  else if (data.enabled) setStatus(data.overridden ? "พร้อม · กำลังใช้ค่าที่บันทึกจาก Voice Lab" : "พร้อม · กำลังใช้ค่าจากไฟล์นิสัย");

  for (const lang of data.langs) $("#langs").append(buildLanguage(lang, voices, data.samples[lang], data.emotions));
  for (const emo of data.emotions) $("#emotions").append(buildEmotion(emo));
  markDirty();
}

$("#save-btn").addEventListener("click", async () => {
  const res = await fetch("/api/voice", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config: state }),
  });
  if (res.ok) {
    saved = JSON.stringify(state);
    markDirty();
    setStatus("บันทึกแล้ว — คำตอบถัดไปของ Ciel จะใช้เสียงนี้", "ok");
  } else {
    setStatus("บันทึกไม่สำเร็จ", "err");
  }
});

$("#reset-btn").addEventListener("click", async () => {
  if (!confirm("คืนค่าเสียงทั้งหมดเป็นค่าในไฟล์นิสัย (persona/ciel.yaml)?")) return;
  await fetch("/api/voice", { method: "DELETE" });
  location.reload();
});

$("#yaml-btn").addEventListener("click", () => {
  const pre = $("#yaml");
  pre.hidden = !pre.hidden;
  pre.textContent = toYaml();
});

load();
