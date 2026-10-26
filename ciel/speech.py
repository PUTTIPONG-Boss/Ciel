"""Turns the LLM's token stream into (a) clean text for the screen and
(b) speakable segments: one sentence, one language, one emotion each.

Ciel marks emotion with tags like [shy] at the start of a sentence. Tags are
removed from the displayed text but steer the voice and the magic circle.
"""

import re
from dataclasses import dataclass

from .tts import EMOTIONS

TAG = re.compile(r"\[(" + "|".join(EMOTIONS) + r")\]", re.IGNORECASE)
MAX_TAG_LEN = max(len(e) for e in EMOTIONS) + 2
SENTENCE_END = set(".!?。！？…\n")
FIRST_CUT, NEXT_CUT, HARD_CUT = 24, 60, 220  # chars before cutting at a space

EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")
MARKDOWN = re.compile(r"[*_`#~>|]+")


@dataclass
class Segment:
    text: str
    lang: str
    emotion: str


def script(ch: str) -> str | None:
    o = ord(ch)
    if 0x0E00 <= o <= 0x0E7F:
        return "th"
    if (0x3040 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF or 0x3400 <= o <= 0x4DBF
            or 0x4E00 <= o <= 0x9FFF or 0xFF66 <= o <= 0xFF9F or 0x3000 <= o <= 0x303F):
        return "ja"
    return None  # Latin, digits, punctuation: rides along with its neighbours


def split_languages(text: str) -> list[tuple[str, str]]:
    """Split a sentence into Thai / Japanese runs. Latin text joins the run it
    sits in (a Thai voice reads "Ciel" fine); a sentence with no Thai or
    Japanese at all is English."""
    runs: list[list] = []
    pending = ""  # neutral text before the first Thai/Japanese char
    for ch in text:
        s = script(ch)
        if s is None:
            if runs:
                runs[-1][1] += ch
            else:
                pending += ch
        elif runs and runs[-1][0] == s:
            runs[-1][1] += ch
        else:
            runs.append([s, pending + ch])
            pending = ""
    if not runs:
        return [("en", pending)]
    # move trailing spaces/punctuation-only tails into a cleaner split
    return [(lang, chunk) for lang, chunk in runs]


def clean_for_speech(text: str) -> str:
    text = EMOJI.sub("", MARKDOWN.sub("", text))
    return re.sub(r"\s+", " ", text).strip()


class SpeechStream:
    def __init__(self):
        self.emotion = "calm"
        self.held = ""  # raw text that might be the start of a tag
        self.sentence = ""
        self.sentence_emotion = "calm"
        self.cut_at = FIRST_CUT

    def feed(self, chunk: str) -> tuple[str, list[Segment]]:
        """Returns (text to display, finished segments)."""
        buf = self.held + chunk
        self.held = ""
        shown: list[str] = []
        segments: list[Segment] = []
        i = 0
        while i < len(buf):
            ch = buf[i]
            if ch == "[":
                m = TAG.match(buf, i)
                if m:
                    segments += self._cut()
                    self.emotion = m.group(1).lower()
                    i = m.end()
                    # swallow the space after a tag so the screen doesn't show double spaces
                    while i < len(buf) and buf[i] == " " and not shown:
                        i += 1
                    continue
                if "]" not in buf[i:] and len(buf) - i < MAX_TAG_LEN:
                    self.held = buf[i:]  # maybe a tag split across chunks
                    break
            shown.append(ch)
            segments += self._add(ch)
            i += 1
        return "".join(shown), segments

    def flush(self) -> tuple[str, list[Segment]]:
        rest, self.held = self.held, ""
        segments = []
        for ch in rest:
            segments += self._add(ch)
        return rest, segments + self._cut()

    def _add(self, ch: str) -> list[Segment]:
        if not self.sentence:
            self.sentence_emotion = self.emotion
        self.sentence += ch
        n = len(self.sentence.strip())
        if ch in SENTENCE_END or (ch.isspace() and n >= self.cut_at) or n >= HARD_CUT:
            return self._cut()
        return []

    def _cut(self) -> list[Segment]:
        text, self.sentence = clean_for_speech(self.sentence), ""
        if not any(c.isalnum() for c in text):
            return []
        self.cut_at = NEXT_CUT
        out = []
        for lang, chunk in split_languages(text):
            chunk = chunk.strip()
            if any(c.isalnum() for c in chunk):
                out.append(Segment(chunk, lang, self.sentence_emotion))
        return out


def strip_tags(text: str) -> str:
    return re.sub(r" {2,}", " ", TAG.sub("", text)).strip()
