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
         "segments": [], "subs": {}, "audio_errors": 0, "error": None}
    ws.send(json.dumps({"type": "chat", "text": text, "speak": True}))
    while True:
        raw = ws.recv(timeout=180)
        if isinstance(raw, bytes):
            m["first_audio"] = m["first_audio"] or at()
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
            first = r["segments"][0][1] if r["segments"] else "—"
            print(f"{r['first_audio'] or 0:5.1f}s first audio · {r['text_done'] or 0:5.1f}s text · {r['audio_done'] or 0:5.1f}s all · {q}  →  {first}")

    ok = [r for r in results if not r["error"]]
    first_lines = [r["segments"][0][1] for r in ok if r["segments"]]
    short_first = sum(len(t) <= 10 for t in first_lines)
    translated = sum(len(r["subs"]) for r in ok)
    segs = sum(len(r["segments"]) for r in ok)

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
        f"| ประโยคญี่ปุ่นแรกเสร็จ | {stats([r['first_line'] for r in ok])} |",
        f"| **เสียงประโยคแรกมาถึง** | **{stats([r['first_audio'] for r in ok])}** |",
        f"| ข้อความครบ | {stats([r['text_done'] for r in ok])} |",
        f"| เสียงครบทุกประโยค | {stats([r['audio_done'] for r in ok])} |",
        "",
        f"- บรรทัดแรกเป็นคำรับคำสั้น (≤ 10 ตัวอักษร): {short_first}/{len(first_lines)}",
        f"- ประโยคที่มีคำแปล: {translated}/{segs} · เสียงสร้างไม่สำเร็จ: {sum(r['audio_errors'] for r in ok)}",
        "",
        "## รายข้อ",
        "",
        "| คำถาม | เสียงแรก | ข้อความครบ | เสียงครบ | ประโยคแรก |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        if r["error"]:
            lines.append(f"| {r['q']} | ❌ {r['error']} | | | |")
            continue
        first = r["segments"][0][1] if r["segments"] else "—"
        lines.append(f"| {r['q']} | {r['first_audio'] or 0:.1f}s | {r['text_done'] or 0:.1f}s | {r['audio_done'] or 0:.1f}s | {first} |")
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
