import logging
import mimetypes

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth
from .config import WEB_DIR, settings
from .llm import LLMError, create_llm
from .persona import PersonaStore

log = logging.getLogger("ciel")

# Windows sometimes maps .js to text/plain in the registry, which breaks ES modules
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")

app = FastAPI(title="Ciel")
llm = create_llm(settings)
personas = PersonaStore(settings.persona_path)

MAX_INPUT_CHARS = 4000


class LoginBody(BaseModel):
    password: str


@app.get("/api/health")
async def health():
    return {"ok": True, "llm": settings.llm, "model": settings.model}


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


@app.websocket("/ws")
async def chat(ws: WebSocket):
    if not auth.is_authed(ws.cookies.get(auth.COOKIE)):
        await ws.close(code=4401)
        return
    await ws.accept()

    history: list[dict] = []
    persona = personas.get()
    await ws.send_json({"type": "hello", "name": persona.name, "greeting": persona.greeting})

    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")

            if kind == "reset":
                history.clear()
                persona = personas.get()  # pick up persona edits
                await ws.send_json({"type": "hello", "name": persona.name, "greeting": persona.greeting})
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
            try:
                async for delta in llm.stream(messages):
                    reply += delta
                    await ws.send_json({"type": "delta", "text": delta})
            except LLMError as e:
                log.warning("LLM error: %s", e)
                history.pop()
                await ws.send_json({"type": "error", "message": str(e)})
                continue

            reply = reply.strip()
            history.append({"role": "assistant", "content": reply})
            await ws.send_json({"type": "end", "text": reply})
    except WebSocketDisconnect:
        pass


# Served last so /api and /ws take priority
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
