"""Names the question parser and the line check recognise: people, places, the item, clock times.

Built from the public world plus the content pack's aliases; it holds no truth. Both languages are
always accepted, whatever language the game is played in. Matching is case-insensitive after NFKC
normalisation (full-width digits and colons become ASCII). ASCII aliases match whole words only;
CJK aliases match as substrings, longest first, so 书房 (study) is not read as a shorter alias.
An alias shared by two entities is dropped rather than guessed.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from functools import cached_property

from loosethread.content import ContentPack
from loosethread.model import CrimeReport, LocalizedText, SlotIndex, World


class EntityKind(Enum):
    PERSON = "person"
    LOCATION = "location"
    ITEM = "item"


@dataclass(frozen=True)
class Entry:
    kind: EntityKind
    id: str
    name: LocalizedText
    aliases: tuple[str, ...]  # every accepted form, normalised; the names come first


@dataclass(frozen=True)
class Mention:
    kind: EntityKind
    id: str
    text: str


# Polite and familiar forms built from a Chinese surname.
_ZH_HONORIFICS = ("先生", "女士", "小姐", "老板", "师傅", "老师", "姐", "哥", "叔", "阿姨", "同学")
_EN_TITLES = ("mr", "mr.", "mister", "ms", "ms.", "mrs", "mrs.", "miss")
# English name parts that are also everyday words; they only count inside a full name or title.
_EN_STOPWORDS = frozenset({"he", "man"})
# Generic words for the stolen item and the scene, in any setting.
_STOLEN_ITEM = (
    "藏品", "失物", "被偷的东西", "丢的东西", "失窃的东西", "那件东西",
    "the stolen item", "the missing item", "the stolen piece", "the item", "the piece",
)  # fmt: skip
_SCENE = ("现场", "案发现场", "the scene", "crime scene", "scene of the crime")


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("’", "'").lower().strip()


def _is_ascii(text: str) -> bool:
    return all(ord(ch) < 128 for ch in text)


def _person_forms(name: LocalizedText, role: LocalizedText) -> list[str]:
    zh, en = name.zh, name.en
    surname, given = zh[0], zh[1:]
    forms = [zh, en, role.zh, role.en, "老" + surname, "小" + surname]
    forms += [surname + h for h in _ZH_HONORIFICS]
    if len(given) >= 2:
        forms.append(given)
    family, *rest = en.split()
    forms += [f"{title} {family}" for title in _EN_TITLES]
    forms += [part for part in (family, *rest) if part.lower() not in _EN_STOPWORDS]
    return forms


@dataclass(frozen=True)
class Lexicon:
    entries: tuple[Entry, ...]
    start_minute: int  # start of the first slot
    slot_minutes: int
    n_slots: int

    @classmethod
    def build(cls, world: World, crime: CrimeReport, pack: ContentPack) -> "Lexicon":
        raw: list[tuple[EntityKind, str, LocalizedText, list[str]]] = []
        for p in world.people:
            forms = _person_forms(p.name, p.role)
            raw.append((EntityKind.PERSON, p.id, p.name, [*forms, *pack.aliases_for(p.id)]))
        for loc in world.locations:
            forms = [loc.name.zh, loc.name.en, *pack.aliases_for(loc.id)]
            if loc.id == crime.location:
                forms += _SCENE
            raw.append((EntityKind.LOCATION, loc.id, loc.name, forms))
        for item in world.items:
            forms = [item.name.zh, item.name.en, *pack.aliases_for(item.id)]
            if item.id == crime.item:
                forms += _STOLEN_ITEM
            raw.append((EntityKind.ITEM, item.id, item.name, forms))
        owners: dict[str, set[str]] = {}
        for _, entity, _, forms in raw:
            for form in forms:
                owners.setdefault(normalize(form), set()).add(entity)
        entries = tuple(
            Entry(
                kind,
                entity,
                name,
                tuple(
                    dict.fromkeys(f for f in map(normalize, forms) if f and owners[f] == {entity})
                ),
            )
            for kind, entity, name, forms in raw
        )
        first = world.slots[0]
        return cls(
            entries, first.start_minute, first.end_minute - first.start_minute, len(world.slots)
        )

    # --- Entities ----------------------------------------------------------------------------

    @cached_property
    def _pattern(self) -> re.Pattern[str]:
        forms = sorted({a for e in self.entries for a in e.aliases}, key=lambda a: (-len(a), a))
        parts = [
            rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])" if _is_ascii(a) else re.escape(a)
            for a in forms
        ]
        return re.compile("|".join(parts))

    @cached_property
    def _owner(self) -> dict[str, Entry]:
        return {a: e for e in self.entries for a in e.aliases}

    def mentions(self, text: str) -> tuple[Mention, ...]:
        found = self._pattern.finditer(normalize(text))
        return tuple(
            Mention(self._owner[m.group()].kind, self._owner[m.group()].id, m.group())
            for m in found
        )

    def people_by_alias(self) -> tuple[tuple[str, str], ...]:
        """(alias, person id) pairs, longest alias first."""
        pairs = [(a, e.id) for e in self.entries if e.kind is EntityKind.PERSON for a in e.aliases]
        return tuple(sorted(pairs, key=lambda p: (-len(p[0]), p[0])))

    def person_named(self, text: str) -> str | None:
        """The person whose name or alias is exactly `text`, if any."""
        key = normalize(text)
        return next((pid for alias, pid in self.people_by_alias() if alias == key), None)

    def without_names(self, text: str) -> str:
        """`text`, normalised, with every recognised name replaced by a space."""
        return self._pattern.sub(" ", normalize(text))

    def entry(self, entity_id: str) -> Entry:
        for e in self.entries:
            if e.id == entity_id:
                return e
        raise KeyError(entity_id)

    # --- Clock times -------------------------------------------------------------------------

    def times(self, text: str) -> tuple[int, ...]:
        """Clock times named in `text`, as minutes after midnight, in reading order."""
        return clock_times(text)

    def slot_at(self, minute: int) -> SlotIndex | None:
        offset = minute - self.start_minute
        if not 0 <= offset < self.slot_minutes * self.n_slots:
            return None
        return SlotIndex(offset // self.slot_minutes)

    def slot_bounds(self, slot: int) -> tuple[int, int]:
        start = self.start_minute + slot * self.slot_minutes
        return start, start + self.slot_minutes


# --- Clock-time parsing --------------------------------------------------------------------------

_CN_DIGITS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}  # fmt: skip
_CN_NUM = "[0-9零〇一二两三四五六七八九十]{1,3}"
_EN_HOURS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}  # fmt: skip
_EN_MINUTES = {"fifteen": 15, "thirty": 30, "forty-five": 45, "forty five": 45, "o'clock": 0}
_EN_HOUR = "(?:" + "|".join(_EN_HOURS) + r"|\d{1,2})"
# A bare number word is read as a time only for evening hours ("no one" is not 13:00).
_EN_EVENING = ("seven", "eight", "nine", "ten", "eleven")

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("half", re.compile(rf"\bhalf past ({_EN_HOUR})\b")),
    ("past", re.compile(rf"\b(?:a )?quarter past ({_EN_HOUR})\b")),
    ("to", re.compile(rf"\b(?:a )?quarter to ({_EN_HOUR})\b")),
    ("clock", re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")),
    ("zh", re.compile(rf"({_CN_NUM})\s*[点點](?:\s*(半|一刻|三刻|钟|整|({_CN_NUM})\s*分?))?")),
    ("ampm", re.compile(r"(?<![\d:])(\d{1,2})\s*(?:pm|p\.m\.|am|a\.m\.|o'clock|oclock)")),
    (
        "word",
        re.compile(
            r"\b(" + "|".join(_EN_EVENING) + r")(?:[ -](" + "|".join(_EN_MINUTES) + r"))?\b"
        ),
    ),
    ("at", re.compile(r"\b(?:at|around|about|by|after|before|until|till)\s+(\d{1,2})(?![\d:])")),
)


def _cn_number(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    if "十" in text:
        tens, _, ones = text.partition("十")
        high = _CN_DIGITS.get(tens) if tens else 1
        low = _CN_DIGITS.get(ones) if ones else 0
        return None if high is None or low is None else high * 10 + low
    return _CN_DIGITS.get(text) if len(text) == 1 else None


def _hour(text: str) -> int | None:
    return _EN_HOURS[text] if text in _EN_HOURS else _cn_number(text)


def _evening(hour: int, minute: int) -> int:
    """Clock reading to minutes after midnight; small hours mean the evening (9 means 21:00)."""
    if 1 <= hour <= 11:
        hour += 12
    return hour * 60 + minute


def clock_times(text: str) -> tuple[int, ...]:
    return tuple(minute for _, minute in _clock_readings(normalize(text))[0])


def first_time_at(norm: str) -> int | None:
    """Where the first clock time starts in normalised text, if it names one."""
    readings = _clock_readings(norm)[0]
    return readings[0][0] if readings else None


def without_times(text: str) -> str:
    """`text`, normalised, with its clock times taken out."""
    norm = normalize(text)
    taken = _clock_readings(norm)[1]
    return "".join(ch for ch, gone in zip(norm, taken, strict=True) if not gone)


def _clock_readings(norm: str) -> tuple[list[tuple[int, int]], list[bool]]:
    """(position, minute) of every clock time in normalised text, in reading order, and which
    characters they cover."""
    found: list[tuple[int, int]] = []  # (position, minute)
    taken = [False] * len(norm)
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(norm):
            if any(taken[m.start() : m.end()]):
                continue
            minute = _reading(kind, m)
            if minute is None:
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            found.append((m.start(), minute))
    return sorted(found), taken


def _reading(kind: str, m: re.Match[str]) -> int | None:
    hour = _hour(m.group(1))
    if hour is None or hour > 23:
        return None
    match kind:
        case "half":
            return _evening(hour, 30)
        case "past":
            return _evening(hour, 15)
        case "to":
            return _evening(hour, 0) - 15
        case "clock":
            minutes = int(m.group(2))
            return _evening(hour, minutes) if minutes < 60 else None
        case "zh":
            # 一点 and 两点 also mean "a little" and "two points"; only evening hours count.
            if not (7 <= hour <= 12 or 19 <= hour <= 23):
                return None
            extra = m.group(2)
            minute = {"半": 30, "一刻": 15, "三刻": 45, "钟": 0, "整": 0, None: 0}.get(extra)
            if minute is None:
                minute = _cn_number(m.group(3) or "")
            return _evening(hour, minute) if minute is not None and minute < 60 else None
        case "word":
            return _evening(hour, _EN_MINUTES.get(m.group(2) or "o'clock", 0))
        case _:  # "ampm", "at"
            return _evening(hour, 0)
