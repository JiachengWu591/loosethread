"""Content packs: setting, map, roster, items and evidence templates as zh/en data files.

Packs live in `loosethread/content/<pack_id>.json`. Loading validates every field and fails loudly;
nothing in the generator hard-codes names or text.
"""

import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

from loosethread.model import (
    EvidenceKind,
    ItemId,
    Lang,
    LocalizedText,
    Location,
    LocationId,
    Person,
    PersonId,
)


@dataclass(frozen=True)
class EvidenceTemplate:
    """Text with `{person}`, `{time}`, `{location}`, `{client}` and `{item}` placeholders."""

    kind: EvidenceKind
    text: LocalizedText


@dataclass(frozen=True)
class RosterEntry:
    person: Person
    motive: LocalizedText
    haunts: frozenset[LocationId]  # places this character tends to spend time in


@dataclass(frozen=True)
class ItemSpec:
    id: ItemId
    name: LocalizedText


@dataclass(frozen=True)
class Aliases:
    """Extra names the question parser accepts for one person, location or item."""

    zh: tuple[str, ...]
    en: tuple[str, ...]


@dataclass(frozen=True)
class ContentPack:
    id: str
    setting: LocalizedText
    start_minute: int
    slot_minutes: int
    crime_location: LocationId
    locations: tuple[Location, ...]
    optional_locations: frozenset[LocationId]
    client: Person
    client_haunts: frozenset[LocationId]
    roster: tuple[RosterEntry, ...]
    items: tuple[ItemSpec, ...]
    last_seen_template: EvidenceTemplate
    evidence_templates: tuple[tuple[LocationId, tuple[EvidenceTemplate, ...]], ...]
    fallback_templates: tuple[EvidenceTemplate, ...]
    # Opening text, lines joined by "\n" (long lines get wrapped, "" is a blank line);
    # placeholders {setting} {client} {item} {seen} {found}.
    intro: LocalizedText
    # Map drawing, lines joined by "\n". `{<location id>}` marks where an optional location's
    # snippet from `map_art_optional` attaches; it renders empty when that location is dropped.
    map_art: LocalizedText
    map_art_optional: tuple[tuple[LocationId, LocalizedText], ...]
    # Parser aliases by person, location or item id; names and roles are always accepted too.
    aliases: tuple[tuple[str, Aliases], ...] = ()

    def aliases_for(self, entity_id: str) -> tuple[str, ...]:
        for key, found in self.aliases:
            if key == entity_id:
                return (*found.zh, *found.en)
        return ()

    def map_picture(self, lang: Lang, present: frozenset[LocationId]) -> str:
        snippets = {
            str(loc): (text.get(lang) if loc in present else "")
            for loc, text in self.map_art_optional
        }
        return self.map_art.get(lang).format(**snippets)

    def templates_for(self, location: LocationId) -> tuple[EvidenceTemplate, ...]:
        for loc, templates in self.evidence_templates:
            if loc == location:
                return templates
        return self.fallback_templates

    def map_without(self, dropped: frozenset[LocationId]) -> tuple[Location, ...]:
        """The location graph with `dropped` locations (and edges to them) removed."""
        if self.crime_location in dropped:
            raise ValueError("cannot drop the crime location")
        return tuple(
            Location(loc.id, loc.name, loc.neighbors - dropped)
            for loc in self.locations
            if loc.id not in dropped
        )


@cache
def load_pack(pack_id: str = "mistpine") -> ContentPack:
    resource = files("loosethread") / "content" / f"{pack_id}.json"
    raw = json.loads(resource.read_text(encoding="utf-8"))
    return _parse_pack(_obj(raw, "pack"))


# --- Parsing helpers (JSON is untyped; every access is checked) ---------------------------------


def _obj(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected an object")
    return value


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{where}: expected a list")
    return value


def _str(obj: dict[str, Any], key: str, where: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}.{key}: expected a non-empty string")
    return value


def _int(obj: dict[str, Any], key: str, where: str) -> int:
    value = obj.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{where}.{key}: expected an integer")
    return value


def _text(obj: dict[str, Any], key: str, where: str) -> LocalizedText:
    inner = _obj(obj.get(key), f"{where}.{key}")
    return LocalizedText(
        zh=_str(inner, "zh", f"{where}.{key}"), en=_str(inner, "en", f"{where}.{key}")
    )


def _lines(obj: dict[str, Any], key: str, where: str) -> LocalizedText:
    """A zh/en pair of non-empty string lists, each joined with newlines."""
    inner = _obj(obj.get(key), f"{where}.{key}")

    def join(lang: str) -> str:
        items = _list(inner.get(lang), f"{where}.{key}.{lang}")
        if not items or not all(isinstance(x, str) for x in items):
            raise ValueError(f"{where}.{key}.{lang}: expected a non-empty list of strings")
        return "\n".join(items)

    return LocalizedText(zh=join("zh"), en=join("en"))


def _person(obj: dict[str, Any], where: str) -> Person:
    return Person(
        id=PersonId(_str(obj, "id", where)),
        name=_text(obj, "name", where),
        role=_text(obj, "role", where),
        persona=_text(obj, "persona", where),
    )


def _template(value: Any, where: str) -> EvidenceTemplate:
    obj = _obj(value, where)
    return EvidenceTemplate(
        kind=EvidenceKind(_str(obj, "kind", where)), text=_text(obj, "text", where)
    )


def _parse_pack(raw: dict[str, Any]) -> ContentPack:
    locations = tuple(
        Location(
            id=LocationId(_str(loc, "id", "locations")),
            name=_text(loc, "name", "locations"),
            neighbors=frozenset(
                LocationId(n) for n in _list(loc.get("neighbors"), "locations.neighbors")
            ),
        )
        for loc in (_obj(v, "locations[]") for v in _list(raw.get("locations"), "locations"))
    )
    location_ids = {loc.id for loc in locations}
    by_id = {loc.id: loc for loc in locations}
    for loc in locations:
        for other in loc.neighbors:
            if other not in by_id or loc.id not in by_id[other].neighbors:
                raise ValueError(f"locations: adjacency {loc.id!r}-{other!r} is broken")

    crime_location = LocationId(_str(raw, "crime_location", "pack"))
    optional = frozenset(
        LocationId(v) for v in _list(raw.get("optional_locations"), "optional_locations")
    )
    if crime_location not in location_ids or not optional <= location_ids:
        raise ValueError("pack: crime or optional location is not on the map")

    def haunts(obj: dict[str, Any], where: str) -> frozenset[LocationId]:
        found = frozenset(LocationId(v) for v in _list(obj.get("haunts"), f"{where}.haunts"))
        if not found <= location_ids - {crime_location}:
            raise ValueError(f"{where}.haunts: unknown location or the crime scene")
        return found

    roster = tuple(
        RosterEntry(
            person=_person(entry, "roster[]"),
            motive=_text(entry, "motive", "roster[]"),
            haunts=haunts(entry, "roster[]"),
        )
        for entry in (_obj(v, "roster[]") for v in _list(raw.get("roster"), "roster"))
    )
    client_raw = _obj(raw.get("client"), "client")
    items = tuple(
        ItemSpec(id=ItemId(_str(entry, "id", "items[]")), name=_text(entry, "name", "items[]"))
        for entry in (_obj(v, "items[]") for v in _list(raw.get("items"), "items"))
    )
    templates_raw = _obj(raw.get("evidence_templates"), "evidence_templates")
    evidence_templates = tuple(
        (
            LocationId(loc_id),
            tuple(_template(t, f"evidence_templates.{loc_id}") for t in _list(ts, loc_id)),
        )
        for loc_id, ts in templates_raw.items()
    )
    if not {loc for loc, _ in evidence_templates} <= location_ids - {crime_location}:
        raise ValueError("evidence_templates: unknown location, or a template for the crime scene")
    art_optional = _obj(raw.get("map_art_optional"), "map_art_optional")
    aliases_raw = _obj(raw.get("aliases", {}), "aliases")

    def names(entry: Any, where: str) -> tuple[str, ...]:
        found = _list(entry, where)
        if not all(isinstance(x, str) and x.strip() for x in found):
            raise ValueError(f"{where}: expected a list of non-empty strings")
        return tuple(found)

    aliases = tuple(
        (
            key,
            Aliases(
                zh=names(_obj(value, f"aliases.{key}").get("zh"), f"aliases.{key}.zh"),
                en=names(_obj(value, f"aliases.{key}").get("en"), f"aliases.{key}.en"),
            ),
        )
        for key, value in aliases_raw.items()
    )

    pack = ContentPack(
        id=_str(raw, "id", "pack"),
        setting=_text(raw, "setting", "pack"),
        start_minute=_int(raw, "start_minute", "pack"),
        slot_minutes=_int(raw, "slot_minutes", "pack"),
        crime_location=crime_location,
        locations=locations,
        optional_locations=optional,
        client=_person(client_raw, "client"),
        client_haunts=haunts(client_raw, "client"),
        roster=roster,
        items=items,
        last_seen_template=_template(raw.get("last_seen_template"), "last_seen_template"),
        evidence_templates=evidence_templates,
        fallback_templates=tuple(
            _template(t, "fallback_templates")
            for t in _list(raw.get("fallback_templates"), "fallback_templates")
        ),
        intro=_lines(raw, "intro", "pack"),
        map_art=_lines(raw, "map_art", "pack"),
        map_art_optional=tuple(
            (LocationId(loc_id), _text(art_optional, loc_id, "map_art_optional"))
            for loc_id in art_optional
        ),
        aliases=aliases,
    )
    _check_text(pack)
    ids = [pack.client.id, *(e.person.id for e in roster)]
    if len(set(ids)) != len(ids):
        raise ValueError("pack: duplicate person ids")
    known = {*ids, *location_ids, *(i.id for i in items)}
    unknown = sorted(key for key, _ in aliases if key not in known)
    if unknown:
        raise ValueError(f"aliases: unknown ids {unknown}")
    if not pack.fallback_templates or not pack.items or not pack.roster:
        raise ValueError("pack: needs fallback templates, items and a roster")
    return pack


def _check_text(pack: ContentPack) -> None:
    """The intro formats, and the map drawing names exactly the locations on the map.

    This cannot check that the drawn lines match the adjacency list; that stays a review item.
    """
    if {loc for loc, _ in pack.map_art_optional} != pack.optional_locations:
        raise ValueError("map_art_optional: must cover exactly the optional locations")
    every = frozenset(loc.id for loc in pack.locations)
    for lang in Lang:
        try:
            pack.intro.get(lang).format(setting="", client="", item="", seen="", found="")
            pictures = [
                (present, pack.map_picture(lang, present))
                for present in (every, every - pack.optional_locations)
            ]
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"intro/map_art ({lang.value}): bad placeholder {exc}") from exc
        for present, picture in pictures:
            for loc in pack.locations:
                if (loc.name.get(lang) in picture) != (loc.id in present):
                    raise ValueError(f"map_art ({lang.value}): {loc.id!r} drawn wrongly")
