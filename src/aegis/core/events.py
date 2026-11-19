"""Synchronous, thread-safe publish/subscribe event bus."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from aegis.core.logging import get_logger

WILDCARD = "*"

log = get_logger("events")


@dataclass(frozen=True)
class Event:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


Handler = Callable[[Event], None]


class EventBus:
    """Delivers events to handlers subscribed to an exact topic or to ``"*"``.

    Handlers run on the publisher's thread. A failing handler is logged and skipped;
    it never breaks the publisher or other handlers.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        """Register ``handler``. Returns a function that unsubscribes it."""
        if not topic:
            raise ValueError("topic must be a non-empty string")
        with self._lock:
            self._subs[topic].append(handler)
        return lambda: self.unsubscribe(topic, handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            handlers = self._subs.get(topic, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> Event:
        if not topic or topic == WILDCARD:
            raise ValueError("cannot publish to an empty or wildcard topic")
        event = Event(topic=topic, payload=dict(payload or {}))
        with self._lock:
            handlers = [*self._subs.get(topic, []), *self._subs.get(WILDCARD, [])]
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                log.exception("Event handler %r failed on topic %r", handler, topic)
        return event

    def subscriber_count(self, topic: str) -> int:
        with self._lock:
            return len(self._subs.get(topic, []))
