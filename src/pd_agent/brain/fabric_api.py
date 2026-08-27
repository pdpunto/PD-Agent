"""Fabric API artifact source for the v0.7 knowledge foundation."""

from __future__ import annotations

import hashlib
import io
import json
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .canonical import KnowledgePack, KnowledgePackManifest, KnowledgePolicy, KnowledgeRecord, canonical_json
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


@dataclass(slots=True)
class FabricApiKnowledgeSource:
    """Conservative source adapter backed by a pinned Fabric API JAR."""

    version: str = "0.141.6+1.21.11"
    minecraft_version: str = "1.21.11"
    loader_version: str = "0.19.3"
    repository_url: str = "https://maven.fabricmc.net"
    timeout_seconds: float = 30.0
    fetcher: Callable[[str, float], bytes] | None = None
    artifact_bytes: bytes | None = None
    artifact_checksum: str | None = None
    _records: tuple[KnowledgeRecord, ...] | None = field(default=None, init=False, repr=False)

    source_id: str = field(init=False)
    source_kind: str = field(init=False)
    artifact_version: str = field(init=False)
    artifact_coordinate: str = field(init=False)
    artifact_url: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", "net.fabricmc.fabric-api:fabric-api")
        object.__setattr__(self, "source_kind", "fabric-api-artifact")
        object.__setattr__(self, "artifact_version", self.version)
        coordinate = f"net.fabricmc.fabric-api:fabric-api:{self.version}"
        object.__setattr__(self, "artifact_coordinate", coordinate)
        url = (
            f"{self.repository_url.rstrip('/')}/net/fabricmc/fabric-api/fabric-api/{self.version}/"
            f"fabric-api-{self.version}.jar"
        )
        object.__setattr__(self, "artifact_url", url)
        if self.fetcher is None:
            object.__setattr__(self, "fetcher", self._default_fetcher)

    def supports(self, need: KnowledgeNeed) -> bool:
        return need.type in {KnowledgeType.API, KnowledgeType.SYMBOL, KnowledgeType.CAPABILITY}

    def compatibility(self, environment: KnowledgeEnvironment) -> CompatibilityStatus:
        if environment.minecraft_version is None or environment.fabric_api_version is None:
            return CompatibilityStatus.UNKNOWN
        if environment.minecraft_version != self.minecraft_version:
            return CompatibilityStatus.INCOMPATIBLE
        if environment.fabric_api_version != self.version:
            return CompatibilityStatus.INCOMPATIBLE
        if environment.loader_version is None:
            return CompatibilityStatus.UNKNOWN
        if environment.loader_version != self.loader_version:
            return CompatibilityStatus.INCOMPATIBLE
        return CompatibilityStatus.COMPATIBLE

    @classmethod
    def from_artifact_path(cls, path: str | Path, **kwargs: object) -> "FabricApiKnowledgeSource":
        return cls(artifact_bytes=Path(path).read_bytes(), **kwargs)

    def resolve(self, need: KnowledgeNeed, offline: bool = False) -> KnowledgeSourceResult:
        if not self.supports(need):
            return self._result(need, KnowledgeRetrievalStatus.UNSUPPORTED_NEED, "unsupported need type")
        compatibility = self.compatibility(need.environment)
        if compatibility != CompatibilityStatus.COMPATIBLE:
            status = (KnowledgeRetrievalStatus.VERSION_MISMATCH if compatibility == CompatibilityStatus.INCOMPATIBLE
                      else KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE)
            return self._result(need, status, f"Fabric API environment is {compatibility.value}")
        if offline and self.artifact_bytes is None:
            return self._result(need, KnowledgeRetrievalStatus.OFFLINE_MISS, "offline and no artifact is loaded")
        try:
            records = self.materialize_records(need.environment)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            return self._result(need, KnowledgeRetrievalStatus.SOURCE_ERROR, str(exc))
        terms = [term.casefold() for term in need.query.split() if term]
        matches = tuple(record for record in records if all(term in canonical_json(record.content).casefold() for term in terms))
        if not matches:
            return self._result(need, KnowledgeRetrievalStatus.NO_COMPATIBLE_KNOWLEDGE, "no public Fabric API record matched")
        provenance = self._provenance()
        items = tuple(
            KnowledgeItem(
                id=record.record_id,
                content=record.content,
                environment=need.environment,
                authority=record.authority,
                provenance=provenance,
                metadata={"record_identity": record.identity(), "artifact_coordinate": self.artifact_coordinate},
            )
            for record in matches
        )
        return KnowledgeSourceResult(
            KnowledgeRetrievalStatus.SUCCESS, self.source_id, self.source_kind, need,
            items=items, provenance=(provenance,),
        )

    def materialize_records(self, environment: KnowledgeEnvironment | None = None) -> tuple[KnowledgeRecord, ...]:
        target = environment or KnowledgeEnvironment(
            minecraft_version=self.minecraft_version, loader_version=self.loader_version,
            fabric_api_version=self.version,
        )
        if self.compatibility(target) != CompatibilityStatus.COMPATIBLE:
            raise ValueError("Fabric API materialization requires compatible environment")
        if self._records is not None:
            return self._records
        data = self._load_artifact()
        checksum = hashlib.sha256(data).hexdigest()
        if self.artifact_checksum is not None and self.artifact_checksum != checksum:
            raise ValueError("artifact checksum mismatch")
        object.__setattr__(self, "artifact_checksum", checksum)
        try:
            names = self._public_class_names(data)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"invalid Fabric API artifact: {exc}") from exc
        provenance = self._provenance()
        records = []
        for name in names:
            content = {
                "module": name.split(".")[4] if len(name.split(".")) > 4 else "fabric-api",
                "package": name.rsplit(".", 1)[0],
                "class": name.rsplit(".", 1)[-1],
                "qualified_name": name,
                "public_api": True,
                "artifact": self.artifact_coordinate,
            }
            content_checksum = hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
            record_id = "fabric-api:" + hashlib.sha256(
                canonical_json({"artifact": checksum, "qualified_name": name}).encode("utf-8")
            ).hexdigest()
            records.append(KnowledgeRecord(
                record_id=record_id, kind=KnowledgeType.API, content=content,
                environment=target, provenance=provenance,
                authority=SourceAuthority.AUTHORITATIVE_ARTIFACT,
                version_sensitive=True, license_policy=KnowledgePolicy.FETCH_CACHE_REFERENCE_ONLY,
                integrity={"algorithm": "sha256", "value": content_checksum}, source_revision=self.version,
            ))
        if not records:
            raise ValueError("artifact contains no public Fabric API records")
        result = tuple(records)
        object.__setattr__(self, "_records", result)
        return result

    def materialize_pack(self, environment: KnowledgeEnvironment | None = None) -> KnowledgePack:
        target = environment or KnowledgeEnvironment(
            minecraft_version=self.minecraft_version, loader_version=self.loader_version,
            fabric_api_version=self.version,
        )
        records = self.materialize_records(target)
        inventory = tuple({"record_id": record.record_id, "record_identity": record.identity()} for record in records)
        manifest = KnowledgePackManifest(
            environment=target,
            source_set=({
                "source_id": self.source_id, "source_kind": self.source_kind,
                "version": self.version, "coordinate": self.artifact_coordinate,
                "locator": self.artifact_url, "checksum_algorithm": "sha256",
                "checksum": self.artifact_checksum, "authority": SourceAuthority.AUTHORITATIVE_ARTIFACT.value,
                "license_policy": KnowledgePolicy.FETCH_CACHE_REFERENCE_ONLY.value,
            },),
            record_inventory=inventory, license_policy=KnowledgePolicy.FETCH_CACHE_REFERENCE_ONLY,
        )
        return KnowledgePack(manifest, records)

    def _load_artifact(self) -> bytes:
        if self.artifact_bytes is not None:
            return self.artifact_bytes
        assert self.fetcher is not None
        return self.fetcher(self.artifact_url, self.timeout_seconds)

    @staticmethod
    def _public_class_names(data: bytes) -> tuple[str, ...]:
        names: set[str] = set()
        with zipfile.ZipFile(io.BytesIO(data)) as outer:
            nested = [name for name in outer.namelist() if name.startswith("META-INF/jars/") and name.endswith(".jar")]
            for nested_name in sorted(nested):
                with zipfile.ZipFile(io.BytesIO(outer.read(nested_name))) as inner:
                    for entry in inner.namelist():
                        if not entry.endswith(".class") or "$" in entry:
                            continue
                        qualified = entry[:-6].replace("/", ".")
                        if not qualified.startswith("net.fabricmc.fabric.api."):
                            continue
                        if any(segment.casefold() in {"impl", "internal", "mixin", "client"} for segment in qualified.split(".")):
                            continue
                        names.add(qualified)
        return tuple(sorted(names))

    def _provenance(self) -> KnowledgeProvenance:
        return KnowledgeProvenance(
            source_id=self.source_id, source_kind=self.source_kind, locator=self.artifact_url,
            artifact_or_document_version=self.version, revision=self.version,
            checksum_algorithm="sha256", checksum=self.artifact_checksum,
            license_id_or_policy="Apache-2.0", retrieved_at=datetime.now(timezone.utc),
        )

    def _result(self, need: KnowledgeNeed, status: KnowledgeRetrievalStatus, error: str) -> KnowledgeSourceResult:
        return KnowledgeSourceResult(status, self.source_id, self.source_kind, need, error=error)

    def _default_fetcher(self, url: str, timeout: float) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "PD-Agent/0.7"})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec: B310
            return response.read()
