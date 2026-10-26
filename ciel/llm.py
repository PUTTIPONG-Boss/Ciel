"""Ciel's brain. Every backend streams plain text chunks, so swapping models
(or moving to a bigger machine later) never touches the rest of the app."""

import asyncio
import json
import random
from typing import AsyncIterator, Protocol

import httpx

from .config import Settings


class LLMError(Exception):
    pass


class LLM(Protocol):
    def stream(self, messages: list[dict]) -> AsyncIterator[str]: ...


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


class OllamaLLM:
    def __init__(self, s: Settings):
        self.s = s
        self.client = httpx.AsyncClient(base_url=s.ollama_url, timeout=httpx.Timeout(300, connect=5))

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        payload = {
            "model": self.s.model,
            "messages": messages,
            "stream": True,
            "think": self.s.think,
            "options": {"temperature": self.s.temperature, "num_ctx": self.s.num_ctx},
        }
        think = ThinkFilter()
        try:
            async with self.client.stream("POST", "/api/chat", json=payload) as r:
                if r.status_code != 200:
                    body = (await r.aread()).decode(errors="ignore")
                    raise LLMError(f"Ollama ตอบกลับ {r.status_code}: {body[:200]}")
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise LLMError(data["error"])
                    text = think.feed(data.get("message", {}).get("content", ""))
                    if text:
                        yield text
                    if data.get("done"):
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

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        last = messages[-1]["content"].lower() if messages else ""
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
