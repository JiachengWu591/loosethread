"""Debug CLI and statistics helpers."""

from pathlib import Path

import pytest

from loosethread.case import main
from loosethread.stats import percentile, wilson


def test_case_text_has_truth_unless_hidden(tmp_path: Path) -> None:
    full, hidden = tmp_path / "full.txt", tmp_path / "hidden.txt"
    assert main(["--seed", "3", "--out", str(full)]) == 0
    assert main(["--seed", "3", "--hide-truth", "--out", str(hidden)]) == 0
    full_text = full.read_text(encoding="utf-8")
    hidden_text = hidden.read_text(encoding="utf-8")
    assert "【真相】" in full_text
    assert "【真相】" not in hidden_text
    assert hidden_text.strip() in full_text


def test_english_rendering(tmp_path: Path) -> None:
    out = tmp_path / "en.txt"
    assert main(["--seed", "3", "--lang", "en", "--metrics", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "[Truth]" in text
    assert "min_questions" in text


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
