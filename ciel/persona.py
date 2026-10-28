"""Turns persona/*.yaml into the system prompt + few-shot messages Ciel runs on.

The YAML file is re-read whenever it changes, so you can tune Ciel's
personality while the server is running — just start a new chat.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml


EXAMPLE_TIME = datetime(2026, 1, 5, 20, 30)


def subtitle_language(text: str) -> str:
    """Which language the subtitles should be in for this message: English
    only when it is written in English (Latin letters, no Thai or Japanese),
    Thai otherwise."""
    thai = any("฀" <= c <= "๿" for c in text)
    japanese = any("぀" <= c <= "ヿ" or "一" <= c <= "鿿" for c in text)
    latin = any(c.isascii() and c.isalpha() for c in text)
    return "English" if latin and not thai and not japanese else "Thai"


@dataclass
class Persona:
    name: str
    user_name: str
    greeting: str
    identity: str
    personality: list[str] = field(default_factory=list)
    speech: dict = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)
    emotions: dict = field(default_factory=dict)  # tag → when to use it
    voice: dict = field(default_factory=dict)  # raw voice: section, see tts.py
    style: str = "native"  # "anime" = always speak Japanese, show a translation
    greeting_ja: str = ""
    tuned: bool = False  # the model is fine-tuned on training/ (see Settings.tuned)

    @classmethod
    def from_dict(cls, data: dict) -> "Persona":
        user_name = data.get("user_name", "มาสเตอร์")
        fill = lambda s: str(s).replace("{user_name}", user_name).replace("{name}", data.get("name", "Ciel"))
        examples = lambda key: [{"user": fill(e["user"]), "ciel": fill(e["ciel"])} for e in data.get(key) or []]
        speaking = data.get("speaking") or {}
        style = speaking.get("style", "native")
        return cls(
            name=data.get("name", "Ciel"),
            user_name=user_name,
            greeting=fill(data.get("greeting", "")),
            greeting_ja=fill(data.get("greeting_ja", "")),
            identity=fill(data.get("identity", "")),
            personality=[fill(p) for p in data.get("personality", [])],
            speech={k: (fill(v) if isinstance(v, str) else [fill(x) for x in v]) for k, v in (data.get("speech") or {}).items()},
            rules=[fill(r) for r in data.get("rules", []) + (speaking.get(f"{style}_rules") or [])],
            examples=examples("examples" if style == "anime" else "native_examples") or examples("examples"),
            emotions={k: fill(v) for k, v in (data.get("emotions") or {}).items()},
            voice=data.get("voice") or {},
            style=style,
        )

    def system_prompt(self) -> str:
        if self.tuned:
            return self.tuned_prompt()
        s = self.speech
        lines = [f"คุณคือ {self.name}", "", "# ตัวตน", self.identity.strip(), "", "# บุคลิก"]
        lines += [f"- {p}" for p in self.personality]
        lines += ["", "# วิธีพูด"]
        if s.get("self"):
            lines.append(f'- แทนตัวเองว่า "{s["self"]}"')
        lines.append(f'- เรียกผู้ใช้ว่า "{self.user_name}"')
        if s.get("endings"):
            lines.append("- คำลงท้ายที่ใช้: " + ", ".join(f'"{e}"' for e in s["endings"]))
        if s.get("tone"):
            lines.append(f"- น้ำเสียง: {s['tone']}")
        lines += [f"- {h}" for h in s.get("habits", [])]
        lines += ["", "# กฎ"]
        lines += [f"- {r}" for r in self.rules]
        if self.emotions:
            lines += [
                "",
                "# แท็กอารมณ์ (ควบคุมน้ำเสียงตอนพูด)",
                "- ขึ้นต้นทุกคำตอบด้วยแท็กอารมณ์ และใส่แท็กใหม่เฉพาะหน้าประโยคที่อารมณ์เปลี่ยน (ไม่ต้องใส่ซ้ำทุกบรรทัด) เช่น [calm]...[shy]...",
                "- แท็กจะถูกซ่อนจากหน้าจอ ใช้ได้เฉพาะแท็กเหล่านี้เท่านั้น:",
            ]
            lines += [f"  - [{tag}] {desc}" for tag, desc in self.emotions.items()]
        if self.style == "anime":
            # the server parses this exact layout (speech.AnimeStream) — keep in sync
            lines += [
                "",
                "# รูปแบบคำตอบ (สำคัญที่สุด ต้องทำตามทุกครั้ง)",
                f"- เสียงของ{self.name}เป็นภาษาญี่ปุ่นเสมอ ไม่ว่า{self.user_name}จะพิมพ์มาเป็นภาษาอะไร",
                "- เขียนบรรทัดภาษาญี่ปุ่นทั้งหมดก่อน แล้วค่อยเขียนคำแปลทั้งหมด (ห้ามสลับทีละคู่):",
                "  1) บรรทัดภาษาญี่ปุ่น บรรทัดละ 1 ประโยค (บรรทัดแรกขึ้นต้นด้วยแท็กอารมณ์)",
                '  2) จากนั้นบรรทัดละ 1 คำแปล ขึ้นต้นด้วย ">> " ตามด้วยเลขลำดับของประโยคญี่ปุ่นที่แปล (>> 1, >> 2) จำนวนเท่ากัน',
                "- คำแปลบรรทัด n แปลเฉพาะประโยคญี่ปุ่นบรรทัด n ให้ตรงความหมาย ห้ามแปลคำพูดของผู้ใช้ และห้ามเอาความหมายของประโยคอื่นมาปน",
                f"- คำแปลใช้ภาษาเดียวกับที่{self.user_name}พิมพ์มา (ภาษาไทยเป็นค่าเริ่มต้น ถ้าพิมพ์อังกฤษให้แปลเป็นอังกฤษ)",
                "- คำแปลภาษาไทยต้องคงบุคลิก คำแทนตัว และคำลงท้ายตาม # วิธีพูด",
                "- ห้ามเขียนข้อความอื่นนอกจากบรรทัดเหล่านี้ ตัวอย่าง:",
                "[calm]了解しました。",
                "すぐ始めます。",
                f">> 1 รับทราบค่ะ {self.user_name}",
                ">> 2 จะเริ่มเดี๋ยวนี้เลยค่ะ",
            ]
        lines += [
            "",
            "# ข้อมูลตอนนี้",
            f"- ข้อความของ{self.user_name}ขึ้นต้นด้วยวันเวลาตอนที่ส่ง เช่น [2026-10-27 Tue 15:10] ใช้เป็นข้อมูลเท่านั้น ไม่ต้องพูดถึงถ้าไม่ได้ถูกถาม และไม่ใช่ภาษาที่{self.user_name}ใช้",
        ]
        if self.style == "anime":
            # the examples sit in the chat as earlier turns; asked "what were we just
            # talking about?" the model answered from them (2026-10-28-0141-latency.md)
            lines.append(f"- ข้อความที่ลงเวลา {EXAMPLE_TIME:%Y-%m-%d %a %H:%M} เป็นตัวอย่างเท่านั้น ไม่ใช่บทสนทนาจริง ถ้าถูกถามว่าคุยอะไรกันไป ให้ดูเฉพาะข้อความหลังจากนั้น")
        return "\n".join(lines)

    def tuned_prompt(self) -> str:
        """The short system prompt of a model fine-tuned on training/ — it is
        trained with exactly this, so the rules and examples it learned don't
        have to be in every prompt (~3,100 tokens + ~3,400 of examples). With
        the full prompt every training sample was ~3,300 tokens and one
        iteration took ~4 min on the M1 (2026-10-29-finetune-trial.md).
        Identity and personality stay, so persona edits still take effect."""
        tags = " ".join(f"[{t}]" for t in self.emotions)
        lines = [f"คุณคือ {self.name}", self.identity.strip(), ""]
        lines += [f"- {p}" for p in self.personality]
        lines += [
            "",
            "# รูปแบบคำตอบ",
            f"- พูดภาษาญี่ปุ่นเสมอ 1-3 บรรทัด บรรทัดละ 1 ประโยค บรรทัดแรกสั้นมากและขึ้นต้นด้วยแท็กอารมณ์ ({tags})",
            '- จากนั้นคำแปลบรรทัดละ 1 ขึ้นต้นด้วย ">> n" แปลตรงกับประโยคญี่ปุ่นบรรทัด n ภาษาตาม sub: ในวงเล็บเวลา',
            f"- เรียก{self.user_name}ว่า マスター แทนตัวเองว่า 私 · คำแปลใช้ \"{self.user_name}\" และ \"{self.speech.get('self', 'ฉัน')}\"",
            "- จำได้เฉพาะในแชทนี้ ห้ามอ้างว่าทำสิ่งที่ทำไม่ได้ · วันเวลาหน้าข้อความเป็นข้อมูล ไม่ต้องพูดถึงถ้าไม่ถูกถาม",
        ]
        return "\n".join(lines)

    def stamp(self, text: str, now: datetime | None = None) -> str:
        """Prefix a user message with when it was sent. Done ONCE, when the
        message arrives, and stored in history that way: the clock can't live in
        the system prompt (it would change the prompt every minute), and it must
        not change on old messages either, or Ollama's prompt cache breaks from
        that point on. Language-neutral, so an English question still looks
        English to the model (a Thai date made it answer with Thai subtitles).

        Anime style also names the subtitle language: with only Thai examples
        the model kept writing Thai subtitles for English questions."""
        now = now or datetime.now()
        head = f"{now:%Y-%m-%d %a %H:%M}"
        if self.style == "anime":
            head += f" · sub: {subtitle_language(text)}"
        return f"[{head}]\n{text}"

    def build_messages(self, history: list[dict]) -> list[dict]:
        """System prompt + examples + history (user messages already stamped).
        Every turn only appends to this list, so everything before the new user
        message is byte-identical to last time and comes from the prompt cache
        (~3,000 tokens would otherwise take ~10 s to re-read on an M1)."""
        messages = [{"role": "system", "content": self.system_prompt()}]
        for ex in [] if self.tuned else self.examples:
            # stamped like real messages (fixed time: the prompt must not change) so
            # the examples show which "sub:" goes with which subtitle language
            user = self.stamp(ex["user"], EXAMPLE_TIME) if self.style == "anime" else ex["user"]
            messages.append({"role": "user", "content": user})
            messages.append({"role": "assistant", "content": ex["ciel"]})
        return messages + history


class PersonaStore:
    """Caches the persona and reloads it when the YAML file changes."""

    def __init__(self, path: Path, tuned: bool = False):
        self.path = path
        self.tuned = tuned
        self._mtime = 0.0
        self._persona: Persona | None = None

    def get(self) -> Persona:
        mtime = self.path.stat().st_mtime
        if self._persona is None or mtime != self._mtime:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            self._persona = Persona.from_dict(data)
            self._persona.tuned = self.tuned
            self._mtime = mtime
        return self._persona
