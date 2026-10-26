// Ciel's body. Anything that implements setState() and setLevel() can be the avatar,
// so the Live2D model will drop in here later without touching app.js.
//   setState("idle" | "thinking" | "speaking")
//   setLevel(0..1)  — voice energy; will be driven by TTS audio volume

const NS = "http://www.w3.org/2000/svg";
const GREEK = "ΣΟΦΙΑ · ΓΝΩΣΙΣ · ΛΟΓΟΣ · ΝΟΥΣ · ΑΛΗΘΕΙΑ · ΠΡΟΝΟΙΑ · ΜΝΗΜΗ · ΑΡΜΟΝΙΑ · ";
const RUNES = "ᚠᚢᚦᚨᚱᚲᚷᚹ ᚺᚾᛁᛃᛇᛈᛉᛊ ᛏᛒᛖᛗᛚᛜᛞᛟ ";

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
  const t = el("text", { fill, "font-size": size, "font-family": family, opacity, "letter-spacing": 0 }, parent);
  const tp = el("textPath", { href: `#${id}`, textLength: circ - size, lengthAdjust: "spacing" }, t);
  tp.textContent = text.repeat(Math.ceil(chars / text.length)).slice(0, chars);
}

function ticks(parent, count, r1, r2, attrs) {
  for (let i = 0; i < count; i++) {
    const deg = (360 / count) * i;
    const long = i % 5 === 0;
    const [x1, y1] = polar(r1 - (long ? 4 : 0), deg);
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
    this.host = host;
    this.state = "idle";
    this.level = 0;
    this.speed = 1;
    this.layers = [];
    this.sparks = [];
    this.calm = matchMedia("(prefers-reduced-motion: reduce)").matches ? 0.12 : 1;
    this.#build();
    this.last = performance.now();
    requestAnimationFrame((t) => this.#frame(t));
  }

  // a rotating layer: period in seconds for one turn, dir ±1
  #layer(svg, period, dir = 1) {
    const g = el("g", {}, svg);
    this.layers.push({ g, rate: (360 / period) * dir, angle: Math.random() * 360 });
    return g;
  }

  #build() {
    const svg = el("svg", { viewBox: "-300 -300 600 600", role: "img", "aria-label": "Ciel" });
    const defs = el("defs", {}, svg);

    const core = el("radialGradient", { id: "mc-core" }, defs);
    [["0", "#fffbea", 1], ["0.28", "#ffe08a", 1], ["0.58", "#ff9a2e", 0.85], ["0.82", "#7a3a06", 0.35], ["1", "#2a1402", 0]]
      .forEach(([offset, color, op]) => el("stop", { offset, "stop-color": color, "stop-opacity": op }, core));

    const aura = el("radialGradient", { id: "mc-aura" }, defs);
    [["0", "#ffd77a", 0.35], ["0.5", "#3fd8b8", 0.08], ["1", "#3fd8b8", 0]]
      .forEach(([offset, color, op]) => el("stop", { offset, "stop-color": color, "stop-opacity": op }, aura));

    const glow = el("filter", { id: "mc-glow", x: "-50%", y: "-50%", width: "200%", height: "200%" }, defs);
    el("feGaussianBlur", { stdDeviation: 5, result: "b" }, glow);
    const merge = el("feMerge", {}, glow);
    el("feMergeNode", { in: "b" }, merge);
    el("feMergeNode", { in: "SourceGraphic" }, merge);

    const GOLD = "#e9b949", HI = "#ffe39a", AETHER = "#3fd8b8";

    el("circle", { r: 300, fill: "url(#mc-aura)" }, svg);

    // light rays
    const rays = this.#layer(svg, 400, -1);
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
    const outer = this.#layer(svg, 180, 1);
    el("circle", { r: 286, fill: "none", stroke: GOLD, "stroke-width": 0.6, opacity: 0.45 }, outer);
    el("circle", { r: 272, fill: "none", stroke: GOLD, "stroke-width": 1.4 }, outer);
    ticks(outer, 120, 276, 282, { stroke: GOLD, "stroke-width": 0.8, opacity: 0.7 });
    ringText(outer, 251, GREEK, { size: 17, fill: GOLD, family: "EB Garamond, serif" });
    el("circle", { r: 244, fill: "none", stroke: GOLD, "stroke-width": 0.8, opacity: 0.8 }, outer);

    // rune ring
    const runes = this.#layer(svg, 120, -1);
    el("circle", { r: 226, fill: "none", stroke: AETHER, "stroke-width": 0.8, opacity: 0.55 }, runes);
    ringText(runes, 206, RUNES, { size: 15, fill: AETHER, family: "Noto Sans Runic, sans-serif", opacity: 0.85 });
    el("circle", { r: 198, fill: "none", stroke: GOLD, "stroke-width": 0.8, opacity: 0.7 }, runes);

    // sacred geometry
    const geo = this.#layer(svg, 90, 1);
    polygon(geo, 188, 4, 0, { stroke: GOLD, "stroke-width": 0.9, opacity: 0.65 });
    polygon(geo, 188, 4, 45, { stroke: GOLD, "stroke-width": 0.9, opacity: 0.65 });
    polygon(geo, 188, 3, -90, { stroke: AETHER, "stroke-width": 0.7, opacity: 0.35 });
    polygon(geo, 188, 3, 90, { stroke: AETHER, "stroke-width": 0.7, opacity: 0.35 });
    el("circle", { r: 170, fill: "none", stroke: GOLD, "stroke-width": 0.8, "stroke-dasharray": "2 7", opacity: 0.8 }, geo);

    // inner ring with nodes
    const inner = this.#layer(svg, 50, -1);
    el("circle", { r: 148, fill: "none", stroke: GOLD, "stroke-width": 1.6 }, inner);
    for (let i = 0; i < 12; i++) {
      const [cx, cy] = polar(148, i * 30);
      el("circle", { cx, cy, r: i % 3 === 0 ? 5 : 3, fill: "#050807", stroke: HI, "stroke-width": 1.2 }, inner);
    }

    // the bright halo + core
    this.heart = el("g", {}, svg);
    const halo = this.#layer(this.heart, 70, 1);
    this.halo = polygon(halo, 120, 15, 0, { stroke: "#fff4cf", "stroke-width": 6, filter: "url(#mc-glow)", "stroke-linejoin": "round" });
    el("circle", { r: 116, fill: "url(#mc-core)" }, this.heart);
    const sparkle = this.#layer(this.heart, 24, -1);
    for (let i = 0; i < 28; i++) {
      const [x2, y2] = polar(40 + Math.random() * 70, (360 / 28) * i);
      el("line", { x1: 0, y1: 0, x2, y2, stroke: "#fffbea", "stroke-width": 0.8, opacity: 0.25 + Math.random() * 0.35 }, sparkle);
    }
    el("circle", { r: 10, fill: "#fffef5", filter: "url(#mc-glow)" }, this.heart);

    // drifting motes
    const motes = this.#layer(svg, 260, 1);
    for (let i = 0; i < 26; i++) {
      const [cx, cy] = polar(80 + Math.random() * 215, Math.random() * 360);
      const dot = el("circle", { cx, cy, r: 0.8 + Math.random() * 1.8, fill: Math.random() < 0.7 ? HI : AETHER }, motes);
      this.sparks.push({ dot, phase: Math.random() * Math.PI * 2, rate: 0.6 + Math.random() * 1.8 });
    }

    this.host.replaceChildren(svg);
  }

  #frame(now) {
    const dt = Math.min(0.1, (now - this.last) / 1000);
    this.last = now;

    // ease toward the speed of the current state
    const target = SPEED[this.state] * this.calm;
    this.speed += (target - this.speed) * Math.min(1, dt * 2.5);

    if (this.state === "speaking" && !this.externalLevel) {
      const t = now / 1000;
      this.level = Math.max(0, 0.45 + 0.4 * Math.sin(t * 11) * Math.sin(t * 27));
    } else if (this.state !== "speaking") {
      this.level += (0 - this.level) * Math.min(1, dt * 4);
    }

    for (const l of this.layers) {
      l.angle = (l.angle + l.rate * this.speed * dt) % 360;
      l.g.setAttribute("transform", `rotate(${l.angle.toFixed(2)})`);
    }

    const breathe = 1 + Math.sin(now / 900) * 0.015;
    const pulse = this.state === "thinking" ? Math.sin(now / 160) * 0.025 : 0;
    this.heart.setAttribute("transform", `scale(${(breathe + pulse + this.level * 0.12).toFixed(4)})`);
    this.halo.setAttribute("stroke-width", (6 + this.level * 5).toFixed(2));
    this.rays.setAttribute("opacity", (0.65 + this.level * 0.35 + (this.state === "thinking" ? 0.2 : 0)).toFixed(2));

    const t = now / 1000;
    for (const s of this.sparks) s.dot.setAttribute("opacity", (0.25 + 0.75 * Math.abs(Math.sin(s.phase + t * s.rate))).toFixed(2));

    requestAnimationFrame((n) => this.#frame(n));
  }

  setState(state) {
    this.state = state;
    this.host.dataset.state = state;
  }

  setLevel(v) {
    this.externalLevel = true;
    this.level = v;
  }
}

export async function createAvatar(stage) {
  // TODO(phase 5): if web/live2d/config.json exists, place the Live2D model in front of the circle.
  return new MagicCircle(stage.querySelector("#circle"));
}
