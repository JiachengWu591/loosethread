"""Template lines, the line payload and the entity post-check."""

import json
from dataclasses import replace

import pytest

from loosethread.content import load_pack
from loosethread.generator import generate
from loosethread.lexicon import Lexicon
from loosethread.lines import line_payload, template_line, unauthorised
from loosethread.lookup import AnswerBook, in_scope_queries
from loosethread.model import AllowedFacts, Lang, Query, QueryKind, Stance, Tone
from loosethread.npc import ClarifyReason, LineRequest

CASE = generate(7).case
WORLD = CASE.view.world
LEX = Lexicon.build(WORLD, CASE.view.crime, load_pack())
BOOK = AnswerBook.from_truth(WORLD, CASE.truth)
PEOPLE = {p.id: p for p in WORLD.people}


def _request(query: Query, lang: Lang, repeat: bool = False) -> LineRequest:
    facts = replace(BOOK.answer(query), tone=Tone.CALM)
    return LineRequest(lang, PEOPLE[query.addressee], facts, WORLD, repeat=repeat)


@pytest.mark.parametrize("lang", list(Lang))
@pytest.mark.parametrize("seed", [0, 7, 213])
def test_template_lines_pass_the_post_check(seed: int, lang: Lang) -> None:
    case = generate(seed).case
    world = case.view.world
    lexicon = Lexicon.build(world, case.view.crime, load_pack())
    book = AnswerBook.from_truth(world, case.truth)
    people = {p.id: p for p in world.people}
    extra = [
        Query(kind, p.id)
        for p in world.people
        for kind in (QueryKind.SMALL_TALK, QueryKind.OUT_OF_SCOPE)
    ]
    for query in [*in_scope_queries(world), *extra]:
        request = LineRequest(lang, people[query.addressee], book.answer(query), world)
        line = template_line(request)
        assert line
        assert unauthorised(line, request, lexicon) == (), line


def test_post_check_catches_invented_names_and_times() -> None:
    lin = next(p.id for p in WORLD.people if p.id != CASE.truth.culprit)
    request = _request(Query(QueryKind.SMALL_TALK, lin), Lang.ZH)
    others = [p for p in WORLD.people if p.id != lin]
    invented = f"我 21:15 在书房看见{others[0].name.zh}了。"
    found = unauthorised(invented, request, LEX)
    assert others[0].name.zh in found
    assert "21:15" in found
    assert "书房" in found
    assert unauthorised("是啊，雨真大。", request, LEX) == ()


def test_clarify_lines_follow_the_reason() -> None:
    speaker = WORLD.people[0]
    facts = AllowedFacts(speaker.id, None, Stance.CLARIFY)
    zh = LineRequest(Lang.ZH, speaker, facts, WORLD, reason=ClarifyReason.BAD_TIME)
    en = LineRequest(Lang.EN, speaker, facts, WORLD, reason=ClarifyReason.NEED_TIME)
    assert "20:00" in template_line(zh)
    assert "22:00" in template_line(zh)
    assert template_line(en).startswith("Which time")
    with pytest.raises(ValueError, match="clarify reason"):
        LineRequest(Lang.ZH, speaker, facts, WORLD)
    for reason in ClarifyReason:
        for lang in Lang:
            request = LineRequest(lang, speaker, facts, WORLD, reason=reason)
            assert unauthorised(template_line(request), request, LEX) == (), (reason, lang)


def test_repeat_and_tone_prefixes() -> None:
    who = WORLD.people[1].id
    query = Query(QueryKind.WHERE, who, slot=CASE.view.crime.window[0])
    plain = template_line(_request(query, Lang.ZH))
    again = template_line(_request(query, Lang.ZH, repeat=True))
    assert again == "刚才说过了：" + plain
    irritated = replace(
        _request(query, Lang.EN), facts=replace(BOOK.answer(query), tone=Tone.IRRITATED)
    )
    assert template_line(irritated).startswith("You ask a lot of questions.")


def test_payload_holds_only_the_allowed_facts() -> None:
    culprit = CASE.truth.culprit
    query = Query(QueryKind.WHERE, culprit, slot=CASE.truth.events[0].slot)
    payload = json.loads(line_payload(_request(query, Lang.ZH)))
    assert set(payload) == {"lang", "speaker", "question", "stance", "tone", "repeat", "facts"}
    assert set(payload["speaker"]) == {"name", "role", "persona"}
    text = json.dumps(payload, ensure_ascii=False)
    scene = next(x.name.zh for x in WORLD.locations if x.id == CASE.view.crime.location)
    # The culprit's answer for the theft slot is the alibi lie, so the scene is never named.
    assert scene not in text
    for marker in ("culprit", "thief", "lie", "truth", "motive", "犯人", "谎", "真相", "动机"):
        assert marker not in text
