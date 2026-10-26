// Ciel's body. Anything that implements setState() and setLevel() can be the avatar,
// so the Live2D model will drop in here later without touching app.js.
//   setState("idle" | "thinking" | "speaking")
//   setLevel(0..1)  — voice energy; will be driven by TTS audio volume
//
// Performance: every ring is its own <svg> that is drawn ONCE, then spun with a
// CSS transform animation. The GPU rotates the finished bitmaps, so the phone never
// redraws the circle (no per-frame JS, no per-frame SVG filters).

const NS = "http://www.w3.org/2000/svg";
const VIEWBOX = "-300 -300 600 600";
const GREEK = "ΣΟΦΙΑ · ΓΝΩΣΙΣ · ΛΟΓΟΣ · ΝΟΥΣ · ΑΛΗΘΕΙΑ · ΠΡΟΝΟΙΑ · ΜΝΗΜΗ · ΑΡΜΟΝΙΑ · ";
const RUNES = "ᚠᚢᚦᚨᚱᚲᚷᚹ ᚺᚾᛁᛃᛇᛈᛉᛊ ᛏᛒᛖᛗᛚᛜᛞᛟ ";
const GOLD = "#e9b949", HI = "#ffe39a", AETHER = "#3fd8b8";

// how fast the circle turns in each state (multiplier on every ring's base speed)
const SPEED = { idle: 1, thinking: 5, speaking: 1.8 };

function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  parent?.append(node);
  return node;
}

function polar(r, deg) {
  const a = (deg * Math.PI) / 180;
  return [r * Math.cos(a), r * Math.sin(a)];
}

let uid = 0;
function ringText(parent, r, text, { size, fill, family, opacity = 1 }) {
  const id = `ring-${uid++}`;
  el("path", { id, d: `M ${-r} 0 a ${r} ${r} 0 1 1 ${2 * r} 0 a ${r} ${r} 0 1 1 ${-2 * r} 0`, fill: "none" }, parent);
  const circ = 2 * Math.PI * r;
  const chars = Math.floor(circ / (size * 0.78));
  const t = el("text", { fill, "font-size": size, "font-family": family, opacity }, parent);
  const tp = el("textPath", { href: `#${id}`, textLength: circ - size, lengthAdjust: "spacing" }, t);
  tp.textContent = text.repeat(Math.ceil(chars / text.length)).slice(0, chars);
}

function ticks(parent, count, r1, r2, attrs) {
  for (let i = 0; i < count; i++) {
    const deg = (360 / count) * i;
    const [x1, y1] = polar(r1 - (i % 5 === 0 ? 4 : 0), deg);
    const [x2, y2] = polar(r2, deg);
    el("line", { x1, y1, x2, y2, ...attrs }, parent);
  }
}

function polygon(parent, r, sides, rotate, attrs) {
  const pts = Array.from({ length: sides }, (_, i) => polar(r, rotate + (360 / sides) * i).join(","));
  return el("polygon", { points: pts.join(" "), fill: "none", ...attrs }, parent);
}

class MagicCircle {
  constructor(host) {
    this.state = "idle";
    this.spins = [];
    this.calm = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0.12 : 1;
    this.rate = this.calm;

    this.root = document.createElement("div");
    this.root.className = "mc";
    this.root.dataset.state = "idle";
    host.replaceChildren(this.root);
    this.#build();

    // keep the layers square and as small as possible (smaller GPU textures)
    new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      this.root.style.setProperty("--mc-size", `${Math.floor(Math.min(width, height))}px`);
    }).observe(host);
  }

  #layer(parent = this.root, cls = "") {
    const svg = el("svg", { viewBox: VIEWBOX, class: `mc-layer ${cls}`, "aria-hidden": "true" });
    parent.append(svg);
    return svg;
  }

  // rotate a whole layer on the compositor; period = seconds per turn
  #spin(node, period, dir = 1) {
    const anim = node.animate([{ transform: "rotate(0turn)" }, { transform: "rotate(1turn)" }], {
      duration: period * 1000,
      iterations: Infinity,
      direction: dir < 0 ? "reverse" : "normal",
    });
    anim.currentTime = Math.random() * period * 1000;
    anim.playbackRate = this.rate;
    this.spins.push(anim);
    return node;
  }

  #build() {
    // static background: aura + shared defs (ids are document-wide)
    const base = this.#layer();
    const defs = el("defs", {}, base);
    const core = el("radialGradient", { id: "mc-core" }, defs);
    [["0", "#fffbea", 1], ["0.28", "#ffe08a", 1], ["0.58", "#ff9a2e", 0.85], ["0.82", "#7a3a06", 0.35], ["1", "#2a1402", 0]]
      .forEach(([offset, color, op]) => el("stop", { offset, "stop-color": color, "stop-opacity": op }, core));
    const aura = el("radialGradient", { id: "mc-aura" }, defs);
    [["0", "#ffd77a", 0.3], ["0.5", "#3fd8b8", 0.07], ["1", "#3fd8b8", 0]]
      .forEach(([offset, color, op]) => el("stop", { offset, "stop-color": color, "stop-opacity": op }, aura));
    const glow = el("filter", { id: "mc-glow", x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs);
    el("feGaussianBlur", { stdDeviation: 5, result: "b" }, glow);
    const merge = el("feMerge", {}, glow);
    el("feMergeNode", { in: "b" }, merge);
    el("feMergeNode", { in: "SourceGraphic" }, merge);
    el("circle", { r: 300, fill: "url(#mc-aura)" }, base);

    // voice ripple: a ring that swells out of the heart with each syllable
    this.ripple = this.#layer(this.root, "ripple");
    el("circle", { r: 132, fill: "none", stroke: HI, "stroke-width": 2 }, this.ripple);
    el("circle", { r: 140, fill: "none", stroke: GOLD, "stroke-width": 0.8, "stroke-dasharray": "1 5" }, this.ripple);

    // light rays
    const rays = this.#spin(this.#layer(this.root, "rays"), 400, -1);
    this.rays = rays;
    for (let i = 0; i < 44; i++) {
      const deg = (360 / 44) * i + Math.random() * 4;
      const [x1, y1] = polar(70, deg);
      const [x2, y2] = polar(200 + Math.random() * 110, deg);
      el("line", { x1, y1, x2, y2, stroke: HI, "stroke-width": 0.4 + Math.random() * 1.1, opacity: 0.12 + Math.random() * 0.4 }, rays);
    }
    for (const deg of [0, 90, 180, 270]) {
      const [x2, y2] = polar(300, deg);
      el("line", { x1: 0, y1: 0, x2, y2, stroke: GOLD, "stroke-width": 0.6, opacity: 0.5 }, rays);
    }

    // outer ring: Greek inscription
    const outer = this.#spin(this.#layer(), 180, 1);
    this.outer = outer;
    el("circle", { r: 286, fill: "none", stroke: GOLD, "stroke-width": 0.6, opacity: 0.45 }, outer);
    el("circle", { r: 272, fill: "none", stroke: GOLD, "stroke-width": 1.4 }, outer);
    ticks(outer, 120, 276, 282, { stroke: GOLD, "stroke-width": 0.8, opacity: 0.7 });
    ringText(outer, 251, GREEK, { size: 17, fill: GOLD, family: "EB Garamond, serif" });
    el("circle", { r: 244, fill: "none", stroke: GOLD, "stroke-width": 0.8, opacity: 0.8 }, outer);

    // rune ring
    const runes = this.#spin(this.#layer(), 120, -1);
    el("circle", { r: 226, fill: "none", stroke: AETHER, "stroke-width": 0.8, opacity: 0.55 }, runes);
    ringText(runes, 206, RUNES, { size: 15, fill: AETHER, family: "Noto Sans Runic, sans-serif", opacity: 0.85 });
    el("circle", { r: 198, fill: "none", stroke: GOLD, "stroke-width": 0.8, opacity: 0.7 }, runes);

    // sacred geometry
    const geo = this.#spin(this.#layer(), 90, 1);
    polygon(geo, 188, 4, 0, { stroke: GOLD, "stroke-width": 0.9, opacity: 0.65 });
    polygon(geo, 188, 4, 45, { stroke: GOLD, "stroke-width": 0.9, opacity: 0.65 });
    polygon(geo, 188, 3, -90, { stroke: AETHER, "stroke-width": 0.7, opacity: 0.35 });
    polygon(geo, 188, 3, 90, { stroke: AETHER, "stroke-width": 0.7, opacity: 0.35 });
    el("circle", { r: 170, fill: "none", stroke: GOLD, "stroke-width": 0.8, "stroke-dasharray": "2 7", opacity: 0.8 }, geo);

    // inner ring with nodes
    const inner = this.#spin(this.#layer(), 50, -1);
    el("circle", { r: 148, fill: "none", stroke: GOLD, "stroke-width": 1.6 }, inner);
    for (let i = 0; i < 12; i++) {
      const [cx, cy] = polar(148, i * 30);
      el("circle", { cx, cy, r: i % 3 === 0 ? 5 : 3, fill: "#000", stroke: HI, "stroke-width": 1.2 }, inner);
    }

    // the heart: halo + core + sparkle, scaled by CSS (breathe / pulse / talk)
    this.heart = document.createElement("div");
    this.heart.className = "mc-heart";
    this.root.append(this.heart);
    const halo = this.#spin(this.#layer(this.heart), 70, 1);
    polygon(halo, 120, 15, 0, { stroke: "#fff4cf", "stroke-width": 6, filter: "url(#mc-glow)", "stroke-linejoin": "round" });
    const coreLayer = this.#layer(this.heart);
    el("circle", { r: 116, fill: "url(#mc-core)" }, coreLayer);
    const sparkle = this.#spin(this.#layer(this.heart), 24, -1);
    for (let i = 0; i < 28; i++) {
      const [x2, y2] = polar(40 + Math.random() * 70, (360 / 28) * i);
      el("line", { x1: 0, y1: 0, x2, y2, stroke: "#fffbea", "stroke-width": 0.8, opacity: 0.25 + Math.random() * 0.35 }, sparkle);
    }
    el("circle", { r: 10, fill: "#fffef5", filter: "url(#mc-glow)" }, coreLayer);

    // drifting motes: two layers that spin and twinkle out of phase
    for (const [period, dir, cls] of [[260, 1, "motes-a"], [200, -1, "motes-b"]]) {
      const wrap = document.createElement("div");
      wrap.className = "mc-spin";
      this.root.append(wrap);
      this.#spin(wrap, period, dir);
      const motes = this.#layer(wrap, cls);
      for (let i = 0; i < 13; i++) {
        const [cx, cy] = polar(80 + Math.random() * 215, Math.random() * 360);
        el("circle", { cx, cy, r: 0.8 + Math.random() * 1.8, fill: Math.random() < 0.7 ? HI : AETHER }, motes);
      }
    }
  }

  // ease every ring toward the new speed over ~0.6s (a few frames, then idle)
  #easeRate(target) {
    cancelAnimationFrame(this.raf);
    const from = this.rate;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / 600);
      this.rate = from + (target - from) * (1 - (1 - t) ** 3);
      for (const a of this.spins) a.playbackRate = this.rate;
      if (t < 1) this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  }

  setState(state) {
    if (state === this.state) return;
    this.state = state;
    this.root.dataset.state = state;
    this.#easeRate(SPEED[state] * this.calm);
  }

  // Live voice → circle. Only `scale` / `opacity` on already-composited layers,
  // so this is cheap even at 60 fps on a phone.
  //   level: loudness 0..1, low: voice body 0..1, high: consonants/sibilance 0..1
  setLevel(level, low = level, high = 0) {
    const on = level > 0.01;
    if (on !== this.audioOn) {
      this.audioOn = on;
      this.root.toggleAttribute("data-audio", on);
    }
    this.heart.style.scale = (1 + level * 0.16 + low * 0.05).toFixed(3);
    this.ripple.style.scale = (1 + level * 0.55).toFixed(3);
    this.ripple.style.opacity = Math.min(1, level * 1.6).toFixed(2);
    this.rays.style.opacity = (0.6 + level * 0.4 + high * 0.3).toFixed(2);
    this.outer.style.scale = (1 + high * 0.025).toFixed(4);
  }

  setEmotion(emotion) {
    this.root.dataset.emotion = emotion || "calm";
  }
}

export async function createAvatar(stage) {
  // TODO(phase 5): if web/live2d/config.json exists, place the Live2D model in front of the circle.
  return new MagicCircle(stage.querySelector("#circle"));
}
