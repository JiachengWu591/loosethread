"""Answer lookup tests: answers follow the lie policy and are stable."""

import pytest

from loosethread.generator import generate
from loosethread.lookup import AnswerBook, in_scope_queries
from loosethread.model import (
    Occupants,
    PersonAt,
    PersonId,
    Query,
    QueryKind,
    SlotIndex,
    Stance,
)


def _book(seed: int = 11) -> tuple[AnswerBook, object]:
    case = generate(seed).case
    return AnswerBook.from_truth(case.view.world, case.truth), case


def test_same_query_same_answer() -> None:
    book, _ = _book()
    for query in in_scope_queries(book.world)[:200]:
        assert book.answer(query) == book.answer(query)


def test_liar_claims_the_lie_and_to_be_alone() -> None:
    case = generate(11).case
    book = AnswerBook.from_truth(case.view.world, case.truth)
    for lie in case.truth.lies:
        claim = lie.statement.claim
        assert isinstance(claim, PersonAt)
        where = book.answer(Query(QueryKind.WHERE, claim.person, slot=claim.slot))
        assert where.claims == (lie.statement,)
        company = book.answer(Query(QueryKind.WITH_WHOM, claim.person, slot=claim.slot))
        (said,) = company.claims
        assert said.claim == Occupants(claim.location, claim.slot, frozenset({claim.person}))


def test_truthful_answers_match_the_timeline() -> None:
    case = generate(11).case
    book = AnswerBook.from_truth(case.view.world, case.truth)
    lie_cells = {(lie.statement.speaker, lie.statement.claim.slot) for lie in case.truth.lies}
    for fact in case.truth.timeline:
        if (fact.person, fact.slot) in lie_cells:
            continue
        answer = book.answer(Query(QueryKind.WHERE, fact.person, slot=fact.slot))
        assert answer.claims[0].claim == fact


def test_view_testimony_is_the_lookup_output() -> None:
    case = generate(11).case
    book = AnswerBook.from_truth(case.view.world, case.truth)
    assert book.testimony() == case.view.testimony


def test_non_factual_queries_deflect() -> None:
    book, _ = _book()
    person = book.world.people[1].id
    for kind in (QueryKind.SMALL_TALK, QueryKind.OUT_OF_SCOPE):
        assert book.answer(Query(kind, person)).stance is Stance.DEFLECT
    other = book.world.people[2].id
    assert book.answer(Query(QueryKind.OPINION, person, person=other)).claims == ()


def test_unknown_entities_fail_closed() -> None:
    book, _ = _book()
    with pytest.raises(ValueError, match="unknown addressee"):
        book.answer(Query(QueryKind.WHERE, PersonId("ghost"), slot=SlotIndex(0)))
    person = book.world.people[0].id
    with pytest.raises(ValueError, match="outside the evening"):
        book.answer(Query(QueryKind.WHERE, person, slot=SlotIndex(99)))
