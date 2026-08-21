from texecom_alarm import __version__, healthcheck


def test_healthcheck_identifies_package() -> None:
    assert healthcheck() == f"texecom-alarm/{__version__}"
    assert __version__
