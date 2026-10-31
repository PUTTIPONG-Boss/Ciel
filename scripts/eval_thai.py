"""Multi-turn Thai comprehension check: runs the conversations in
training/eval.yaml (not in the training data) on one or more models and
writes them side by side, so a fine-tuned model can be compared with the
one Ciel runs now.

    .venv/bin/python scripts/eval_thai.py qwen3:8b ciel-qwen3@tuned

MODEL uses the prompt the app uses today (system prompt + the persona's
examples); MODEL@tuned uses the short prompt a model fine-tuned on
training/ runs with (CIEL_TUNED=true). Talks to Ollama directly, not to
the app: run it while nobody is chatting. Before each model every other
loaded model is unloaded (two 8B models + the rest didn't fit in 16 GB and
the run took 10 h, 2026-10-29-2005-thai-eval.md); the app's model comes
back with its next keep-warm probe.

Every reply is also checked with the training data's format rules
(training/build_dataset.check_reply): a reply the app would show without a
voice or with a stray number counts as broken, whatever it says.
"""

import argparse
import asyncio
import dataclasses
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ciel.config import KEEP_WARM_PAUSE, ROOT, settings  # noqa: E402
from ciel.llm import OllamaLLM  # noqa: E402
from ciel.persona import PersonaStore, subtitle_language  # noqa: E402
from ciel.speech import AnimeStream  # noqa: E402

sys.path.insert(0, str(ROOT / "training"))
from build_dataset import check_reply  # noqa: E402

SCENARIOS = ROOT / "training" / "eval.yaml"


def pairs(raw: str) -> list[tuple[str, str, str]]:
    """(emotion, Japanese line, its subtitle) as the app would show them."""
    s = AnimeStream()
    events = s.events(raw) + s.end_events()
    segments = [e[1] for e in events if e[0] == "segment"]
    subs = {e[1]: e[2] for e in events if e[0] == "sub" and e[1] >= 0}
    out = [(seg.emotion, seg.text, subs.get(i, "—")) for i, seg in enumerate(segments)]
    return out + [("", "—", e[2]) for e in events if e[0] == "sub" and e[1] < 0]


async def run(spec: str, scenarios: list[dict]) -> list[list[tuple[str, float]]]:
    model, _, mode = spec.partition("@")
    # don't keep an extra model pinned in RAM next to the one the app uses
    llm = OllamaLLM(dataclasses.replace(settings, model=model, keep_alive="5m", tuned=mode == "tuned"))
    loaded = (await llm.client.get("/api/ps")).json().get("models", [])
    for m in loaded:
        if m["name"] not in (model, f"{model}:latest"):
            print(f"unloading {m['name']}", flush=True)
            await llm.client.post("/api/generate", json={"model": m["name"], "keep_alive": 0})
    persona = PersonaStore(settings.persona_path, tuned=mode == "tuned").get()
    now = datetime.now().replace(second=0, microsecond=0)
    results = []
    for sc in scenarios:
        history: list[dict] = []
        replies = []
        for text in sc["turns"]:
            history.append({"role": "user", "content": persona.stamp(text, now)})
            t0, raw = time.perf_counter(), ""
            async for delta in llm.stream(persona.build_messages(history)):
                raw += delta
            history.append({"role": "assistant", "content": raw})
            replies.append((raw, time.perf_counter() - t0))
            now += timedelta(minutes=1)
        results.append(replies)
        print(f"{spec}: {sc['name']} done", flush=True)
    return results


def report(specs: list[str], scenarios: list[dict], results: dict) -> str:
    out = [f"# ทดสอบความเข้าใจภาษาไทยหลายรอบ — {datetime.now():%Y-%m-%d %H:%M}", ""]
    out.append("โมเดล: " + " · ".join(f"`{s}`" for s in specs) + "  (`@tuned` = prompt สั้นแบบโมเดลที่เทรนแล้ว ไม่มีตัวอย่าง)")
    out.append("")
    for i, sc in enumerate(scenarios):
        out += [f"## {i + 1}. {sc['name']}", "", f"ควรเป็น: {sc.get('check', '—')}", ""]
        for t, text in enumerate(sc["turns"]):
            out.append(f"**มาสเตอร์:** {text}")
            out.append("")
            for spec in specs:
                raw, secs = results[spec][i][t]
                problems = check_reply(raw.strip(), subtitle_language(text))
                out.append(f"- `{spec}` ({secs:.1f}s){' ⚠️ ' + ' · '.join(problems) if problems else ''}")
                for emotion, jp, sub in pairs(raw):
                    out.append(f"  - `[{emotion}]` {jp} → {sub}")
            out.append("")
    out += ["## รูปแบบคำตอบ (ตรวจอัตโนมัติด้วยกฎของข้อมูลเทรน)", "", "| โมเดล | รูปแบบถูก |", "|---|---|"]
    for spec in specs:
        replies = [(raw, sc["turns"][t]) for sc, rs in zip(scenarios, results[spec]) for t, (raw, _) in enumerate(rs)]
        ok = sum(not check_reply(raw.strip(), subtitle_language(text)) for raw, text in replies)
        out.append(f"| `{spec}` | {ok}/{len(replies)} |")
    out += ["", "## สรุป (ให้คนอ่านกรอก)", "", "| ชุด | " + " | ".join(specs) + " |", "|---|" + "---|" * len(specs)]
    out += [f"| {i + 1}. {sc['name']} |" + " |" * len(specs) for i, sc in enumerate(scenarios)]
    return "\n".join(out) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="+", help="MODEL or MODEL@tuned")
    ap.add_argument("--out", type=Path, help="report path (default docs/model-compare/<date>-thai-eval.md)")
    args = ap.parse_args()
    scenarios = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))
    # stop the app's keep-warm from loading its model back mid-test (expires in 4 h if we die)
    KEEP_WARM_PAUSE.parent.mkdir(exist_ok=True)
    KEEP_WARM_PAUSE.write_text(str(time.time() + 4 * 3600))
    try:
        results = {spec: await run(spec, scenarios) for spec in args.models}  # one model at a time
    finally:
        KEEP_WARM_PAUSE.unlink(missing_ok=True)
    out = args.out or ROOT / "docs" / "model-compare" / f"{datetime.now():%Y-%m-%d-%H%M}-thai-eval.md"
    out.write_text(report(args.models, scenarios, results), encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    asyncio.run(main())
