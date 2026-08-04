"""E2E-shaped tests against a mocked panel — never the live household panel."""

from __future__ import annotations

from texecom_alarm import healthcheck


class FakePanel:
    """Stand-in for the ComIP TCP session used by future E2E suites."""

    def __init__(self) -> None:
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False


def test_fake_panel_session_lifecycle() -> None:
    panel = FakePanel()
    assert not panel.connected
    panel.connect()
    assert panel.connected
    assert healthcheck().startswith("texecom-alarm/")
    panel.close()
    assert not panel.connected
