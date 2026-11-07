"""Event-publishing interface for case workflow events."""

from typing import Any, Protocol


class EventPublisher(Protocol):
    def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


class NoOpEventPublisher:
    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        return None
