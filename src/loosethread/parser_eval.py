"""Parser accuracy on the frozen question set (D-018 item 2; definitions in data/parser/README.md).

python -m loosethread.parser_eval run --backend rule --split test
python -m loosethread.parser_eval run --backend local --split dev
python -m loosethread.parser_eval run --backend deepseek --split dev --limit 10   # pilot
python -m loosethread.parser_eval score results/rows/parser-rule-test.jsonl [more rows ...]

`run` writes one row per question to `results/rows/` and prints the scores; `score` recomputes
them offline from rows. Guardrails: the set must match `FROZEN_SHA256`; the test split is measured
once per backend (an existing rows file is never overwritten); DeepSeek runs start with a pilot of
at most 10 items and stop before the projected total spend passes the P2 cap (D-018 item 4).
Failed calls are recorded by exception type only, never by message, because provider messages may
echo part of the key.
"""

import argparse
import hashlib
import io
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loosethread.content import load_pack
from loosethread.generator import DAILY, generate
from loosethread.lexicon import Lexicon
from loosethread.model import ItemId, LocationId, PersonId, Query, QueryKind, SlotIndex
from loosethread.npc import ClarifyReason, ParseRequest, Usage
from loosethread.parser import RuleParser
from loosethread.stats import mcnemar_exact, wilson

SET = Path("data/parser/questions.jsonl")
ROWS = Path("results/rows")
# Frozen 2026-10-31 after the owner's spot-check of 30 items found no error (D-022).
FROZEN_SHA256: str | None = "13e22acc0eaf413cfede733e6138169ccdb9e668fada5db0c14060b0ba57d60d"
CAP_CNY = 20.0  # P2 spending cap for API calls (D-018 item 4)
PILOT = 10


@dataclass(frozen=True)
class Invalid:
    """The backend gave nothing usable: malformed reply, unknown id, failed call."""

    detail: str


Label = Query | ClarifyReason
Outcome = Query | ClarifyReason | Invalid


@dataclass(frozen=True)
class Item:
    id: str
    split: str
    lang: str
    seed: int
    addressee: PersonId
    question: str
    expect: Label
    also: tuple[Label, ...]
    tag: str


# --- Labels as JSON ------------------------------------------------------------------------------


def to_json(outcome: Outcome) -> dict[str, Any]:
    if isinstance(outcome, Invalid):
        return {"invalid": outcome.detail}
    if isinstance(outcome, ClarifyReason):
        return {"clarify": outcome.value}
    data: dict[str, Any] = {"kind": outcome.kind.value}
    for name in ("slot", "location", "person", "item"):
        if (value := getattr(outcome, name)) is not None:
            data[name] = value
    return data


def from_json(data: dict[str, Any], addressee: PersonId) -> Outcome:
    if "invalid" in data:
        return Invalid(str(data["invalid"]))
    if "clarify" in data:
        return ClarifyReason(data["clarify"])
    slot, location, person, item = (data.get(k) for k in ("slot", "location", "person", "item"))
    return Query(
        QueryKind(data["kind"]),
        addressee,
        slot=SlotIndex(slot) if slot is not None else None,
        location=LocationId(location) if location is not None else None,
        person=PersonId(person) if person is not None else None,
        item=ItemId(item) if item is not None else None,
    )


def _label(data: dict[str, Any], addressee: PersonId) -> Label:
    label = from_json(data, addressee)
    if isinstance(label, Invalid):
        raise ValueError("a label cannot be invalid")
    return label


def load_items(path: Path = SET) -> list[Item]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        who = PersonId(raw["addressee"])
        items.append(
            Item(
                id=raw["id"],
                split=raw["split"],
                lang=raw["lang"],
                seed=int(raw["seed"]),
                addressee=who,
                question=raw["question"],
                expect=_label(raw["expect"], who),
                also=tuple(_label(a, who) for a in raw["also"]),
                tag=raw["tag"],
            )
        )
    return items


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Scoring -------------------------------------------------------------------------------------

CORRECT, CHARGED_WRONG = "correct", "charged_wrong"
NEEDLESS, INVALID = "needless_rephrase", "invalid"


def classify(expect: Label, also: Sequence[Label], got: Outcome) -> str:
    """What one parse cost the player (data/parser/README.md, "Scoring")."""
    if isinstance(got, Invalid):
        return INVALID
    accepted = (expect, *also)
    if isinstance(got, ClarifyReason):
        return CORRECT if any(isinstance(a, ClarifyReason) for a in accepted) else NEEDLESS
    return CORRECT if got in accepted else CHARGED_WRONG


@dataclass(frozen=True)
class Score:
    n: int
    counts: dict[str, int]
    strict: int

    @property
    def correct(self) -> int:
        return self.counts.get(CORRECT, 0)

    def line(self, title: str) -> str:
        lo, hi = wilson(self.correct, self.n)
        parts = [
            f"{title}: accuracy {self.correct}/{self.n} = {self.correct / self.n:.1%}"
            f" [Wilson 95%: {lo:.1%}, {hi:.1%}]",
            f"strict {self.strict}/{self.n}",
        ]
        parts += [f"{k} {self.counts.get(k, 0)}" for k in (CHARGED_WRONG, NEEDLESS, INVALID)]
        return "; ".join(parts)


def score(rows: Sequence[dict[str, Any]], variant: str) -> Score:
    counts: dict[str, int] = {}
    strict = 0
    for row in rows:
        who = PersonId(row["addressee"])
        expect = _label(row["expect"], who)
        also = [_label(a, who) for a in row["also"]]
        got = from_json(row[variant], who)
        kind = classify(expect, also, got)
        counts[kind] = counts.get(kind, 0) + 1
        strict += got in (expect, *also)
    return Score(len(rows), counts, strict)


def _correct_ids(rows: Sequence[dict[str, Any]], variant: str) -> dict[str, bool]:
    return {r["id"]: score([r], variant).correct == 1 for r in rows}


def report(rows: Sequence[dict[str, Any]], title: str) -> list[str]:
    variants = ["guarded", "raw"] if rows and rows[0]["backend"] != "rule" else ["guarded"]
    lines = []
    for variant in variants:
        name = f"{title} ({variant})" if len(variants) > 1 else title
        lines.append(score(rows, variant).line(name))
        for lang in ("zh", "en"):
            part = [r for r in rows if r["lang"] == lang]
            if part:
                lines.append("  " + score(part, variant).line(lang))
    if len(variants) > 1:
        guarded, raw = _correct_ids(rows, "guarded"), _correct_ids(rows, "raw")
        only_g = sum(guarded[i] and not raw[i] for i in guarded)
        only_r = sum(raw[i] and not guarded[i] for i in guarded)
        p = mcnemar_exact(only_g, only_r)
        lines.append(
            f"  guard vs raw: only guarded right {only_g}, only raw right {only_r};"
            f" exact McNemar p = {p:.3g}"
        )
    usage = [r["usage"] for r in rows]
    cost = sum(float(r["cost_cny_max"]) for r in rows)
    tokens = sum(u["prompt_tokens"] + u["completion_tokens"] for u in usage)
    seconds = sum(float(u["seconds"]) for u in usage)
    lines.append(
        f"  usage: {tokens} tokens, {seconds:.1f} s, at most CNY {cost:.4f}"
        f" ({cost / len(rows):.5f} per question)"
    )
    return lines


def compare(a: Sequence[dict[str, Any]], b: Sequence[dict[str, Any]]) -> str:
    """Exact McNemar test on the items both rows files share (guarded variants)."""
    ca, cb = _correct_ids(a, "guarded"), _correct_ids(b, "guarded")
    common = sorted(set(ca) & set(cb))
    only_a = sum(ca[i] and not cb[i] for i in common)
    only_b = sum(cb[i] and not ca[i] for i in common)
    p = mcnemar_exact(only_a, only_b)
    return (
        f"{len(common)} shared items: only first right {only_a}, only second right {only_b};"
        f" exact McNemar p = {p:.3g}"
    )


# --- Running -------------------------------------------------------------------------------------

Parse = Callable[[ParseRequest], tuple[Outcome, Outcome, str | None, Usage]]


def rule_parse(request: ParseRequest) -> tuple[Outcome, Outcome, str | None, Usage]:
    result = RuleParser().parse(request)
    got: Outcome = result.query or result.reason or ClarifyReason.UNCLEAR
    return got, got, None, Usage()


def model_parse(backend: str) -> tuple[Parse, str, Callable[[Usage], float]]:
    # The optional extra is imported only for model backends, so the core stays stdlib-only.
    from loosethread.llm.client import open_model  # noqa: PLC0415
    from loosethread.llm.parser import parse_prompt, read_reply, time_guard  # noqa: PLC0415

    model = open_model(backend)

    def parse(request: ParseRequest) -> tuple[Outcome, Outcome, str | None, Usage]:
        system, user = parse_prompt(request)
        try:
            reply = model.complete(system, user, json_mode=True, max_tokens=120)
        except Exception as exc:  # record the type only: messages may echo the key
            failed = Invalid(f"call_error:{type(exc).__name__}")
            return failed, failed, None, Usage(calls=1)
        try:
            got: Outcome = read_reply(reply.text, request)
        except ValueError as defect:
            got = Invalid(str(defect))
            return got, got, reply.text, reply.usage
        guarded = got
        if isinstance(got, Query) and (reason := time_guard(got, request)) is not None:
            guarded = reason
        return got, guarded, reply.text, reply.usage

    return parse, model.backend.model, model.backend.cost


def _spent(rows_dir: Path) -> tuple[float, int]:
    """CNY already spent on DeepSeek parser runs, and how many questions that covered."""
    cost, n = 0.0, 0
    for path in rows_dir.glob("parser-deepseek*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            cost += float(json.loads(line)["cost_cny_max"])
            n += 1
    return cost, n


def run(
    backend: str,
    split: str,
    limit: int | None,
    set_path: Path = SET,
    rows_dir: Path = ROWS,
    frozen: str | None = None,
    parse: Parse | None = None,
) -> Path:
    frozen = frozen if frozen is not None else FROZEN_SHA256
    if frozen is None or sha256(set_path) != frozen:
        raise SystemExit("the question set is not frozen (or changed since); see data/parser")
    items = [i for i in load_items(set_path) if split in (i.split, "all")]
    items = items[:limit] if limit is not None else items
    stem = f"parser-{backend}-{split}" + (f"-first{limit}" if limit is not None else "")
    if split == "dev":  # tuning rounds are numbered and all kept
        out = rows_dir / f"{stem}-r{len(list(rows_dir.glob(f'{stem}-r*.jsonl'))) + 1}.jsonl"
    else:
        out = rows_dir / f"{stem}.jsonl"
        if out.exists():
            raise SystemExit(f"{out} exists: the test split is measured once per backend")
    model_name, prompt = "rules", "rules"
    cost: Callable[[Usage], float] = lambda usage: 0.0  # noqa: E731
    if parse is None and backend == "rule":
        parse = rule_parse
    elif parse is None:
        if backend.startswith("deepseek"):
            spent, covered = _spent(rows_dir)
            if covered == 0 and (limit is None or limit > PILOT):
                raise SystemExit(f"run a pilot first: --limit {PILOT} or fewer")
            if covered:
                projected = spent + spent / covered * len(items)
                print(f"spent so far CNY {spent:.4f}; this run projects CNY {projected:.4f} total")
                if projected > CAP_CNY:
                    raise SystemExit(f"projected spend passes the cap of CNY {CAP_CNY}")
        parse, model_name, cost = model_parse(backend)
        from loosethread.llm.parser import SYSTEM  # noqa: PLC0415

        prompt = hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest()[:12]
    assert parse is not None

    lexicons: dict[int, Lexicon] = {}
    rows = []
    for item in items:
        if item.seed not in lexicons:
            view = generate(item.seed, DAILY).case.view
            lexicons[item.seed] = Lexicon.build(view.world, view.crime, load_pack())
        raw, guarded, reply, usage = parse(
            ParseRequest(item.question, item.addressee, lexicons[item.seed])
        )
        rows.append(
            {
                "id": item.id,
                "split": item.split,
                "lang": item.lang,
                "tag": item.tag,
                "addressee": item.addressee,
                "question": item.question,
                "backend": backend,
                "model": model_name,
                "prompt": prompt,
                "expect": to_json(item.expect),
                "also": [to_json(a) for a in item.also],
                "raw": to_json(raw),
                "guarded": to_json(guarded),
                "reply": reply,
                "usage": {
                    "calls": usage.calls,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "seconds": round(usage.seconds, 3),
                },
                "cost_cny_max": round(cost(usage), 6),
            }
        )
    rows_dir.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    out.write_text(text, encoding="utf-8", newline="\n")
    return out


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m loosethread.parser_eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    go = sub.add_parser("run", help="parse the set with one backend and write rows")
    go.add_argument("--backend", required=True, help="rule, local, deepseek, ...")
    go.add_argument("--split", choices=["dev", "test", "all"], required=True)
    go.add_argument("--limit", type=int, help="only the first N items (pilot)")
    again = sub.add_parser("score", help="recompute scores from rows files, offline")
    again.add_argument("rows", type=Path, nargs="+")
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    paths = [run(args.backend, args.split, args.limit)] if args.command == "run" else args.rows
    loaded = [read_rows(p) for p in paths]
    for path, rows in zip(paths, loaded, strict=True):
        print("\n".join(report(rows, path.stem)))
    if len(loaded) == 2:
        print(compare(*loaded))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
