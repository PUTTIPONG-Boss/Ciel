// Plays Ciel's voice: MP3 sentences arrive out of order over the socket
// (4-byte seq + MP3), get decoded, and play back-to-back in seq order.
// An analyser reads the live audio so the magic circle can react to it.

export class VoicePlayer {
  constructor({ onLevel, onSegment, onIdle } = {}) {
    this.onLevel = onLevel || (() => {});
    this.onSegment = onSegment || (() => {});
    this.onIdle = onIdle || (() => {});
    this.ctx = null;
    this.ignore = true; // drop audio until a turn begins
    this.#reset();
  }

  #reset() {
    this.#resetTurn();
    this.source = null;
  }

  #resetTurn() {
    this.meta = new Map(); // seq → {text, lang, emotion}
    this.buffers = new Map(); // seq → AudioBuffer | null (failed)
    this.next = 0;
    this.ended = false;
  }

  // ── instant acknowledgement ("ん。" / "はい。") ──────────────
  // Pre-fetched once; played the moment a message is sent so Ciel reacts
  // within ~0.1 s while the model is still thinking. The real answer queues
  // behind it (#pump waits for the current source to end).

  async loadAcks(urls) {
    this.acks = [];
    for (const url of urls) {
      try {
        const res = await fetch(url);
        if (res.ok) this.acks.push({ data: await res.arrayBuffer(), gain: Number(res.headers.get("X-Ciel-Gain") || 1) });
      } catch {}
    }
  }

  async playAck() {
    if (!this.ctx || !this.acks?.length || this.source) return;
    const ack = this.acks[Math.floor(Math.random() * this.acks.length)];
    try {
      ack.buffer ||= await this.ctx.decodeAudioData(ack.data.slice(0));
    } catch {
      return;
    }
    if (this.source) return; // the real answer beat us to it
    const src = this.ctx.createBufferSource();
    const amp = this.ctx.createGain();
    amp.gain.value = ack.gain;
    src.buffer = ack.buffer;
    src.connect(amp).connect(this.analyser);
    src.isAck = true;
    src.onended = () => {
      if (this.source !== src) return;
      this.source = null;
      if (!this.ignore) this.#pump();
      else {
        cancelAnimationFrame(this.raf);
        this.raf = 0;
        this.onLevel(0, 0, 0);
      }
    };
    this.source = src;
    src.start();
    if (!this.raf) this.#meter();
  }

  get playing() {
    return !!this.source;
  }

  // a voiced reply is in progress (maybe still waiting for its first audio)
  get active() {
    return !this.ignore;
  }

  // must be called from a user gesture (tap / send) — browsers block audio otherwise
  unlock() {
    if (!this.ctx) {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 512;
      this.analyser.smoothingTimeConstant = 0.55;
      this.analyser.connect(this.ctx.destination);
      this.wave = new Uint8Array(this.analyser.fftSize);
      this.freq = new Uint8Array(this.analyser.frequencyBinCount);
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
  }

  beginTurn() {
    if (this.source?.isAck) this.#resetTurn(); // let the acknowledgement finish
    else this.stop();
    this.ignore = false;
  }

  addSegment(seg) {
    if (!this.ignore) this.meta.set(seg.seq, seg);
  }

  async addAudio(data) {
    if (this.ignore || !this.ctx) return;
    const seq = new DataView(data).getUint32(0);
    const turnMeta = this.meta;
    try {
      const buffer = await this.ctx.decodeAudioData(data.slice(4));
      if (turnMeta === this.meta) this.buffers.set(seq, buffer); // still the same turn?
    } catch {
      if (turnMeta === this.meta) this.buffers.set(seq, null);
    }
    this.#pump();
  }

  failed(seq) {
    if (this.ignore) return;
    this.buffers.set(seq, null);
    this.#pump();
  }

  end() {
    this.ended = true;
    this.#pump();
  }

  stop() {
    this.ignore = true;
    if (this.source) {
      this.source.onended = null;
      try { this.source.stop(); } catch {}
    }
    const wasActive = this.source || this.meta.size;
    this.#reset();
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    if (wasActive) {
      this.onLevel(0, 0, 0);
      this.onIdle();
    }
  }

  #pump() {
    if (this.source) return;
    while (this.buffers.has(this.next) && this.buffers.get(this.next) === null) this.next++; // skip failures
    const buffer = this.buffers.get(this.next);
    if (!buffer) {
      if (this.ended && this.next >= this.meta.size) this.#finish();
      return;
    }
    const seq = this.next;
    const meta = this.meta.get(seq) || { seq };
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    // per-sentence volume (emotion) is applied here, see ciel/tts.py gain()
    const amp = this.ctx.createGain();
    amp.gain.value = meta.gain ?? 1;
    src.connect(amp).connect(this.analyser);
    src.onended = () => {
      this.source = null;
      this.next = seq + 1;
      this.#pump();
    };
    this.source = src;
    src.start();
    this.onSegment(meta);
    if (!this.raf) this.#meter();
  }

  #finish() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.onLevel(0, 0, 0);
    this.ignore = true;
    this.#reset();
    this.onIdle();
  }

  // loudness + low/high energy, ~60×/s, only while speaking
  #meter() {
    const a = this.analyser;
    const tick = () => {
      a.getByteTimeDomainData(this.wave);
      let sum = 0;
      for (const v of this.wave) sum += (v - 128) ** 2;
      const rms = Math.sqrt(sum / this.wave.length) / 128;
      a.getByteFrequencyData(this.freq);
      const band = (from, to) => {
        let s = 0;
        for (let i = from; i < to; i++) s += this.freq[i];
        return s / ((to - from) * 255);
      };
      // bins are ~94 Hz wide at 48 kHz: low ≈ 90–750 Hz (voice body), high ≈ 2–6 kHz (consonants)
      this.onLevel(Math.min(1, rms * 3.2), band(1, 8), band(22, 64));
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }
}
