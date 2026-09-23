"""Compact, stable OMOP class identifiers for NAACCR dictionary sections."""

from __future__ import annotations

import hashlib
import re

from sdc_cdm.db.errors import VocabularyError


def concept_class_id(section: str, parent_xml_element: str) -> str:
    raw = f"{section}\x00{parent_xml_element}"
    slug = re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]+", "_", f"{section}_{parent_xml_element}".upper())).strip("_")
    if not slug:
        slug = "NAACCR"
    if len(slug) <= 20:
        return slug
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:5].upper()
    return f"{slug[:14]}_{digest}"


def class_definitions(items: list[tuple[int, str, str, str]]) -> dict[str, str]:
    definitions: dict[str, str] = {}
    origins: dict[str, tuple[str, str]] = {}
    for _item_num, _name, section, parent in items:
        identifier = concept_class_id(section, parent)
        origin = (section, parent)
        if identifier in origins and origins[identifier] != origin:
            raise VocabularyError(
                f"NAACCR concept class id collision: {identifier} for {origins[identifier]!r} and {origin!r}"
            )
        origins[identifier] = origin
        definitions[identifier] = f"{section} / {parent}" if parent else section
    return definitions
