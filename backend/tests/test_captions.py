from app.models import Word
from app.pipeline.captions import HIGHLIGHTS, ass_time, build_ass, chunk_words, clean


def w(text, start, end):
    return Word(text=text, start=start, end=end)


def test_ass_time_format():
    assert ass_time(0) == "0:00:00.00"
    assert ass_time(61.257) == "0:01:01.26"
    assert ass_time(3725.5) == "1:02:05.50"


def test_chunks_break_on_punctuation_pause_and_size():
    words = [w("Hello", 0, 0.3), w("there.", 0.35, 0.6), w("This", 0.7, 0.9), w("is", 0.95, 1.0),
             w("a", 1.05, 1.1), w("test", 1.15, 1.4), w("again", 2.5, 2.8)]
    chunks = [[x.text for x in c] for c in chunk_words(words)]
    assert chunks == [["Hello", "there."], ["This", "is", "a"], ["test"], ["again"]]


def test_build_ass_has_hook_and_one_event_per_word():
    words = [w("so", 0.2, 0.4), w("crazy!", 0.5, 0.9), w("wow", 1.0, 1.3)]
    ass = build_ass(words, "He did WHAT? 😳", 5.0, "Inter Display Black", variant=2)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    hook_lines = [line for line in ass.splitlines() if ",Hook," in line]
    assert len(hook_lines) == 1 and hook_lines[0].endswith("He did WHAT?")
    caption_lines = [line for line in ass.splitlines() if ",Caption," in line]
    assert len(caption_lines) == 3
    assert HIGHLIGHTS[2] in caption_lines[0]
    assert "CRAZY!" in caption_lines[1]


def test_clean_strips_ass_control_chars_and_emoji():
    assert clean("hi {\\b1} 🔥 there") == "hi (/b1) there"
