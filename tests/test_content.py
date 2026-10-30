"""Content pack tests."""

from loosethread.content import load_pack


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
