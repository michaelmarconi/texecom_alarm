"""aiomqtt-backed publisher with Last-Will for app-liveness availability."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import aiomqtt

from texecom_alarm.mqtt.discovery import AVAILABILITY_OFFLINE

logger = logging.getLogger(__name__)


class AiomqttPublisher:
    """Thin wrapper around ``aiomqtt.Client`` with injectable connect/publish/disconnect."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        *,
        username: str = "",
        password: str = "",
        identifier: str | None = None,
        keepalive: int = 60,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.identifier = identifier
        self.keepalive = keepalive
        self._client: aiomqtt.Client | None = None

    async def connect(
        self,
        *,
        will_topic: str | None = None,
        will_payload: str | bytes | None = None,
        will_retain: bool = False,
    ) -> None:
        will: aiomqtt.Will | None = None
        if will_topic is not None:
            payload = will_payload if will_payload is not None else AVAILABILITY_OFFLINE
            if isinstance(payload, str):
                payload_bytes = payload.encode("utf-8")
            else:
                payload_bytes = payload
            will = aiomqtt.Will(topic=will_topic, payload=payload_bytes, retain=will_retain)

        kwargs: dict[str, Any] = {
            "hostname": self.host,
            "port": self.port,
            "will": will,
            "keepalive": self.keepalive,
        }
        if self.identifier is not None:
            kwargs["identifier"] = self.identifier
        if self.username:
            kwargs["username"] = self.username
        if self.password:
            kwargs["password"] = self.password

        client = aiomqtt.Client(**kwargs)
        await client.__aenter__()
        self._client = client
        logger.debug("mqtt_connected", extra={"host": self.host, "port": self.port})

    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None:
        if self._client is None:
            raise RuntimeError("MQTT publisher not connected")
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        await self._client.publish(topic, data, qos=qos, retain=retain)
        logger.debug("mqtt_publish", extra={"topic": topic, "retain": retain})

    async def subscribe(self, topic: str) -> None:
        if self._client is None:
            raise RuntimeError("MQTT publisher not connected")
        await self._client.subscribe(topic)
        logger.debug("mqtt_subscribed", extra={"topic": topic})

    @property
    def inbound_messages(self) -> AsyncIterator[Any]:
        """Async iterator of inbound MQTT messages (aiomqtt ``Message`` objects)."""
        if self._client is None:
            raise RuntimeError("MQTT publisher not connected")
        return self._client.messages

    async def disconnect(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            await client.__aexit__(None, None, None)
            logger.debug("mqtt_disconnected")

    async def abort(self) -> None:
        """Drop the TCP session without an MQTT DISCONNECT so the broker fires LWT.

        Keeps the aiomqtt client object referenced until the broker observes the
        TCP close — clearing it too early can prevent Last-Will delivery.
        """
        client = self._client
        if client is None:
            raise RuntimeError("MQTT publisher not connected")
        paho = getattr(client, "_client", None)
        sock = getattr(paho, "_sock", None) if paho is not None else None
        if sock is None and paho is not None:
            socket_fn = getattr(paho, "socket", None)
            if callable(socket_fn):
                sock = socket_fn()
        if sock is None:
            sock_close = getattr(paho, "_sock_close", None) if paho is not None else None
            if callable(sock_close):
                sock_close()
                logger.debug("mqtt_aborted_via_sock_close")
                return
            raise RuntimeError("unable to abort MQTT connection without clean disconnect")
        sock.close()
        logger.debug("mqtt_aborted")
