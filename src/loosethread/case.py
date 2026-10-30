"""Debug CLI: print a generated case as readable text, or run a batch and report statistics.

python -m loosethread.case --seed 7                # zh, including the truth
python -m loosethread.case --seed 7 --lang en --hide-truth
python -m loosethread.case --batch 1000 --metrics  # acceptance, timing, metric distributions
"""

import argparse
import io
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from loosethread.audit import audit
from loosethread.content import load_pack
from loosethread.difficulty import Metrics, measure
from loosethread.generator import ContradictionRule, Generated, GenParams, generate
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
    Query,
    QueryKind,
    Statement,
)
from loosethread.stats import percentile, wilson

_UI: dict[str, tuple[str, str]] = {
    "title": ("破绽 · {setting} · 案件 #{seed}", "Loose Thread · {setting} · case #{seed}"),
    "stolen": ("失物：{item}（失主：{owner}）", "Stolen: the {item} (owner: {owner})"),
    "scene": (
        "现场：{loc}。最后确认还在：{seen}；发现失窃：{found}。",
        "Scene: the {loc}. Last confirmed there: {seen}; found missing: {found}.",
    ),
    "window": (
        "作案时间窗：{start}–{end}（共 {n} 个时段）",
        "Theft window: {start}–{end} ({n} slots)",
    ),
    "suspects": ("【嫌疑人】", "[Suspects]"),
    "suspect_line": ("{name}（{role}）动机：{motive}", "{name} ({role}) — motive: {motive}"),
    "client_line": (
        "{name}（{role}；失主，不是嫌疑人）",
        "{name} ({role}; the owner, not a suspect)",
    ),
    "map": ("【地图】（相邻地点）", "[Map] (adjacent locations)"),
    "evidence": ("【证据】（一定为真）", "[Evidence] (always true)"),
    "testimony": (
        "【证词】（每人对各类问题的固定回答）",
        "[Testimony] (each person's fixed answers)",
    ),
    "where": ("行踪", "whereabouts"),
    "with": ("同处一室", "company"),
    "item_seen": ("见过失物", "saw the item"),
    "heard": ("听说", "heard"),
    "alone": ("独自一人", "alone"),
    "told": ("{src}说自己 {time} 在{loc}", "{src} said they were in the {loc} at {time}"),
    "truth": ("【真相】（剧透）", "[Truth] (spoilers)"),
    "culprit": (
        "犯人：{name}，在 {time} 于{loc}下手。",
        "Culprit: {name}, in the {loc} at {time}.",
    ),
    "timeline": ("真实行踪：", "True whereabouts:"),
    "lies": ("谎言：", "Lies:"),
    "lie": (
        "{name}（{why}）声称 {time} 在{claim}，实际在{real}。能揭穿它的：{by}",
        "{name} ({why}) claims the {claim} at {time}, was really in the {real}. Exposed by: {by}",
    ),
    "alibi": ("编造不在场证明", "alibi"),
    "privacy": ("隐私小谎", "privacy"),
    "metrics": ("【难度】", "[Difficulty]"),
    "plan": ("一种最短问法：", "A shortest question plan:"),
    "q_where": ("问{p}：{time} 你在哪？", "Ask {p}: where were you at {time}?"),
    "q_when": ("问{p}：你什么时候去过{loc}？", "Ask {p}: when were you in the {loc}?"),
    "q_with_whom": ("问{p}：{time} 你和谁在一起？", "Ask {p}: who was with you at {time}?"),
    "q_saw_person": ("问{p}：今晚见过{x}吗？", "Ask {p}: did you see {x} tonight?"),
    "q_saw_person_slot": ("问{p}：{time} 见过{x}吗？", "Ask {p}: did you see {x} at {time}?"),
    "q_about_item": ("问{p}：你见过{item}吗？", "Ask {p}: did you see the {item}?"),
}


def _t(key: str, lang: Lang, **fields: object) -> str:
    zh, en = _UI[key]
    return (zh if lang is Lang.ZH else en).format(**fields)


class _Names:
    def __init__(self, case: Case, lang: Lang) -> None:
        world = case.view.world
        self.lang = lang
        self.person = {p.id: p.name.get(lang) for p in world.people}
        self.loc = {loc.id: loc.name.get(lang) for loc in world.locations}
        self.slot = {int(s.index): s for s in world.slots}

    def time(self, slot: int) -> str:
        return self.slot[slot].label.split("–")[0]

    def people(self, ids: frozenset[PersonId]) -> str:
        sep = "、" if self.lang is Lang.ZH else ", "
        return sep.join(sorted(self.person[p] for p in ids))


def render_case(case: Case, lang: Lang = Lang.ZH, show_truth: bool = True) -> str:
    view, world = case.view, case.view.world
    nm = _Names(case, lang)
    item = world.items[0]
    client = next(p for p in world.people if p.id not in view.suspects)
    window = view.crime.window
    out: list[str] = []
    add = out.append

    pack = load_pack()
    add("═" * 60)
    add(_t("title", lang, setting=pack.setting.get(lang), seed=view.seed))
    add("═" * 60)
    add(_t("stolen", lang, item=item.name.get(lang), owner=nm.person[client.id]))
    add(
        _t(
            "scene",
            lang,
            loc=nm.loc[view.crime.location],
            seen=nm.slot[view.crime.last_seen].label,
            found=nm.slot[view.crime.discovered].label,
        )
    )
    add(
        _t(
            "window",
            lang,
            start=nm.time(window[0]),
            end=nm.slot[window[-1]].label.split("–")[1],
            n=len(window),
        )
    )
    add("")
    add(_t("suspects", lang))
    motives = {m.person: m.reason.get(lang) for m in view.motives}
    for p in world.people:
        key = "suspect_line" if p.id in view.suspects else "client_line"
        add(
            "  · "
            + _t(key, lang, name=p.name.get(lang), role=p.role.get(lang), motive=motives.get(p.id))
        )
    add("")
    add(_t("map", lang))
    for loc in world.locations:
        nbrs = sorted(nm.loc[n] for n in loc.neighbors)
        add(f"  {nm.loc[loc.id]} — {'、'.join(nbrs) if lang is Lang.ZH else ', '.join(nbrs)}")
    add("")
    add(_t("evidence", lang))
    for e in view.evidence:
        add(f"  {e.id}  {e.text.get(lang)}")
    add("")
    add(_t("testimony", lang))
    add(_testimony_block(case, nm))
    if show_truth:
        add("")
        add(_truth_block(case, nm))
    return "\n".join(out)


def _testimony_block(case: Case, nm: _Names) -> str:
    lang = nm.lang
    by_speaker: dict[PersonId, list[Statement]] = {}
    for s in case.view.statements:
        by_speaker.setdefault(s.speaker, []).append(s)
    lines: list[str] = []
    for person in case.view.world.people:
        stmts = by_speaker.get(person.id, [])
        lines.append(f"  ◆ {nm.person[person.id]}")
        own = sorted(
            (int(s.claim.slot), s.claim.location)
            for s in stmts
            if isinstance(s.claim, PersonAt) and s.claim.person == person.id
        )
        lines.append(
            f"    {_t('where', lang)}："
            + " | ".join(f"{nm.time(t)} {nm.loc[loc]}" for t, loc in own)
        )
        company = sorted(
            (int(s.claim.slot), s.claim.location, s.claim.people)
            for s in stmts
            if isinstance(s.claim, Occupants)
        )
        parts = []
        for t, _, people in company:
            others = people - {person.id}
            who = nm.people(others) if others else _t("alone", lang)
            parts.append(f"{nm.time(t)} {who}")
        lines.append(f"    {_t('with', lang)}：" + " | ".join(parts))
        seen = sorted(int(s.claim.slot) for s in stmts if isinstance(s.claim, ItemAt))
        if seen:
            lines.append(f"    {_t('item_seen', lang)}：" + "、".join(nm.time(t) for t in seen))
        heard = [s for s in stmts if s.basis is Basis.HEARSAY and isinstance(s.claim, PersonAt)]
        for s in heard:
            assert s.source is not None
            assert isinstance(s.claim, PersonAt)
            told = _t(
                "told",
                lang,
                src=nm.person[s.source],
                time=nm.time(int(s.claim.slot)),
                loc=nm.loc[s.claim.location],
            )
            lines.append(f"    {_t('heard', lang)}：{told}")
    return "\n".join(lines)


def _truth_block(case: Case, nm: _Names) -> str:
    lang, truth = nm.lang, case.truth
    (theft,) = truth.events
    lines = [
        _t("truth", lang),
        _t(
            "culprit",
            lang,
            name=nm.person[truth.culprit],
            time=nm.slot[int(theft.slot)].label,
            loc=nm.loc[theft.location],
        ),
        _t("timeline", lang),
    ]
    where: dict[tuple[PersonId, int], LocationId] = {
        (f.person, int(f.slot)): f.location for f in truth.timeline
    }
    slots = sorted(nm.slot)
    width = 7
    lines.append(" " * 10 + "".join(nm.time(t).ljust(width) for t in slots))
    for p in case.view.world.people:
        name = nm.person[p.id]
        pad = 10 - _display_width(name)
        cells = "".join(_pad(nm.loc[where[(p.id, t)]], width) for t in slots)
        lines.append(name + " " * max(pad, 1) + cells)
    lines.append(_t("lies", lang))
    book = AnswerBook.from_truth(case.view.world, truth)
    for lie in truth.lies:
        claim = lie.statement.claim
        assert isinstance(claim, PersonAt)
        speaker, slot = lie.statement.speaker, int(claim.slot)
        by = []
        for x in lie.exposed_by:
            by.append(x if isinstance(x, str) else nm.person[x.speaker])
        lines.append(
            "  - "
            + _t(
                "lie",
                lang,
                name=nm.person[speaker],
                why=_t("alibi" if lie.reason is LieReason.ALIBI else "privacy", lang),
                time=nm.time(slot),
                claim=nm.loc[book.claimed_location(speaker, slot)],
                real=nm.loc[where[(speaker, slot)]],
                by="、".join(dict.fromkeys(by))
                if lang is Lang.ZH
                else ", ".join(dict.fromkeys(by)),
            )
        )
    return "\n".join(lines)


def _display_width(text: str) -> int:
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(1, width - _display_width(text))


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


def run_batch(count: int, start: int, params: GenParams, with_metrics: bool) -> str:
    durations: list[float] = []
    attempts = 0
    rejections: Counter[str] = Counter()
    failures: list[str] = []
    verified = 0
    metric_rows: list[Metrics] = []
    metric_secs: list[float] = []
    for seed in range(start, start + count):
        began = time.perf_counter()
        generated: Generated = generate(seed, params)
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
        f"Batch: seeds {start}..{start + count - 1}, params {params}",
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
    parser.add_argument("--rule", choices=[r.value for r in ContradictionRule], default="naive")
    parser.add_argument("--out", type=Path, help="write UTF-8 output to this file")
    args = parser.parse_args(argv)
    params = GenParams(contradiction_rule=ContradictionRule(args.rule))

    if args.batch:
        text = run_batch(args.batch, args.seed, params, args.metrics)
    else:
        generated = generate(args.seed, params)
        text = render_case(generated.case, Lang(args.lang), show_truth=not args.hide_truth)
        if args.metrics and not args.hide_truth:
            case = generated.case
            block = _metrics_block(measure(case.view), _Names(case, Lang(args.lang)), case)
            text += "\n" + _t("metrics", Lang(args.lang)) + "\n" + block
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8", newline="\n")
    else:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
