"""Content pack tests."""

import json
from importlib.resources import files
from typing import Any

import pytest

from loosethread.content import _parse_pack, load_pack
from loosethread.model import Lang


def _raw_pack() -> dict[str, Any]:
    text = (files("loosethread") / "content" / "mistpine.json").read_text(encoding="utf-8")
    raw: dict[str, Any] = json.loads(text)
    return raw


def test_default_pack_loads_and_is_consistent() -> None:
    pack = load_pack()
    by_id = {loc.id: loc for loc in pack.locations}
    for loc in pack.locations:
        for other in loc.neighbors:
            assert loc.id in by_id[other].neighbors
    assert pack.crime_location in by_id
    assert len(pack.roster) >= 6
    assert all(e.haunts for e in pack.roster)


def test_every_template_formats_in_both_languages() -> None:
    pack = load_pack()
    fields = {"person": "X", "client": "Y", "item": "Z", "location": "L", "time": "20:00"}
    templates = [pack.last_seen_template, *pack.fallback_templates]
    templates += [t for _, ts in pack.evidence_templates for t in ts]
    for template in templates:
        assert template.text.zh.format(**fields)
        assert template.text.en.format(**fields)


def test_dropping_optional_locations_keeps_the_map_symmetric() -> None:
    pack = load_pack()
    trimmed = pack.map_without(pack.optional_locations)
    ids = {loc.id for loc in trimmed}
    assert ids.isdisjoint(pack.optional_locations)
    assert all(loc.neighbors <= ids for loc in trimmed)


@pytest.mark.parametrize("lang", list(Lang))
def test_map_picture_shows_optional_locations_only_when_present(lang: Lang) -> None:
    pack = load_pack()
    every = frozenset(loc.id for loc in pack.locations)
    terrace = next(loc for loc in pack.locations if loc.id == "terrace").name.get(lang)
    assert terrace in pack.map_picture(lang, every)
    assert terrace not in pack.map_picture(lang, every - pack.optional_locations)


def test_map_art_missing_a_location_is_rejected() -> None:
    raw = _raw_pack()
    raw["map_art"]["zh"] = [line.replace("客房区", "") for line in raw["map_art"]["zh"]]
    with pytest.raises(ValueError, match="guest_wing"):
        _parse_pack(raw)


def test_aliases_load_and_unknown_ids_are_rejected() -> None:
    assert "印章" in load_pack().aliases_for("jade_seal")
    raw = _raw_pack()
    raw["aliases"]["ghost"] = {"zh": ["鬼"], "en": []}
    with pytest.raises(ValueError, match="ghost"):
        _parse_pack(raw)


def test_intro_with_an_unknown_placeholder_is_rejected() -> None:
    raw = _raw_pack()
    raw["intro"]["en"] = ["{culprit} did it."]
    with pytest.raises(ValueError, match="placeholder"):
        _parse_pack(raw)
