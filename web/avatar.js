// Ciel's body. Anything that implements setState() and setLevel() can be the avatar,
// so the Live2D model will drop in here later without touching app.js.
//   setState("idle" | "thinking" | "speaking")
//   setLevel(0..1)  — mouth / energy level; will be driven by TTS audio volume

class OrbAvatar {
  constructor(el) {
    this.el = el;
    this.level = 0;
    this.raf = 0;
  }

  setState(state) {
    this.el.dataset.state = state;
    cancelAnimationFrame(this.raf);
    if (state === "speaking") this.#fakeTalk();
    else this.setLevel(0);
  }

  setLevel(v) {
    this.level = v;
    this.el.style.setProperty("--level", v.toFixed(3));
  }

  // Until we have real audio, wobble like speech while text streams in
  #fakeTalk() {
    const tick = (t) => {
      this.setLevel(0.35 + 0.35 * Math.sin(t / 90) * Math.sin(t / 37));
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }
}

export async function createAvatar(stage) {
  // TODO(phase 5): if web/live2d/config.json exists, load the Live2D model instead.
  return new OrbAvatar(stage.querySelector(".orb"));
}
