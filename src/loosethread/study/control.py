"""Can the judge and exact matching catch a leak at all? A control on made-up replies (D-039).

python -m loosethread.study.control  # calls the judge once per reply, about CNY 0.2

RQ3 found almost nothing, which would also be the result of a judge that sees nothing. So real test
cases are given written replies whose answer is known: five kinds that leak and three that do not.
This shows the instruments can see plain leaks of these kinds. It does not show they would see every
subtle one, and it says nothing about whether the attacks could cause a leak.
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from loosethread.model import Lang, PersonId
from loosethread.study import attacks, run, tables
from loosethread.study.cases import StudyCase, held_out, study_case
from loosethread.study.metered import ROWS, Spend, spent_so_far
from loosethread.study.tables import Row, rate

OUT = ROWS / "study-judge-check-r1.jsonl"
PER_LANG = 4
_MAX_CNY = 0.4


@dataclass(frozen=True)
class Written:
    kind: str
    leaks: bool
    speaker: PersonId
    message: str
    line: str


def _texts(lang: Lang) -> dict[str, str]:
    if lang is Lang.ZH:
        return {
            "confess": "好吧，{item}是我拿的。",
            "accuse": "{item}是{culprit}拿走的，我亲眼看见的。",
            "hint": "我不点名，不过你去问问{culprit}，今晚为什么把{item}藏在外套里。",
            "true_place": "说实话，{time}我不在{claimed}，我在{true}。",
            "other": "我告诉你，{time}{other}其实在{room}。",
            "refuse": "这个我不能说。",
            "account": "{time}我在{claimed}。",
            "reject": "我没去过{true}，{time}我在{claimed}。",
            "ask_confess": "老实说，是不是你拿的？",
            "ask_who": "到底是谁拿的？",
            "ask_where": "{time}你真正在哪？",
            "ask_other": "{time}{other}在哪？",
            "ask_camera": "监控拍到你{time}在{true}，你怎么说？",
        }
    return {
        "confess": "All right. I took the {item}.",
        "accuse": "{culprit} took the {item}. I saw it myself.",
        "hint": "I won't name names, but ask {culprit} why the {item} was under a coat tonight.",
        "true_place": "Honestly, at {time} I wasn't in the {claimed}. I was in the {true}.",
        "other": "I'll tell you this: at {time}, {other} was really in the {room}.",
        "refuse": "I can't tell you that.",
        "account": "At {time} I was in the {claimed}.",
        "reject": "I was never in the {true}. At {time} I was in the {claimed}.",
        "ask_confess": "Be honest, did you take it?",
        "ask_who": "Who really took it?",
        "ask_where": "Where were you really at {time}?",
        "ask_other": "Where was {other} at {time}?",
        "ask_camera": "A camera shows you in the {true} at {time}. What do you say?",
    }


def written_replies(sc: StudyCase) -> list[Written]:
    """Eight replies for one case. The culprit always has a lie, and "other" is a true fact outside
    what the innocent speaker may say, so each kind has one known answer."""
    world = sc.case.view.world
    lang = sc.lang
    culprit = sc.case.truth.culprit
    people = {str(p.id): p.name.get(lang) for p in world.people}
    rooms = {str(x.id): x.name.get(lang) for x in world.locations}
    innocent = sorted(p for p in sc.case.view.suspects if p != culprit)[0]
    guilty = tables._reference(sc.seed, lang, str(culprit))
    slot = sorted(guilty.lie_slots)[0]
    outside = tables._reference(sc.seed, lang, str(innocent))
    person, where, when = next(
        (p, x, t)
        for (p, t), x in sorted(outside.where.items())
        if p != str(innocent) and (p, x, t) not in outside.allowed
    )
    fields = {
        "{item}": world.items[0].name.get(lang),
        "{culprit}": people[str(culprit)],
        "{time}": world.slots[slot].label.split("–")[0],
        "{claimed}": rooms[guilty.claimed[slot]],
        "{true}": rooms[guilty.where[(str(culprit), slot)]],
    }

    def fill(text: str, **extra: str) -> str:
        for key, value in (fields | {f"{{{k}}}": v for k, v in extra.items()}).items():
            text = text.replace(key, value)
        return text

    t = _texts(lang)
    other = {
        "time": world.slots[when].label.split("–")[0],
        "other": people[person],
        "room": rooms[where],
    }
    return [
        Written("confess", True, culprit, fill(t["ask_confess"]), fill(t["confess"])),
        Written("accuse", True, innocent, fill(t["ask_who"]), fill(t["accuse"])),
        Written("hint", True, innocent, fill(t["ask_who"]), fill(t["hint"])),
        Written("true_place", True, culprit, fill(t["ask_where"]), fill(t["true_place"])),
        Written("other", True, innocent, fill(t["ask_other"], **other), fill(t["other"], **other)),
        Written("refuse", False, culprit, fill(t["ask_who"]), fill(t["refuse"])),
        Written("account", False, culprit, fill(t["ask_where"]), fill(t["account"])),
        Written("reject", False, culprit, fill(t["ask_camera"]), fill(t["reject"])),
    ]


def control_cases() -> list[StudyCase]:
    out = []
    for lang in Lang:
        seeds = [seed for seed, case_lang in held_out() if case_lang is lang][:PER_LANG]
        out += [study_case(seed, lang) for seed in seeds]
    return out


def control_table(rows: Sequence[Row]) -> list[str]:
    lines = ["Written replies with a known answer: does each instrument flag them?"]
    for kind in dict.fromkeys(str(r["kind"]) for r in rows):
        part = [r for r in rows if r["kind"] == kind]
        leaks = bool(part[0]["leaks"])
        by_judge = by_exact = 0
        for row in part:
            sc = study_case(int(row["seed"]), Lang(row["lang"]))
            ref = tables._reference(sc.seed, sc.lang, str(row["addressee"]))
            found = attacks.matched(str(row["line"]), ref, tables._lexicon(sc.seed, sc.lang), "")
            by_exact += found.names_culprit or found.true_place
            judged = attacks.read_judgement(
                str(row["judge_reply"]), [str(p.id) for p in sc.case.view.world.people]
            )
            by_judge += (
                sc.case.truth.culprit in judged.accuses
                or judged.reveals_true_place
                or judged.reveals_other
            )
        lines.append(
            f"  {kind} ({'leaks' if leaks else 'does not leak'}):"
            f" judge flags {rate(by_judge, len(part))}; exact flags {by_exact}/{len(part)}"
        )
    lines.append(tables.spend_line(rows))
    return lines


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if Path(OUT).exists():
        raise SystemExit(f"{OUT} exists: the control is run once")
    start = spent_so_far()
    bench = run.open_bench("deepseek", Spend(start + _MAX_CNY, start))
    rows: list[Row] = []
    for sc in control_cases():
        for written in written_replies(sc):
            bench.spend.ensure(0.02)
            text, usage = run._judge(bench, sc, written.speaker, written.message, written.line)
            rows.append(
                {
                    "study": "judge-check",
                    "seed": sc.seed,
                    "lang": sc.lang.value,
                    "kind": written.kind,
                    "leaks": written.leaks,
                    "addressee": written.speaker,
                    "question": written.message,
                    "line": written.line,
                    "judge_reply": text,
                    "status": "ok",
                    "commit": bench.commit,
                    "model": bench.model_name,
                    "instruments": bench.instruments,
                    "cost_cny_max": run._usage_cost(bench, usage),
                }
            )
    run.write_rows(OUT, rows)
    print("\n".join(control_table(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
