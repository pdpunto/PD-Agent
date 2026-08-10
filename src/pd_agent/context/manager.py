"""Context manager for PD Agent v0.1."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from pd_agent.core import AgentMessage, ContextSource, ExecutionLimits
from pd_agent.reporting.redaction import Redactor

from .knowledge import KnowledgeContextSource, KnowledgeTrace
from .models import ContextBundle, ContextItem, ContextRequest
from .sources import ExternalContextSource, ProjectContextSource, RunContextSource


@dataclass(frozen=True, slots=True)
class _RegisteredSource:
    name: str
    source: ContextSource


class ContextManager:
    """Combine context sources into a bounded provider-neutral bundle."""

    def __init__(
        self,
        sources: Sequence[tuple[str, ContextSource]] | None = None,
        *,
        redactor: Redactor | None = None,
        max_context_bytes: int = 2_000_000,
    ) -> None:
        self.redactor = redactor or Redactor()
        self.max_context_bytes = max_context_bytes
        default_sources = (
            ("project", ProjectContextSource()),
            ("run", RunContextSource()),
            ("knowledge", KnowledgeContextSource()),
            ("external", ExternalContextSource()),
        )
        source_pairs = sources if sources is not None else default_sources
        self._sources = tuple(_RegisteredSource(name=name, source=source) for name, source in source_pairs)
        self.last_knowledge_traces: tuple[KnowledgeTrace, ...] = ()

    def register_source(self, name: str, source: ContextSource) -> None:
        self._sources = (*self._sources, _RegisteredSource(name=name, source=source))

    def collect(self, request: ContextRequest) -> ContextBundle:
        items: list[ContextItem] = []
        traces: list[KnowledgeTrace] = []
        for binding_index, binding in enumerate(self._sources):
            source_items = binding.source.get(request) or ()
            for item_index, item in enumerate(source_items):
                normalized = self._normalize_item(item, binding.name)
                items.append(
                    normalized.with_content(
                        metadata={
                            **dict(normalized.metadata),
                            "source_name": binding.name,
                            "source_index": binding_index,
                            "item_index": item_index,
                        },
                    )
                )
            source_traces = getattr(binding.source, "last_traces", ())
            if source_traces:
                traces.extend(trace for trace in source_traces if trace is not None)

        ordered = sorted(
            items,
            key=lambda item: (
                item.priority,
                item.source.casefold(),
                (item.label or "").casefold(),
                item.metadata.get("source_index", 0),
                item.metadata.get("item_index", 0),
            ),
        )
        max_bytes = request.limits.max_context_bytes if request.limits is not None else self.max_context_bytes
        self.last_knowledge_traces = tuple(traces)
        return ContextBundle.build(ordered, max_bytes=max_bytes, redactor=request.redactor or self.redactor)

    def build_context(
        self,
        *,
        project_snapshot=None,
        run_state=None,
        external_context=(),
        limits: ExecutionLimits | None = None,
        redactor: Redactor | None = None,
    ) -> ContextBundle:
        return self.collect(
            ContextRequest(
                project_snapshot=project_snapshot,
                run_state=run_state,
                external_context=self._normalize_external_context(external_context),
                limits=limits,
                redactor=redactor,
            )
        )

    def to_messages(self, request: ContextRequest) -> tuple[AgentMessage, ...]:
        return self.collect(request).to_messages()

    def _normalize_item(self, item: object, default_source: str) -> ContextItem:
        if isinstance(item, ContextItem):
            if not item.source:
                return item.with_content(metadata=dict(item.metadata))
            return item
        if isinstance(item, str):
            return ContextItem.from_text(
                source=default_source,
                priority=100,
                label=default_source,
                content=item,
            )
        if isinstance(item, dict):
            return ContextItem.from_text(
                source=str(item.get("source", default_source)),
                priority=int(item.get("priority", 100)),
                label=item.get("label"),
                content=str(item.get("content", "")),
                metadata=dict(item.get("metadata", {})),
                truncated=bool(item.get("truncated", False)),
            )
        return ContextItem.from_text(
            source=default_source,
            priority=100,
            label=default_source,
            content=str(item),
            metadata={"kind": type(item).__name__},
        )

    def _normalize_external_context(self, external_context: object) -> tuple[object, ...]:
        if external_context is None:
            return ()
        if isinstance(external_context, tuple):
            return external_context
        if isinstance(external_context, str):
            return (external_context,)
        if isinstance(external_context, Sequence):
            return tuple(external_context)
        return (external_context,)
