"""Whether a newer Synchotic release is out than the one this build is based on.

The launcher keeps a normal install on the latest release, so for most people
this never says anything. It is for builds the launcher does not update: a
fork's build run with the launcher's --dev, a source checkout. Those otherwise
go on running an old base without a word.

It only warns. It never updates, never blocks startup, and says nothing when
GitHub cannot be reached: a failed check is a log line, not a screen.

"Based on" is read from VERSION. Merging upstream brings its VERSION along, so
a build at or past the latest release tag has that release in it. Unreleased
upstream commits are not counted, since nothing live has them yet.
"""
import re
import threading

from .logging import debug_log

LATEST_URL = "https://api.github.com/repos/noahbaxter/synchotic/releases/latest"
TIMEOUT = 3  # seconds; runs alongside startup, so it costs nothing until then

_NUMBERS = re.compile(r"^v?(\d+(?:\.\d+)*)")


def parse_version(text: str):
    """(1, 5, 8) for "1.5.8", "v1.5.8" or a CI stamp like "1.5.8-dev.2026...".
    None for anything without a leading version."""
    match = _NUMBERS.match((text or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _padded(a: tuple, b: tuple) -> tuple:
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)), b + (0,) * (width - len(b))


def is_newer(latest: str, current: str) -> bool:
    """Whether the `latest` tag is a later release than `current`. False when
    either cannot be read: an unknown version is never a reason to warn."""
    a, b = parse_version(latest), parse_version(current)
    if a is None or b is None:
        return False
    a, b = _padded(a, b)
    return a > b


def _fetch_latest_tag() -> str:
    import requests
    response = requests.get(LATEST_URL, timeout=TIMEOUT,
                            headers={"Accept": "application/vnd.github+json",
                                     "User-Agent": "synchotic"})
    response.raise_for_status()
    return response.json().get("tag_name", "")


class UpstreamCheck:
    """The check, run on a thread from startup so the request overlaps with
    everything else startup does."""

    def __init__(self, current: str, fetch=_fetch_latest_tag):
        self._current = current
        self._fetch = fetch
        self._latest = None
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="upstream-check")

    def start(self) -> "UpstreamCheck":
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            self._latest = self._fetch()
        except Exception as e:
            debug_log(f"UPSTREAM | check failed | {e!r}")
            return
        debug_log(f"UPSTREAM | latest {self._latest} | this build {self._current}")

    def newer(self, wait: float = 0.0):
        """The newer release's tag, or None: none newer, the check failed, or
        it has not answered within `wait` seconds."""
        self._thread.join(wait)
        if self._thread.is_alive() or not self._latest:
            return None
        return self._latest if is_newer(self._latest, self._current) else None
