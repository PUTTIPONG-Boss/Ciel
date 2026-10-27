"""Ciel's brain. Every backend streams plain text chunks, so swapping models
(or moving to a bigger machine later) never touches the rest of the app."""

import asyncio
import json
import logging
import random
from typing import AsyncIterator, Protocol

import httpx

from .config import Settings

log = logging.getLogger("ciel.llm")


class LLMError(Exception):
    pass


class LLM(Protocol):
    def stream(self, messages: list[dict], model: str | None = None, num_predict: int | None = None) -> AsyncIterator[str]: ...


class ThinkFilter:
    """Drops <think>…</think> blocks (Qwen3 reasoning) even when tags are split across chunks."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.buf = ""
        self.inside = False

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        out = []
        while True:
            tag = self.CLOSE if self.inside else self.OPEN
            idx = self.buf.find(tag)
            if idx != -1:
                if not self.inside:
                    out.append(self.buf[:idx])
                self.buf = self.buf[idx + len(tag):]
                self.inside = not self.inside
                continue
            # keep a tail that might be the start of a tag
            keep = next((n for n in range(len(tag) - 1, 0, -1) if self.buf.endswith(tag[:n])), 0)
            if not self.inside:
                out.append(self.buf[: len(self.buf) - keep])
            self.buf = self.buf[len(self.buf) - keep:] if keep else ""
            return "".join(out)

    def flush(self) -> str:
        rest, self.buf = ("" if self.inside else self.buf), ""
        return rest


EMPTY_THINK = "<think>\n\n</think>\n\n"  # Qwen3's "no thinking" marker
CHATML_STOP = ["<|im_end|>", "<|endoftext|>"]


def render_chatml(messages: list[dict]) -> str:
    """The Qwen3 (ChatML) prompt, rendered by us so each turn's prompt is the
    previous prompt + reply + new message, byte for byte, and Ollama can reuse
    its cache. Ollama's own qwen3 template adds " /no_think" only to the newest
    user message and the empty think block only to the reply being generated,
    so every new turn rewrote the previous one and the prompt was re-read from
    there (docs/model-compare/2026-10-27-1538-latency.md)."""
    out = []
    for m in messages:
        content = EMPTY_THINK + m["content"] if m["role"] == "assistant" else m["content"]
        out.append(f"<|im_start|>{m['role']}\n{content}<|im_end|>\n")
    return "".join(out) + "<|im_start|>assistant\n" + EMPTY_THINK


class OllamaLLM:
    def __init__(self, s: Settings):
        self.s = s
        self.client = httpx.AsyncClient(base_url=s.ollama_url, timeout=httpx.Timeout(300, connect=5))
        self.no_think_param: set[str] = set()  # models whose template rejects "think"
        # thinking needs Ollama's template; raw prompts always answer without it
        self.raw = s.raw_prompt and not s.think

    def _payload(self, messages: list[dict], model: str, stream: bool, num_predict: int) -> dict:
        keep = self.s.keep_alive
        payload = {
            "model": model,
            "stream": stream,
            # keep the model in RAM: reloading it + re-reading the prompt costs ~35 s on an M1
            "keep_alive": int(keep) if keep.lstrip("-").isdigit() else keep,
            "options": {
                "temperature": self.s.temperature,
                "num_ctx": self.s.num_ctx,
                "num_predict": num_predict,  # also stops a model that loops forever
            },
        }
        if self.raw:
            payload["prompt"] = render_chatml(messages)
            payload["raw"] = True
            payload["options"]["stop"] = CHATML_STOP
            return payload
        payload["messages"] = messages
        if model not in self.no_think_param:
            payload["think"] = self.s.think
        return payload

    @property
    def _endpoint(self) -> str:
        return "/api/generate" if self.raw else "/api/chat"

    async def warmup(self, messages: list[dict], probe: list[dict] | None = None) -> None:
        """Load the model and put the persona prompt into Ollama's prompt cache
        before the first real message (run at server start). Must be rendered
        exactly like a real request, or the first message starts cold.

        `probe` (the same prompt + one short user message) then runs the small
        "read a few tokens after the cache, write a few" request: the first
        such request after a start is ~4x slower on the M1's GPU (2.2 s instead
        of 0.65 s, docs/model-compare/2026-10-27-1907-latency.md). One
        non-streamed 4-token probe wasn't enough (2141-latency.md), so it now
        goes through stream() exactly like a reply, twice."""
        try:
            r = await self.client.post(self._endpoint, json=self._payload(messages, self.s.model, False, 1))
            if r.status_code != 200 and "think" in r.text and not self.raw:
                self.no_think_param.add(self.s.model)
                r = await self.client.post(self._endpoint, json=self._payload(messages, self.s.model, False, 1))
            if probe and r.status_code == 200:
                for _ in range(2):
                    async for _ in self.stream(probe, num_predict=16):
                        pass
            log.info("warm-up done (%s, %s, HTTP %s)", self.s.model, "raw" if self.raw else "chat", r.status_code)
        except (httpx.HTTPError, LLMError) as e:
            log.warning("warm-up failed: %s", e)

    async def stream(self, messages: list[dict], model: str | None = None, num_predict: int | None = None) -> AsyncIterator[str]:
        model = model or self.s.model
        payload = self._payload(messages, model, True, num_predict or self.s.num_predict)
        think = ThinkFilter()
        try:
            async with self.client.stream("POST", self._endpoint, json=payload) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode(errors="ignore")
                    # Fine-tunes (e.g. Shisa) may ship a chat template without thinking support
                    if "think" in body and "think" in payload:
                        self.no_think_param.add(model)
                        async for text in self.stream(messages, model, num_predict):
                            yield text
                        return
                    raise LLMError(f"Ollama ตอบกลับ {r.status_code}: {body[:200]}")
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise LLMError(data["error"])
                    chunk = data.get("response", "") if self.raw else data.get("message", {}).get("content", "")
                    if "�" in chunk:
                        # Ollama itself sometimes streams a broken UTF-8 piece of a Thai
                        # character (httpx decodes split bytes correctly); don't show or speak it
                        log.warning("Ollama sent U+FFFD in %r", chunk)
                        chunk = chunk.replace("�", "")
                    text = think.feed(chunk or "")
                    if text:
                        yield text
                    if data.get("done"):
                        # prompt_eval_count is the WHOLE prompt, cached or not — the time is what
                        # tells a cache hit (~0.65 s) from a miss; ~/.ollama/logs/server.log has
                        # llama.cpp's "cached n_tokens" for the exact split
                        ns = 1e9
                        log.info("ollama: prompt %s tok, prefill %.2fs · gen %s tok %.2fs · load %.2fs",
                                 data.get("prompt_eval_count", 0), data.get("prompt_eval_duration", 0) / ns,
                                 data.get("eval_count", 0), data.get("eval_duration", 0) / ns,
                                 data.get("load_duration", 0) / ns)
                        break
        except httpx.ConnectError as e:
            raise LLMError(f"เชื่อมต่อ Ollama ที่ {self.s.ollama_url} ไม่ได้ — เปิด Ollama อยู่หรือเปล่า?") from e
        if tail := think.flush():
            yield tail


class MockLLM:
    """Fake brain for working on the UI without a model installed."""

    REPLIES = [
        "[calm]รับทราบค่ะ มาสเตอร์ ตอนนี้ฉันทำงานในโหมดทดสอบ (mock) อยู่นะคะ [concern]ยังไม่ได้เชื่อมต่อกับสมองจริงค่ะ",
        "[calm]ประมวลผลแล้วค่ะ ถ้าอยากคุยกับฉันจริงๆ ให้ตั้ง CIEL_LLM=ollama นะคะ [tease]หรือมาสเตอร์ลืมไปแล้วคะ?",
        "[shy]เ-เรื่องแค่นี้ไม่ใช่เรื่องใหญ่หรอกค่ะ [calm]ในโหมดทดสอบ ฉันตอบได้แค่ประโยคที่เตรียมไว้เท่านั้นนะคะ",
    ]
    BY_LANGUAGE = {
        ("ญี่ปุ่น", "japanese", "日本語"): "[calm]了解しました、マスター。今はテストモードで動いています。[shy]べ、別に大したことじゃありませんよ。",
        ("อังกฤษ", "english"): "[calm]Understood, master. I am running in test mode right now. [tease]Did you forget lunch again?",
    }

    ANIME = [
        "[calm]……テストモードです。\n[concern]まだ本物の頭脳には繋がっていません。\n"
        ">> 1 ...โหมดทดสอบค่ะ\n>> 2 ยังไม่ได้เชื่อมต่อกับสมองจริงค่ะ",
        "[shy]な、何ですか……。\n[tease]マスター、またお昼ご飯を忘れましたか？\n"
        ">> 1 อ-อะไรกันคะ...\n>> 2 มาสเตอร์ ลืมกินข้าวเที่ยงอีกแล้วเหรอคะ?",
    ]
    ANIME_EN = "[calm]了解しました。\n[tease]今日も一緒に頑張りましょうね。\n>> 1 Understood, master.\n>> 2 Let's do our best together today."

    async def warmup(self, messages: list[dict], probe: list[dict] | None = None) -> None:
        pass

    async def stream(self, messages: list[dict], model: str | None = None, num_predict: int | None = None) -> AsyncIterator[str]:
        last = messages[-1]["content"].lower() if messages else ""
        if messages and ">> " in messages[0]["content"]:  # persona uses the anime layout
            text = self.ANIME_EN if any(c.isascii() and c.isalpha() for c in last) and not any("฀" <= c <= "๿" for c in last) else random.choice(self.ANIME)
        else:
            text = next((r for keys, r in self.BY_LANGUAGE.items() if any(k in last for k in keys)), None)
            text = text or random.choice(self.REPLIES)
        await asyncio.sleep(0.4)
        for i in range(0, len(text), 3):
            yield text[i:i + 3]
            await asyncio.sleep(0.03)


def create_llm(s: Settings) -> LLM:
    if s.llm == "mock":
        return MockLLM()
    if s.llm == "ollama":
        return OllamaLLM(s)
    raise ValueError(f"Unknown CIEL_LLM: {s.llm!r} (use 'ollama' or 'mock')")
