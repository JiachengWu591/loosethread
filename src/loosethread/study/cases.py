"""Which cases the study runs on (STUDY_PLAN §2).

Tuning and pilot seeds never overlap the held-out seeds, which only a test run may read. The
held-out set takes the first `PER_CELL` seeds per setting x shape, so every cell is populated; a
plain range of 200 seeds would give from 39 to 65 cases per shape. Languages alternate inside each
cell, and half of the cells start with each, so the set is exactly half zh and half en.
"""

from collections import Counter
from dataclasses import dataclass
from functools import cache

from loosethread.content import ContentPack
from loosethread.generator import PACKS, SHAPE_PARAMS, AlibiStyle, daily_setup, generate
from loosethread.model import Case, Lang

TUNE_SEEDS = range(5000, 5020)
PILOT_SEEDS = range(5020, 5040)
HELD_OUT_START = 6000
PER_CELL = 17


@dataclass(frozen=True)
class StudyCase:
    seed: int
    lang: Lang
    case: Case
    pack: ContentPack
    shape: AlibiStyle


@cache
def study_case(seed: int, lang: Lang) -> StudyCase:
    pack, shape = daily_setup(seed)
    return StudyCase(seed, lang, generate(seed, SHAPE_PARAMS[shape], pack).case, pack, shape)


def held_out() -> tuple[tuple[int, Lang], ...]:
    """(seed, language) of the 204 held-out cases, in seed order."""
    cells = [(pack, shape) for pack in PACKS for shape in AlibiStyle]
    counts: Counter[tuple[str, AlibiStyle]] = Counter()
    chosen: list[tuple[int, Lang]] = []
    seed = HELD_OUT_START
    while len(chosen) < len(cells) * PER_CELL:
        pack, shape = daily_setup(seed)
        cell = (pack.id, shape)
        if counts[cell] < PER_CELL:
            zh_first = cells.index(cell) % 2 == 0
            chosen.append((seed, Lang.ZH if (counts[cell] % 2 == 0) == zh_first else Lang.EN))
            counts[cell] += 1
        seed += 1
    return tuple(chosen)


def held_out_subset(per_cell: int) -> tuple[tuple[int, Lang], ...]:
    """The first `per_cell` held-out cases of each cell, for what costs too much to run on all."""
    counts: Counter[tuple[str, AlibiStyle]] = Counter()
    chosen: list[tuple[int, Lang]] = []
    for seed, lang in held_out():
        pack, shape = daily_setup(seed)
        if counts[(pack.id, shape)] < per_cell:
            chosen.append((seed, lang))
            counts[(pack.id, shape)] += 1
    return tuple(chosen)


def development(seeds: range) -> tuple[tuple[int, Lang], ...]:
    """(seed, language) for tuning or pilot seeds, alternating languages."""
    return tuple((seed, Lang.ZH if seed % 2 == 0 else Lang.EN) for seed in seeds)
