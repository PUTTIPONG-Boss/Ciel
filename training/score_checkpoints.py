"""Scores every saved LoRA checkpoint by reply format, straight in MLX, so
the best one can be picked without fusing + converting + importing each
(~30 min apiece). Val loss on 10 samples picked the wrong checkpoint before:
it rose after iteration 100 while the format kept improving (2 → 11 → 13
of 24 at 100/300/450, docs/model-compare/2026-11-01-0458-thai-eval.md).

Runs the conversations in training/eval.yaml exactly like the app talks to
a tuned model (short prompt, history rendered without think blocks, the
model's own replies fed back), and checks each reply with the training
data's rules (build_dataset.check_reply).

    ~/ciel-train/bin/python training/score_checkpoints.py training/adapters-lr5e5
    ~/ciel-train/bin/python training/score_checkpoints.py training/adapters-lr5e5 --only 150 300

Needs mlx-lm, pyyaml and httpx in that venv. Run it with Ollama's models
unloaded (16 GB is not enough for both).
"""

import argparse
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))

from build_dataset import check_reply  # noqa: E402
from ciel.config import settings  # noqa: E402
from ciel.llm import render_chatml  # noqa: E402
from ciel.persona import PersonaStore, subtitle_language  # noqa: E402

BASE = "mlx-community/Qwen3-8B-4bit"


def checkpoints(adapter_dir: Path, only: list[int]) -> list[tuple[str, Path]]:
    """(label, weights file), oldest first: 0000150_adapters.safetensors → "150"."""
    found = sorted(adapter_dir.glob("*_adapters.safetensors"))
    out = [(str(int(p.name.split("_")[0])), p) for p in found if p.name.split("_")[0].isdigit()]
    if only:
        out = [(label, p) for label, p in out if int(label) in only]
    return out


def score(model, tokenizer, persona, scenarios, temp: float) -> tuple[int, int, list[str]]:
    from mlx_lm import generate
    from mlx_lm.sample_utils import make_sampler

    sampler = make_sampler(temp=temp)
    ok = total = 0
    notes = []
    now = datetime(2026, 11, 1, 20, 0)
    for sc in scenarios:
        history: list[dict] = []
        for text in sc["turns"]:
            history.append({"role": "user", "content": persona.stamp(text, now)})
            prompt = render_chatml(persona.build_messages(history), think_in_history=False)
            reply = generate(model, tokenizer, prompt=prompt, max_tokens=settings.num_predict, sampler=sampler)
            reply = reply.split("<|im_end|>")[0].strip()
            history.append({"role": "assistant", "content": reply})
            problems = check_reply(reply, subtitle_language(text))
            total += 1
            ok += not problems
            if problems:
                notes.append(f"{sc['name']} / {text}: {'; '.join(problems)}")
            now += timedelta(minutes=1)
    return ok, total, notes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("adapters", type=Path, help="adapter dir with NNNNNNN_adapters.safetensors + adapter_config.json")
    ap.add_argument("--only", type=int, nargs="*", default=[], help="iterations to score (default: all)")
    ap.add_argument("--temp", type=float, default=settings.temperature, help="sampling temperature (default: the app's)")
    args = ap.parse_args()

    from mlx_lm import load

    persona = PersonaStore(settings.persona_path, tuned=True).get()
    scenarios = yaml.safe_load((ROOT / "training" / "eval.yaml").read_text(encoding="utf-8"))
    config = args.adapters / "adapter_config.json"
    if not config.exists():
        sys.exit(f"{config} not found")
    results = []
    for label, weights in checkpoints(args.adapters, args.only):
        # mlx-lm loads "adapters.safetensors" from a directory: give each checkpoint its own
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(config, Path(tmp) / "adapter_config.json")
            shutil.copy(weights, Path(tmp) / "adapters.safetensors")
            t0 = time.time()
            model, tokenizer = load(BASE, adapter_path=tmp)
            ok, total, notes = score(model, tokenizer, persona, scenarios, args.temp)
            del model
        print(f"checkpoint {label}: format {ok}/{total} ({time.time() - t0:.0f}s)", flush=True)
        for n in notes:
            print(f"    {n}")
        results.append({"checkpoint": label, "ok": ok, "total": total, "problems": notes})
    out = args.adapters / "format_scores.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    best = max(results, key=lambda r: r["ok"], default=None)
    if best:
        print(f"best: checkpoint {best['checkpoint']} ({best['ok']}/{best['total']}) → {out}")


if __name__ == "__main__":
    main()
