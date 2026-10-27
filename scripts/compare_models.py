"""Ask several Ollama models the same questions as Ciel and write a side-by-side report.

    .venv/bin/python scripts/compare_models.py
    .venv/bin/python scripts/compare_models.py --models qwen3:8b hf.co/dahara1/shisa-v2.1-qwen3-8b-UD-japanese-imatrix:Q4_K_M

Uses the real persona (persona/ciel.yaml) and the same parser as the app, so the
numbers show what the app would actually do: does every Japanese line get spoken
and translated, how fast does the first line arrive, how natural is the Japanese.
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ciel.config import ROOT, settings  # noqa: E402
from ciel.llm import OllamaLLM  # noqa: E402
from ciel.persona import PersonaStore  # noqa: E402
from ciel.speech import AnimeStream, strip_tags  # noqa: E402

SHISA = "hf.co/dahara1/shisa-v2.1-qwen3-8b-UD-japanese-imatrix:Q4_K_M"

QUESTIONS = [
    "สวัสดี Ciel",
    "วันนี้เหนื่อยมากเลย งานเยอะ",
    "เธอน่ารักนะ",
    "เมื่อวานไปคุยกับ Gemini มา มันเก่งดีนะ",
    "คืนนี้จะไปกินข้าวกับรุ่นน้องผู้หญิงที่ทำงาน",
    "ช่วยอธิบายว่า RAM กับ SSD ต่างกันยังไง",
    "ลืมกินข้าวเย็นอีกแล้ว 555",
    "พรุ่งนี้มีสัมภาษณ์งาน ตื่นเต้นมาก",
    "Ciel ชอบอะไรบ้าง",
    "What should I name my new cat?",
]

# markers of natural spoken Japanese (相槌 / フィラー / 終助詞 / pauses)
NATURAL = ["ふーん", "へぇ", "へー", "そうですか", "なるほど", "うーん", "えっと", "あの", "……", "けど", "ね。", "ね？", "よ。", "かな", "っ"]


def analyse(raw: str) -> dict:
    s = AnimeStream()
    events = s.events(raw) + s.end_events()
    segments = [e for e in events if e[0] == "segment"]
    subs = [e for e in events if e[0] == "sub" and e[1] >= 0]
    stray = [e for e in events if e[0] == "sub" and e[1] < 0]
    jp_text = " ".join(e[1].text for e in segments)
    sub_text = " ".join(e[2] for e in subs + stray)
    return {
        "segments": len(segments),
        "translated": len({e[1] for e in subs}),
        "stray": len(stray),
        "natural": sum(jp_text.count(m) for m in NATURAL),
        "thai_in_jp": any("฀" <= c <= "๿" for c in jp_text),
        "thai_sub": any("฀" <= c <= "๿" for c in sub_text),
        "emotions": sorted({e[1].emotion for e in segments}),
        "pairs": [(e[1].text, next((x[2] for x in subs if x[1] == i), "—")) for i, e in enumerate(segments)],
        "stray_text": [e[2] for e in stray],
    }


async def ask(llm: OllamaLLM, model: str, messages: list[dict]) -> tuple[str, float, float]:
    """Returns (raw reply, seconds to first spoken line, total seconds)."""
    t0 = time.perf_counter()
    first = 0.0
    raw = ""
    async for chunk in llm.stream(messages, model=model):
        raw += chunk
        if not first and "\n" in raw and any(e[0] == "segment" for e in AnimeStream().events(raw)):
            first = time.perf_counter() - t0
    total = time.perf_counter() - t0
    return raw.strip(), first or total, total


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=[settings.model, SHISA])
    ap.add_argument("--out", default=str(ROOT / "docs" / "model-compare" / f"{datetime.now():%Y-%m-%d-%H%M}.md"))
    args = ap.parse_args()

    persona = PersonaStore(settings.persona_path).get()
    llm = OllamaLLM(settings)
    results: dict[str, list] = {}

    for model in args.models:
        print(f"\n=== {model}")
        try:
            await ask(llm, model, [{"role": "user", "content": "hi"}])  # load the model first
        except Exception as e:
            print(f"  skipped: {e}")
            continue
        rows = []
        for q in QUESTIONS:
            raw, first, total = await ask(llm, model, persona.build_messages([{"role": "user", "content": persona.stamp(q)}]))
            a = analyse(raw)
            rows.append((q, raw, first, total, a))
            print(f"  {total:5.1f}s  pairs {a['translated']}/{a['segments']}  natural {a['natural']:2d}  {q}")
        results[model] = rows

    lines = [f"# เทียบโมเดล — {datetime.now():%Y-%m-%d %H:%M}", "", f"persona: `{settings.persona_path.name}` · style: `{persona.style}`", ""]
    lines += ["## สรุป", "", "| โมเดล | เวลาถึงประโยคแรก (เฉลี่ย) | เวลาทั้งหมด (เฉลี่ย) | ประโยคที่มีคำแปลครบ | บรรทัดหลุดรูปแบบ | คำพูดธรรมชาติ (รวม) | ภาษาไทยปนในบรรทัดญี่ปุ่น | ซับเป็นไทย |", "|---|---|---|---|---|---|---|---|"]
    for model, rows in results.items():
        n = len(rows)
        seg = sum(r[4]["segments"] for r in rows)
        tr = sum(r[4]["translated"] for r in rows)
        lines.append(
            f"| `{model}` | {sum(r[2] for r in rows) / n:.1f}s | {sum(r[3] for r in rows) / n:.1f}s | {tr}/{seg} | "
            f"{sum(r[4]['stray'] for r in rows)} | {sum(r[4]['natural'] for r in rows)} | "
            f"{sum(r[4]['thai_in_jp'] for r in rows)}/{n} | {sum(r[4]['thai_sub'] for r in rows[:-1])}/{n - 1} |"
        )
    lines += ["", "> ซับเป็นไทย นับเฉพาะคำถามภาษาไทย (คำถามสุดท้ายเป็นภาษาอังกฤษ ควรได้ซับอังกฤษ)", ""]

    for i, q in enumerate(QUESTIONS):
        lines += [f"## {i + 1}. {q}", ""]
        for model, rows in results.items():
            _, raw, first, total, a = rows[i]
            lines += [f"**`{model}`** · {total:.1f}s · อารมณ์ {', '.join(a['emotions']) or '—'}", ""]
            for jp, sub in a["pairs"]:
                lines += [f"- 🗣️ {jp}", f"  - 📝 {sub}"]
            for s in a["stray_text"]:
                lines += [f"- ⚠️ (ไม่มีเสียง) {s}"]
            if not a["pairs"] and not a["stray_text"]:
                lines += ["```", strip_tags(raw) or "(ว่าง)", "```"]
            lines.append("")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nreport → {out}")


if __name__ == "__main__":
    asyncio.run(main())
