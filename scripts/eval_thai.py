"""Multi-turn Thai comprehension check: runs the conversations in
training/eval.yaml (not in the training data) on one or more models and
writes them side by side, so a fine-tuned model can be compared with the
one Ciel runs now.

    .venv/bin/python scripts/eval_thai.py qwen3:8b ciel-qwen3@plain

MODEL uses the prompt the app uses today (system prompt + the persona's
examples); MODEL@plain leaves the examples out, the way a model fine-tuned
on training/ runs (CIEL_FEW_SHOT=false). Talks to Ollama directly, not to
the app: run it while nobody is chatting (models swap in and out of RAM).
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

from ciel.config import ROOT, settings  # noqa: E402
from ciel.llm import OllamaLLM  # noqa: E402
from ciel.persona import PersonaStore  # noqa: E402
from ciel.speech import AnimeStream  # noqa: E402

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
    llm = OllamaLLM(dataclasses.replace(settings, model=model, keep_alive="5m"))
    persona = PersonaStore(settings.persona_path, few_shot=mode != "plain").get()
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
    out.append("โมเดล: " + " · ".join(f"`{s}`" for s in specs) + "  (`@plain` = ไม่มีตัวอย่างใน prompt)")
    out.append("")
    for i, sc in enumerate(scenarios):
        out += [f"## {i + 1}. {sc['name']}", "", f"ควรเป็น: {sc.get('check', '—')}", ""]
        for t, text in enumerate(sc["turns"]):
            out.append(f"**มาสเตอร์:** {text}")
            out.append("")
            for spec in specs:
                raw, secs = results[spec][i][t]
                out.append(f"- `{spec}` ({secs:.1f}s)")
                for emotion, jp, sub in pairs(raw):
                    out.append(f"  - `[{emotion}]` {jp} → {sub}")
            out.append("")
    out += ["## สรุป (ให้คนอ่านกรอก)", "", "| ชุด | " + " | ".join(specs) + " |", "|---|" + "---|" * len(specs)]
    out += [f"| {i + 1}. {sc['name']} |" + " |" * len(specs) for i, sc in enumerate(scenarios)]
    return "\n".join(out) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="+", help="MODEL or MODEL@plain")
    ap.add_argument("--out", type=Path, help="report path (default docs/model-compare/<date>-thai-eval.md)")
    args = ap.parse_args()
    scenarios = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))
    results = {spec: await run(spec, scenarios) for spec in args.models}  # one model at a time
    out = args.out or ROOT / "docs" / "model-compare" / f"{datetime.now():%Y-%m-%d-%H%M}-thai-eval.md"
    out.write_text(report(args.models, scenarios, results), encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    asyncio.run(main())
