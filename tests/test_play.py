"""Terminal front end, driven with scripted input."""

import json
from collections.abc import Callable
from pathlib import Path

from loosethread.generator import DAILY, generate
from loosethread.play import main

CASE = generate(213, DAILY).case
CULPRIT_ZH = next(p.name.zh for p in CASE.view.world.people if p.id == CASE.truth.culprit)


def _script(lines: list[str]) -> tuple[Callable[[str], str], list[str]]:
    feed = iter(lines)
    out: list[str] = []

    def read(prompt: str) -> str:
        out.append(prompt)
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    return read, out


def _run(argv: list[str], lines: list[str]) -> str:
    read, out = _script(lines)
    assert main(argv, read=read, write=out.append) == 0
    return "\n".join(out)


def test_zh_session_from_question_to_truth(tmp_path: Path) -> None:
    log = tmp_path / "session.jsonl"
    text = _run(
        ["--seed", "213", "--log", str(log)],
        [
            "你在哪？",  # nobody addressed yet
            "林小雨：你 21:15 在哪？",
            "你 21:15 在哪？",  # same person, same question: free
            "嗯……",
            "/笔记",
            "/飞",
            "/指认 林小雨 S1",
            f"/指认 {CULPRIT_ZH} S1 E1",
            "n",
            f"/指认 {CULPRIT_ZH} S1 E1",
            "y",
        ],
    )
    assert "先说明问谁" in text
    assert "→ 记入笔记：S1" in text
    assert "（问过了，不计次数）" in text
    assert "（没听懂，不计次数）" in text
    assert "S1  林小雨：21:15 自己在" in text
    assert "不认识的命令：/飞" in text
    assert "用法：/指认" in text
    assert "已取消。" in text
    assert "─── 真相" in text
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["type"] for r in rows] == ["turn"] * 3 + ["summary"]
    assert [r["cost"] for r in rows[:3]] == [1, 0, 0]
    assert rows[-1]["questions_used"] == 1
    assert rows[-1]["outcome"] in {"hunch", "wrong", "solved"}
    assert "key" not in log.read_text(encoding="utf-8").lower()


def test_en_accusation_takes_a_full_name() -> None:
    culprit = next(p.name.en for p in CASE.view.world.people if p.id == CASE.truth.culprit)
    text = _run(["--seed", "213", "--lang", "en"], [f"/accuse {culprit} E1 E2", "y"])
    assert "Right person, but E1 and E2 do not expose a lie" in text


def test_en_session_and_quit() -> None:
    text = _run(
        ["--seed", "213", "--lang", "en", "--hard"],
        ["@Lin where were you at 9:15?", "/notes", "/quit", "y"],
    )
    assert "Lin Xiaoyu: Between 21:15 and 21:30 I was in the" in text
    assert "(hard mode: no contradiction hints)" in text
    assert "Goodbye." in text
    assert "Truth (spoilers)" not in text


def test_running_out_forces_an_accusation() -> None:
    text = _run(["--seed", "213", "--budget", "1"], ["林小雨：你 21:15 在哪？", "你 20:00 在哪？"])
    assert text.count("问题用完了") == 2
