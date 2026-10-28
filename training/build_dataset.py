"""Builds the LoRA training set from training/dialogs/*.yaml (+ the persona's
examples) in mlx-lm's chat format, after checking every reply against the
same parser the app uses (speech.AnimeStream).

Every sample is exactly what the app sends: the system prompt WITHOUT the
examples (a fine-tuned model runs with CIEL_FEW_SHOT=false), user messages
stamped "[YYYY-MM-DD Day HH:MM · sub: Thai]", and the history so far. Each
reply of a dialog becomes one sample (earlier turns are context, only the
last reply is trained: mlx-lm --mask-prompt).

    python training/build_dataset.py            # → training/data/{train,valid}.jsonl
    python training/build_dataset.py --check    # only check the dialogs
"""

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ciel.persona import PersonaStore, subtitle_language  # noqa: E402
from ciel.speech import TAG, AnimeStream, has_japanese  # noqa: E402

DIALOGS = ROOT / "training" / "dialogs"
OUT = ROOT / "training" / "data"
FIRST_LINE_MAX = 16  # the persona asks for ~12; a little slack, longer is an error


def check_reply(reply: str, sub_lang: str) -> list[str]:
    """Problems with one reply, [] if the app would show and speak it right."""
    problems = []
    lines = [l for l in reply.split("\n") if l.strip()]
    if not lines or not TAG.match(lines[0]):
        problems.append("first line has no emotion tag")
    stream = AnimeStream()
    events = stream.events(reply) + stream.end_events()
    spoken = [e[1].text for e in events if e[0] == "segment"]
    subs = {e[1]: e[2] for e in events if e[0] == "sub"}
    jp_lines = [l for l in lines if not l.lstrip().startswith(">>")]
    if len(spoken) != len(jp_lines):
        problems.append(f"{len(jp_lines)} Japanese lines but the app speaks {len(spoken)} (untagged line starting with Latin?)")
    if not 1 <= len(spoken) <= 3:
        problems.append(f"{len(spoken)} Japanese lines (1-3 allowed)")
    for n in range(len(spoken)):
        if n not in subs:
            problems.append(f"Japanese line {n + 1} has no '>> {n + 1}' translation")
    if -1 in subs:
        problems.append("a translation matches no Japanese line")
    subs_lines = [l for l in lines if l.lstrip().startswith(">>")]
    for i, l in enumerate(subs_lines, 1):
        if not l.lstrip()[2:].lstrip().startswith(str(i)):
            problems.append(f"translation {i} is not numbered '>> {i}'")
    if spoken:
        first = TAG.sub("", lines[0]).strip()
        if len(first) > FIRST_LINE_MAX:
            problems.append(f"first line {len(first)} chars (max {FIRST_LINE_MAX}): {first}")
    for text in subs.values():
        thai = any("฀" <= c <= "๿" for c in text)
        if has_japanese(text):
            problems.append(f"Japanese in a translation: {text}")
        if sub_lang == "English" and thai:
            problems.append(f"Thai in an English translation: {text}")
        if sub_lang == "Thai" and not thai:
            problems.append(f"translation without Thai: {text}")
    return problems


def load_dialogs(persona) -> list[dict]:
    dialogs = []
    for path in sorted(DIALOGS.glob("*.yaml")):
        for i, d in enumerate(yaml.safe_load(path.read_text(encoding="utf-8")) or []):
            dialogs.append({"source": f"{path.name}#{i + 1}", "turns": d["turns"]})
    # the persona's single-turn examples too: they are the style the prompt used to show
    for i, ex in enumerate(persona.examples):
        dialogs.append({"source": f"persona example #{i + 1}", "turns": [{"u": ex["user"], "c": ex["ciel"]}]})
    return dialogs


def parse_at(at: str, default: datetime) -> datetime:
    if len(at) <= 5:  # "HH:MM" on the dialog's random day
        h, m = map(int, at.split(":"))
        return default.replace(hour=h, minute=m)
    return datetime.strptime(at, "%Y-%m-%d %H:%M")


def samples_of(dialog: dict, persona, system: str, rng: random.Random) -> list[dict]:
    when = datetime(2026, 1, 1) + timedelta(days=rng.randrange(365 * 2), minutes=rng.randrange(7 * 60, 24 * 60))
    history: list[dict] = []
    out = []
    for turn in dialog["turns"]:
        if "at" in turn:
            when = parse_at(str(turn["at"]), when)
        history.append({"role": "user", "content": persona.stamp(turn["u"], when)})
        history.append({"role": "assistant", "content": turn["c"]})
        out.append({"messages": [{"role": "system", "content": system}] + list(history)})
        when += timedelta(minutes=rng.randint(1, 4))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only check the dialogs, write nothing")
    ap.add_argument("--valid", type=float, default=0.1, help="share of dialogs held out for validation")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    persona = PersonaStore(ROOT / "persona" / "ciel.yaml", few_shot=False).get()
    if persona.style != "anime":
        sys.exit("persona style must be 'anime' (the training data is in that layout)")
    system = persona.system_prompt()
    dialogs = load_dialogs(persona)

    errors = 0
    for d in dialogs:
        for t, turn in enumerate(d["turns"], 1):
            for p in check_reply(turn["c"], subtitle_language(turn["u"])):
                print(f"{d['source']} turn {t}: {p}")
                errors += 1
    replies = sum(len(d["turns"]) for d in dialogs)
    print(f"{len(dialogs)} dialogs, {replies} replies, {errors} problems")
    if errors:
        sys.exit(1)
    if args.check:
        return

    rng = random.Random(args.seed)
    rng.shuffle(dialogs)
    n_valid = max(2, round(len(dialogs) * args.valid))
    split = {"valid": dialogs[:n_valid], "train": dialogs[n_valid:]}  # split by dialog: no turn leaks across
    OUT.mkdir(parents=True, exist_ok=True)
    for name, part in split.items():
        samples = [s for d in part for s in samples_of(d, persona, system, rng)]
        rng.shuffle(samples)
        with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for s in samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        longest = max(sum(len(m["content"]) for m in s["messages"]) for s in samples)
        # ~0.55 tokens per character for this Thai/Japanese mix (see main.trim_history)
        print(f"{name}: {len(samples)} samples, longest ~{longest * 0.55:.0f} tokens → {OUT / (name + '.jsonl')}")


if __name__ == "__main__":
    main()
