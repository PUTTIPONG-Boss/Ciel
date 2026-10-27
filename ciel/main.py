import asyncio
import logging
import mimetypes
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, tts, updater
from .config import WEB_DIR, settings
from .llm import LLMError, create_llm
from .persona import PersonaStore
from .speech import AnimeStream, SpeechStream, strip_tags
from .version import info as version_info
from .voice_api import create_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
log = logging.getLogger("ciel")

# Windows sometimes maps .js to text/plain in the registry, which breaks ES modules
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("font/otf", ".otf")

llm = create_llm(settings)
personas = PersonaStore(settings.persona_path)

MAX_INPUT_CHARS = 4000
generating = 0  # replies in progress — the updater waits for this to hit 0
warmed = None  # the persona whose prompt is in Ollama's cache
warming: asyncio.Task | None = None


def warm_up(persona) -> None:
    """Put this persona's prompt into Ollama's cache. Run at start and again
    whenever persona/*.yaml changes (no restart for that), so the first message
    after an edit doesn't re-read the whole ~5,000-token prompt."""
    global warmed, warming
    if persona is warmed:
        return
    warmed = persona
    probe = [{"role": "user", "content": persona.stamp("สวัสดี")}]
    warming = asyncio.create_task(llm.warmup(persona.build_messages([]), persona.build_messages(probe)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(updater.run_forever(lambda: generating == 0)) if settings.auto_update else None
    # load the model + cache the persona prompt now, not when the first message arrives
    warm_up(personas.get())
    yield
    if warming:
        warming.cancel()
    if task:
        task.cancel()


app = FastAPI(title="Ciel", lifespan=lifespan)
app.include_router(create_router(personas))


class LoginBody(BaseModel):
    password: str


@app.get("/api/health")
async def health():
    return {"ok": True, "llm": settings.llm, "model": settings.model, **version_info()}


@app.get("/api/me")
async def me(request: Request):
    persona = personas.get()
    return {
        "authed": auth.is_authed(request.cookies.get(auth.COOKIE)),
        "auth_required": auth.enabled(),
        "name": persona.name,
    }


@app.post("/api/login")
async def login(body: LoginBody, request: Request, response: Response):
    if not auth.enabled():
        return {"ok": True}
    if not auth.check_password(body.password):
        return JSONResponse({"ok": False, "error": "รหัสผ่านไม่ถูกต้อง"}, status_code=401)
    response.set_cookie(
        auth.COOKIE,
        auth.session_token(),
        max_age=60 * 60 * 24 * 90,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )
    return {"ok": True}


def hello(persona) -> dict:
    return {
        "type": "hello",
        "name": persona.name,
        "user_name": persona.user_name,
        "greeting": strip_tags(persona.greeting),
        "greeting_ja": persona.greeting_ja if persona.style == "anime" else "",
        "style": persona.style,
        "model": settings.model if settings.llm != "mock" else "mock",
        "tts": tts.enabled(),
        **version_info(),
    }


@app.websocket("/ws")
async def chat(ws: WebSocket):
    global generating
    if not auth.is_authed(ws.cookies.get(auth.COOKIE)):
        await ws.close(code=4401)
        return
    await ws.accept()

    channel = Channel(ws)
    history: list[dict] = []
    persona = personas.get()
    warm_up(persona)  # no-op unless the YAML changed since the last warm-up
    await channel.send_json(hello(persona))

    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")

            if kind == "reset":
                history.clear()
                persona = personas.get()  # pick up persona edits
                warm_up(persona)
                await channel.send_json(hello(persona))
                continue

            if kind != "chat":
                continue
            text = str(msg.get("text", "")).strip()[:MAX_INPUT_CHARS]
            if not text:
                continue

            history.append({"role": "user", "content": persona.stamp(text)})  # stamped once, see Persona.stamp
            del history[: max(0, len(history) - settings.max_history)]
            speak = bool(msg.get("speak")) and tts.enabled()

            generating += 1
            try:
                reply = await reply_to(channel, persona, persona.build_messages(history), speak)
            except LLMError as e:
                log.warning("LLM error: %s", e)
                history.pop()
                await channel.send_json({"type": "error", "message": str(e)})
                continue
            finally:
                generating -= 1

            # keep the [tags] in history so Ciel keeps using them
            history.append({"role": "assistant", "content": reply})
    except WebSocketDisconnect:
        pass


class Channel:
    """Serialises sends: text deltas and audio come from different tasks."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.lock = asyncio.Lock()

    async def send_json(self, data: dict) -> None:
        async with self.lock:
            await self.ws.send_json(data)

    async def send_bytes(self, data: bytes) -> None:
        async with self.lock:
            await self.ws.send_bytes(data)


async def reply_to(channel: Channel, persona, messages: list[dict], speak: bool) -> str:
    """Streams one reply. Text goes out as `delta`s; each finished sentence goes
    out as a `segment` (language + emotion, drives the circle) and, when
    speaking, as a binary frame: 4-byte big-endian seq + MP3 bytes, in order.

    In anime style deltas carry kind "jp" | "sub", lines close with `line_end`,
    and each Japanese segment's translation follows as `sub` (same seq)."""
    anime = persona.style == "anime"
    stream = AnimeStream() if anime else SpeechStream()
    voice_cfg = tts.load_config(persona.voice) if speak else None
    audio_jobs: asyncio.Queue = asyncio.Queue()
    limit = asyncio.Semaphore(2)  # don't hammer the TTS service
    seq = 0
    # when each stage was first reached, in seconds since the reply started (logged at the end)
    t0 = time.perf_counter()
    marks: dict[str, float] = {}

    def mark(name: str) -> None:
        marks.setdefault(name, time.perf_counter() - t0)

    async def synth(seg) -> bytes:
        async with limit:
            return await tts.synthesize(seg.text, **tts.prosody(voice_cfg, seg.lang, seg.emotion))

    async def send_audio_in_order() -> None:
        while (job := await audio_jobs.get()) is not None:
            n, task = job
            try:
                await channel.send_bytes(n.to_bytes(4, "big") + await task)
                mark("first audio")
            except tts.TTSError as e:
                log.warning("%s", e)
                await channel.send_json({"type": "audio_error", "seq": n})
        await channel.send_json({"type": "audio_end"})

    async def emit(events: list[tuple]) -> None:
        nonlocal seq
        pending = None  # merge consecutive deltas of the same kind into one message
        for ev in events + [("flush",)]:
            if ev[0] == "delta":
                if pending and pending["kind"] == ev[1]:
                    pending["text"] += ev[2]
                    continue
                if pending:
                    await send_delta(pending)
                pending = {"kind": ev[1], "text": ev[2]}
                continue
            if pending:
                await send_delta(pending)
                pending = None
            if ev[0] == "segment":
                seg = ev[1]
                gain = tts.gain(tts.prosody(voice_cfg, seg.lang, seg.emotion)["volume"]) if speak else 1
                mark("first sentence")
                await channel.send_json({"type": "segment", "seq": seq, "lang": seg.lang, "emotion": seg.emotion, "text": seg.text, "audio": speak, "gain": gain})
                if speak:
                    await audio_jobs.put((seq, asyncio.create_task(synth(seg))))
                seq += 1
            elif ev[0] == "sub":
                await channel.send_json({"type": "sub", "seq": ev[1], "text": ev[2]})
            elif ev[0] == "line_end":
                await channel.send_json({"type": "line_end", "kind": ev[1]})

    async def send_delta(d: dict) -> None:
        msg = {"type": "delta", "text": d["text"]}
        if d["kind"]:
            msg["kind"] = d["kind"]
        await channel.send_json(msg)

    sender = asyncio.create_task(send_audio_in_order()) if speak else None
    await channel.send_json({"type": "start", "speak": speak, "style": persona.style})
    raw = ""
    try:
        async for delta in llm.stream(messages):
            mark("first token")
            raw += delta
            await emit(stream.events(delta))
        await emit(stream.end_events())
        await channel.send_json({"type": "end", "text": strip_tags(raw), "structured": anime})
        mark("text done")
    finally:
        if sender:
            await audio_jobs.put(None)
            await sender
        mark("audio done")
        log.info("reply timing: %s", " · ".join(f"{k} {v:.2f}s" for k, v in marks.items()))
    # unstripped: the next prompt must repeat this reply exactly as generated (prompt cache)
    return raw


# Served last so /api and /ws take priority
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
