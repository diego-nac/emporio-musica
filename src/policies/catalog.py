"""Small, versioned lexical lookup for the shop's public policy transcript."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


def normalize_query(value: str) -> str:
    """Normalize accents and spacing while retaining meaningful money syntax."""
    normalized = unicodedata.normalize("NFD", value.casefold())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.rstrip("?!.,;: \t")


@dataclass(frozen=True)
class PolicySection:
    id: str
    title: str
    content: str
    source_path: str
    pages: tuple[int, ...]
    version: str
    topics: tuple[str, ...]


@dataclass(frozen=True)
class PolicyLookup:
    status: str
    sections: tuple[PolicySection, ...]
    version: str


class PolicyService:
    """Loads a JSON catalog and caches only exact, allowlisted public FAQs."""

    FAQ_WHITELIST = frozenset(
        {
            "horario",
            "horario de funcionamento",
            "horario de atendimento",
            "qual e o horario da loja",
            "formas de pagamento",
            "politica de trocas e devolucoes",
            "frete e entregas",
            "politica de frete e entregas",
            "promocoes e descontos",
            "garantia",
            "privacidade e protecao de dados",
        }
    )

    def __init__(self, catalog_path: Path) -> None:
        self.catalog_path = Path(catalog_path)
        self._fingerprint: str | None = None
        self._version = ""
        self._sections: dict[str, PolicySection] = {}
        self._topics: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = ()

        @lru_cache(maxsize=128)
        def cached_lookup(version: str, normalized_query: str) -> PolicyLookup:
            return self._lookup_uncached(normalized_query, version)

        self._cached_lookup = cached_lookup
        self._load_catalog()

    def _load_catalog(self) -> None:
        raw_bytes = self.catalog_path.read_bytes()
        fingerprint = hashlib.sha256(raw_bytes).hexdigest()
        if fingerprint == self._fingerprint:
            return
        raw: dict[str, Any] = json.loads(raw_bytes)
        version = str(raw["version"])
        sections: dict[str, PolicySection] = {}
        for item in raw["sections"]:
            source = item["source"]
            section = PolicySection(
                id=str(item["id"]),
                title=str(item["title"]),
                content=str(item["content"]),
                source_path=str(source["path"]),
                pages=tuple(int(page) for page in source.get("pages", [])),
                version=str(item.get("version", version)),
                topics=tuple(str(topic) for topic in item.get("topics", [])),
            )
            sections[section.id] = section

        topics = tuple(
            (
                str(topic["id"]),
                tuple(normalize_query(alias) for alias in topic["aliases"]),
                tuple(str(section_id) for section_id in topic["sections"]),
            )
            for topic in raw["topics"]
        )
        known_ids = set(sections)
        for topic_id, aliases, section_ids in topics:
            if not aliases or any(not alias for alias in aliases):
                raise ValueError(f"Topic {topic_id!r} must have non-empty aliases")
            if any(section_id not in known_ids for section_id in section_ids):
                raise ValueError(f"Topic {topic_id!r} references an unknown section")

        self._sections = sections
        self._topics = topics
        self._version = version
        self._fingerprint = fingerprint
        self._cached_lookup.cache_clear()

    def _lookup_uncached(self, query: str, version: str) -> PolicyLookup:
        padded_query = f" {query} "
        matched_topics = {
            topic_id
            for topic_id, aliases, _ in self._topics
            if any(f" {alias} " in padded_query for alias in aliases)
        }
        section_ids = {
            section_id
            for topic_id, _, topic_section_ids in self._topics
            if topic_id in matched_topics
            for section_id in topic_section_ids
        }
        sections = tuple(
            self._sections[section_id]
            for section_id in self._sections
            if section_id in section_ids
        )
        return PolicyLookup("ok" if sections else "not_found", sections, version)

    def lookup(self, query: str) -> PolicyLookup:
        self._load_catalog()
        normalized = normalize_query(query)
        if not normalized:
            return PolicyLookup("not_found", (), self._version)
        if normalized in self.FAQ_WHITELIST:
            return self._cached_lookup(self._version, normalized)
        return self._lookup_uncached(normalized, self._version)

    def cache_info(self):
        return self._cached_lookup.cache_info()
