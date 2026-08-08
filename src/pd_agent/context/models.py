"""Context model for PD Agent v0.1."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from pd_agent.core import AgentMessage, ExecutionLimits, RunState
from pd_agent.project import ProjectSnapshot
from pd_agent.reporting.redaction import Redactor, json_ready


@dataclass(frozen=True, slots=True)
class ContextItem:
    """Single context fragment."""

    source: str
    priority: int
    content: str
    label: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "priority": self.priority,
            "content": self.content,
            "label": self.label,
            "metadata": dict(self.metadata),
            "truncated": self.truncated,
        }

    def with_content(
        self,
        *,
        content: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        truncated: bool | None = None,
    ) -> "ContextItem":
        return replace(
            self,
            content=self.content if content is None else content,
            metadata=self.metadata if metadata is None else metadata,
            truncated=self.truncated if truncated is None else truncated,
        )

    def render(self) -> str:
        lines = [
            f"[source] {self.source}",
            f"[priority] {self.priority}",
        ]
        if self.label:
            lines.insert(1, f"[label] {self.label}")
        if self.truncated:
            lines.append("[truncated] true")
        if self.metadata:
            lines.append(f"[metadata] {json_ready(dict(self.metadata))}")
        lines.append("[content]")
        lines.append(self.content)
        return "\n".join(lines).rstrip()

    @classmethod
    def from_text(
        cls,
        *,
        source: str,
        priority: int,
        content: str,
        label: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        truncated: bool = False,
    ) -> "ContextItem":
        return cls(
            source=source,
            priority=priority,
            content=content,
            label=label,
            metadata=dict(metadata or {}),
            truncated=truncated,
        )


@dataclass(frozen=True, slots=True)
class ContextBundle:
    """Ordered, bounded context payload."""

    items: tuple[ContextItem, ...] = ()
    max_bytes: int = 0
    total_bytes: int = 0
    truncated: bool = False
    omitted_count: int = 0
    omitted_labels: tuple[str, ...] = ()

    def to_text(self) -> str:
        return "\n\n".join(item.render() for item in self.items)

    def to_messages(self) -> tuple[AgentMessage, ...]:
        if not self.items:
            return ()
        return (
            AgentMessage(
                role="system",
                content=self.to_text(),
                metadata={
                    "context_items": len(self.items),
                    "context_bytes": self.total_bytes,
                    "context_max_bytes": self.max_bytes,
                    "context_truncated": self.truncated,
                    "context_omitted_count": self.omitted_count,
                    "context_omitted_labels": list(self.omitted_labels),
                },
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "max_bytes": self.max_bytes,
            "total_bytes": self.total_bytes,
            "truncated": self.truncated,
            "omitted_count": self.omitted_count,
            "omitted_labels": list(self.omitted_labels),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextBundle":
        return cls(
            items=tuple(
                ContextItem.from_text(
                    source=str(item["source"]),
                    priority=int(item["priority"]),
                    content=str(item["content"]),
                    label=item.get("label"),
                    metadata=dict(item.get("metadata", {})),
                    truncated=bool(item.get("truncated", False)),
                )
                for item in data.get("items", [])
            ),
            max_bytes=int(data.get("max_bytes", 0)),
            total_bytes=int(data.get("total_bytes", 0)),
            truncated=bool(data.get("truncated", False)),
            omitted_count=int(data.get("omitted_count", 0)),
            omitted_labels=tuple(str(item) for item in data.get("omitted_labels", [])),
        )

    @classmethod
    def build(
        cls,
        items: Sequence[ContextItem],
        *,
        max_bytes: int,
        redactor: Redactor | None = None,
    ) -> "ContextBundle":
        redactor = redactor or Redactor()
        ordered = list(items)
        rendered_items: list[ContextItem] = []
        omitted_labels: list[str] = []
        total_bytes = 0

        for item in ordered:
            safe_item = _redact_item(item, redactor)
            separator_bytes = 2 if rendered_items else 0
            rendered, item_bytes, truncated = _fit_item(
                safe_item,
                max_bytes - total_bytes - separator_bytes,
            )
            if rendered is None:
                omitted_labels.append(_item_label(safe_item))
                continue
            rendered_items.append(rendered)
            total_bytes += separator_bytes + item_bytes
            if truncated:
                omitted_labels.extend(_item_label(remaining) for remaining in ordered[len(rendered_items) :])
                break

        return cls(
            items=tuple(rendered_items),
            max_bytes=max_bytes,
            total_bytes=total_bytes,
            truncated=bool(omitted_labels) or any(item.truncated for item in rendered_items),
            omitted_count=len(omitted_labels),
            omitted_labels=tuple(omitted_labels),
        )


@dataclass(frozen=True, slots=True)
class ContextRequest:
    """Inputs provided to context sources."""

    project_snapshot: ProjectSnapshot | None = None
    run_state: RunState | None = None
    external_context: tuple[Any, ...] = ()
    limits: ExecutionLimits | None = None
    redactor: Redactor | None = None


def _redact_item(item: ContextItem, redactor: Redactor) -> ContextItem:
    return item.with_content(
        content=redactor.redact_text(item.content),
        metadata=redactor.redact_data(dict(item.metadata)),
    )


def _fit_item(item: ContextItem, remaining_bytes: int) -> tuple[ContextItem | None, int, bool]:
    if remaining_bytes <= 0:
        return None, 0, False

    rendered = item.render()
    encoded = rendered.encode("utf-8")
    if len(encoded) <= remaining_bytes:
        return item, len(encoded), False

    header = item.with_content(
        content="",
        truncated=True,
        metadata={
            **dict(item.metadata),
            "truncated": True,
            "original_bytes": len(item.content.encode("utf-8")),
        },
    ).render()
    header_bytes = len(header.encode("utf-8"))
    if header_bytes > remaining_bytes:
        return None, 0, False

    content_budget = remaining_bytes - header_bytes
    truncated_content = _truncate_utf8_tail(item.content, content_budget)
    truncated_item = item.with_content(
        content=truncated_content,
        metadata={
            **dict(item.metadata),
            "truncated": True,
            "original_bytes": len(item.content.encode("utf-8")),
        },
        truncated=True,
    )
    truncated_rendered = truncated_item.render()
    truncated_bytes = len(truncated_rendered.encode("utf-8"))
    if truncated_bytes > remaining_bytes:
        return None, 0, False
    return truncated_item, truncated_bytes, True


def _truncate_utf8_tail(text: str, limit_bytes: int) -> str:
    if limit_bytes <= 0:
        return "..."
    encoded = text.encode("utf-8")
    if len(encoded) <= limit_bytes:
        return text
    suffix = "..."
    suffix_bytes = len(suffix.encode("utf-8"))
    if limit_bytes <= suffix_bytes:
        return suffix
    budget = limit_bytes - suffix_bytes
    chunk = encoded[-budget:]
    while chunk:
        try:
            return chunk.decode("utf-8") + suffix
        except UnicodeDecodeError as exc:
            if exc.start == 0:
                chunk = chunk[1:]
            else:
                chunk = chunk[: exc.start]
    return suffix


def _item_label(item: ContextItem) -> str:
    return item.label or item.source
