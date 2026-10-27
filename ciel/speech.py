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

    # uniform event API shared with AnimeStream (see main.reply_to)
    def events(self, chunk: str) -> list[tuple]:
        return self._as_events(*self.feed(chunk))

    def end_events(self) -> list[tuple]:
        return self._as_events(*self.flush())

    @staticmethod
    def _as_events(shown: str, segments: list[Segment]) -> list[tuple]:
        return ([("delta", None, shown)] if shown else []) + [("segment", s) for s in segments]


SUB_PREFIXES = (">>", "＞＞", "»")


def has_japanese(text: str) -> bool:
    return any(0x3040 <= ord(c) <= 0x30FF or 0x4E00 <= ord(c) <= 0x9FFF for c in text)


class AnimeStream:
    """'Anime' style: Ciel always speaks Japanese and the screen shows a
    translation. The model answers in line pairs:

        [shy]べ、別に大したことじゃありませんよ。
        >> ไม่ใช่เรื่องใหญ่หรอกค่ะ

    Japanese lines become spoken segments; '>>' lines are subtitles for the
    segment before them. Events:
      ("delta", "jp"|"sub", text)  text to append to the current line on screen
      ("line_end", kind)           that line is finished
      ("segment", Segment)         a Japanese line to speak
      ("sub", seq, text)           subtitle for segment number `seq`
    """

    def __init__(self):
        self.emotion = "calm"
        self.seq = -1  # index of the last spoken segment
        self.translated = True  # has segment `seq` got its translation yet?
        self._reset_line()

    def _reset_line(self):
        self.line = ""
        self.kind: str | None = None
        self.sent = 0  # visible chars of this line already sent

    def events(self, chunk: str) -> list[tuple]:
        out: list[tuple] = []
        for ch in chunk:
            if ch == "\n":
                out += self._end_line()
            else:
                self.line += ch
                out += self._stream_line()
        return out

    def end_events(self) -> list[tuple]:
        return self._end_line()

    def _detect_kind(self, final: bool) -> str | None:
        s = self.line.lstrip()
        if not s:
            return None
        if s.startswith(SUB_PREFIXES):
            return "sub"
        if not final and (len(s) < 2 and s[0] in ">＞»" or s.startswith("[") and "]" not in s and len(s) < MAX_TAG_LEN):
            return None  # can't tell yet
        # Translations never carry an emotion tag, so a tagged line is Japanese —
        # even "[calm]RAMは…", which starts with Latin letters.
        if TAG.match(s):
            return "jp"
        # The model sometimes forgets ">>". Decide by the first real character:
        # Japanese → a line to speak, anything else (Thai, English) → translation.
        first = s[0]
        if script(first) == "ja" or first in "「『（(…":
            return "jp"
        return "sub"

    def _visible(self) -> str:
        text = self.line.lstrip()
        if self.kind == "sub":
            for p in SUB_PREFIXES:
                if text.startswith(p):
                    text = text[len(p):]
                    break
        return TAG.sub("", text).lstrip()

    def _stream_line(self) -> list[tuple]:
        if self.kind is None:
            self.kind = self._detect_kind(final=False)
            if self.kind is None:
                return []
        visible = self._visible()
        cut = visible.rfind("[")  # hold back a tag that may still be arriving
        if cut != -1 and "]" not in visible[cut:] and len(visible) - cut < MAX_TAG_LEN:
            visible = visible[:cut]
        new, self.sent = visible[self.sent:], max(self.sent, len(visible))
        return [("delta", self.kind, new)] if new else []

    def _end_line(self) -> list[tuple]:
        if not self.line.strip():
            self._reset_line()
            return []
        self.kind = self.kind or self._detect_kind(final=True)
        out: list[tuple] = []
        visible = self._visible().rstrip()
        # a tagged line with no Japanese at all is really a translation the
        # model mis-tagged; line_end carries the corrected kind for the screen
        if self.kind == "jp" and not has_japanese(visible) and any(c.isalpha() for c in visible):
            if visible[self.sent:]:  # finish the line in the span it was streaming into
                out.append(("delta", "jp", visible[self.sent:]))
                self.sent = len(visible)
            self.kind = "sub"
        if visible[self.sent:]:
            out.append(("delta", self.kind, visible[self.sent:]))
        out.append(("line_end", self.kind))
        tags = TAG.findall(self.line)
        if tags:
            self.emotion = tags[-1].lower()
        if self.kind == "jp":
            spoken = clean_for_speech(visible)
            if has_japanese(spoken):
                self.seq += 1
                self.translated = False
                out.append(("segment", Segment(spoken, "ja", self.emotion)))
        elif self.kind == "sub":
            # first translation after a Japanese line belongs to it; any extra
            # stray line is shown on its own (seq -1: no voice)
            if self.seq >= 0 and not self.translated:
                self.translated = True
                out.append(("sub", self.seq, visible))
            else:
                out.append(("sub", -1, visible))
        self._reset_line()
        return out


def strip_tags(text: str) -> str:
    return re.sub(r" {2,}", " ", TAG.sub("", text)).strip()
