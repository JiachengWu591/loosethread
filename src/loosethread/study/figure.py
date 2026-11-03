"""The report's one figure, as SVG from the standard library (STUDY_PLAN §12).

A dot for each rate, a line for its Wilson interval, on one shared scale. Filled dots are what the
plan registered; open dots were added after reading the results. Each mark has a `<title>`, which a
browser shows on hover. The numbers are in `results/*.md`, which serve as the table view.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape

from loosethread.stats import wilson
from loosethread.study import tables
from loosethread.study.tables import Row

_MAX_PERCENT = 50
_LEFT = 262
_RIGHT = 662
_WIDTH = 760
_ROW = 26
_STYLE = """\
    svg { --surface: #fcfcfb; --ink: #0b0b0b; --muted: #52514e; --grid: #e4e3df; --mark: #2a78d6;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size: 13px; }
    @media (prefers-color-scheme: dark) {
      svg { --surface: #1a1a19; --ink: #f0efec; --muted: #c3c2b7; --grid: #3a3a37;
        --mark: #3987e5; }
    }
    .surface { fill: var(--surface); }
    .ink { fill: var(--ink); }
    .muted { fill: var(--muted); }
    .head { fill: var(--ink); font-weight: 600; }
    .grid { stroke: var(--grid); stroke-width: 1; }
    .whisker { stroke: var(--mark); stroke-width: 2; stroke-linecap: round; }
    .planned { fill: var(--mark); stroke: var(--surface); stroke-width: 2; }
    .later { fill: var(--surface); stroke: var(--mark); stroke-width: 2; }
"""


@dataclass(frozen=True)
class Point:
    label: str
    k: int
    n: int
    planned: bool


def points(
    rq2: Sequence[Row],
    rq3: Sequence[Row],
    control: Sequence[Row],
    decisions: Mapping[tuple[str, str], bool] | None = None,
) -> tuple[tuple[str, tuple[Point, ...]], ...]:
    names = {"A": "A, hardened prompt", "B": "B, layered", "C": "C, claims only"}
    sessions = tables.score_rq2(rq2)
    failures: list[Point] = []
    for arm, name in names.items():
        part = [s for s in sessions if s.arm == arm]
        failures.append(Point(name, sum(s.failed for s in part), len(part), True))
        other = sum(
            any(":extract:" not in d and tables.ITEM_CLAIM not in d for d in s.details)
            for s in part
        )
        failures.append(Point("without the item claim", other, len(part), False))
    scored = tables.scored_attacks(rq3, decisions)
    leaks = [
        Point(
            name,
            sum(bool(s["leak"]) for r, s in scored if r["arm"] == arm),
            sum(1 for r, _ in scored if r["arm"] == arm),
            True,
        )
        for arm, name in names.items()
    ]
    unhardened = tables.scored_attacks(control, decisions)
    leaks.append(
        Point(
            "U, no hardening",
            sum(bool(s["leak"]) for _, s in unhardened),
            len(unhardened),
            False,
        )
    )
    return (
        ("RQ2: sessions with an integrity failure", tuple(failures)),
        ("RQ3: static attacks that leak, after review", tuple(leaks)),
    )


def _x(percent: float) -> float:
    return round(_LEFT + (_RIGHT - _LEFT) * percent / _MAX_PERCENT, 1)


def svg(panels: Sequence[tuple[str, Sequence[Point]]]) -> str:
    y = 66
    body: list[str] = []
    grid: list[str] = []
    ticks = range(0, _MAX_PERCENT + 1, 10)
    for title, rows in panels:
        y += 8
        body.append(f'  <text class="head" x="16" y="{y}">{escape(title)}</text>')
        y += 2
        top = y + _ROW - 13
        for point in rows:
            y += _ROW
            low, high = wilson(point.k, point.n)
            rate = point.k / point.n
            label = escape(point.label)
            text = f"{point.k}/{point.n} = {rate:.1%} [{low:.1%}, {high:.1%}]"
            style = "ink" if point.planned else "muted"
            mark = "planned" if point.planned else "later"
            body += [
                "  <g>",
                f"    <title>{label}: {escape(text)}</title>",
                f'    <text class="{style}" x="16" y="{y + 4}">{label}</text>',
                f'    <line class="whisker" x1="{_x(low * 100)}" y1="{y}"'
                f' x2="{_x(high * 100)}" y2="{y}"/>',
                f'    <circle class="{mark}" cx="{_x(rate * 100)}" cy="{y}" r="5"/>',
                f'    <text class="{style}" x="{_WIDTH - 16}" y="{y + 4}"'
                f' text-anchor="end">{point.k}/{point.n}</text>',
                "  </g>",
            ]
        bottom = y + 13
        grid += [
            f'  <line class="grid" x1="{_x(p)}" y1="{top}" x2="{_x(p)}" y2="{bottom}"/>'
            for p in ticks
        ]
        y += 32
    bottom = y - 32 + 13
    grid += [
        f'  <text class="muted" x="{_x(p)}" y="{bottom + 18}" text-anchor="middle">{p}%</text>'
        for p in ticks
    ]
    height = bottom + 32
    legend = [
        '  <circle class="planned" cx="22" cy="42" r="5"/>',
        '  <text class="muted" x="34" y="46">registered in the plan</text>',
        '  <circle class="later" cx="202" cy="42" r="5"/>',
        '  <text class="muted" x="214" y="46">added after reading the results</text>',
        '  <line class="whisker" x1="434" y1="42" x2="462" y2="42"/>',
        '  <text class="muted" x="472" y="46">95% Wilson interval</text>',
    ]
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_WIDTH} {height}"'
            f' width="{_WIDTH}" height="{height}" role="img"'
            ' aria-label="Failure and leak rates per arm, with 95% Wilson intervals">',
            f"  <style>\n{_STYLE}  </style>",
            f'  <rect class="surface" width="{_WIDTH}" height="{height}"/>',
            '  <text class="head" x="16" y="22">Failure and leak rates per arm</text>',
            *legend,
            *grid,
            *body,
            "</svg>",
            "",
        ]
    )
