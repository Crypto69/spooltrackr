"""Tiny in-process pub/sub used to push live updates to SSE clients."""
import asyncio
import json
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: str, data: Any = None) -> None:
        msg = {"event": event, "data": data}
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # slow client; drop

    @staticmethod
    def encode(msg: dict) -> str:
        return json.dumps(msg, default=str)


bus = EventBus()
