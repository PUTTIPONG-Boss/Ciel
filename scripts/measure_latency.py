"""Measure how fast Ciel answers through the real app (WebSocket → LLM → TTS),
the way the phone experiences it. Run it on the server:

    .venv/bin/python scripts/measure_latency.py            # ~12 min, 65 s between messages
    .venv/bin/python scripts/measure_latency.py --gap 5    # quick run

Logs in with CIEL_PASSWORD from .env (never printed), asks the questions in
one conversation, and writes docs/model-compare/<date>-latency.md.

The gap matters: before v0.3.1 a message more than a minute after the last one
re-read the whole ~3,000-token prompt, so the default gap is just over a minute.
"""

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ciel.config import ROOT, settings  # noqa: E402

QUESTIONS = [
    "สวัสดี Ciel",
    "วันนี้เหนื่อยมากเลย งานเยอะ",
    "เธอน่ารักนะ",
    "เมื่อวานไปคุยกับ Gemini มา มันเก่งดีนะ",
    "ช่วยอธิบายว่า RAM กับ SSD ต่างกันยังไง",
    "ลืมกินข้าวเย็นอีกแล้ว",
    "พรุ่งนี้มีสัมภาษณ์งาน ตื่นเต้นมาก",
    "What should I name my new cat?",
]


def login(base: str) -> str:
    if not settings.password:
        return ""
    r = httpx.post(f"{base}/api/login", json={"password": settings.password})
    r.raise_for_status()
    return f"ciel_session={r.cookies['ciel_session']}"


def ask(ws, text: str) -> dict:
    t0 = time.perf_counter()
    at = lambda: time.perf_counter() - t0  # noqa: E731
    m = {"q": text, "first_text": None, "first_line": None, "first_audio": None, "text_done": None, "audio_done": None,
         "segments": [], "subs": {}, "audio_errors": 0, "error": None, "audio_at": {}, "audio_bytes": {}}
    ws.send(json.dumps({"type": "chat", "text": text, "speak": True}))
    while True:
        raw = ws.recv(timeout=180)
        if isinstance(raw, bytes):
            m["first_audio"] = m["first_audio"] or at()
            seq = int.from_bytes(raw[:4], "big")
            m["audio_at"][seq] = at()
            m["audio_bytes"][seq] = len(raw) - 4
            continue
        msg = json.loads(raw)
        kind = msg["type"]
        if kind == "delta":
            m["first_text"] = m["first_text"] or at()
        elif kind == "segment":
            m["first_line"] = m["first_line"] or at()
            m["segments"].append((msg["emotion"], msg["text"]))
        elif kind == "sub":
            m["subs"][msg["seq"]] = msg["text"]
        elif kind == "audio_error":
            m["audio_errors"] += 1
        elif kind == "end":
            m["text_done"] = at()
        elif kind == "error":
            m["error"] = msg["message"]
            return m
        elif kind == "audio_end":
            m["audio_done"] = at()
            return m


TARGET = 4.0  # seconds until the first real (content) sentence is heard


ACK_WORDS = {"はい", "あ", "え", "ん", "うん", "えっと", "あの", "うーん", "へぇ", "ふーん", "ふむ", "了解", "了解です"}


def is_ack(text: str) -> bool:
    """A bare acknowledgement line ("……はい。") with no real content. Since
    v0.3.3 the model shouldn't write these (the browser plays one instead)."""
    return re.sub(r"[…。、？！?!\s]", "", text) in ACK_WORDS


def content_audio(r: dict) -> float | None:
    """When the first content sentence's audio arrived (skipping an opening ack line)."""
    seq = 1 if len(r["segments"]) > 1 and is_ack(r["segments"][0][1]) else 0
    return r["audio_at"].get(seq)


MP3_BYTES_PER_SEC = 6000  # edge-tts sends 48 kbit/s MP3


def playback(r: dict) -> tuple[float | None, float]:
    """Simulate the phone's player: a sentence starts once its audio has
    arrived and the one before it has finished. Returns (when the last
    sentence finishes, total silence between sentences)."""
    end, silence = None, 0.0
    for seq in sorted(r["audio_at"]):
        start = r["audio_at"][seq] if end is None else max(r["audio_at"][seq], end)
        if end is not None:
            silence += start - end
        end = start + r["audio_bytes"][seq] / MP3_BYTES_PER_SEC
    return end, silence


def stats(values: list[float | None]) -> str:
    v = [x for x in values if x is not None]
    if not v:
        return "—"
    return f"{statistics.mean(v):.1f}s (median {statistics.median(v):.1f}s, max {max(v):.1f}s)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=f"http://127.0.0.1:{settings.port}")
    ap.add_argument("--gap", type=float, default=65, help="seconds between messages")
    ap.add_argument("--out", default=str(ROOT / "docs" / "model-compare" / f"{datetime.now():%Y-%m-%d-%H%M}-latency.md"))
    args = ap.parse_args()

    health = httpx.get(f"{args.base}/api/health").json()
    cookie = login(args.base)
    ws_url = args.base.replace("http", "ws", 1) + "/ws"
    results = []
    with connect(ws_url, additional_headers={"Cookie": cookie} if cookie else None, open_timeout=10) as ws:
        hello = json.loads(ws.recv())
        if hello.get("style") != "anime":
            print("note: persona style is", hello.get("style"))
        ws.send(json.dumps({"type": "reset"}))
        ws.recv()
        for i, q in enumerate(QUESTIONS):
            if i:
                time.sleep(args.gap)
            r = ask(ws, q)
            results.append(r)
            first = " / ".join(t for _, t in r["segments"][:2]) or "—"
            c = content_audio(r)
            mark = "✅" if c is not None and c <= TARGET else "❌"
            done, silence = playback(r)
            print(f"{mark} {c or 0:4.1f}s content voice · {silence:3.1f}s silent between · {done or 0:4.1f}s spoken · {r['text_done'] or 0:4.1f}s text · {q}  →  {first}")

    ok = [r for r in results if not r["error"]]
    first_lines = [r["segments"][0][1] for r in ok if r["segments"]]
    short_first = sum(is_ack(t) for t in first_lines)
    content = [content_audio(r) for r in ok]
    passed = sum(c is not None and c <= TARGET for c in content)
    translated = sum(len(r["subs"]) for r in ok)
    # the opening ack line has no translation by design, so don't count it
    segs = sum(len(r["segments"]) - (1 if r["segments"] and is_ack(r["segments"][0][1]) else 0) for r in ok)

    lines = [
        f"# เวลาตอบของ Ciel ในแอปจริง — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"v{health.get('version')} ({health.get('commit')}) · `{health.get('model')}` · ห่างกันข้อความละ {args.gap:.0f} วินาที · {len(ok)}/{len(results)} ข้อสำเร็จ",
        "",
        "วัดจากฝั่ง client ผ่าน WebSocket แบบเดียวกับมือถือ (ไม่รวมเสียงรับคำ ん。/はい。 ที่เบราว์เซอร์เล่นเองภายใน ~0.1 วินาที)",
        "",
        "## ค่าเฉลี่ย",
        "",
        "| ช่วง | ค่าเฉลี่ย |",
        "|---|---|",
        f"| ตัวอักษรแรกขึ้นจอ | {stats([r['first_text'] for r in ok])} |",
        f"| เสียงบรรทัดแรก | {stats([r['first_audio'] for r in ok])} |",
        f"| **เสียงประโยคเนื้อหาแรก** (เป้า ≤ {TARGET:.0f}s) | **{stats(content)}** |",
        f"| ข้อความครบ | {stats([r['text_done'] for r in ok])} |",
        f"| เสียงไฟล์สุดท้ายมาถึง | {stats([r['audio_done'] for r in ok])} |",
        f"| **พูดจบจริง** (จำลองการเล่น) | {stats([playback(r)[0] for r in ok])} |",
        f"| **เงียบรวมระหว่างประโยค** | {stats([playback(r)[1] for r in ok])} |",
        "",
        f"- **ผ่านเป้า ≤ {TARGET:.0f} วินาที: {passed}/{len(ok)} ข้อ**",
        f"- บรรทัดแรกเป็นคำรับคำเปล่าๆ (ไม่ควรมีแล้ว): {short_first}/{len(first_lines)}",
        f"- ความยาวบรรทัดแรก (ตัวอักษร): เฉลี่ย {statistics.mean([len(t) for t in first_lines]) if first_lines else 0:.1f}",
        f"- ประโยคเนื้อหาที่มีคำแปล: {translated}/{segs} · เสียงสร้างไม่สำเร็จ: {sum(r['audio_errors'] for r in ok)}",
        "",
        "## รายข้อ",
        "",
        "| คำถาม | เสียงเนื้อหาแรก | เสียงแรก | ข้อความครบ | พูดจบ | เงียบระหว่างประโยค | สองบรรทัดแรก |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r["error"]:
            lines.append(f"| {r['q']} | ❌ {r['error']} | | | | | |")
            continue
        first = " / ".join(t for _, t in r["segments"][:2]) or "—"
        c = content_audio(r)
        mark = "✅" if c is not None and c <= TARGET else "❌"
        done, silence = playback(r)
        lines.append(f"| {r['q']} | {mark} {c or 0:.1f}s | {r['first_audio'] or 0:.1f}s | {r['text_done'] or 0:.1f}s | {done or 0:.1f}s | {silence:.1f}s | {first} |")
    lines += ["", "## คำตอบเต็ม", ""]
    for r in ok:
        lines += [f"**{r['q']}**", ""]
        for i, (emo, jp) in enumerate(r["segments"]):
            lines += [f"- `[{emo}]` {jp}", f"  - {r['subs'].get(i, '—')}"]
        lines.append("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nreport → {out}")


if __name__ == "__main__":
    main()
