"""Terminal front end, driven with scripted input."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from loosethread.case import render_notebook
from loosethread.content import load_pack
from loosethread.game import Game
from loosethread.generator import DAILY, PACKS, daily_case, generate
from loosethread.lines import TemplateWriter
from loosethread.model import Lang, Occupants, PersonAt, PersonId, Query, QueryKind
from loosethread.npc import BackendUnavailable, ParseRequest, ParseResult
from loosethread.parser import RuleParser
from loosethread.play import Session, main
from loosethread.simulate import star_rule

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
    """The case numbers below mean the classic cases, whose names the scripts rely on."""
    read, out = _script(lines)
    assert main(["--classic", *argv], read=read, write=out.append) == 0
    return "\n".join(out)


def test_zh_session_from_question_to_truth(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "session.jsonl"  # the folder does not exist yet
    text = _run(
        ["--seed", "213", "--log", str(log)],
        [
            "你在哪？",  # nobody addressed yet
            "林小雨：你 21:15 在哪？",
            "你 21:15 在哪？",  # same person, same question: free
            "嗯……",
            "/笔记",
            "/飞",
            "/指认",
            "/指认 林小雨 S1",
            f"/指认 {CULPRIT_ZH} S1 E1",
            "n",
            f"/指认 {CULPRIT_ZH} S1 E1",
            "y",
        ],
    )
    assert "先说明问谁" in text
    assert "→ 按“林小雨 21:15–21:30 在哪、和谁在一起”记入笔记：S1" in text
    assert "（按“林小雨 21:15–21:30 在哪、和谁在一起”算问过了，不计次数）" in text
    assert "（没听懂，不计次数）" in text
    assert "S1  林小雨：21:15 " in text
    assert "不认识的命令：/飞" in text
    assert "用法：/指认" in text
    assert "还差一个编号：指认要给出两条不能同时成立的记录。" in text
    assert "笔记里还没有和 S1 矛盾的记录。" in text
    assert "注意：S1 与 E1 并不矛盾。" in text
    assert "已取消。" in text
    assert f"笔记里还没有能揭穿{CULPRIT_ZH}谎言的一对。" in text
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
    assert "Note: E1 and E2 do not contradict each other." in text
    assert "Right person, but E1 and E2 do not expose a lie" in text
    assert f"Your notebook had no pair yet that exposes {culprit}'s lie." in text
    # Most systematic players need more than the budget for case 213 (CP-5; budget 12, CP-6).
    assert "(This case: any solve within 12 questions earns ★★★.)" in text
    assert "simulated" not in text


def test_the_result_shows_this_case_s_star_thresholds() -> None:
    case = generate(0, DAILY).case
    rule = star_rule(case)
    culprit = next(p.name.zh for p in case.view.world.people if p.id == case.truth.culprit)
    text = _run(["--seed", "0"], [f"/指认 {culprit} E1 E2", "y"])
    assert f"（本案：★★★ 不超过 {rule.three} 问，★★ 不超过 {rule.two} 问，★ 其余。）" in text
    assert "模拟" not in text


def test_after_a_miss_the_exposing_pair_is_shown() -> None:
    innocent = next(
        p.name.zh
        for p in CASE.view.world.people
        if p.id in CASE.view.suspects and p.id != CASE.truth.culprit
    )
    text = _run(
        ["--seed", "213"],
        [
            "沈怀山：20:15 你和谁在一起？",
            "林小雨：你今晚见过苏曼吗？",
            "你什么时候去过大堂？",
            "苏曼：20:30 你和谁在一起？",
            f"/指认 {innocent} S6 S9",
            "y",
        ],
    )
    assert "→ 按“林小雨什么时候在大堂”记入笔记：S5、S6、S7、S8" in text
    assert f"确认指认 {innocent}，理由是 S6 与 S9 不能同时成立？" in text
    assert "抓错人了。" in text
    assert f"笔记里能揭穿{CULPRIT_ZH}谎言的：S6 与 S9。" in text


def test_accusation_hints_name_the_conflicting_items() -> None:
    text = _run(
        ["--seed", "213"],
        [
            "林小雨：你今晚见过苏曼吗？",
            "你什么时候去过大堂？",
            "苏曼：20:30 你和谁在一起？",
            f"/指认 {CULPRIT_ZH} S5",
            f"/指认 {CULPRIT_ZH} S5 E1",
            "n",
        ],
    )
    assert "还差一个编号" in text
    assert "笔记里和 S5 矛盾的：S8。" in text
    assert "笔记里和它们有关的矛盾：S5 与 S8。" in text
    assert "注意：S5 与 E1 并不矛盾。" in text


def test_hard_mode_does_not_warn_about_the_pair() -> None:
    text = _run(["--seed", "213", "--hard"], [f"/指认 {CULPRIT_ZH} E1 E2", "n", "/退出", "y"])
    assert "并不矛盾" not in text
    assert "理由是 E1 与 E2 不能同时成立？" in text


def test_en_session_and_quit() -> None:
    text = _run(
        ["--seed", "213", "--lang", "en", "--hard"],
        ["﻿@Lin where were you at 9:15?", "/notes", "/quit", "y"],  # BOM from a pipe
    )
    assert "Lin Xiaoyu: Between 21:15 and 21:30 I was in the" in text
    assert "→ read as “where Lin Xiaoyu was at 21:15–21:30, and with whom”; noted: S1" in text
    assert "(hard mode: no contradiction hints)" in text
    assert "Goodbye." in text
    assert "Truth (spoilers)" not in text


def test_the_opening_is_short_and_the_rest_is_one_command_away() -> None:
    text = _run(["--seed", "213"], ["/规则", "/案情"])
    opening, rules, sheet = text.split("[还剩 12 问]> ")[:3]
    assert "─── 推理要点" in opening
    assert "目标：找出犯人" in opening
    assert "说法对不上时会亮 ⚠" in opening
    assert "共 3 个时段（每段 15 分钟）" in opening
    assert "嫌疑人：" in opening
    assert "印象：" not in opening
    assert "推理规则" not in opening
    assert "7. “听说”如实转述原话" in rules
    assert "印象：" in sheet
    assert "动机：" in sheet
    assert "（输入结束，游戏退出。）" in text  # the script ran out: said, not silent


def _play_game_case(seed: int, lang: str) -> str:
    read, out = _script(["/quit", "y"])
    assert main(["--seed", str(seed), "--lang", lang], read=read, write=out.append) == 0
    return "\n".join(out)


@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_each_number_opens_its_own_setting_and_the_help_uses_its_people(
    seed: int, lang: str
) -> None:
    text = _play_game_case(seed, lang)
    case = daily_case(seed).case
    pack = load_pack(PACKS[seed % 3])
    language = Lang(lang)
    assert pack.setting.get(language) in text
    assert pack.locations[0].name.get(language) in text  # the map
    names = [p.name.get(language) for p in case.view.world.people if p.id in case.view.suspects]
    start = case.view.world.slots[case.view.crime.window[0]].label.split("–")[0]
    assert (
        f"{names[0]}：你 {start} 在哪" in text or f"{names[0]}: where were you at {start}" in text
    )
    other = {
        p.person.name.get(language) for e in PACKS if e != pack.id for p in load_pack(e).roster
    }
    assert not any(name in text for name in other)


def test_a_game_case_plays_to_the_truth_in_any_setting() -> None:
    for seed in (1, 2):
        case = daily_case(seed).case
        name = next(p.name.zh for p in case.view.world.people if p.id == case.truth.culprit)
        read, out = _script([f"/指认 {name} E1 E2", "y"])
        assert main(["--seed", str(seed)], read=read, write=out.append) == 0
        text = "\n".join(out)
        assert "─── 真相" in text
        assert "人抓对了" in text


def test_classic_keeps_the_old_case() -> None:
    assert "雾松山庄" in _run(["--seed", "1"], ["/退出", "y"])


def test_denials_stay_in_the_notes() -> None:
    game = Game(CASE, RuleParser(), TemplateWriter(), Lang.ZH)
    never = next(
        loc
        for loc in CASE.view.world.locations
        if not game._book.answer(Query(QueryKind.WHEN, PersonId("lin"), location=loc.id)).claims
    )
    read, out = _script([f"林小雨：你什么时候去过{never.name.zh}？", "/笔记"])
    Session(game, read, out.append).run()
    text = "\n".join(out)
    assert "否认过的（不能当指认的编号）：" in text
    assert f"· 林小雨：我今晚没去过{never.name.zh}。" in text


def test_the_notes_grid_shows_where_a_sighting_places_the_speaker() -> None:
    game = Game(CASE, RuleParser(), TemplateWriter(), Lang.ZH)
    lin = next(p for p in CASE.view.world.people if p.id == "lin")
    game.ask(lin.id, "你今晚见过苏曼吗？")
    statements = [s for _, s in game.notebook.statements]
    assert statements
    rooms = {x.id: x.name.zh for x in CASE.view.world.locations}
    grid = render_notebook(game.notebook.obtained_view(), Lang.ZH, unknown="·")
    row = next(line for line in grid if line.startswith(f"  {lin.name.zh}"))
    for s in statements:
        assert isinstance(s.claim, PersonAt)
        assert rooms[s.claim.location] in row


def test_a_name_and_a_space_address_that_person() -> None:
    text = _run(["--seed", "213"], ["沈怀山 21:15 你在哪？", "/退出", "y"])
    assert "[还剩 11 问] 沈怀山> " in text
    assert "→ 按“沈怀山 21:15–21:30 在哪、和谁在一起”" in text
    text = _run(
        ["--seed", "213", "--lang", "en"],
        ["Shen Huaishan where were you at 9:15?", "/quit", "y"],
    )
    assert "[11 left] Shen Huaishan> " in text


def test_a_name_in_english_only_addresses_before_a_question_word() -> None:
    text = _run(
        ["--seed", "213", "--lang", "en"],
        ["Su Man: where were you at 9:15?", "Lin Xiaoyu was with you at 9:15?", "/quit", "y"],
    )
    assert "whether Su Man saw Lin Xiaoyu at 21:15–21:30" in text
    assert "Lin Xiaoyu> " not in text


def test_a_question_with_no_case_facts_says_it_was_free() -> None:
    text = _run(["--seed", "213"], ["林小雨：谁是犯人？", "/退出", "y"])
    assert "（按“案情以外的问题”算，不计次数）" in text
    assert "[还剩 12 问] 林小雨> " in text


def test_the_notes_grid_shows_where_a_company_answer_places_the_speaker() -> None:
    game = Game(CASE, RuleParser(), TemplateWriter(), Lang.ZH)
    person = CASE.view.world.people[1]
    game.ask(person.id, "20:15 你和谁在一起？")
    ((_, statement),) = game.notebook.statements
    assert isinstance(statement.claim, Occupants)
    place = next(x for x in CASE.view.world.locations if x.id == statement.claim.location)
    grid = render_notebook(game.notebook.obtained_view(), Lang.ZH, unknown="·")
    row = next(line for line in grid if line.startswith(f"  {person.name.zh}"))
    assert place.name.zh in row


def test_ctrl_c_keeps_the_log(tmp_path: Path) -> None:
    log = tmp_path / "cut.jsonl"
    feed = iter(["林小雨：你 21:15 在哪？"])

    def read(prompt: str) -> str:
        try:
            return next(feed)
        except StopIteration:
            raise KeyboardInterrupt from None

    out: list[str] = []
    argv = ["--classic", "--seed", "213", "--log", str(log)]
    assert main(argv, read=read, write=out.append) == 130
    assert out[-1] == "（已中断。）"
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["type"] for r in rows] == ["turn", "summary"]
    assert rows[-1]["outcome"] is None


class _Unreachable:
    def parse(self, request: ParseRequest) -> ParseResult:
        raise BackendUnavailable("APITimeoutError")


def test_an_unreachable_model_is_named_not_blamed_on_the_question() -> None:
    game = Game(CASE, _Unreachable(), TemplateWriter(), Lang.ZH)
    read, out = _script(["林小雨：你 21:15 在哪？"])
    Session(game, read, out.append).run()
    text = "\n".join(out)
    assert "（连不上模型，不计次数，请再问一次）" in text
    assert "（没听懂，不计次数）" not in text
    assert game.used == 0


def test_running_out_forces_an_accusation() -> None:
    text = _run(["--seed", "213", "--budget", "1"], ["林小雨：你 21:15 在哪？", "你 20:00 在哪？"])
    assert text.count("问题用完了") == 2
