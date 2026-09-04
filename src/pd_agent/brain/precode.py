"""Deterministic pre-code knowledge need derivation for v0.7 I11."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any, Mapping, Sequence

from .models import KnowledgeEnvironment, KnowledgeNeed, KnowledgeType


class PreCodePhase(StrEnum):
    """Lifecycle boundary used by pre-code preparation."""

    PRE_FIRST_EDIT = "PRE_FIRST_EDIT"
    FIRST_EDIT = "FIRST_EDIT"


@dataclass(frozen=True, slots=True)
class PreCodeDerivation:
    """Needs plus deterministic reasons, ready for later trace persistence."""

    needs: tuple[KnowledgeNeed, ...]
    reasons: tuple[str, ...] = ()
    phase: PreCodePhase = PreCodePhase.PRE_FIRST_EDIT


@dataclass(slots=True)
class FirstEditTracker:
    """Recognize the first effective mutation without coupling to a tool name."""

    phase: PreCodePhase = PreCodePhase.PRE_FIRST_EDIT

    def observe(self, *, changed: bool, mutation: bool = True) -> PreCodePhase:
        if self.phase == PreCodePhase.PRE_FIRST_EDIT and changed and mutation:
            self.phase = PreCodePhase.FIRST_EDIT
        return self.phase

    @property
    def first_edit_seen(self) -> bool:
        return self.phase == PreCodePhase.FIRST_EDIT


_CAPABILITIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("registries", ("registry", "registries")),
    ("items", ("item", "items")),
    ("blocks", ("block", "blocks")),
    ("data_components", ("data component", "data components", "component")),
    ("block_entities", ("block entity", "block entities")),
    ("inventories", ("inventory", "inventories")),
    ("persistence", ("persist", "persistence", "reopen")),
    ("commands", ("command", "commands")),
    ("events", ("event", "events")),
    ("tags", ("tag", "tags")),
    ("recipes", ("recipe", "recipes", "crafting")),
    ("loot", ("loot", "loot table")),
)
_SYMBOL = re.compile(r"\b(?:[A-Z][A-Za-z0-9_]*\.)+[A-Z][A-Za-z0-9_]*\b")

_VERTICAL_A_DOMAINS: tuple[tuple[str, KnowledgeType, tuple[str, ...]], ...] = (
    ("vertical_a_composition", KnowledgeType.CAPABILITY, ("composition", "composed", "capability")),
    ("block_registration", KnowledgeType.API, ("block", "registry", "register")),
    ("block_item", KnowledgeType.PATTERN, ("block item", "blockitem", "associated item")),
    ("blockstate_asset", KnowledgeType.PATTERN, ("blockstate", "block state")),
    ("block_model_asset", KnowledgeType.PATTERN, ("block model", "model")),
    ("item_model_asset", KnowledgeType.PATTERN, ("item model",)),
    ("texture_reference", KnowledgeType.PATTERN, ("texture", "asset strategy", "resource")),
    ("recipe_resource", KnowledgeType.CONCEPT, ("recipe", "crafting")),
)


@dataclass(frozen=True, slots=True)
class PreCodeKnowledgeNeedDeriver:
    """Derive a small, repeatable set of needs from legitimate task signals."""

    max_needs: int = 8

    def __post_init__(self) -> None:
        if not 1 <= self.max_needs <= 8:
            raise ValueError("max_needs must be between 1 and 8")

    def derive(
        self,
        task_text: str,
        environment: KnowledgeEnvironment,
        *,
        capability_signals: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> PreCodeDerivation:
        if not isinstance(task_text, str) or not task_text.strip():
            return PreCodeDerivation(())
        metadata = metadata or {}
        text = " ".join((task_text, *[str(signal) for signal in capability_signals],
                         *[str(value) for value in metadata.values() if isinstance(value, str)])).casefold()
        if self._is_vertical_a(text):
            return self._derive_vertical_a(environment)
        capabilities = [capability for capability, aliases in _CAPABILITIES
                        if any(re.search(rf"\b{re.escape(alias)}\b", text) for alias in aliases)]
        needs: list[KnowledgeNeed] = []
        reasons: list[str] = []
        for capability in capabilities:
            for kind in (KnowledgeType.API, KnowledgeType.PATTERN, KnowledgeType.CAPABILITY):
                if len(needs) >= self.max_needs:
                    break
                needs.append(KnowledgeNeed(
                    id=f"pre-code:{capability}:{kind.value.casefold()}",
                    type=kind,
                    query=capability,
                    environment=environment,
                    hints=(capability,),
                    version_sensitive=True,
                ))
                reasons.append(f"capability signal: {capability}")
            if len(needs) >= self.max_needs:
                break

        for symbol in _SYMBOL.findall(task_text):
            if len(needs) >= self.max_needs:
                break
            needs.append(KnowledgeNeed(
                id=f"pre-code:symbol:{symbol}", type=KnowledgeType.SYMBOL,
                query=symbol, environment=environment, hints=(symbol,), version_sensitive=True,
            ))
            reasons.append(f"explicit symbol signal: {symbol}")

        unique: dict[tuple[str, str, str], KnowledgeNeed] = {}
        for need in needs:
            key = (need.type.value, need.query.casefold(), repr(need.environment.to_dict()))
            unique.setdefault(key, need)
        ordered = tuple(unique.values())[: self.max_needs]
        return PreCodeDerivation(ordered, tuple(reasons[:len(ordered)]))

    @staticmethod
    def _is_vertical_a(text: str) -> bool:
        return (
            bool(re.search(r"\bblock\b|\bbloque\b", text))
            and bool(re.search(r"block item|blockitem|associated item|item asociado", text))
            and bool(re.search(r"recipe|receta|crafting|craftable", text))
            and bool(re.search(r"asset|assets|resource|recursos|blockstate|model", text))
        )

    @staticmethod
    def _derive_vertical_a(environment: KnowledgeEnvironment) -> PreCodeDerivation:
        needs = tuple(
            KnowledgeNeed(
                id=f"pre-code:vertical-a:{domain}",
                type=need_type,
                query=domain,
                environment=environment,
                hints=(domain, *hints),
                version_sensitive=True,
            )
            for domain, need_type, hints in _VERTICAL_A_DOMAINS
        )
        return PreCodeDerivation(needs, tuple(f"Vertical A knowledge domain: {domain}" for domain, _, _ in _VERTICAL_A_DOMAINS))
