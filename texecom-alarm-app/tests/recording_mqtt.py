"""In-memory MQTT publisher stub for unit tests (no broker)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class PublishedMessage:
    topic: str
    payload: str | bytes
    retain: bool = False
    qos: int = 0


@dataclass(frozen=True, slots=True)
class InboundMessage:
    topic: str
    payload: bytes


@dataclass
class RecordingMqttPublisher:
    """Records publish calls; supports the same surface used by the app."""

    connected: bool = False
    messages: list[PublishedMessage] = field(default_factory=list)
    will_topic: str | None = None
    will_payload: str | bytes | None = None
    will_retain: bool = False
    subscribed: list[str] = field(default_factory=list)
    _inbound: asyncio.Queue[InboundMessage] = field(default_factory=asyncio.Queue)

    async def connect(
        self,
        *,
        will_topic: str | None = None,
        will_payload: str | bytes | None = None,
        will_retain: bool = False,
    ) -> None:
        self.connected = True
        self.will_topic = will_topic
        self.will_payload = will_payload
        self.will_retain = will_retain

    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        if not self.connected:
            raise RuntimeError("MQTT publisher not connected")
        self.messages.append(PublishedMessage(topic=topic, payload=payload, retain=retain, qos=qos))

    async def subscribe(self, topic: str) -> None:
        if not self.connected:
            raise RuntimeError("MQTT publisher not connected")
        self.subscribed.append(topic)

    @property
    def inbound_messages(self) -> AsyncIterator[InboundMessage]:
        return self._iter_inbound()

    async def _iter_inbound(self) -> AsyncIterator[InboundMessage]:
        while True:
            yield await self._inbound.get()

    async def push_inbound(self, topic: str, payload: str | bytes) -> None:
        """Test helper: deliver an inbound MQTT message to subscribed listeners."""
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        await self._inbound.put(InboundMessage(topic=topic, payload=data))

    async def disconnect(self) -> None:
        self.connected = False

    def payloads_for(self, topic: str) -> list[str]:
        out: list[str] = []
        for msg in self.messages:
            if msg.topic != topic:
                continue
            if isinstance(msg.payload, bytes):
                out.append(msg.payload.decode("utf-8"))
            else:
                out.append(msg.payload)
        return out
