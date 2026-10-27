"""Turns persona/*.yaml into the system prompt + few-shot messages Ciel runs on.

The YAML file is re-read whenever it changes, so you can tune Ciel's
personality while the server is running — just start a new chat.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]


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
                "- ขึ้นต้นทุกคำตอบด้วยแท็กอารมณ์ และใส่แท็กใหม่หน้าประโยคที่อารมณ์เปลี่ยน เช่น [calm]...[shy]...",
                "- แท็กจะถูกซ่อนจากหน้าจอ ใช้ได้เฉพาะแท็กเหล่านี้เท่านั้น:",
            ]
            lines += [f"  - [{tag}] {desc}" for tag, desc in self.emotions.items()]
        if self.style == "anime":
            # the server parses this exact layout (speech.AnimeStream) — keep in sync
            lines += [
                "",
                "# รูปแบบคำตอบ (สำคัญที่สุด ต้องทำตามทุกครั้ง)",
                f"- เสียงของ{self.name}เป็นภาษาญี่ปุ่นเสมอ ไม่ว่า{self.user_name}จะพิมพ์มาเป็นภาษาอะไร",
                "- ตอบเป็นคู่บรรทัด ทีละประโยค:",
                "  1) บรรทัดภาษาญี่ปุ่น 1 ประโยค ขึ้นต้นด้วยแท็กอารมณ์",
                '  2) บรรทัดถัดไปขึ้นต้นด้วย ">> " ตามด้วยคำแปลของประโยคนั้น',
                f"- คำแปลใช้ภาษาเดียวกับที่{self.user_name}พิมพ์มา (ภาษาไทยเป็นค่าเริ่มต้น ถ้าพิมพ์อังกฤษให้แปลเป็นอังกฤษ)",
                "- คำแปลภาษาไทยต้องคงบุคลิก คำแทนตัว และคำลงท้ายตาม # วิธีพูด",
                "- ห้ามเขียนข้อความอื่นนอกจากคู่บรรทัดเหล่านี้ ตัวอย่าง:",
                "[calm]了解しました、マスター。",
                f">> รับทราบค่ะ {self.user_name}",
            ]
        lines += [
            "",
            "# ข้อมูลตอนนี้",
            f"- ข้อความล่าสุดของ{self.user_name}ขึ้นต้นด้วยวันเวลาปัจจุบันในวงเล็บ ใช้เป็นข้อมูลเท่านั้น ไม่ต้องพูดถึงถ้าไม่ได้ถูกถาม",
        ]
        return "\n".join(lines)

    def build_messages(self, history: list[dict], now: datetime | None = None) -> list[dict]:
        """System prompt + examples + history. Everything before the last user
        message stays byte-identical between turns, so Ollama's prompt cache can
        skip re-reading it (~3,000 tokens, ~10 s on an M1). That's why the clock
        is stamped onto the last user message here, not into the system prompt,
        and never stored in `history`."""
        messages = [{"role": "system", "content": self.system_prompt()}]
        for ex in self.examples:
            messages.append({"role": "user", "content": ex["user"]})
            messages.append({"role": "assistant", "content": ex["ciel"]})
        messages += history
        if history and history[-1]["role"] == "user":
            now = now or datetime.now()
            stamp = f"({'วัน' + THAI_DAYS[now.weekday()]}ที่ {now.day}/{now.month}/{now.year + 543} เวลา {now:%H:%M} น.)"
            messages[-1] = {"role": "user", "content": f"{stamp}\n{history[-1]['content']}"}
        return messages


class PersonaStore:
    """Caches the persona and reloads it when the YAML file changes."""

    def __init__(self, path: Path):
        self.path = path
        self._mtime = 0.0
        self._persona: Persona | None = None

    def get(self) -> Persona:
        mtime = self.path.stat().st_mtime
        if self._persona is None or mtime != self._mtime:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            self._persona = Persona.from_dict(data)
            self._mtime = mtime
        return self._persona
