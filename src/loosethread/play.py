"""Play a case in the terminal.

python -m loosethread.play                      # today's case, Chinese, offline template backend
python -m loosethread.play --seed 213 --lang en
python -m loosethread.play --hard               # no contradiction hints
python -m loosethread.play --log session.jsonl  # per-turn log: questions, parses, lines, usage
"""

import argparse
import io
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from loosethread.case import hang, render_notebook, render_rules, render_sheet, render_truth, rule
from loosethread.game import DEFAULT_BUDGET, AccusationError, Game, Outcome, Turn
from loosethread.generator import DAILY, generate
from loosethread.lexicon import normalize
from loosethread.lines import TemplateWriter
from loosethread.model import Lang, PersonId, Query, QueryKind, Stance, World
from loosethread.notebook import describe
from loosethread.npc import ClarifyReason, LineWriter, QueryParser, Usage
from loosethread.parser import RuleParser

_UI: dict[str, tuple[str, str]] = {
    # The opening screen shows the short help, /help the full one (CP-6: less at once).
    "help_short": (
        "怎么玩\n"
        "  目标：找出犯人，并拿出两条不能同时成立的记录，揭穿犯人的谎。\n"
        "  同一时段多问几个人，说法对不上时会亮 ⚠。\n"
        "  提问：林小雨：你 21:15 在哪？（或用 @林小雨 开头；接着问同一个人直接输入）\n"
        "  一次问一个人、一个时段。每问花 1 次；没听懂的、问过的、闲聊不花。\n"
        "  指认：/指认 嫌疑人 编号 编号\n"
        "  其他命令：/笔记  /规则  /案情（人物、动机、全部规则）  /帮助  /退出",
        "How to play\n"
        "  Goal: name the culprit, with two items that cannot both be true, to expose their lie.\n"
        "  Ask several people about the same time; ⚠ shows when their stories clash.\n"
        "  Ask:  Lin Xiaoyu: where were you at 21:15?  (or @Lin; then just type)\n"
        "  One person, one time each. Costs 1; unclear questions, repeats, small talk: free.\n"
        "  Accuse: /accuse SUSPECT ID ID\n"
        "  Other commands: /notes  /rules  /case (the full sheet)  /help  /quit",
    ),
    "help": (
        "怎么玩\n"
        "  向某人提问：林小雨：你 21:15 在哪？（也可以用 @林小雨 开头）\n"
        "  接着问同一个人：直接输入问题。\n"
        "  能问的：某个时段在哪、和谁在一起、见没见过某人、什么时候去过某处、见没见过失物。\n"
        "  一次问一个人、一个时段。每个问题花 1 次；没听懂的、问过的、闲聊和案情外的话不花。\n"
        "  指认：/指认 嫌疑人 编号 编号。两个编号取自笔记（S）或证物（E），是不能同时成立的两条，"
        "其中一条是犯人的谎话。只能指认一次。\n"
        "  命令：/笔记  /规则  /案情  /指认  /帮助  /退出",
        "How to play\n"
        "  Ask someone:  Lin Xiaoyu: where were you at 21:15?  (or start with @Lin)\n"
        "  Ask the same person again: just type the question.\n"
        "  You can ask: where they were at a time, who was with them, whether they saw someone,"
        " when they were somewhere, whether they saw the stolen item.\n"
        "  One person and one time per question. Each costs 1; questions not understood, repeats,"
        " small talk and anything outside the case are free.\n"
        "  Accuse: /accuse SUSPECT ID ID. The ids come from your notebook (S) or the evidence (E):"
        " two items that cannot both be true, one of them the culprit's lie. One accusation only.\n"
        "  Commands: /notes  /rules  /case  /accuse  /help  /quit",
    ),
    "prompt": ("[还剩 {left} 问]{who}> ", "[{left} left]{who}> "),
    "no_addressee": (
        "先说明问谁，比如：林小雨：你 21:15 在哪？",
        "Say whom you are asking first, e.g.  Lin Xiaoyu: where were you at 21:15?",
    ),
    "to": ("现在问的是：{name}", "Now asking: {name}"),
    "unknown_person": ("没有这个人：{name}", "No such person: {name}"),
    "free_clarify": ("（没听懂，不计次数）", "(not understood; free)"),
    "free_unavailable": (
        "（连不上模型，不计次数，请再问一次）",
        "(could not reach the model; free, please ask again)",
    ),
    "free_repeat": ("（按“{q}”算问过了，不计次数）", "(read as “{q}”, asked before; free)"),
    "free_no_facts": ("（按“{q}”算，不计次数）", "(read as “{q}”; free)"),
    "noted": ("→ 按“{q}”记入笔记：{ids}", "→ read as “{q}”; noted: {ids}"),
    "nothing_new": ("→ 按“{q}”回答，没有新说法", "→ read as “{q}”; nothing new"),
    "answered": ("→ 按“{q}”回答", "→ read as “{q}”"),
    "conflict": ("⚠ {a} 与 {b} 不能同时成立", "⚠ {a} and {b} cannot both be true"),
    "notes_title": ("笔记（已记 {n} 条说法）", "Notebook ({n} statements)"),
    "statements": ("说法（时间指时段开始，21:15 即 21:15–21:30）：", "Statements (slot starts):"),
    "notes_empty": ("还没有问到任何说法。", "No statements yet."),
    "hints": ("矛盾提示：", "Contradiction hints:"),
    "no_hints": ("目前没有发现不能同时成立的两条。", "No contradictions found yet."),
    "hard": ("（困难模式：不提示矛盾）", "(hard mode: no contradiction hints)"),
    "evidence_ids": ("证物编号见 /案情。", "Evidence ids are on /case."),
    "out": (
        "问题用完了，现在请指认：/指认 嫌疑人 编号 编号",
        "No questions left. Make your accusation: /accuse SUSPECT ID ID",
    ),
    "accuse_usage": (
        "用法：/指认 嫌疑人 编号 编号，两个编号是不能同时成立的两条",
        "Usage: /accuse SUSPECT ID ID, two items that cannot both be true",
    ),
    "accuse_one": (
        "还差一个编号：指认要给出两条不能同时成立的记录。",
        "One more id: an accusation names two items that cannot both be true.",
    ),
    "conflicts_with": (
        "笔记里和 {x} 矛盾的：{ids}。",
        "In your notebook, {x} conflicts with {ids}.",
    ),
    "conflicts_none": (
        "笔记里还没有和 {x} 矛盾的记录。",
        "Nothing in your notebook conflicts with {x} yet.",
    ),
    "conflicts_related": (
        "笔记里和它们有关的矛盾：{pairs}。",
        "Contradictions in your notebook that involve them: {pairs}.",
    ),
    "not_suspect": ("{x} 不是嫌疑人。", "{x} is not a suspect."),
    "unknown_item": ("笔记和证物里都没有 {x}。", "There is no {x} in the notebook or evidence."),
    "same_item": ("两个编号不能相同。", "The two ids must differ."),
    "confirm": (
        "只能指认一次。确认指认 {name}，理由是 {a} 与 {b} 不能同时成立？(y/n) ",
        "You get one accusation. Accuse {name}, because {a} and {b} cannot both be true? (y/n) ",
    ),
    "confirm_no_conflict": (
        "注意：{a} 与 {b} 并不矛盾。只能指认一次，仍要指认 {name} 吗？(y/n) ",
        "Note: {a} and {b} do not contradict each other. You get one accusation;"
        " accuse {name} anyway? (y/n) ",
    ),
    "cancel": ("已取消。", "Cancelled."),
    "solved": ("破案！{stars}", "Solved! {stars}"),
    "hunch": (
        "人抓对了，但 {a} 和 {b} 没有揭穿 {name} 的谎言。☆",
        "Right person, but {a} and {b} do not expose a lie by {name}. ☆",
    ),
    "wrong": ("抓错人了。✗", "Wrong person. ✗"),
    "could_expose": (
        "笔记里能揭穿{name}谎言的：{pairs}。",
        "In your notebook, {pairs} would have exposed {name}'s lie.",
    ),
    "none_expose": (
        "笔记里还没有能揭穿{name}谎言的一对。",
        "Your notebook had no pair yet that exposes {name}'s lie.",
    ),
    "summary": (
        "用了 {used}/{budget} 问；这个案子最少 {min} 问能破。",
        "You used {used}/{budget} questions; this case can be solved in {min}.",
    ),
    "stars_rule": (
        "（本案：★★★ 不超过 {three} 问，★★ 不超过 {two} 问，★ 其余。）",
        "(This case: ★★★ within {three} questions, ★★ within {two}, ★ otherwise.)",
    ),
    "stars_rule_all": (
        "（本案：在 {budget} 问内破案即得 ★★★。）",
        "(This case: any solve within {budget} questions earns ★★★.)",
    ),
    "quit_confirm": ("确定退出吗？不会揭晓真相。(y/n) ", "Quit without seeing the truth? (y/n) "),
    "bye": ("再见。", "Goodbye."),
    "input_ended": ("（输入结束，游戏退出。）", "(Input ended; leaving the game.)"),
    "interrupted": ("（已中断。）", "(Interrupted.)"),
    "unknown_cmd": ("不认识的命令：{cmd}。见 /帮助。", "Unknown command: {cmd}; see /help."),
}  # fmt: skip

# What the parser understood, shown with every answered question so a misreading is visible.
_READ_AS: dict[QueryKind, tuple[str, str]] = {
    QueryKind.WHERE: ("{who} {t} 在哪", "where {who} was at {t}"),
    QueryKind.WHEN: ("{who}什么时候在{loc}", "when {who} was in the {loc}"),
    QueryKind.WITH_WHOM: ("{who} {t} 在哪、和谁在一起", "where {who} was at {t}, and with whom"),
    QueryKind.SAW_PERSON: ("{who}今晚见没见过{p}", "whether {who} saw {p} tonight"),
    QueryKind.ABOUT_ITEM: ("{who}见没见过{item}", "whether {who} saw the {item}"),
    QueryKind.OPINION: ("{who}怎么看{p}", "what {who} thinks of {p}"),
    QueryKind.SMALL_TALK: ("和{who}闲聊", "small talk with {who}"),
    QueryKind.OUT_OF_SCOPE: ("案情以外的问题", "a question outside the case"),
}
_SAW_AT = ("{who} {t} 见没见过{p}", "whether {who} saw {p} at {t}")

_COMMANDS: dict[str, str] = {
    "/help": "help", "/h": "help", "/?": "help", "/帮助": "help",
    "/notes": "notes", "/n": "notes", "/笔记": "notes",
    "/case": "case", "/c": "case", "/案情": "case",
    "/rules": "rules", "/r": "rules", "/规则": "rules",
    "/accuse": "accuse", "/a": "accuse", "/指认": "accuse",
    "/to": "to", "/问": "to",
    "/quit": "quit", "/q": "quit", "/退出": "quit",
}  # fmt: skip

_SEPARATORS = ":,;"  # after a name; NFKC turns full-width ：，； into these
_ASKING = frozenset(
    {"where", "who", "whom", "what", "when", "were", "did", "do", "have", "are", "tell"}
)


def _t(key: str, lang: Lang, **fields: object) -> str:
    zh, en = _UI[key]
    return (zh if lang is Lang.ZH else en).format(**fields)


def _asks_after_name(rest: str) -> bool:
    """A name, a space and a question address that person. An English word must be a question word:
    "Lin was with you at 9?" asks the current person about Lin."""
    words = rest.split(maxsplit=1)
    if not rest.startswith(" ") or not words:
        return False
    return not (words[0].isascii() and words[0].isalpha()) or words[0] in _ASKING


def read_as(query: Query, world: World, lang: Lang) -> str:
    """The query in third person, e.g. "苏曼 20:15–20:30 在哪"."""
    saw_at = query.kind is QueryKind.SAW_PERSON and query.slot is not None
    zh, en = _SAW_AT if saw_at else _READ_AS[query.kind]
    names = {p.id: p.name.get(lang) for p in world.people}
    fields = {
        "who": names[query.addressee],
        "t": world.slots[query.slot].label if query.slot is not None else "",
        "loc": next((x.name.get(lang) for x in world.locations if x.id == query.location), ""),
        "p": names.get(query.person, "") if query.person is not None else "",
        "item": next((i.name.get(lang) for i in world.items if i.id == query.item), ""),
    }
    return (zh if lang is Lang.ZH else en).format(**fields)


class Session:
    """The terminal front end: reads lines, talks to a `Game`, writes text."""

    def __init__(
        self,
        game: Game,
        read: Callable[[str], str],
        write: Callable[[str], None],
        hints: bool = True,
    ) -> None:
        self.game, self.read, self.write, self.hints = game, read, write, hints
        self.lang = game.lang
        self.current: PersonId | None = None
        self.names = {p.id: p.name.get(self.lang) for p in game.case.view.world.people}

    def say(self, key: str, **fields: object) -> None:
        self.write(_t(key, self.lang, **fields))

    def help(self, key: str = "help") -> None:
        lines: list[str] = []
        for line in _t(key, self.lang).split("\n"):
            body = line.lstrip()
            lines += hang(line[: len(line) - len(body)], body)
        self.write("\n".join(lines))

    def run(self) -> None:
        self.write("\n".join(render_sheet(self.game.case.view, self.lang, full=False)))
        self.help("help_short")
        while self.game.verdict is None:
            who = f" {self.names[self.current]}" if self.current else ""
            try:
                raw = self.read(_t("prompt", self.lang, left=self.game.left, who=who))
            except EOFError:  # say so: a game that just stops looks like a crash
                self.say("input_ended")
                return
            text = raw.lstrip("﻿").strip()  # piped input may start with a byte-order mark
            if not text:
                continue
            if text.startswith("/"):
                if self.command(text) == "quit":
                    return
            elif self.game.left <= 0:
                self.say("out")
            else:
                self.question(text)
        self.reveal()

    # --- Questions -----------------------------------------------------------------------------

    def _addressee(self, text: str) -> tuple[PersonId | None, str]:
        norm = normalize(text)
        at = norm.startswith("@")
        body = norm[1:].lstrip() if at else norm
        for alias, pid in self.game.lexicon.people_by_alias():
            rest = body[len(alias) :]
            if body.startswith(alias) and (at or rest[:1] in _SEPARATORS or _asks_after_name(rest)):
                return PersonId(pid), rest.lstrip(_SEPARATORS + " ")
        return None, text

    def question(self, text: str) -> None:
        addressee, question = self._addressee(text)
        if addressee is not None:
            self.current = addressee
        if self.current is None:
            self.say("no_addressee")
            return
        if not question.strip():
            self.say("to", name=self.names[self.current])
            return
        turn = self.game.ask(self.current, question)
        self.show(turn)
        if self.game.left <= 0:
            self.say("out")

    def show(self, turn: Turn) -> None:
        colon = "：" if self.lang is Lang.ZH else ": "
        self.write("\n".join(hang(f"  {self.names[turn.addressee]}{colon}", turn.line)))
        if turn.query is None:
            unavailable = turn.reason is ClarifyReason.UNAVAILABLE
            self.say("free_unavailable" if unavailable else "free_clarify")
            return
        q = read_as(turn.query, self.game.case.view.world, self.lang)
        if turn.repeat:
            self.say("free_repeat", q=q)
        elif not turn.cost:
            self.say("free_no_facts", q=q)
        elif turn.new_notes:
            sep = "、" if self.lang is Lang.ZH else ", "
            self.say("noted", q=q, ids=sep.join(turn.new_notes))
        elif turn.stance is Stance.ANSWER:
            self.say("nothing_new", q=q)
        else:
            self.say("answered", q=q)
        if self.hints:
            for a, b in turn.new_conflicts:
                self.say("conflict", a=a, b=b)

    # --- Commands ------------------------------------------------------------------------------

    def command(self, text: str) -> str:
        head, *args = text.split()
        name = _COMMANDS.get(head.lower())
        match name:
            case "help":
                self.help()
            case "notes":
                self.notes()
            case "case":
                self.write("\n".join(render_sheet(self.game.case.view, self.lang)))
            case "rules":
                self.write("\n".join(render_rules(self.lang)))
            case "to":
                self.switch(" ".join(args))
            case "accuse":
                self.accuse(args)
            case "quit":
                if self.confirm(_t("quit_confirm", self.lang)):
                    self.say("bye")
                    return "quit"
            case _:
                self.say("unknown_cmd", cmd=head)
        return name or ""

    def switch(self, name: str) -> None:
        pid = self.game.lexicon.person_named(name.lstrip("@"))
        if pid is None:
            self.say("unknown_person", name=name)
        else:
            self.current = PersonId(pid)
            self.say("to", name=self.names[self.current])

    def notes(self) -> None:
        nb = self.game.notebook
        statements = nb.statements
        title = _t("notes_title", self.lang, n=len(statements))
        if not statements:
            self.write(rule(title))
            self.say("notes_empty")
            return
        lines = render_notebook(nb.obtained_view(), self.lang, title=title, unknown="·")
        lines += ["", "  " + _t("statements", self.lang)]
        world = self.game.case.view.world
        for note_id, s in statements:
            lines += hang(f"  {note_id:<4}", describe(s, world, self.lang))
        lines += ["", "  " + _t("hints", self.lang)]
        if not self.hints:
            lines.append("  " + _t("hard", self.lang))
        elif nb.conflicts():
            lines += ["  " + _t("conflict", self.lang, a=a, b=b) for a, b in nb.conflicts()]
        else:
            lines.append("  " + _t("no_hints", self.lang))
        lines.append("  " + _t("evidence_ids", self.lang))
        self.write("\n".join(lines))

    def confirm(self, prompt: str) -> bool:
        try:
            answer = self.read(prompt)
        except EOFError:
            return False
        return normalize(answer) in {"y", "yes", "是", "确定", "确认", "好"}

    def _conflicts_text(self, pairs: Sequence[tuple[str, str]]) -> str:
        if self.lang is Lang.ZH:
            return "、".join(f"{x} 与 {y}" for x, y in pairs)
        return ", ".join(f"{x}/{y}" for x, y in pairs)

    def _one_id(self, args: list[str]) -> bool:
        """`/accuse NAME ID`: say a second id is needed and, in normal mode, which items conflict
        with the first. Both playtests named the right person with a pair that did not conflict."""
        nb = self.game.notebook
        note = args[-1].strip().upper() if args else ""
        if len(args) < 2 or nb.lookup(note) is None:
            return False
        if self.game.lexicon.person_named(" ".join(args[:-1])) is None:
            return False
        self.say("accuse_one")
        if self.hints:
            partners = [y if x == note else x for x, y in nb.conflicts() if note in (x, y)]
            sep = "、" if self.lang is Lang.ZH else ", "
            if partners:
                self.say("conflicts_with", x=note, ids=sep.join(partners))
            else:
                self.say("conflicts_none", x=note)
        return True

    def accuse(self, args: list[str]) -> None:
        if self._one_id(args):
            return
        if len(args) < 3:
            self.say("accuse_usage")
            return
        name, first, second = " ".join(args[:-2]), args[-2], args[-1]  # en names have spaces
        pid = self.game.lexicon.person_named(name)
        if pid is None:
            self.say("unknown_person", name=name)
            return
        suspect = PersonId(pid)
        try:
            a, b = self.game.check_accusation(suspect, first, second)
        except AccusationError as err:
            self.say(err.key, x=self.names.get(PersonId(err.detail), err.detail))
            return
        # In normal mode, warn using the same contradiction hints the player already sees.
        warn = self.hints and not self.game.notebook.in_conflict(a, b)
        if warn and (related := [p for p in self.game.notebook.conflicts() if a in p or b in p]):
            self.say("conflicts_related", pairs=self._conflicts_text(related))
        key = "confirm_no_conflict" if warn else "confirm"
        if not self.confirm(_t(key, self.lang, name=self.names[suspect], a=a, b=b)):
            self.say("cancel")
            return
        self.game.accuse(suspect, a, b)

    # --- End -----------------------------------------------------------------------------------

    def reveal(self) -> None:
        verdict = self.game.verdict
        assert verdict is not None
        a, b = verdict.pair
        lines = [""]
        match verdict.outcome:
            case Outcome.SOLVED:
                lines.append(_t("solved", self.lang, stars="★" * verdict.stars))
            case Outcome.HUNCH:
                lines.append(_t("hunch", self.lang, a=a, b=b, name=self.names[verdict.accused]))
            case Outcome.WRONG:
                lines.append(_t("wrong", self.lang))
        if verdict.outcome is not Outcome.SOLVED:
            culprit = self.names[self.game.case.truth.culprit]
            if pairs := self.game.exposing_pairs():
                zh = "、".join(f"{x} 与 {y}" for x, y in pairs)
                en = " or ".join(f"{x}/{y}" for x, y in pairs)
                text = zh if self.lang is Lang.ZH else en
                lines.append(_t("could_expose", self.lang, name=culprit, pairs=text))
            else:
                lines.append(_t("none_expose", self.lang, name=culprit))
        lines.append(
            _t(
                "summary",
                self.lang,
                used=verdict.questions_used,
                budget=verdict.budget,
                min=verdict.min_questions,
            )
        )
        rule = verdict.star_rule
        if rule.three >= verdict.budget:
            lines.append(_t("stars_rule_all", self.lang, budget=verdict.budget))
        else:
            lines.append(_t("stars_rule", self.lang, three=rule.three, two=rule.two))
        lines += ["", *render_truth(self.game.case, self.lang)]
        self.write("\n".join(lines))


# --- Session log ---------------------------------------------------------------------------------


def _query_row(query: Query | None) -> dict[str, Any] | None:
    if query is None:
        return None
    row: dict[str, Any] = {"kind": query.kind.value, "addressee": query.addressee}
    for name in ("slot", "location", "person", "item"):
        value = getattr(query, name)
        if value is not None:
            row[name] = value
    return row


def session_rows(
    game: Game, seed: int, backend: str, cost: Callable[[Usage], float] | None = None
) -> list[dict[str, Any]]:
    """One row per turn plus a summary row. Contains no credentials of any kind."""
    rows: list[dict[str, Any]] = []
    total = Usage()
    for turn in game.turns:
        total = total + turn.parse_usage + turn.line_usage
        rows.append(
            {
                "type": "turn",
                "n": turn.number,
                "addressee": turn.addressee,
                "question": turn.question,
                "query": _query_row(turn.query),
                "reason": turn.reason.value if turn.reason else None,
                "stance": turn.stance.value,
                "tone": turn.tone.value if turn.tone else None,
                "line": turn.line,
                "cost": turn.cost,
                "repeat": turn.repeat,
                "new_notes": list(turn.new_notes),
                "new_conflicts": [list(c) for c in turn.new_conflicts],
                "problems": list(turn.problems),
                "parse_usage": asdict(turn.parse_usage),
                "line_usage": asdict(turn.line_usage),
            }
        )
    verdict = game.verdict
    rows.append(
        {
            "type": "summary",
            "seed": seed,
            "lang": game.lang.value,
            "backend": backend,
            "questions_used": game.used,
            "budget": game.budget,
            "outcome": verdict.outcome.value if verdict else None,
            "stars": verdict.stars if verdict else None,
            "accused": verdict.accused if verdict else None,
            "pair": list(verdict.pair) if verdict else None,
            "min_questions": verdict.min_questions if verdict else None,
            "stars_three_within": verdict.star_rule.three if verdict else None,
            "stars_two_within": verdict.star_rule.two if verdict else None,
            "usage": asdict(total),
            "cost_cny_max": round(cost(total), 6) if cost else 0.0,
        }
    )
    return rows


def main(
    argv: Sequence[str] | None = None,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m loosethread.play", description=__doc__)
    parser.add_argument("--seed", type=int, help="case number (default: today's date)")
    parser.add_argument("--lang", choices=[lang.value for lang in Lang], default="zh")
    parser.add_argument("--hard", action="store_true", help="no contradiction hints")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--log", type=Path, help="write a JSONL session log here")
    parser.add_argument(
        "--backend",
        default="template",
        help="template (offline, default) or a model backend from llm/backends.toml"
        " (local, deepseek, ...); model backends need the `llm` extra",
    )
    args = parser.parse_args(argv)
    seed = args.seed if args.seed is not None else int(date.today().strftime("%Y%m%d"))
    if write is print and isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

    case = generate(seed, DAILY).case
    query_parser: QueryParser = RuleParser()
    writer: LineWriter = TemplateWriter()
    cost: Callable[[Usage], float] | None = None
    if args.backend != "template":
        # The optional extra is imported only when asked for, so the core stays stdlib-only.
        from loosethread.llm.client import open_model  # noqa: PLC0415
        from loosethread.llm.parser import LLMParser  # noqa: PLC0415
        from loosethread.llm.writer import LLMWriter  # noqa: PLC0415

        model = open_model(args.backend)
        query_parser, writer, cost = LLMParser(model), LLMWriter(model), model.backend.cost
    game = Game(case, query_parser, writer, Lang(args.lang), budget=args.budget)
    code = 0
    try:
        Session(game, read, write, hints=not args.hard).run()
    except KeyboardInterrupt:  # Ctrl-C ends the session
        write(_t("interrupted", game.lang))
        code = 130
    finally:  # a cut-short or crashed playtest still keeps its turns
        if args.log:
            rows = session_rows(game, seed, args.backend, cost)
            text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
            args.log.parent.mkdir(parents=True, exist_ok=True)
            args.log.write_text(text, encoding="utf-8", newline="\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
