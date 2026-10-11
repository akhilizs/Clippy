"""Animated word-by-word captions and the top hook text, as an ASS subtitle file burned in by ffmpeg.

Layout is for a 1080x1920 frame and keeps text out of the areas TikTok / Reels cover with
their own UI (top tabs, right-side buttons, bottom caption area).
"""

from __future__ import annotations

import re

from ..models import Word
from .moments import SENTENCE_END

W, H = 1080, 1920
CAPTION_MARGIN_V = 520  # bottom of caption text sits ~27% above the bottom edge
HOOK_MARGIN_V = 250     # below the "Following / For You" tabs
HOOK_SECONDS = 3.2

# ASS colours are &HAABBGGRR. Highlight colour rotates with the clip variant for uniqueness.
HIGHLIGHTS = ["&H0000D7FF&", "&H0014FF39&", "&H00FFE500&", "&H007F3DFF&"]  # yellow, green, cyan, pink


def ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# Burned-in text can't draw colour emoji (they show up as empty boxes), so drop them on screen.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\U0000200D\U00002B00-\U00002BFF]")


def clean(text: str) -> str:
    text = EMOJI.sub("", text)
    text = text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def display_word(text: str) -> str:
    return clean(text).upper().rstrip(".,;:")


def chunk_words(words: list[Word], max_words: int = 3, max_chars: int = 16, max_gap: float = 0.5) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            joined = len(" ".join(x.text for x in cur + [w]))
            breaks = (
                len(cur) >= max_words
                or joined > max_chars
                or w.start - cur[-1].end > max_gap
                or cur[-1].text.endswith(SENTENCE_END + (",",))
            )
            if breaks:
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words: list[Word], hook: str, duration: float, font: str, variant: int = 0) -> str:
    highlight = HIGHLIGHTS[variant % len(HIGHLIGHTS)]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,4,2,90,90,{CAPTION_MARGIN_V},1
Style: Hook,{font},70,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,22,0,8,110,110,{HOOK_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    hook = clean(hook)
    if hook:
        end = min(HOOK_SECONDS, duration)
        events.append(f"Dialogue: 1,{ass_time(0)},{ass_time(end)},Hook,,0,0,0,,{{\\fad(120,250)}}{hook}")

    chunks = chunk_words(words)
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0].start if ci + 1 < len(chunks) else duration
        for i, w in enumerate(chunk):
            t0 = chunk[0].start if i == 0 else w.start
            if i + 1 < len(chunk):
                t1 = chunk[i + 1].start
            else:  # hold the last word until the next chunk if the pause is short
                t1 = next_start if next_start - w.end < 0.6 else w.end + 0.25
            t1 = min(t1, duration)
            if t1 <= t0:
                continue
            parts = []
            for k, x in enumerate(chunk):
                text = display_word(x.text)
                if k == i:
                    parts.append(f"{{\\c{highlight}\\fscx112\\fscy112}}{text}{{\\r}}")
                else:
                    parts.append(text)
            pop = "{\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)}" if i == 0 else ""
            events.append(f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},Caption,,0,0,0,,{pop}{' '.join(parts)}")
    return header + "\n".join(events) + "\n"
