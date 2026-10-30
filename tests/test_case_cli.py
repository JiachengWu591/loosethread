"""Debug CLI, case layout and statistics helpers."""

from pathlib import Path

import pytest

from loosethread.case import _WIDTH, _display_width, _wrap, main, render_case
from loosethread.generator import generate
from loosethread.model import Lang
from loosethread.stats import percentile, wilson


def test_case_text_has_truth_unless_hidden(tmp_path: Path) -> None:
    full, hidden = tmp_path / "full.txt", tmp_path / "hidden.txt"
    assert main(["--seed", "3", "--out", str(full)]) == 0
    assert main(["--seed", "3", "--hide-truth", "--out", str(hidden)]) == 0
    full_text = full.read_text(encoding="utf-8")
    hidden_text = hidden.read_text(encoding="utf-8")
    assert "─── 真相" in full_text
    assert "─── 真相" not in hidden_text
    assert hidden_text.strip() in full_text


def test_english_rendering(tmp_path: Path) -> None:
    out = tmp_path / "en.txt"
    assert main(["--seed", "3", "--lang", "en", "--metrics", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "─── Truth (spoilers)" in text
    assert "min_questions" in text


def _columns(line: str, chars: str) -> list[int]:
    return [_display_width(line[:i]) for i, ch in enumerate(line) if ch in chars]


@pytest.mark.parametrize("lang", list(Lang))
@pytest.mark.parametrize("seed", [0, 7, 213])
def test_window_bars_line_up(seed: int, lang: Lang) -> None:
    """In every grid, the window bars and the band's corners sit in the same two columns."""
    lines = render_case(generate(seed).case, lang).splitlines()
    label = "作案时间窗" if lang is Lang.ZH else "theft window"
    bands = [i for i, line in enumerate(lines) if "┌" in line and label in line]
    assert len(bands) == 2  # testimony notebook and true timeline
    for start in bands:
        corners = _columns(lines[start], "┌┐")
        body = lines[start + 1 :]
        rows = body[: next(i for i, line in enumerate(body) if "│" not in line)]
        assert len(rows) > 6
        for row in rows:
            assert _columns(row, "│") == corners


@pytest.mark.parametrize("seed", [0, 7, 213])
def test_chinese_text_fits_the_page(seed: int) -> None:
    for line in render_case(generate(seed).case, Lang.ZH).splitlines():
        assert _display_width(line) <= _WIDTH, line


def test_wrap_keeps_words_names_and_numbers_whole() -> None:
    zh = "马建国（隐私小谎）声称 20:15 在走廊，实际在客房区。能揭穿它的：沈怀山、何秀兰、苏曼"
    lines = _wrap(zh, 40)
    assert all(_display_width(line) <= 40 for line in lines)
    assert "".join(lines).replace(" ", "") == zh.replace(" ", "")
    assert not any(line.endswith(("沈", "沈怀")) for line in lines)
    en = "Innocent people never lie about the theft window at 21:15–21:30 or any other"
    for line in _wrap(en, 20):
        assert _display_width(line) <= 20
        assert all(word in en.split() for word in line.split())
    assert _wrap("", 10) == [""]


def test_wrap_avoids_a_lone_character_on_the_last_line() -> None:
    lines = _wrap("一二三四五六七八九十上。", 20)
    assert _display_width(lines[-1]) > 4


def test_batch_report(tmp_path: Path) -> None:
    out = tmp_path / "batch.txt"
    assert main(["--batch", "5", "--out", str(out)]) == 0
    assert "audited OK (unique + all guarantees): 5/5" in out.read_text(encoding="utf-8")


def test_wilson_interval() -> None:
    low, high = wilson(1000, 1000)
    assert high == 1.0
    assert low == pytest.approx(0.99617, abs=1e-4)
    low, high = wilson(50, 100)
    assert (low, high) == pytest.approx((0.4038, 0.5962), abs=1e-4)


def test_percentile_nearest_rank() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0
