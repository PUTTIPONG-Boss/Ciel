"""Ciel's voice: text → speech, one sentence at a time.

Voice settings come from the persona's `voice:` section, overridden by
data/voice.yaml (written by the Voice Lab). The override lives outside git
so tuning the voice on the server never blocks auto-update.
"""

import asyncio
import logging
from copy import deepcopy
from pathlib import Path

import yaml

from .config import ROOT, settings

log = logging.getLogger("ciel.tts")

LANGS = ("th", "ja", "en")
EMOTIONS = ("calm", "shy", "tease", "concern")
OVERRIDE_PATH = ROOT / "data" / "voice.yaml"

DEFAULT_VOICE = {
    "languages": {
        "th": {"voice": "th-TH-PremwadeeNeural", "rate": -5, "pitch": 4, "volume": 0},
        "ja": {"voice": "ja-JP-NanamiNeural", "rate": -5, "pitch": 6, "volume": 0},
        "en": {"voice": "en-US-AvaNeural", "rate": -5, "pitch": 4, "volume": 0},
    },
    "emotions": {
        "calm": {"rate": 0, "pitch": 0, "volume": 0},
        "shy": {"rate": 8, "pitch": 14, "volume": -5},
        "tease": {"rate": 5, "pitch": 8, "volume": 0},
        "concern": {"rate": -10, "pitch": -4, "volume": -10},
    },
}


class TTSError(Exception):
    pass


def _merge(base: dict, extra: dict) -> dict:
    out = deepcopy(base)
    for k, v in (extra or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(persona_voice: dict | None, with_override: bool = True) -> dict:
    cfg = _merge(DEFAULT_VOICE, persona_voice or {})
    if with_override and OVERRIDE_PATH.exists():
        try:
            cfg = _merge(cfg, yaml.safe_load(OVERRIDE_PATH.read_text(encoding="utf-8")) or {})
        except yaml.YAMLError:
            log.warning("ignoring broken %s", OVERRIDE_PATH)
    return cfg


def save_override(cfg: dict) -> None:
    clean = {
        "languages": {lang: {k: cfg["languages"][lang][k] for k in ("voice", "rate", "pitch", "volume")} for lang in LANGS},
        "emotions": {emo: {k: int(cfg["emotions"][emo].get(k, 0)) for k in ("rate", "pitch", "volume")} for emo in EMOTIONS},
    }
    OVERRIDE_PATH.parent.mkdir(exist_ok=True)
    OVERRIDE_PATH.write_text(
        "# Saved by Voice Lab — overrides the voice: section of the persona file\n"
        + yaml.safe_dump(clean, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def clear_override() -> None:
    OVERRIDE_PATH.unlink(missing_ok=True)


def prosody(cfg: dict, lang: str, emotion: str = "calm") -> dict:
    """Voice, rate (%), pitch (Hz) and volume (%) for a language + emotion."""
    base = cfg["languages"][lang]
    emo = cfg["emotions"].get(emotion, cfg["emotions"]["calm"])
    return {
        "voice": base["voice"],
        "rate": int(base.get("rate", 0)) + int(emo.get("rate", 0)),
        "pitch": int(base.get("pitch", 0)) + int(emo.get("pitch", 0)),
        "volume": max(-90, min(100, int(base.get("volume", 0)) + int(emo.get("volume", 0)))),
    }


def gain(volume: int) -> float:
    """Volume is applied in the browser (Web Audio gain), not by the TTS
    service — the Thai Edge voices return no audio at all when volume != 0."""
    return round(1 + volume / 100, 3)


async def _edge(text: str, voice: str, rate: int, pitch: int) -> bytes:
    import edge_tts  # imported lazily so the app still starts without it

    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=f"{rate:+d}%", pitch=f"{pitch:+d}Hz").stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    return bytes(audio)


async def _hedged(text: str, voice: str, rate: int, pitch: int, copies: int = 3, every: float = 0.9) -> bytes:
    """The Edge service (Thai voices especially) has bursts where a request
    silently returns nothing after ~3 s. A healthy answer takes ~0.6 s, so if
    none has arrived after `every` seconds, launch another identical request —
    up to `copies` in flight — and use whichever succeeds first."""
    tasks: set[asyncio.Task] = set()
    launched = 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 7
    try:
        while loop.time() < deadline:
            if len(tasks) < copies and launched < copies + 2:
                tasks.add(asyncio.create_task(_edge(text, voice, rate, pitch)))
                launched += 1
            if not tasks:
                break  # every attempt failed
            done, _ = await asyncio.wait(tasks, timeout=every, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                tasks.discard(t)
                if not t.exception() and t.result():
                    return t.result()
        raise TTSError("no audio")
    finally:
        for t in tasks:
            t.cancel()


async def synthesize(text: str, voice: str, rate: int = 0, pitch: int = 0, volume: int = 0) -> bytes:
    """Returns MP3 bytes (volume is ignored here, see gain()).

    The free Edge endpoint sometimes returns nothing for a while. Retry, easing
    the pitch toward neutral, rather than let Ciel go silent."""
    attempts = [(rate, pitch), (0, 0)]
    last: Exception | None = None
    for i, (r, p) in enumerate(attempts):
        try:
            audio = await _hedged(text, voice, r, p)
            if i:
                log.info("TTS ok on attempt %d (rate %+d, pitch %+d)", i + 1, r, p)
            return audio
        except Exception as e:  # NoAudioReceived, timeouts, network hiccups
            last = e
    raise TTSError(f"TTS failed for voice {voice}: {last!r}")


_voice_list: list[dict] | None = None


async def list_voices() -> list[dict]:
    """Voices usable for Thai, Japanese, English (incl. multilingual ones)."""
    global _voice_list
    if _voice_list is None:
        import edge_tts

        keep = []
        for v in await edge_tts.list_voices():
            locale = v["Locale"]
            if locale.startswith(("th-", "ja-", "en-")) or "Multilingual" in v["ShortName"]:
                keep.append({
                    "name": v["ShortName"],
                    "locale": locale,
                    "gender": v["Gender"],
                    "tags": v.get("VoiceTag", {}).get("VoicePersonalities", []),
                })
        _voice_list = sorted(keep, key=lambda v: (v["locale"], v["name"]))
    return _voice_list


def enabled() -> bool:
    return settings.tts == "edge"
