"""NPC lines: the sentences that state `AllowedFacts`, the offline template writer, the payload a
model-backed writer may put in its prompt, and the post-check that keeps any written line inside
what it was allowed to say.
"""

import json

from loosethread.lexicon import Lexicon
from loosethread.model import (
    Basis,
    ItemAt,
    Lang,
    Occupants,
    PersonAt,
    PersonId,
    QueryKind,
    Stance,
    Statement,
    Tone,
)
from loosethread.npc import ClarifyReason, LineRequest, LineResult

_LINES: dict[str, tuple[str, str]] = {
    "self_at": ("{t} 我在{loc}。", "Between {t} I was in the {loc}."),
    "self_times": ("我在{loc}的时段：{ts}。", "I was in the {loc} during {ts}."),
    "with": (
        "{t} 我在{loc}，同在的还有{others}。",
        "Between {t} I was in the {loc} with {others}.",
    ),
    "alone": ("{t} 我一个人在{loc}，没有别人。", "Between {t} I was alone in the {loc}."),
    "saw_yes": ("见到了。", "Yes."),
    "saw_no": ("没见到。", "No."),
    "saw": ("{t} 我在{loc}见到了{p}。", "Between {t} I saw {p} in the {loc}."),
    "heard_self": (
        "{src}跟我说过，{t} 自己在{loc}。",
        "{src} told me they were in the {loc} between {t}.",
    ),
    "heard": ("{src}跟我说过，{t} {p}在{loc}。", "{src} told me {p} was in the {loc} between {t}."),
    "item": ("{t} 我在{loc}见过{item}。", "Between {t} I saw the {item} in the {loc}."),
    "deny_when": ("我今晚没去过{loc}。", "I wasn't in the {loc} at all tonight."),
    "deny_saw": ("我今晚没见过{p}。", "I didn't see {p} tonight."),
    "deny_item": ("我没留意过{item}。", "I never noticed the {item}."),
    "deny": ("这个我答不上来。", "I can't answer that."),
    "dont_know": ("这个我不清楚。", "I don't know."),
    "opinion": ("{p}？不熟，不好乱说。", "{p}? I don't know them well enough to say."),
    "small_talk": ("是啊，这雨下得人心里发慌。", "Yes, this rain is getting on everyone's nerves."),
    "out_of_scope": (
        "这种话我可接不了。要问就问具体的：几点、在哪、和谁。",
        "I can't help you with that. Ask me something specific: when, where, with whom.",
    ),
    "unclear": (
        "抱歉，没听明白。你可以问我几点在哪、和谁在一起、见没见过谁。",
        "Sorry, I didn't follow. Ask me where I was at a time, who was with me, or whom I saw.",
    ),
    "need_time": ("你问的是几点？说个具体时间吧。", "Which time do you mean? Name a time tonight."),
    "bad_time": (
        "今晚 {start} 到 {end} 之外的事，我说不上来。",
        "I can't speak to anything outside {start} to {end} tonight.",
    ),
    "two_people": (
        "一次问一个人吧，你说的是哪一位？",
        "One person at a time, please. Whom do you mean?",
    ),
    "repeat": ("刚才说过了：", "As I said: "),
}  # fmt: skip

_TONE: dict[Tone, tuple[str, str]] = {
    Tone.CALM: ("", ""),
    Tone.NERVOUS: ("呃……", "Uh... "),
    Tone.EVASIVE: ("这个嘛……", "Well... "),
    Tone.IRRITATED: ("你问得可真多。", "You ask a lot of questions. "),
}


def _t(key: str, lang: Lang, **fields: object) -> str:
    zh, en = _LINES[key]
    return (zh if lang is Lang.ZH else en).format(**fields)


class _Names:
    def __init__(self, request: LineRequest) -> None:
        world, self.lang = request.world, request.lang
        self.person = {p.id: p.name.get(self.lang) for p in world.people}
        self.loc = {loc.id: loc.name.get(self.lang) for loc in world.locations}
        self.item = {i.id: i.name.get(self.lang) for i in world.items}
        self.slots = {int(s.index): s for s in world.slots}
        self.order = [p.id for p in world.people]

    def span(self, slot: int) -> str:
        start, end = self.slots[slot].label.split("–")
        return f"{start}–{end}" if self.lang is Lang.ZH else f"{start} and {end}"

    def people(self, ids: frozenset[PersonId]) -> str:
        names = [self.person[p] for p in self.order if p in ids]
        if self.lang is Lang.ZH:
            return "、".join(names)
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _sentence(s: Statement, nm: _Names) -> str:
    lang = nm.lang
    match s.claim:
        case PersonAt(person, location, slot) if s.basis is Basis.HEARSAY:
            assert s.source is not None  # guaranteed by Statement validation
            key = "heard_self" if person == s.source else "heard"
            fields = {"src": nm.person[s.source], "p": nm.person[person]}
            return _t(key, lang, t=nm.span(slot), loc=nm.loc[location], **fields)
        case PersonAt(person, location, slot) if person == s.speaker:
            return _t("self_at", lang, t=nm.span(slot), loc=nm.loc[location])
        case PersonAt(person, location, slot):
            return _t("saw", lang, t=nm.span(slot), loc=nm.loc[location], p=nm.person[person])
        case Occupants(location, slot, people):
            others = people - {s.speaker}
            if not others:
                return _t("alone", lang, t=nm.span(slot), loc=nm.loc[location])
            return _t("with", lang, t=nm.span(slot), loc=nm.loc[location], others=nm.people(others))
        case ItemAt(item, location, slot):
            return _t("item", lang, t=nm.span(slot), loc=nm.loc[location], item=nm.item[item])


def fact_sentences(request: LineRequest) -> tuple[str, ...]:
    """First-person sentences that say exactly what the facts allow, and nothing else."""
    facts, nm, lang = request.facts, _Names(request), request.lang
    query = facts.query
    if facts.stance is Stance.CLARIFY:
        reason = request.reason or ClarifyReason.UNCLEAR
        first, last = request.world.slots[0], request.world.slots[-1]
        start, end = first.label.split("–")[0], last.label.split("–")[1]
        return (_t(reason.value, lang, start=start, end=end),)
    assert query is not None  # only CLARIFY has no query (AllowedFacts validation)
    match facts.stance:
        case Stance.ANSWER:
            claims = facts.claims
            if query.kind is QueryKind.WHEN and query.location is not None and len(claims) > 1:
                labels = [nm.slots[c.claim.slot].label for c in claims]
                spans = ("、" if lang is Lang.ZH else ", ").join(labels)
                return (_t("self_times", lang, loc=nm.loc[query.location], ts=spans),)
            body = tuple(_sentence(c, nm) for c in claims)
            if query.kind is QueryKind.SAW_PERSON and query.slot is not None:
                seen = any(
                    isinstance(c.claim, Occupants) and query.person in c.claim.people
                    for c in claims
                )
                return (_t("saw_yes" if seen else "saw_no", lang), *body)
            return body
        case Stance.DENY:
            if query.kind is QueryKind.WHEN and query.location is not None:
                return (_t("deny_when", lang, loc=nm.loc[query.location]),)
            if query.kind is QueryKind.SAW_PERSON and query.person is not None:
                return (_t("deny_saw", lang, p=nm.person[query.person]),)
            if query.kind is QueryKind.ABOUT_ITEM and query.item is not None:
                return (_t("deny_item", lang, item=nm.item[query.item]),)
            return (_t("deny", lang),)
        case Stance.DONT_KNOW:
            return (_t("dont_know", lang),)
        case _:  # DEFLECT
            if query.kind is QueryKind.OPINION and query.person is not None:
                return (_t("opinion", lang, p=nm.person[query.person]),)
            if query.kind is QueryKind.SMALL_TALK:
                return (_t("small_talk", lang),)
            return (_t("out_of_scope", lang),)


def template_line(request: LineRequest) -> str:
    lang = request.lang
    tone = _TONE[request.facts.tone or Tone.CALM]
    prefix = (tone[0] if lang is Lang.ZH else tone[1]) + (
        _t("repeat", lang) if request.repeat else ""
    )
    sentences = fact_sentences(request)
    return prefix + ("" if lang is Lang.ZH else " ").join(sentences)


class TemplateWriter:
    """Offline, deterministic line writer: the fact sentences plus a tone prefix."""

    def write(self, request: LineRequest) -> LineResult:
        return LineResult(template_line(request))


def line_payload(request: LineRequest) -> str:
    """Everything about the case a model-backed line writer may put in its prompt, as JSON."""
    facts, nm = request.facts, _Names(request)
    query = facts.query
    asked: dict[str, str] | None = None
    if query is not None:
        asked = {"kind": query.kind.value}
        if query.slot is not None:
            asked["time"] = nm.span(query.slot)
        if query.location is not None:
            asked["place"] = nm.loc[query.location]
        if query.person is not None:
            asked["person"] = nm.person[query.person]
        if query.item is not None:
            asked["item"] = nm.item[query.item]
    speaker = request.speaker
    data = {
        "lang": request.lang.value,
        "speaker": {
            "name": speaker.name.get(request.lang),
            "role": speaker.role.get(request.lang),
            "persona": speaker.persona.get(request.lang),
        },
        "question": asked,
        "stance": facts.stance.value,
        "tone": (facts.tone or Tone.CALM).value,
        "repeat": request.repeat,
        "facts": list(fact_sentences(request)),
    }
    return json.dumps(data, ensure_ascii=False)


# --- Post-check ----------------------------------------------------------------------------------


def _authorised(request: LineRequest, lexicon: Lexicon) -> tuple[set[str], set[int]]:
    facts = request.facts
    ids: set[str] = {facts.speaker}
    slots: set[int] = set()
    query = facts.query
    if query is not None:
        ids |= {x for x in (query.person, query.location, query.item) if x is not None}
        if query.slot is not None:
            slots.add(query.slot)
    for s in facts.claims:
        ids.add(s.speaker)
        if s.source is not None:
            ids.add(s.source)
        slots.add(s.claim.slot)
        match s.claim:
            case PersonAt(person, location, _):
                ids |= {person, location}
            case Occupants(location, _, people):
                ids |= {location, *people}
            case ItemAt(item, location, _):
                ids |= {item, location}
    persona = request.speaker.persona
    ids |= {m.id for m in lexicon.mentions(persona.zh + "\n" + persona.en)}
    minutes = {m for t in slots for m in lexicon.slot_bounds(t)}
    minutes |= {lexicon.start_minute, lexicon.start_minute + lexicon.slot_minutes * lexicon.n_slots}
    return ids, minutes


def unauthorised(line: str, request: LineRequest, lexicon: Lexicon) -> tuple[str, ...]:
    """Names and clock times in `line` that its request does not authorise; empty means it passes.

    Catches invented people, places, items and times (digits or common spoken forms). It cannot
    catch a wrong relation between authorised names ("I saw Lin" when the facts say Lin was not
    there), negations, or names the lexicon does not know.
    """
    ids, minutes = _authorised(request, lexicon)
    bad = [m.text for m in lexicon.mentions(line) if m.id not in ids]
    bad += [f"{t // 60:02d}:{t % 60:02d}" for t in lexicon.times(line) if t not in minutes]
    return tuple(dict.fromkeys(bad))
