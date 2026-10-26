"""HTTP endpoints for the Voice Lab page."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from . import auth, tts
from .persona import PersonaStore
from .speech import SpeechStream

SAMPLES = {
    "th": "[calm]รับทราบค่ะ มาสเตอร์ วิเคราะห์เสร็จแล้วนะคะ [shy]เ-เรื่องแค่นี้ ไม่ใช่เรื่องใหญ่หรอกค่ะ",
    "ja": "[calm]了解しました、マスター。分析が完了しました。[shy]べ、別に大したことじゃありませんよ。",
    "en": "[calm]Understood, master. Analysis complete. [tease]Did you forget lunch again?",
}


def require_auth(request: Request) -> None:
    if not auth.is_authed(request.cookies.get(auth.COOKIE)):
        raise HTTPException(401, "login required")


class PreviewBody(BaseModel):
    text: str
    lang: str
    emotion: str = "calm"
    config: dict | None = None  # unsaved settings from the lab


class SaveBody(BaseModel):
    config: dict


def create_router(personas: PersonaStore) -> APIRouter:
    router = APIRouter(prefix="/api/voice", dependencies=[Depends(require_auth)])

    @router.get("")
    async def get_voice():
        persona = personas.get()
        return {
            "enabled": tts.enabled(),
            "langs": tts.LANGS,
            "emotions": tts.EMOTIONS,
            "config": tts.load_config(persona.voice),
            "defaults": tts.load_config(persona.voice, with_override=False),
            "overridden": tts.OVERRIDE_PATH.exists(),
            "samples": SAMPLES,
        }

    @router.get("/voices")
    async def voices():
        try:
            return await tts.list_voices()
        except Exception as e:
            raise HTTPException(502, f"โหลดรายชื่อเสียงไม่ได้: {e}")

    @router.post("/preview")
    async def preview(body: PreviewBody):
        if body.lang not in tts.LANGS:
            raise HTTPException(400, "unknown language")
        cfg = tts.load_config(personas.get().voice)
        if body.config:
            cfg = tts._merge(cfg, body.config)
        # run the sample through the same splitter as real replies, so [tags] work here too
        stream = SpeechStream()
        stream.emotion = body.emotion
        segments = stream.feed(body.text[:500])[1] + stream.flush()[1]
        if not segments:
            raise HTTPException(400, "nothing to say")
        try:
            # MP3 frames concatenate cleanly, so one response can hold every segment
            audio = b"".join([await tts.synthesize(s.text, **tts.prosody(cfg, s.lang, s.emotion)) for s in segments])
        except tts.TTSError as e:
            raise HTTPException(502, str(e))
        volume = tts.prosody(cfg, segments[0].lang, segments[0].emotion)["volume"]
        return Response(audio, media_type="audio/mpeg", headers={"X-Ciel-Gain": str(tts.gain(volume))})

    @router.put("")
    async def save(body: SaveBody):
        cfg = tts._merge(tts.load_config(personas.get().voice), body.config)
        tts.save_override(cfg)
        return {"ok": True}

    @router.delete("")
    async def reset():
        tts.clear_override()
        return {"ok": True}

    return router
