"""Debug CLI: print a generated case as readable text, or run a batch and report statistics.

python -m loosethread.case --seed 7                # zh, including the truth
python -m loosethread.case --seed 7 --lang en --hide-truth
python -m loosethread.case --batch 1000 --metrics  # acceptance, timing, metric distributions
"""

import argparse
import io
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from loosethread.audit import audit
from loosethread.content import load_pack
from loosethread.difficulty import Metrics, measure
from loosethread.generator import (
    DAILY,
    ContradictionRule,
    Generated,
    GenParams,
    daily_case,
    generate,
)
from loosethread.lookup import AnswerBook
from loosethread.model import (
    Basis,
    Case,
    ItemAt,
    Lang,
    LieReason,
    LocationId,
    Occupants,
    PersonAt,
    PersonId,
    PlayerView,
    Query,
    QueryKind,
    SlotIndex,
    Statement,
    World,
)
from loosethread.stats import percentile, wilson

_UI: dict[str, tuple[str, str]] = {
    "title": ("破绽 · {setting} · 案件 #{seed}", "Loose Thread · {setting} · case #{seed}"),
    "facts": ("案情", "The case"),
    "f_item": ("失物", "Stolen"),
    "f_item_v": ("{item}（失主：{owner}）", "the {item} (owner: {owner})"),
    "f_scene": ("现场", "Scene"),
    "f_seen": ("最后确认还在", "Last seen"),
    "f_found": ("发现失窃", "Found missing"),
    "f_window": ("作案时间窗", "Theft window"),
    "f_window_v": (
        "{start}–{end}，共 {n} 个时段（每段 {m} 分钟）",
        "{start}–{end}, {n} slots of {m} minutes",
    ),
    "people": ("在场的人", "Who was there"),
    "suspect_head": ("◆ {name} · {role}", "◆ {name} · {role}"),
    "client_head": (
        "◇ {name} · {role}（失主，不是嫌疑人）",
        "◇ {name} · {role} (the owner, not a suspect)",
    ),
    "persona": ("印象：{text}", "Impression: {text}"),
    "motive": ("动机：{text}", "Motive: {text}"),
    "suspects_short": ("嫌疑人：{people}", "Suspects: {people}"),
    "person_short": ("{name}（{role}）", "{name} ({role})"),
    "client_short": (
        "失主：{name}（{role}），不是嫌疑人。",
        "Owner: {name} ({role}), not a suspect.",
    ),
    "map": ("地图", "Map"),
    "rules": ("推理规则", "Rules"),
    "key_rules": ("推理要点", "Key rules"),
    "evidence": (
        "证物（一定为真；[ ] 内是它所属的时段）",
        "Evidence (always true; [ ] = the slot it belongs to)",
    ),
    "notes": ("证词笔记", "Testimony notebook"),
    "notes_legend": (
        "每人两行。在：自称在哪；同：自称同处一室的人（只写姓），“独自”表示自称没有别人。"
        "时段 21:15 指 21:15–21:30。",
        "Two rows per person. at: where they say they were; with: who they say was in the room"
        ' (surnames), "alone" meaning nobody else. Slot 21:15 means 21:15–21:30.',
    ),
    "tag_at": ("在", "at"),
    "tag_with": ("同", "with"),
    "alone": ("独自", "alone"),
    "band": ("作案时间窗", "theft window"),
    "extra": ("其他说法：", "Also on record:"),
    "item_seen": ("{p}：{time} 亲眼见过{item}。", "{p}: saw the {item} at {time}."),
    "heard": ("{p}听说：{told}。", "{p} heard: {told}."),
    "told": ("{src}说自己 {time} 在{loc}", "{src} said they were in the {loc} at {time}"),
    "verdict": ("你的结论", "Your verdict"),
    "verdict_body": (
        "犯人是 ________，\n因为 ________ 和 ________ 不可能同时成立。\n（先写下结论，再看真相。）",
        "The culprit is ________,\nbecause ________ and ________ cannot both be true.\n"
        "(Write it down before you look at the truth.)",
    ),
    "truth": ("真相（剧透）", "Truth (spoilers)"),
    "culprit": (
        "犯人：{name}，{time} 独自在{loc}下手。",
        "Culprit: {name}, alone in the {loc} at {time}.",
    ),
    "timeline": (
        "真实行踪（* 下手的时段；! 本人在这一格撒了谎）",
        "True whereabouts (* the theft; ! they lied about this slot)",
    ),
    "lies": ("谎言：", "Lies:"),
    "lie": (
        "{name}（{why}）声称 {time} 在{claim}{company}，实际在{real}。能揭穿它的：{by}",
        "{name} ({why}) claims the {claim}{company} at {time}, was really in the {real}."
        " Exposed by: {by}",
    ),
    "lie_with": ("，和{others}在一起", " with {others}"),
    "alibi": ("编造不在场证明", "alibi"),
    "privacy": ("隐私小谎", "privacy"),
    "metrics": ("难度（调试数据）", "Difficulty (debug)"),
    "plan": ("一种最短问法：", "A shortest question plan:"),
    "q_where": ("问{p}：{time} 你在哪？", "Ask {p}: where were you at {time}?"),
    "q_when": ("问{p}：你什么时候去过{loc}？", "Ask {p}: when were you in the {loc}?"),
    "q_with_whom": ("问{p}：{time} 你和谁在一起？", "Ask {p}: who was with you at {time}?"),
    "q_saw_person": ("问{p}：今晚见过{x}吗？", "Ask {p}: did you see {x} tonight?"),
    "q_saw_person_slot": ("问{p}：{time} 见过{x}吗？", "Ask {p}: did you see {x} at {time}?"),
    "q_about_item": ("问{p}：你见过{item}吗？", "Ask {p}: did you see the {item}?"),
}

# DESIGN §3–4 in player words (W1+W3, W2, W4, T1, T2+T3, T4, T5).
_RULES: tuple[tuple[str, str], ...] = (
    (
        "每人每个时段只在一个地方；同一时段同处一室的人一定互相看见。",
        "Everyone is in exactly one place per slot; people in the same room in the same slot"
        " see each other.",
    ),
    (
        "相邻两个时段之间，只能原地不动，或沿地图连线走一步。",
        "From one slot to the next, a person stays put or moves one step along a map line.",
    ),
    (
        "犯人在作案时间窗内，至少有一个时段独自待在现场。",
        "During the theft window the culprit was alone at the scene for at least one slot.",
    ),
    ("证物一定为真。", "Evidence is always true."),
    (
        "无辜者（包括失主）在作案时间窗内从不说谎；窗外的小谎一定能被证物戳穿。",
        "Innocent people (the owner included) never lie about the theft window; any lie they"
        " tell about other times is exposed by evidence.",
    ),
    ("犯人会为了不在场证明撒谎。", "The culprit lies to protect their alibi."),
    (
        "“听说”如实转述原话，可信度等同于说原话的人。",
        "Hearsay repeats exactly what the source said, and is as reliable as the source.",
    ),
)
# The opening screen's short form of the rules above (CP-6: the full sheet was too much at once).
_KEY_RULES: tuple[tuple[str, str], ...] = (
    (
        "犯人在作案时间窗内，至少有一个时段独自待在现场。",
        "During the theft window the culprit was alone at the scene for at least one slot.",
    ),
    (
        "无辜者在作案时间窗内从不说谎；证物一定为真。",
        "Innocent people never lie about the theft window; evidence is always true.",
    ),
    (
        "同一时段同处一室的人一定互相看见；相邻时段之间只能原地不动或沿地图连线走一步。",
        "People in the same room in the same slot see each other; between slots a person stays"
        " put or moves one step along a map line.",
    ),
)

WIDTH = 80  # page width in display columns (CJK characters count as 2)


def _t(key: str, lang: Lang, **fields: object) -> str:
    zh, en = _UI[key]
    return (zh if lang is Lang.ZH else en).format(**fields)


class _Names:
    def __init__(self, world: World, lang: Lang) -> None:
        self.lang = lang
        self.person = {p.id: p.name.get(lang) for p in world.people}
        self.loc = {loc.id: loc.name.get(lang) for loc in world.locations}
        self.slot = {int(s.index): s for s in world.slots}
        self.order = [p.id for p in world.people]
        # Surnames when they are unique (they are in the default roster), else full names.
        surname = {
            pid: name[0] if lang is Lang.ZH else name.split()[0]
            for pid, name in self.person.items()
        }
        unique = len(set(surname.values())) == len(surname)
        self.short = surname if unique else dict(self.person)
        self.sep = ("" if unique else "、") if lang is Lang.ZH else ","
        self.row = self.person if lang is Lang.ZH else self.short  # grid name column

    def time(self, slot: int) -> str:
        return self.slot[slot].label.split("–")[0]

    def group(self, ids: frozenset[PersonId]) -> str:
        return self.sep.join(self.short[p] for p in self.order if p in ids)


# --- Text layout ---------------------------------------------------------------------------------


def display_width(text: str) -> int:
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def _fit(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def rule(title: str) -> str:
    head = f"─── {title} "
    return head + "─" * max(3, WIDTH - display_width(head))


_NO_LINE_START = frozenset("，。、；：？！）》」』”’,.;:?!)")
_BREAK_AFTER = frozenset("，。、；：？！）》」』”")
_MAX_CARRY = 12  # columns of CJK text that may move down to break at punctuation instead
_WIDE = f"{chr(0x2E80)}-{chr(0xFFFF)}"  # the range `display_width` counts as two columns
# Tokens: a run of narrow non-space characters (a word, number or time), a space run, or one
# wide character.
_TOKEN = re.compile(rf"[^\s{_WIDE}]+|\s+|.")


def wrap(text: str, width: int) -> list[str]:
    """Greedy wrap by display width. ASCII words and numbers stay whole; CJK text prefers to
    break after punctuation, so names are not split across lines."""
    lines: list[str] = []
    line, used = "", 0
    for token in _TOKEN.findall(text):
        size = display_width(token)
        if used + size > width and line.strip():
            if token[0] in _NO_LINE_START:
                # Punctuation may not start a line: take the last CJK character down with it.
                carry = line[-1] if display_width(line[-1]) == 2 else ""
            else:
                cut = max((i for i, ch in enumerate(line) if ch in _BREAK_AFTER), default=-1)
                carry = line[cut + 1 :] if cut >= 0 and size == 2 else ""
                if display_width(carry) > _MAX_CARRY:
                    carry = ""
            if carry == line:  # nothing would remain; overflow instead
                line += token
                used += size
                continue
            lines.append(line[: len(line) - len(carry)].rstrip())
            line, used = carry, display_width(carry)
            if token.isspace():
                continue
        line += token
        used += size
    lines.append(line.rstrip())
    # No orphan of one or two CJK characters on the last line: pull two down with it.
    if len(lines) > 1 and display_width(lines[-1]) <= 4:
        tail = lines[-2][-2:]
        if len(tail) == 2 and all(display_width(ch) == 2 for ch in tail):
            lines[-2], lines[-1] = lines[-2][:-2], tail + lines[-1]
    return lines


def hang(prefix: str, text: str) -> list[str]:
    """`prefix` + `text` wrapped to the page width, continuation lines aligned after the prefix."""
    pad = display_width(prefix)
    first, *rest = wrap(text, WIDTH - pad)
    return [prefix + first, *(" " * pad + line for line in rest)]


@dataclass(frozen=True)
class _Row:
    name: str
    tag: str
    cells: tuple[str, ...]  # one per time slot


def _grid(nm: _Names, window: Sequence[SlotIndex], rows: Sequence[_Row]) -> list[str]:
    """A people × time-slot table; vertical bars box in the theft window."""
    first, last = int(window[0]), int(window[-1])
    table = [_Row("", "", tuple(nm.time(t) for t in sorted(nm.slot))), *rows]
    count = len(table[0].cells)
    widths = [max(display_width(r.cells[i]) for r in table) + 2 for i in range(count)]
    name_w = max(display_width(r.name) for r in table) + 2
    tag_w = max(display_width(r.tag) for r in table)
    tag_w += 2 if tag_w else 0

    def line(row: _Row) -> str:
        parts = ["  ", _fit(row.name, name_w), _fit(row.tag, tag_w)]
        for i, cell in enumerate(row.cells):
            if i in (first, last + 1):
                parts.append("│ ")
            parts.append(_fit(cell, widths[i]))
        if last + 1 == count:
            parts.append("│")
        return "".join(parts).rstrip()

    left = 2 + name_w + tag_w + sum(widths[:first])
    inner = 1 + sum(widths[first : last + 1])
    label = f" {_t('band', nm.lang)} "
    fill = max(0, inner - display_width(label))
    band = " " * left + "┌" + "─" * (fill // 2) + label + "─" * (fill - fill // 2) + "┐"
    return [band, *(line(r) for r in table)]


# --- Case rendering ------------------------------------------------------------------------------


def render_case(case: Case, lang: Lang = Lang.ZH, show_truth: bool = True) -> str:
    out = render_sheet(case.view, lang)
    out += render_notebook(case.view, lang)
    out.append("")
    out.append(rule(_t("verdict", lang)))
    out += ["  " + line for line in _t("verdict_body", lang).split("\n")]
    if show_truth:
        out += ["", *render_truth(case, lang)]
    return "\n".join(out)


def render_rules(lang: Lang) -> list[str]:
    out = [rule(_t("rules", lang))]
    for i, (zh, en) in enumerate(_RULES, 1):
        out += hang(f"  {i}. ", zh if lang is Lang.ZH else en)
    return out


def render_sheet(view: PlayerView, lang: Lang, full: bool = True) -> list[str]:
    """Banner, story, case facts, people, map, rules and evidence; ends with a blank line.

    `full=False` is the opening screen: people without impressions and motives, and the key
    rules instead of all of them.
    """
    world = view.world
    nm = _Names(world, lang)
    pack = load_pack(view.pack_id)
    item = world.items[0]
    client = next(p for p in world.people if p.id not in view.suspects)
    crime, window = view.crime, view.crime.window
    out: list[str] = []

    title = _t("title", lang, setting=pack.setting.get(lang), seed=view.seed)
    out += ["═" * WIDTH, " " * ((WIDTH - display_width(title)) // 2) + title, "═" * WIDTH, ""]
    intro = pack.intro.get(lang).format(
        setting=pack.setting.get(lang),
        client=nm.person[client.id],
        item=item.name.get(lang),
        seen=nm.slot[crime.last_seen].label,
        found=nm.time(crime.discovered),
    )
    for line in intro.split("\n"):
        out += hang("  ", line) if line else [""]
    out.append("")

    out.append(rule(_t("facts", lang)))
    end = nm.slot[window[-1]].label.split("–")[1]
    length = world.slots[0].end_minute - world.slots[0].start_minute
    span = _t("f_window_v", lang, start=nm.time(window[0]), end=end, n=len(window), m=length)
    facts = [
        ("f_item", _t("f_item_v", lang, item=item.name.get(lang), owner=nm.person[client.id])),
        ("f_scene", nm.loc[crime.location]),
        ("f_seen", nm.slot[crime.last_seen].label),
        ("f_found", nm.slot[crime.discovered].label),
        ("f_window", span),
    ]
    label_w = max(display_width(_t(key, lang)) for key, _ in facts) + 2
    out += [f"  {_fit(_t(key, lang), label_w)}{value}" for key, value in facts]
    out.append("")

    out.append(rule(_t("people", lang)))
    suspects = [p for p in world.people if p.id in view.suspects]
    if full:
        motives = {m.person: m.reason.get(lang) for m in view.motives}
        for p in [*suspects, client]:
            head = "suspect_head" if p.id in view.suspects else "client_head"
            out.append("  " + _t(head, lang, name=nm.person[p.id], role=p.role.get(lang)))
            out += hang("    ", _t("persona", lang, text=p.persona.get(lang)))
            if p.id in motives:
                out += hang("    ", _t("motive", lang, text=motives[p.id]))
    else:
        short = [
            _t("person_short", lang, name=nm.person[p.id], role=p.role.get(lang)) for p in suspects
        ]
        out += hang(
            "  ", _t("suspects_short", lang, people=("、" if lang is Lang.ZH else ", ").join(short))
        )
        out += hang(
            "  ", _t("client_short", lang, name=nm.person[client.id], role=client.role.get(lang))
        )
    out.append("")

    out.append(rule(_t("map", lang)))
    present = frozenset(loc.id for loc in world.locations)
    out += ["  " + line for line in pack.map_picture(lang, present).split("\n")]
    out.append("")

    if full:
        out += render_rules(lang)
    else:
        out.append(rule(_t("key_rules", lang)))
        for zh, en in _KEY_RULES:
            out += hang("  · ", zh if lang is Lang.ZH else en)
    out.append("")

    out.append(rule(_t("evidence", lang)))
    for e in view.evidence:
        slots = sorted({int(f.slot) for f in e.establishes})
        tag = "/".join(nm.time(t) for t in slots)
        out += hang(f"  {e.id} [{tag}] ", e.text.get(lang))
    out.append("")
    return out


def render_notebook(
    view: PlayerView, lang: Lang, title: str | None = None, unknown: str = "?"
) -> list[str]:
    """The testimony grid for every statement in `view`; `unknown` fills cells nobody spoke to."""
    nm = _Names(view.world, lang)
    out = [rule(title or _t("notes", lang)), *hang("  ", _t("notes_legend", lang)), ""]
    return out + _testimony_block(view, nm, unknown)


def _testimony_block(view: PlayerView, nm: _Names, unknown: str = "?") -> list[str]:
    lang = nm.lang
    slots = sorted(nm.slot)
    item = view.world.items[0].name.get(lang)
    by_speaker: dict[PersonId, list[Statement]] = {}
    for s in view.statements:
        by_speaker.setdefault(s.speaker, []).append(s)
    rows: list[_Row] = []
    extras: list[str] = []
    for person in view.world.people:
        stmts = by_speaker.get(person.id, [])
        at = {
            int(s.claim.slot): nm.loc[s.claim.location]
            for s in stmts
            if s.basis is Basis.WITNESSED  # "with Lin in the kitchen" and "saw Lin there" say where
        }
        company = {
            int(s.claim.slot): s.claim.people - {person.id}
            for s in stmts
            if isinstance(s.claim, Occupants)
        }
        rows += [
            _Row(nm.row[person.id], _t("tag_at", lang), tuple(at.get(t, unknown) for t in slots)),
            _Row(
                "",
                _t("tag_with", lang),
                tuple(
                    (nm.group(company[t]) or _t("alone", lang)) if t in company else ""
                    for t in slots
                ),
            ),
            _Row("", "", ("",) * len(slots)),  # spacer; keeps the window bars continuous
        ]
        seen = sorted(int(s.claim.slot) for s in stmts if isinstance(s.claim, ItemAt))
        if seen:
            times = ("、" if lang is Lang.ZH else ", ").join(nm.time(t) for t in seen)
            extras.append(_t("item_seen", lang, p=nm.person[person.id], time=times, item=item))
        for s in stmts:
            if s.basis is Basis.HEARSAY and isinstance(s.claim, PersonAt):
                assert s.source is not None
                told = _t(
                    "told",
                    lang,
                    src=nm.person[s.source],
                    time=nm.time(int(s.claim.slot)),
                    loc=nm.loc[s.claim.location],
                )
                extras.append(_t("heard", lang, p=nm.person[person.id], told=told))
    lines = _grid(nm, view.crime.window, rows[:-1])
    if extras:
        lines += ["", "  " + _t("extra", lang)]
        for extra in extras:
            lines += hang("  · ", extra)
    return lines


def render_truth(case: Case, lang: Lang) -> list[str]:
    nm = _Names(case.view.world, lang)
    truth = case.truth
    (theft,) = truth.events
    where: dict[tuple[PersonId, int], LocationId] = {
        (f.person, int(f.slot)): f.location for f in truth.timeline
    }
    lied = {(lie.statement.speaker, int(lie.statement.claim.slot)) for lie in truth.lies}
    rows = []
    for p in case.view.world.people:
        cells = []
        for t in sorted(nm.slot):
            mark = "*" if p.id == truth.culprit and t == int(theft.slot) else ""
            mark += "!" if (p.id, t) in lied else ""
            cells.append(nm.loc[where[(p.id, t)]] + mark)
        rows.append(_Row(nm.row[p.id], "", tuple(cells)))
    culprit = _t(
        "culprit",
        lang,
        name=nm.person[truth.culprit],
        time=nm.slot[int(theft.slot)].label,
        loc=nm.loc[theft.location],
    )
    lines = [
        rule(_t("truth", lang)),
        "  " + culprit,
        "",
        *hang("  ", _t("timeline", lang)),
        *_grid(nm, case.view.crime.window, rows),
        "",
        "  " + _t("lies", lang),
    ]
    book = AnswerBook.from_truth(case.view.world, truth)
    sep = "、" if lang is Lang.ZH else ", "
    for lie in truth.lies:
        claim = lie.statement.claim
        speaker, slot = lie.statement.speaker, int(claim.slot)
        by = [x if isinstance(x, str) else nm.person[x.speaker] for x in lie.exposed_by]
        others = claim.people - {speaker} if isinstance(claim, Occupants) else frozenset()
        named = sep.join(nm.person[p] for p in nm.order if p in others)
        text = _t(
            "lie",
            lang,
            name=nm.person[speaker],
            why=_t("alibi" if lie.reason is LieReason.ALIBI else "privacy", lang),
            time=nm.time(slot),
            claim=nm.loc[book.claimed_location(speaker, slot)],
            company=_t("lie_with", lang, others=named) if named else "",
            real=nm.loc[where[(speaker, slot)]],
            by=sep.join(dict.fromkeys(by)),
        )
        lines += hang("  · ", text)
    return lines


def _metrics_block(metrics: Metrics, nm: _Names, case: Case) -> str:
    lines = [
        f"  contradictions_required = {metrics.contradictions_required}",
        f"  min_questions           = {metrics.min_questions}"
        + ("" if metrics.min_questions_exact else " (greedy upper bound)"),
        f"  inference_steps         = {metrics.inference_steps}",
        f"  conflict_pairs          = {metrics.conflict_pairs}",
        f"  naive_suspects          = {metrics.naive_suspects}",
        f"  trusting_suspects       = {metrics.trusting_suspects}",
        "  " + _t("plan", nm.lang),
    ]
    item = case.view.world.items[0].name.get(nm.lang)
    lines += [
        f"    {i}. {_render_query(q, nm, item)}" for i, q in enumerate(metrics.question_plan, 1)
    ]
    return "\n".join(lines)


def _render_query(query: Query, nm: _Names, item: str) -> str:
    fields = {
        "p": nm.person[query.addressee],
        "time": nm.time(query.slot) if query.slot is not None else "",
        "loc": nm.loc[query.location] if query.location is not None else "",
        "x": nm.person[query.person] if query.person is not None else "",
        "item": item,
    }
    key = f"q_{query.kind.value}" + (
        "_slot" if query.kind is QueryKind.SAW_PERSON and query.slot is not None else ""
    )
    return _t(key, nm.lang, **fields)


# --- Batch ---------------------------------------------------------------------------------------


def run_batch(
    count: int,
    start: int,
    params: GenParams,
    with_metrics: bool,
    make: Callable[[int], Generated] | None = None,
) -> str:
    """`make` builds each seed's case, by default `generate(seed, params)`."""
    durations: list[float] = []
    attempts = 0
    rejections: Counter[str] = Counter()
    failures: list[str] = []
    verified = 0
    metric_rows: list[Metrics] = []
    metric_secs: list[float] = []
    for seed in range(start, start + count):
        began = time.perf_counter()
        generated: Generated = make(seed) if make else generate(seed, params)
        durations.append(time.perf_counter() - began)
        attempts += generated.attempts
        for reason, n in generated.rejections:
            rejections[reason.value] += n
        problems = audit(generated.case)
        if problems:
            failures.append(f"seed {seed}: {problems[:3]}")
        else:
            verified += 1
        if with_metrics:
            began = time.perf_counter()
            metric_rows.append(measure(generated.case.view))
            metric_secs.append(time.perf_counter() - began)

    rejected = attempts - count
    lo, hi = wilson(verified, count)
    rlo, rhi = wilson(rejected, attempts)
    lines = [
        f"Batch: seeds {start}..{start + count - 1}, " + ("game cases" if make else f"{params}"),
        f"Cases generated: {count}; audited OK (unique + all guarantees): {verified}/{count}"
        f" = {verified / count:.1%} [Wilson 95%: {lo:.1%}, {hi:.1%}]",
        f"Attempts: {attempts}; rejected {rejected} = {rejected / attempts:.1%}"
        f" [Wilson 95%: {rlo:.1%}, {rhi:.1%}]",
        "Rejections by reason: "
        + ", ".join(f"{k} {v}" for k, v in sorted(rejections.items(), key=lambda kv: -kv[1])),
        f"Generation time per case: mean {sum(durations) / count:.3f}s,"
        f" p95 {percentile(durations, 95):.3f}s, max {max(durations):.3f}s,"
        f" cases >= 1s: {sum(d >= 1 for d in durations)}",
    ]
    if failures:
        lines.append("Audit failures (first 5):")
        lines += [f"  {f}" for f in failures[:5]]
    if with_metrics:
        lines.append(
            f"Metric time per case: mean {sum(metric_secs) / count:.3f}s,"
            f" p95 {percentile(metric_secs, 95):.3f}s, max {max(metric_secs):.3f}s"
        )
        for name in (
            "contradictions_required",
            "min_questions",
            "inference_steps",
            "conflict_pairs",
            "naive_suspects",
            "trusting_suspects",
        ):
            dist = Counter(getattr(m, name) for m in metric_rows)
            shown = ", ".join(
                f"{k}:{v}" for k, v in sorted(dist.items(), key=lambda kv: (kv[0] is None, kv[0]))
            )
            lines.append(f"  {name}: {shown}")
        exact = sum(m.min_questions_exact for m in metric_rows)
        lines.append(f"  min_questions exact: {exact}/{count}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loosethread.case", description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--lang", choices=[lang.value for lang in Lang], default="zh")
    parser.add_argument("--hide-truth", action="store_true", help="omit the truth section")
    parser.add_argument("--metrics", action="store_true", help="also compute difficulty metrics")
    parser.add_argument("--batch", type=int, default=0, help="generate N cases and report stats")
    parser.add_argument("--rule", choices=[r.value for r in ContradictionRule], default="trusting")
    parser.add_argument("--daily", action="store_true", help="use the daily-case preset (CP-3)")
    parser.add_argument(
        "--game", action="store_true", help="the case the game plays for this number (D-031)"
    )
    parser.add_argument("--out", type=Path, help="write UTF-8 output to this file")
    args = parser.parse_args(argv)
    params = replace(
        DAILY if args.daily else GenParams(), contradiction_rule=ContradictionRule(args.rule)
    )

    if args.batch:
        make = daily_case if args.game else None
        text = run_batch(args.batch, args.seed, params, args.metrics, make)
    else:
        lang = Lang(args.lang)
        generated = daily_case(args.seed) if args.game else generate(args.seed, params)
        text = render_case(generated.case, lang, show_truth=not args.hide_truth)
        if args.metrics and not args.hide_truth:
            case = generated.case
            block = _metrics_block(measure(case.view), _Names(case.view.world, lang), case)
            text += "\n\n" + rule(_t("metrics", lang)) + "\n" + block
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    else:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
