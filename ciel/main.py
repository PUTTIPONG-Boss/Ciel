import asyncio
import logging
import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, updater
from .config import WEB_DIR, settings
from .llm import LLMError, create_llm
from .persona import PersonaStore
from .version import info as version_info

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
log = logging.getLogger("ciel")

# Windows sometimes maps .js to text/plain in the registry, which breaks ES modules
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")

llm = create_llm(settings)
personas = PersonaStore(settings.persona_path)

MAX_INPUT_CHARS = 4000
generating = 0  # replies in progress — the updater waits for this to hit 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(updater.run_forever(lambda: generating == 0)) if settings.auto_update else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Ciel", lifespan=lifespan)


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
        "greeting": persona.greeting,
        "model": settings.model if settings.llm != "mock" else "mock",
        **version_info(),
    }


@app.websocket("/ws")
async def chat(ws: WebSocket):
    global generating
    if not auth.is_authed(ws.cookies.get(auth.COOKIE)):
        await ws.close(code=4401)
        return
    await ws.accept()

    history: list[dict] = []
    persona = personas.get()
    await ws.send_json(hello(persona))

    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")

            if kind == "reset":
                history.clear()
                persona = personas.get()  # pick up persona edits
                await ws.send_json(hello(persona))
                continue

            if kind != "chat":
                continue
            text = str(msg.get("text", "")).strip()[:MAX_INPUT_CHARS]
            if not text:
                continue

            history.append({"role": "user", "content": text})
            del history[: max(0, len(history) - settings.max_history)]
            messages = persona.build_messages(history)

            await ws.send_json({"type": "start"})
            reply = ""
            generating += 1
            try:
                async for delta in llm.stream(messages):
                    reply += delta
                    await ws.send_json({"type": "delta", "text": delta})
            except LLMError as e:
                log.warning("LLM error: %s", e)
                history.pop()
                await ws.send_json({"type": "error", "message": str(e)})
                continue
            finally:
                generating -= 1

            reply = reply.strip()
            history.append({"role": "assistant", "content": reply})
            await ws.send_json({"type": "end", "text": reply})
    except WebSocketDisconnect:
        pass


# Served last so /api and /ws take priority
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
