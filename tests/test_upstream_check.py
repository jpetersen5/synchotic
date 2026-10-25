"""A build the launcher does not update says when a newer release is out.

Only says: it never updates, never blocks, and is silent when GitHub cannot be
reached. The launcher keeps normal installs current, so for them it never fires.
"""
import threading

import pytest

from src.core.upstream import UpstreamCheck, is_newer, parse_version


@pytest.mark.parametrize("text,expected", [
    ("1.5.8", (1, 5, 8)),
    ("v1.5.8", (1, 5, 8)),
    ("1.5.8-dev.20261025.1200.abc1234", (1, 5, 8)),
    (" 1.6\n", (1, 6)),
    ("launcher-v1.4", None),   # a launcher tag is not an app version
    ("dev", None),             # what the launcher records for a --dev zip
    ("", None),
    (None, None),
])
def test_reading_a_version(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize("latest,current,newer", [
    ("v1.5.9", "1.5.8", True),
    ("v1.6", "1.5.8", True),
    ("v1.5.8", "1.5.8", False),
    ("v1.5.8", "1.5.8-dev.20261025.1200.abc1234", False),
    ("v1.5", "1.5.0", False),
    ("v1.5.7", "1.5.8", False),   # a fork ahead of upstream is not behind
    ("nonsense", "1.5.8", False),
    ("v1.5.9", "garbage", False),  # an unknown build is never told it is behind
])
def test_only_a_later_release_counts(latest, current, newer):
    assert is_newer(latest, current) is newer


def test_a_newer_release_is_reported():
    check = UpstreamCheck("1.5.8", fetch=lambda: "v1.5.9").start()
    assert check.newer(wait=2) == "v1.5.9"


def test_the_same_release_is_quiet():
    check = UpstreamCheck("1.5.8", fetch=lambda: "v1.5.8").start()
    assert check.newer(wait=2) is None


def test_github_unreachable_is_quiet():
    def offline():
        raise OSError("Network is unreachable")

    check = UpstreamCheck("1.5.8", fetch=offline).start()
    assert check.newer(wait=2) is None


def test_a_slow_answer_never_holds_startup():
    """Past the wait, startup goes on without it."""
    release = threading.Event()

    def slow():
        release.wait(5)
        return "v9.9.9"

    check = UpstreamCheck("1.5.8", fetch=slow).start()
    try:
        assert check.newer(wait=0.05) is None
    finally:
        release.set()
