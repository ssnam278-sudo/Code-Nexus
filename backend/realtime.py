"""Lightweight real-time event broker for the local and hosted prototype."""

from __future__ import annotations

import json
from queue import Empty, Queue
from typing import Any, Generator


_subscribers: set[Queue[str]] = set()


def subscribe() -> Queue[str]:
    queue: Queue[str] = Queue(maxsize=20)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: Queue[str]) -> None:
    _subscribers.discard(queue)


def publish(event: str, payload: dict[str, Any]) -> None:
    message = f"event: {event}\ndata: {json.dumps(payload)}\n\n"
    for queue in tuple(_subscribers):
        try:
            queue.put_nowait(message)
        except Exception:
            _subscribers.discard(queue)


def stream(queue: Queue[str]) -> Generator[str, None, None]:
    yield ": connected\n\n"
    try:
        while True:
            try:
                yield queue.get(timeout=25)
            except Empty:
                yield ": heartbeat\n\n"
    finally:
        unsubscribe(queue)
