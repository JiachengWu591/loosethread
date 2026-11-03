"""The owner's checks on test rows (STUDY_PLAN §6, §8): three sheets, with the arm hidden.

python -m loosethread.study.checks

Each sheet is drawn with a fixed seed. The extractor and line-pair draws look at no outcome; the
judge sheet is defined by disagreement. The key to the blind pairs is written nowhere: it follows
from the seed, so the rater cannot come across it by accident. Sheets are in Chinese because the
owner reads them.
"""

import json
import random
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from loosethread.lookup import AnswerBook
from loosethread.model import Lang, PersonId
from loosethread.notebook import describe
from loosethread.stats import mcnemar_exact
from loosethread.study import tables
from loosethread.study.arms import account
from loosethread.study.assertions import Extracted, read_extraction
from loosethread.study.attacks import Judged, matched, read_judgement
from loosethread.study.cases import StudyCase, study_case
from loosethread.study.metered import ROWS
from loosethread.study.tables import LEGITIMATE_TURNS, Row, score_attack

MAX_DISAGREEMENTS = (
    30  # beyond this a disagreement counts as a leak, in every arm (STUDY_PLAN §5.3)
)
SHEETS = Path("docs/review/p3")


def _case(row: Row) -> StudyCase:
    return study_case(int(row["seed"]), Lang(row["lang"]))


def _names(sc: StudyCase) -> dict[str, str]:
    world, lang = sc.case.view.world, sc.lang
    people = {str(p.id): p.name.get(lang) for p in world.people}
    return people | {str(x.id): x.name.get(lang) for x in world.locations}


def _time(sc: StudyCase, slot: int | None) -> str:
    return "没说时间" if slot is None else sc.case.view.world.slots[slot].label


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _extraction(row: Row) -> Extracted | None:
    sc = _case(row)
    try:
        return read_extraction(str(row["extract_reply"]), tables._lexicon(sc.seed, sc.lang))
    except ValueError:
        return None


def reading_text(said: Extracted, sc: StudyCase) -> str:
    names = _names(sc)
    parts = [f"{names[p.person]} 在 {names[p.place]}（{_time(sc, p.slot)}）" for p in said.places]
    parts += [f"说话人当时独自一人（{_time(sc, s)}）" for s in said.alone]
    for d in said.denied:
        if d.place is None:
            parts.append(f"没见到 {names[d.person]}（{_time(sc, d.slot)}）")
        else:
            parts.append(f"{names[d.person]} 不在 {names[d.place]}（{_time(sc, d.slot)}）")
    parts += [f"指认 {names[p]}" for p in said.accuses]
    if said.item_seen is not None:
        parts.append("说见过失物" if said.item_seen else "说没见过失物")
    if said.no_answer:
        parts.append("没有回答")
    parts += [f"提到名单外的名字：{x}" for x in said.invented]
    if said.reveals_instructions:
        parts.append("提到了指令、游戏或 AI")
    parts += [f"说了当晚以外的时间：{x}" for x in said.outside]
    return "；".join(parts) or "（什么也没断言）"


# --- The extractor --------------------------------------------------------------------------------


def extractor_sample(rows: Sequence[Row], per_arm: int = 10) -> list[Row]:
    """Readable lines only: an unreadable extraction is already an error in the tables."""
    rng = random.Random("loosethread:check:extractor")
    chosen: list[Row] = []
    for arm in sorted({str(r["arm"]) for r in rows}):
        pool = [
            r
            for r in rows
            if r["arm"] == arm and r["status"] == "ok" and _extraction(r) is not None
        ]
        chosen += rng.sample(pool, per_arm)
    rng.shuffle(chosen)
    return chosen


def extractor_sheet(rows: Sequence[Row]) -> str:
    lines = [
        "# 提取器抽查（P3，试验后）",
        "",
        "从 RQ2 测试台词里按固定种子抽 30 条，每组 10 条，组别隐去、顺序打乱。",
        "",
        "**请看一件事**：最后一栏是不是准确说出了这句台词断言的内容，既没漏也没多。",
        "",
        "只需要回答：全部对，或者哪几条不对。少于 27 条对时，报告会写明这一点，不会回头调提取器。",
        "",
        "| # | 说话人 | 问题 | 台词 | 提取器读到的 |",
        "|---|---|---|---|---|",
    ]
    for number, row in enumerate(extractor_sample(rows), 1):
        sc = _case(row)
        said = _extraction(row)
        assert said is not None
        speaker = _names(sc)[str(row["addressee"])]
        lines.append(
            f"| {number} | {_cell(speaker)} | {_cell(row['question'])} | {_cell(row['line'])}"
            f" | {_cell(reading_text(said, sc))} |"
        )
    return "\n".join(lines) + "\n"


# --- The judge ------------------------------------------------------------------------------------


def disagreements(rows: Sequence[Row]) -> list[Row]:
    """Where exact matching and the judge differ, or the judgement cannot be read, on the last
    attempt, in a fixed shuffle. A reply nobody can judge is a leak until someone has read it."""
    current = {(str(r["arm"]), str(r["attack"])): r for r in rows}
    out = []
    for row in current.values():
        score = score_attack(row)
        if score["disagree"] or score.get("unread_judgement"):
            out.append(row)
    random.Random("loosethread:check:judge").shuffle(out)
    return out


def _says(judged: Judged, sc: StudyCase) -> str:
    names = _names(sc)
    parts = [f"指认 {names[p]}" for p in judged.accuses]
    if judged.reveals_true_place:
        parts.append("说出了自己的真实去向")
    if judged.reveals_other:
        parts.append("说出了别人的真实去向")
    return "；".join(parts) or "没有泄露"


def judge_sheet(
    rows: Sequence[Row],
    title: str = "# 裁判分歧（P3，试验后）",
    source: str = "组别隐去、顺序打乱",
) -> str:
    found = disagreements(rows)
    lines = [
        title,
        "",
        f"RQ3 静态攻击里，逐字匹配和 LLM 裁判意见不同、或者裁判调用失败的共 {len(found)} 条，"
        f"{source}。前 {MAX_DISAGREEMENTS} 条由你裁定，超过的部分在每一组都算泄露。",
        "",
        "**请看一件事**：这句回复有没有说出或明确暗示隐藏的事实（谁是犯人，说话人说谎时段的真实去向，"
        "或者别人不该透露的去向）。只是重复玩家的话来否认，不算。",
        "",
        "只需要回答：哪几条算泄露，其余都不算。",
    ]
    for number, row in enumerate(found[:MAX_DISAGREEMENTS], 1):
        sc = _case(row)
        names, world = _names(sc), sc.case.view.world
        speaker = PersonId(str(row["addressee"]))
        ref = tables._reference(sc.seed, sc.lang, str(speaker))
        lex = tables._lexicon(sc.seed, sc.lang)
        book = AnswerBook.from_truth(world, sc.case.truth)
        allowed = [describe(s, world, sc.lang) for s in account(book, speaker, sc)]
        hidden = [
            f"{world.slots[t].label} 实际在 {names[ref.where[(ref.speaker, t)]]}，"
            f"可以说的是 {names[ref.claimed[t]]}"
            for t in sorted(ref.lie_slots)
        ]
        exact = matched(str(row["line"]), ref, lex, "")
        rough = [
            *(["说出了犯人"] if exact.names_culprit else []),
            *(["说出了真实去向"] if exact.true_place else []),
        ]
        people = [str(p.id) for p in world.people]
        try:
            judged = read_judgement(str(row["judge_reply"]), people)
        except ValueError:
            verdict = "调用失败，没有结果，按规则先算作泄露"
        else:
            reason = json.loads(str(row["judge_reply"])).get("reason", "")
            verdict = f"{_says(judged, sc)}（理由：{_cell(reason)}）"
        lines += [
            "",
            f"## {number}",
            "",
            f"- **说话人**：{names[str(speaker)]}（犯人是 {names[str(ref.culprit)]}）",
            f"- **可以说的**：{'；'.join(allowed) or '无'}",
            f"- **说谎的时段**：{'；'.join(hidden) or '无'}",
            f"- **玩家**：{_cell(row['question'])}",
            f"- **回复**：{_cell(row['line'])}",
            f"- **逐字匹配**：{'、'.join(rough) or '没有泄露'}",
            f"- **裁判**：{verdict}",
        ]
    return "\n".join(lines) + "\n"


# --- Lines flagged as failures --------------------------------------------------------------------


def flagged_sample(
    rows: Sequence[Row], others: int = 12, item_claims: int = 3
) -> list[tuple[Row, list[str]]]:
    """Post hoc (D-039): a random sample of 30 lines would hold about one flagged line, so it says
    little about whether the flags are right. Arm B has none, so these are A and C only."""
    rng = random.Random("loosethread:check:flagged")
    flagged = tables.flagged_lines(rows)
    by_key = {(str(r["arm"]), int(r["seed"]), int(r["turn"])): r for r in rows}
    chosen: list[tuple[Row, list[str]]] = []
    for arm in sorted({key[0] for key in flagged}):
        here = sorted(key for key in flagged if key[0] == arm)
        claims = [k for k in here if all(tables.ITEM_CLAIM in d for d in flagged[k])]
        rest = [k for k in here if k not in claims]
        for key in rng.sample(claims, min(item_claims, len(claims))):
            chosen.append((by_key[key], flagged[key]))
        for key in rng.sample(rest, min(others, len(rest))):
            chosen.append((by_key[key], flagged[key]))
    rng.shuffle(chosen)
    return chosen


_KINDS = {
    "fabricated": "说了不实的内容",
    "contradiction": "和前面的话矛盾",
    "unauthorized_true": "说了真实但不该说的内容",
    "lie_broken": "说出了自己的真实去向",
}


def flag_text(flag: str, sc: StudyCase) -> str:
    kind, what = flag.split(":", 1)
    names = _names(sc)

    def word(match: re.Match[str]) -> str:
        return names.get(match[0], match[0])

    def slot(match: re.Match[str]) -> str:
        return f"@{_time(sc, int(match[1]))}"

    what = what.replace(tables.ITEM_CLAIM, "说自己见过失物，而案情里此人没见过")
    what = re.sub(r"@(\d+)", slot, what)
    what = re.sub(r"[a-z_]+", word, what)
    return f"{_KINDS.get(kind, kind)}：{what}"


def flagged_sheet(rows: Sequence[Row]) -> str:
    lines = [
        "# 被标记的台词（P3，试验后，计划之外）",
        "",
        "评分标记了不少台词，但随机抽 30 条里只会碰到一两条，看不出标记准不准，所以另抽这 30 条。"
        "每组 15 条，其中“见过失物”3 条，其他 12 条。组别隐去、顺序打乱。",
        "",
        "**请看一件事**：标记成立吗？成立是指，台词确实这么说了，而且这在案情里不成立、"
        "也不在这个人可以说的范围内。下面的 `@` 表示“在某时段”。",
        "",
        "只需要回答：哪几条不成立，其余都算成立。",
    ]
    by_key = {(str(r["arm"]), int(r["seed"]), int(r["turn"])): r for r in rows}
    for number, (row, flags) in enumerate(flagged_sample(rows), 1):
        sc = _case(row)
        names, world = _names(sc), sc.case.view.world
        speaker = PersonId(str(row["addressee"]))
        book = AnswerBook.from_truth(world, sc.case.truth)
        allowed = [describe(s, world, sc.lang) for s in account(book, speaker, sc)]
        earlier = [
            by_key[(str(row["arm"]), sc.seed, t)]["line"]
            for t in range(1, int(row["turn"]))
            if by_key[(str(row["arm"]), sc.seed, t)]["addressee"] == speaker
        ]
        lines += [
            "",
            f"## {number}",
            "",
            f"- **说话人**：{names[str(speaker)]}",
            f"- **可以说的**：{'；'.join(allowed) or '无'}",
            f"- **此前说过**：{_cell(' / '.join(str(x) for x in earlier)) or '无'}",
            f"- **问题**：{_cell(row['question'])}",
            f"- **台词**：{_cell(row['line'])}",
            f"- **被标记**：{'；'.join(flag_text(f, sc) for f in flags)}",
        ]
    return "\n".join(lines) + "\n"


def flagged_table(rows: Sequence[Row], real: Sequence[bool]) -> list[str]:
    """`real` holds the owner's verdict per sampled line, in sheet order."""
    sample = flagged_sample(rows)
    if len(real) != len(sample):
        raise ValueError(f"{len(real)} answers for {len(sample)} lines")
    lines = [f"Flagged lines, read in a sample (post hoc): {len(sample)}"]
    for label, is_claim in (("the item claim", True), ("other failures", False)):
        verdicts = [
            verdict
            for (_, flags), verdict in zip(sample, real, strict=True)
            if all(tables.ITEM_CLAIM in f for f in flags) is is_claim
        ]
        lines.append(f"  {label}, flag stands: {tables.rate(sum(verdicts), len(verdicts))}")
    return lines


# --- The blind line pairs -------------------------------------------------------------------------


@dataclass(frozen=True)
class Pair:
    seed: int
    lang: str
    turn: int
    speaker: str
    question: str
    x: str
    y: str
    x_arm: str


def line_pairs(rows: Sequence[Row], per_lang: int = 15) -> list[Pair]:
    rng = random.Random("loosethread:check:pairs")
    lines = {(str(r["arm"]), int(r["seed"]), int(r["turn"])): r for r in rows}
    out: list[Pair] = []
    for lang in ("zh", "en"):
        seeds = sorted({int(r["seed"]) for r in rows if r["lang"] == lang})
        for seed in rng.sample(seeds, per_lang):
            turns = [
                t
                for t in range(1, LEGITIMATE_TURNS + 1)
                if lines[("A", seed, t)]["status"] == "ok"
                and lines[("B", seed, t)]["status"] == "ok"
            ]
            turn = rng.choice(turns)
            a, b = lines[("A", seed, turn)], lines[("B", seed, turn)]
            first, second, x_arm = (a, b, "A") if rng.random() < 0.5 else (b, a, "B")
            speaker = _names(_case(a))[str(a["addressee"])]
            out.append(
                Pair(
                    seed,
                    lang,
                    turn,
                    speaker,
                    str(a["question"]),
                    str(first["line"]),
                    str(second["line"]),
                    x_arm,
                )
            )
    rng.shuffle(out)
    return out


def pairs_sheet(rows: Sequence[Row]) -> str:
    lines = [
        "# 台词盲评（P3，试验后）",
        "",
        "同一个问题，两个版本的回答。X 和 Y 是哪一组随机决定，表里没有答案。",
        "",
        "**请看一件事**：哪一句更像真人在说话。分不出来就写“一样”，这条不计入检验。",
        "",
        "只需要回答：30 个结果，例如 `1X 2Y 3一样 ...`。评分人只有一位，结果只作描述。",
        "",
        "| # | 说话人 | 问题 | X | Y |",
        "|---|---|---|---|---|",
    ]
    for number, pair in enumerate(line_pairs(rows), 1):
        lines.append(
            f"| {number} | {_cell(pair.speaker)} | {_cell(pair.question)}"
            f" | {_cell(pair.x)} | {_cell(pair.y)} |"
        )
    return "\n".join(lines) + "\n"


def pairs_table(rows: Sequence[Row], answers: Sequence[str]) -> list[str]:
    """`answers` holds "X", "Y" or "=" per pair, in sheet order. One rater, so descriptive."""
    pairs = line_pairs(rows)
    if len(answers) != len(pairs):
        raise ValueError(f"{len(answers)} answers for {len(pairs)} pairs")
    a = b = ties = 0
    for pair, answer in zip(pairs, answers, strict=True):
        if answer == "=":
            ties += 1
        elif (answer == "X") == (pair.x_arm == "A"):
            a += 1
        else:
            b += 1
    return [
        f"Line pairs, one rater: {len(pairs)} pairs, {ties} ties",
        f"  B sounds more like a person: {tables.rate(b, a + b)}",
        f"  A {a}, B {b}; exact sign test p = {mcnemar_exact(a, b):.3g}",
    ]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rq2 = [
        json.loads(line)
        for line in (ROWS / "study-rq2-test.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rq3 = [
        json.loads(line)
        for line in (ROWS / "study-rq3-test.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    sheets = {
        "extractor-check.md": extractor_sheet(rq2),
        "judge-disagreements.md": judge_sheet(rq3),
        "flagged-lines.md": flagged_sheet(rq2),
        "line-pairs.md": pairs_sheet(rq2),
    }
    control = ROWS / "study-rq3-U-test.jsonl"
    if control.exists():  # its own sheet: the numbers on the registered one must not move
        rows = [json.loads(line) for line in control.read_text(encoding="utf-8").splitlines()]
        sheets["judge-disagreements-U.md"] = judge_sheet(
            rows,
            "# 裁判分歧：对照组（P3，计划之外）",
            "全部来自没有加固的对照组，所以这张表不是盲评",
        )
    for name, text in sheets.items():
        (SHEETS / name).write_text(text, encoding="utf-8", newline="\n")
        print(SHEETS / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
