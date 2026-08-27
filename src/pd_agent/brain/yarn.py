"""Yarn mappings source for Minecraft Brain L2."""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from .models import (
    CompatibilityStatus,
    KnowledgeEnvironment,
    KnowledgeItem,
    KnowledgeNeed,
    KnowledgeProvenance,
    KnowledgeRetrievalStatus,
    KnowledgeSourceResult,
    KnowledgeType,
    SourceAuthority,
)
from .canonical import KnowledgePack, KnowledgePackManifest, KnowledgePolicy, KnowledgeRecord, canonical_json


@dataclass(frozen=True, slots=True)
class YarnSymbolRecord:
    """Parsed symbol from Yarn tiny mappings."""

    kind: str
    official: str
    intermediary: str
    named: str
    descriptor: str | None = None
    doc: str | None = None
    owner_named: str | None = None
    owner_intermediary: str | None = None
    line_number: int = 0

    def searchable_text(self) -> str:
        parts = [
            self.kind,
            self.official,
            self.intermediary,
            self.named,
            self.descriptor or "",
            self.doc or "",
            self.owner_named or "",
            self.owner_intermediary or "",
        ]
        return " ".join(part for part in parts if part).casefold()

    def content(self) -> dict[str, str | int | None]:
        return {
            "kind": self.kind,
            "official": self.official,
            "intermediary": self.intermediary,
            "named": self.named,
            "descriptor": self.descriptor,
            "doc": self.doc,
            "owner_named": self.owner_named,
            "owner_intermediary": self.owner_intermediary,
            "line_number": self.line_number,
        }


@dataclass(slots=True)
class YarnMappingsDocument:
    """Parsed Yarn tiny mappings document."""

    source_name: str
    version: str
    checksum_algorithm: str
    checksum: str
    raw_bytes: bytes
    records: tuple[YarnSymbolRecord, ...]

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        source_name: str,
        version: str,
        checksum_algorithm: str = "sha256",
    ) -> "YarnMappingsDocument":
        checksum = hashlib.sha256(data).hexdigest()
        tiny_text = cls._extract_tiny_text(data)
        records = cls._parse_tiny_text(tiny_text)
        return cls(
            source_name=source_name,
            version=version,
            checksum_algorithm=checksum_algorithm,
            checksum=checksum,
            raw_bytes=data,
            records=records,
        )

    @staticmethod
    def _extract_tiny_text(data: bytes) -> str:
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for name in zf.namelist():
                    if name.endswith("mappings.tiny"):
                        return zf.read(name).decode("utf-8")
            raise ValueError("mappings.tiny not found in Yarn archive")
        return data.decode("utf-8")

    @staticmethod
    def _parse_tiny_text(text: str) -> tuple[YarnSymbolRecord, ...]:
        lines = text.splitlines()
        if not lines or not lines[0].startswith("tiny\t2"):
            raise ValueError("unsupported tiny format")
        header_parts = lines[0].split("\t")
        namespaces = tuple(header_parts[3:])
        if not namespaces:
            raise ValueError("tiny header missing namespaces")
        records: list[YarnSymbolRecord] = []
        current_owner_named: str | None = None
        current_owner_intermediary: str | None = None
        last_doc_target: int | None = None

        for line_number, line in enumerate(lines[1:], start=2):
            if not line:
                continue
            parts = line.split("\t")
            indent = len(line) - len(line.lstrip("\t"))
            parts = [part for part in parts if part != "" or len(parts) == 1]
            if indent == 0 and parts[0] == "c" and len(parts) >= 1 + len(namespaces):
                values = parts[1 : 1 + len(namespaces)]
                namespace_map = {namespace: values[index] for index, namespace in enumerate(namespaces)}
                current_owner_intermediary = namespace_map.get("intermediary", values[0])
                current_owner_named = namespace_map.get("named", values[-1])
                records.append(
                    YarnSymbolRecord(
                        kind="class",
                        official=namespace_map.get("official", values[0]),
                        intermediary=current_owner_intermediary,
                        named=current_owner_named,
                        line_number=line_number,
                    )
                )
                last_doc_target = len(records) - 1
                continue
            if parts[0] in {"f", "m"} and len(parts) >= 2 + len(namespaces):
                descriptor = parts[1]
                values = parts[2 : 2 + len(namespaces)]
                namespace_map = {namespace: values[index] for index, namespace in enumerate(namespaces)}
                records.append(
                    YarnSymbolRecord(
                        kind="field" if parts[0] == "f" else "method",
                        official=namespace_map.get("official", values[0]),
                        intermediary=namespace_map.get("intermediary", values[0]),
                        named=namespace_map.get("named", values[-1]),
                        descriptor=descriptor,
                        owner_named=current_owner_named,
                        owner_intermediary=current_owner_intermediary,
                        line_number=line_number,
                    )
                )
                last_doc_target = len(records) - 1
                continue
            if parts[0] == "c" and len(parts) >= 2 and last_doc_target is not None:
                doc = parts[1]
                previous = records[last_doc_target]
                records[last_doc_target] = YarnSymbolRecord(
                    kind=previous.kind,
                    official=previous.official,
                    intermediary=previous.intermediary,
                    named=previous.named,
                    descriptor=previous.descriptor,
                    doc=doc,
                    owner_named=previous.owner_named,
                    owner_intermediary=previous.owner_intermediary,
                    line_number=previous.line_number,
                )
                continue
        return tuple(records)

    def search(self, query: str, limit: int = 5) -> tuple[YarnSymbolRecord, ...]:
        terms = self._normalize_terms(query)
        scored: list[tuple[int, int, YarnSymbolRecord]] = []
        for index, record in enumerate(self.records):
            score = self._score(record, terms)
            if score > 0:
                scored.append((score, index, record))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(record for _, _, record in scored[:limit])

    def _normalize_terms(self, query: str) -> tuple[str, ...]:
        raw = re.findall(r"[A-Za-z0-9_]+", query.casefold())
        expanded: list[str] = []
        for term in raw:
            expanded.append(term)
            if term.endswith("ies"):
                expanded.append(term[:-3] + "y")
            if term.endswith("s") and len(term) > 3:
                expanded.append(term[:-1])
        return tuple(dict.fromkeys(expanded))

    def _score(self, record: YarnSymbolRecord, terms: Sequence[str]) -> int:
        searchable = record.searchable_text()
        score = 0
        named = record.named.casefold()
        official = record.official.casefold()
        intermediary = record.intermediary.casefold()
        doc = (record.doc or "").casefold()
        for term in terms:
            if term == named or term == official or term == intermediary:
                score += 80
                continue
            if term in named:
                score += 50
            elif term in official or term in intermediary:
                score += 35
            elif term in searchable:
                score += 15
            if term in doc:
                score += 20
        if record.kind == "class":
            score += 5
        return score


@dataclass(slots=True)
class YarnKnowledgeSource:
    """Deterministic Yarn mappings source."""

    version: str = "1.21.11+build.6"
    minecraft_version: str = "1.21.11"
    mappings_namespace: str = "yarn"
    repository_url: str = "https://maven.fabricmc.net"
    timeout_seconds: float = 30.0
    fetcher: Callable[[str, float], bytes] | None = None
    artifact_bytes: bytes | None = None
    artifact_checksum: str | None = None
    _document: YarnMappingsDocument | None = field(default=None, init=False, repr=False)

    source_id: str = field(init=False)
    source_kind: str = field(init=False)
    artifact_version: str = field(init=False)
    artifact_coordinate: str = field(init=False)
    artifact_url: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", "net.fabricmc:yarn")
        object.__setattr__(self, "source_kind", "yarn-mappings")
        object.__setattr__(self, "artifact_version", self.version)
        coordinate = f"net.fabricmc:yarn:{self.version}:v2"
        object.__setattr__(self, "artifact_coordinate", coordinate)
        artifact_url = (
            f"{self.repository_url.rstrip('/')}/net/fabricmc/yarn/{self.version}/"
            f"yarn-{self.version}-v2.jar"
        )
        object.__setattr__(self, "artifact_url", artifact_url)
        if self.fetcher is None:
            object.__setattr__(self, "fetcher", self._default_fetcher)

    def supports(self, need: KnowledgeNeed) -> bool:
        return need.type in {KnowledgeType.SYMBOL, KnowledgeType.MAPPING}

    def compatibility(self, environment: KnowledgeEnvironment) -> CompatibilityStatus:
        if environment.minecraft_version is None:
            return CompatibilityStatus.UNKNOWN
        if environment.minecraft_version != self.minecraft_version:
            return CompatibilityStatus.INCOMPATIBLE
        if environment.mappings_namespace is None or environment.mappings_version is None:
            return CompatibilityStatus.UNKNOWN
        if environment.mappings_namespace != self.mappings_namespace:
            return CompatibilityStatus.INCOMPATIBLE
        if environment.mappings_version != self.version:
            return CompatibilityStatus.INCOMPATIBLE
        return CompatibilityStatus.COMPATIBLE

    def resolve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeSourceResult:
        if not self.supports(need):
            return KnowledgeSourceResult(
                status=KnowledgeRetrievalStatus.UNSUPPORTED_NEED,
                source_id=self.source_id,
                source_kind=self.source_kind,
                need=need,
                error=f"unsupported need type: {need.type.value}",
            )
        compatibility = self.compatibility(need.environment)
        if compatibility == CompatibilityStatus.INCOMPATIBLE:
            return KnowledgeSourceResult(
                status=KnowledgeRetrievalStatus.VERSION_MISMATCH,
                source_id=self.source_id,
                source_kind=self.source_kind,
                need=need,
                error="environment incompatible with Yarn source",
            )
        if offline and self.artifact_bytes is None and self._document is None:
            return KnowledgeSourceResult(
                status=KnowledgeRetrievalStatus.OFFLINE_MISS,
                source_id=self.source_id,
                source_kind=self.source_kind,
                need=need,
                error="offline and no preloaded artifact available",
            )

        try:
            document = self._load_document()
        except ValueError as exc:
            return KnowledgeSourceResult(
                status=KnowledgeRetrievalStatus.SOURCE_ERROR,
                source_id=self.source_id,
                source_kind=self.source_kind,
                need=need,
                error=str(exc),
            )
        if document is None:
            return KnowledgeSourceResult(
                status=KnowledgeRetrievalStatus.SOURCE_UNAVAILABLE,
                source_id=self.source_id,
                source_kind=self.source_kind,
                need=need,
                error="Yarn artifact unavailable",
            )

        if self.artifact_checksum is not None and self.artifact_checksum != document.checksum:
            return KnowledgeSourceResult(
                status=KnowledgeRetrievalStatus.PROVENANCE_INVALID,
                source_id=self.source_id,
                source_kind=self.source_kind,
                need=need,
                error="artifact checksum mismatch",
            )

        results = self._resolve_from_document(need, document)
        if not results:
            return KnowledgeSourceResult(
                status=KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE,
                source_id=self.source_id,
                source_kind=self.source_kind,
                need=need,
                error=f"no Yarn symbols matched query: {need.query}",
            )

        provenance = KnowledgeProvenance(
            source_id=self.source_id,
            source_kind=self.source_kind,
            locator=self.artifact_url,
            artifact_or_document_version=self.version,
            revision=self.version,
            retrieved_at=datetime.now(timezone.utc),
            checksum_algorithm=document.checksum_algorithm,
            checksum=document.checksum,
            license_id_or_policy="CC0-1.0",
        )
        items = tuple(
            KnowledgeItem(
                id=self._item_id(need, record, index),
                content={
                    "symbol": record.content(),
                    "query": need.query,
                    "source": {
                        "coordinate": self.artifact_coordinate,
                        "url": self.artifact_url,
                    },
                },
                environment=need.environment,
                authority=SourceAuthority.AUTHORITATIVE_ARTIFACT,
                provenance=provenance,
                metadata={
                    "match_score": score,
                    "query_terms": list(self._normalize_query_terms(need.query)),
                },
            )
            for index, (score, record) in enumerate(results)
        )
        return KnowledgeSourceResult(
            status=KnowledgeRetrievalStatus.SUCCESS,
            source_id=self.source_id,
            source_kind=self.source_kind,
            need=need,
            items=items,
            provenance=(provenance,),
        )

    def materialize_records(self, environment: KnowledgeEnvironment | None = None) -> tuple[KnowledgeRecord, ...]:
        """Materialize the loaded Tiny v2 artifact as deterministic SYMBOL records."""
        target = environment or KnowledgeEnvironment(
            minecraft_version=self.minecraft_version,
            mappings_namespace=self.mappings_namespace,
            mappings_version=self.version,
        )
        compatibility = self.compatibility(target)
        if compatibility != CompatibilityStatus.COMPATIBLE:
            raise ValueError(f"Yarn materialization requires compatible environment: {compatibility.value}")
        document = self._load_document()
        if document is None:
            raise ValueError("Yarn artifact unavailable")
        if self.artifact_checksum is not None and self.artifact_checksum != document.checksum:
            raise ValueError("artifact checksum mismatch")
        provenance = KnowledgeProvenance(
            source_id=self.source_id,
            source_kind=self.source_kind,
            locator=self.artifact_url,
            artifact_or_document_version=self.version,
            revision=self.version,
            checksum_algorithm=document.checksum_algorithm,
            checksum=document.checksum,
            license_id_or_policy="CC0-1.0",
        )
        records: list[KnowledgeRecord] = []
        for index, symbol in enumerate(document.records):
            content = {
                "namespace": self.mappings_namespace,
                "kind": symbol.kind,
                "official": symbol.official,
                "intermediary": symbol.intermediary,
                "named": symbol.named,
                "descriptor": symbol.descriptor,
                "doc": symbol.doc,
                "owner_named": symbol.owner_named,
                "owner_intermediary": symbol.owner_intermediary,
            }
            content_checksum = hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
            identity_input = {"source": self.source_id, "artifact": document.checksum, "index": index, "content": content}
            record_id = "yarn:" + hashlib.sha256(canonical_json(identity_input).encode("utf-8")).hexdigest()
            records.append(
                KnowledgeRecord(
                    record_id=record_id,
                    kind=KnowledgeType.SYMBOL,
                    content=content,
                    environment=target,
                    provenance=provenance,
                    authority=SourceAuthority.AUTHORITATIVE_ARTIFACT,
                    version_sensitive=True,
                    license_policy=KnowledgePolicy.REDISTRIBUTABLE,
                    integrity={"algorithm": "sha256", "value": content_checksum},
                    source_revision=self.version,
                )
            )
        return tuple(records)

    def materialize_pack(self, environment: KnowledgeEnvironment | None = None) -> KnowledgePack:
        """Build a partial, reproducible Yarn pack without migrating legacy caches."""
        target = environment or KnowledgeEnvironment(
            minecraft_version=self.minecraft_version,
            mappings_namespace=self.mappings_namespace,
            mappings_version=self.version,
        )
        records = self.materialize_records(target)
        document = self._document
        assert document is not None
        inventory = tuple({"record_id": item.record_id, "record_identity": item.identity()} for item in records)
        manifest = KnowledgePackManifest(
            environment=target,
            source_set=({
                "source_id": self.source_id,
                "source_kind": self.source_kind,
                "version": self.version,
                "coordinate": self.artifact_coordinate,
                "locator": self.artifact_url,
                "checksum_algorithm": document.checksum_algorithm,
                "checksum": document.checksum,
                "authority": SourceAuthority.AUTHORITATIVE_ARTIFACT.value,
                "license_policy": "CC0-1.0",
            },),
            record_inventory=inventory,
            license_policy=KnowledgePolicy.REDISTRIBUTABLE,
        )
        return KnowledgePack(manifest, records)

    def to_knowledge_records(self, environment: KnowledgeEnvironment | None = None) -> tuple[KnowledgeRecord, ...]:
        """Compatibility alias for callers that use conversion terminology."""
        return self.materialize_records(environment)

    def _load_document(self) -> YarnMappingsDocument | None:
        if self._document is not None:
            return self._document
        if self.artifact_bytes is None:
            try:
                data = self.fetcher(self.artifact_url, self.timeout_seconds)
            except (urllib.error.URLError, TimeoutError, OSError):
                return None
        else:
            data = self.artifact_bytes
        try:
            document = YarnMappingsDocument.from_bytes(
                data,
                source_name=self.source_id,
                version=self.version,
            )
        except Exception as exc:  # noqa: BLE001 - source parsing must surface as retrieval error
            raise ValueError(f"invalid Yarn artifact: {exc}") from exc
        if self.artifact_checksum is None:
            object.__setattr__(self, "artifact_checksum", document.checksum)
        self._document = document
        return document

    def _resolve_from_document(
        self,
        need: KnowledgeNeed,
        document: YarnMappingsDocument,
    ) -> tuple[tuple[int, YarnSymbolRecord], ...]:
        matches = document.search(need.query, limit=5)
        scored: list[tuple[int, YarnSymbolRecord]] = []
        for record in matches:
            score = self._score_record(record, need.query)
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], item[1].line_number))
        return tuple(scored)

    def _score_record(self, record: YarnSymbolRecord, query: str) -> int:
        terms = self._normalize_query_terms(query)
        score = 0
        searchable = record.searchable_text()
        for term in terms:
            if term == record.named.casefold():
                score += 80
            elif term in record.named.casefold():
                score += 50
            elif term in searchable:
                score += 20
        if record.kind == "class":
            score += 5
        return score

    def _normalize_query_terms(self, query: str) -> tuple[str, ...]:
        terms = re.findall(r"[A-Za-z0-9_]+", query.casefold())
        expanded: list[str] = []
        for term in terms:
            expanded.append(term)
            if term.endswith("ies"):
                expanded.append(term[:-3] + "y")
            if term.endswith("s") and len(term) > 3:
                expanded.append(term[:-1])
        return tuple(dict.fromkeys(expanded))

    def _item_id(self, need: KnowledgeNeed, record: YarnSymbolRecord, index: int) -> str:
        data = {
            "source_id": self.source_id,
            "need_id": need.id,
            "query": need.query.casefold(),
            "record": record.content(),
            "index": index,
        }
        return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _default_fetcher(self, url: str, timeout: float) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "PD-Agent/0.3"})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec: B310
            return response.read()
