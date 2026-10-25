"""--sync: one sync from a .bat or shortcut, then exit.

It reuses the menu's own sync, so most of what matters is the seams: that a
dead sign-in is caught before the offer rather than at preflight (the menu has
a sign-in row for that, --sync does not), that a run that did not finish keeps
its window open, and that the exit code says how it ended.
"""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src import copy
from src.app.sync_flow import (SYNC_BLOCKED, SYNC_CANCELLED, SYNC_DONE,
                               SYNC_FAILED)
from src.config.settings import (DOWNLOAD_MODE_ANONYMOUS, DOWNLOAD_MODE_BYOC,
                                 DOWNLOAD_MODE_RCLONE, UserSettings)


# ---------------------------------------------------------------------------
# run_once: outcome to exit code, and how the window closes
# ---------------------------------------------------------------------------

@pytest.fixture
def once(monkeypatch):
    """A SyncApp whose startup and sync are stubbed; returns (app, seen)."""
    from sync import SyncApp

    seen = {"countdown": 0, "keypress": 0, "synced": 0, "notice": 0,
            "stopped": 0, "left_alt": 0}

    monkeypatch.setattr("src.ui.primitives.wait_with_skip",
                        lambda *a, **k: seen.__setitem__("countdown", seen["countdown"] + 1))
    monkeypatch.setattr("src.ui.primitives.getch",
                        lambda *a, **k: seen.__setitem__("keypress", seen["keypress"] + 1) or "x")
    monkeypatch.setattr("chotic_ui.primitives.host.leave_alt_screen",
                        lambda: seen.__setitem__("left_alt", seen["left_alt"] + 1))
    monkeypatch.setattr("src.ui.widgets.display.session_expired_notice",
                        lambda: seen.__setitem__("notice", seen["notice"] + 1))

    app = object.__new__(SyncApp)
    app.folders = [{"folder_id": "d1", "name": "Drive"}]
    app.auth = SimpleNamespace(session_expired=False)

    def start(self, check_signin=False):
        seen["check_signin"] = check_signin

    def sync(self, pause_after=True):
        seen["synced"] += 1
        seen["pause_after"] = pause_after
        self.last_sync_outcome = seen["outcome"]

    monkeypatch.setattr(SyncApp, "_start_session", start)
    monkeypatch.setattr(SyncApp, "handle_sync", sync)
    monkeypatch.setattr(SyncApp, "_stop_background_scan",
                        lambda self: seen.__setitem__("stopped", seen["stopped"] + 1))
    return app, seen


@pytest.mark.parametrize("outcome,code", [
    (SYNC_DONE, 0), (SYNC_BLOCKED, 1), (SYNC_FAILED, 2), (SYNC_CANCELLED, 3),
])
def test_the_exit_code_says_how_it_ended(once, outcome, code, capsys):
    app, seen = once
    seen["outcome"] = outcome

    assert app.run_once() == code
    assert copy.SYNC_EXIT[outcome] in capsys.readouterr().out


def test_it_checks_the_sign_in_and_skips_the_menus_pause(once):
    app, seen = once
    seen["outcome"] = SYNC_DONE

    app.run_once()

    assert seen["check_signin"] is True
    assert seen["pause_after"] is False, "a 'Continuing in 5s' to nowhere"


def test_a_clean_run_closes_by_itself(once):
    app, seen = once
    seen["outcome"] = SYNC_DONE

    app.run_once()

    assert (seen["countdown"], seen["keypress"]) == (1, 0)


@pytest.mark.parametrize("outcome", [SYNC_BLOCKED, SYNC_FAILED, SYNC_CANCELLED])
def test_anything_else_waits_for_a_key(once, outcome):
    """A double-clicked window that closes on its own takes the reason with it."""
    app, seen = once
    seen["outcome"] = outcome

    app.run_once()

    assert (seen["countdown"], seen["keypress"]) == (0, 1)


def test_it_cleans_up_before_exiting(once):
    app, seen = once
    seen["outcome"] = SYNC_DONE

    app.run_once()

    assert seen["stopped"] == 1
    assert seen["left_alt"] == 1


def test_no_drives_is_a_run_that_could_not_start(once, capsys):
    app, seen = once
    app.folders = []

    assert app.run_once() == 1
    assert seen["synced"] == 0
    assert seen["keypress"] == 1
    assert copy.NO_DRIVES in capsys.readouterr().out


def test_a_newer_release_is_shown_before_the_window_closes(once, capsys):
    """The sync screen paints over anything printed at startup, so --sync
    shows it at the end, where the closing pause gives time to read it."""
    app, seen = once
    seen["outcome"] = SYNC_DONE
    app.upstream_notice = "Synchotic v9.9.9 is out."

    app.run_once()

    assert "Synchotic v9.9.9 is out." in capsys.readouterr().out


def test_a_sign_in_that_died_mid_run_is_explained(once):
    app, seen = once
    seen["outcome"] = SYNC_BLOCKED
    app.auth.session_expired = True

    app.run_once()

    assert seen["notice"] == 1


# ---------------------------------------------------------------------------
# _start_session: the sign-in check runs before the offer looks
# ---------------------------------------------------------------------------

class _Auth:
    """A saved BYOC sign-in that Google has revoked, until something checks."""
    is_available = True
    session_expired = False

    def __init__(self, dead=True):
        self.is_signed_in = True
        self.dead = dead
        self.checked = 0

    def check_signin(self):
        self.checked += 1
        if self.dead:
            self.is_signed_in = False
        return not self.dead


@pytest.fixture
def session(monkeypatch):
    """Runs _start_session with everything past the sign-in offer stubbed."""
    from sync import SyncApp

    offered = []
    monkeypatch.setattr("sync.clear_screen", lambda: None)
    monkeypatch.setattr("sync.print_header", lambda: None)
    monkeypatch.setattr("sync.show_oauth_prompt",
                        lambda: offered.append(True) or False)
    monkeypatch.setattr("src.drive.auth.has_custom_client_config", lambda: True)
    monkeypatch.setattr("src.rclone.is_authed", lambda: True)
    monkeypatch.setattr("src.sync.cache.get_scan_cache",
                        lambda: SimpleNamespace(get_newest_time=lambda: None))
    for name in ("load_drives", "_turn_on_library_drives", "_start_background_scan"):
        monkeypatch.setattr(SyncApp, name, lambda self, *a, **k: None)

    def start(auth, mode=DOWNLOAD_MODE_BYOC, check_signin=True):
        app = object.__new__(SyncApp)
        app.auth = auth
        app.user_settings = SimpleNamespace(download_mode=mode)
        app._background_scanner = None
        app._start_session(check_signin=check_signin)
        return offered
    return start


def test_a_revoked_sign_in_is_offered_again(session):
    """The bug this guards: is_signed_in says yes for a dead grant, so the
    offer is skipped and --sync stops at preflight with nowhere to sign in."""
    auth = _Auth(dead=True)

    assert session(auth) == [True]
    assert auth.checked == 1


def test_a_working_sign_in_is_left_alone(session):
    auth = _Auth(dead=False)

    assert session(auth) == []


def test_the_menu_start_does_not_check(session):
    """run() is unchanged: the menu's sign-in row already handles this."""
    auth = _Auth(dead=True)

    assert session(auth, check_signin=False) == []
    assert auth.checked == 0


@pytest.mark.parametrize("mode", [DOWNLOAD_MODE_RCLONE, DOWNLOAD_MODE_ANONYMOUS, ""])
def test_only_byoc_checks_a_google_sign_in(session, mode):
    """The other modes never use Synchotic's own token, so a network call to
    refresh one would only slow every launch down."""
    auth = _Auth(dead=True)

    session(auth, mode=mode)

    assert auth.checked == 0


# ---------------------------------------------------------------------------
# AuthManager.check_signin, against a real token file
# ---------------------------------------------------------------------------

def _expired_token(tmp_path):
    p = tmp_path / "token.json"
    p.write_text(json.dumps({
        "token": "ya29.expired", "refresh_token": "1//0-dead",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "cid", "client_secret": "sec",
        "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
        "expiry": (datetime.now(timezone.utc) - timedelta(hours=2))
                  .replace(tzinfo=None).isoformat() + "Z",
    }))
    return p


@pytest.fixture
def no_admin(monkeypatch):
    """Fail loudly if anything reaches for the admin client, whose fallback
    can open a browser of its own."""
    from src.drive.auth import AuthManager

    def boom(self):
        raise AssertionError("check_signin fell back to the admin client")
    monkeypatch.setattr(AuthManager, "_get_admin_oauth", boom)


def test_a_refused_refresh_signs_out(tmp_path, monkeypatch, no_admin):
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials
    from src.drive.auth import AuthManager

    path = _expired_token(tmp_path)

    def refuse(self, request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")
    monkeypatch.setattr(Credentials, "refresh", refuse)

    auth = AuthManager(token_path=path)
    assert auth.is_signed_in is True

    assert auth.check_signin() is False
    assert auth.is_signed_in is False
    assert auth.session_expired is True


def test_offline_keeps_the_sign_in(tmp_path, monkeypatch, no_admin):
    from google.oauth2.credentials import Credentials
    from src.drive.auth import AuthManager

    path = _expired_token(tmp_path)

    def offline(self, request):
        raise OSError("Network is unreachable")
    monkeypatch.setattr(Credentials, "refresh", offline)

    auth = AuthManager(token_path=path)

    assert auth.check_signin() is False
    assert auth.is_signed_in is True, "offline is not a reason to sign out"


def test_no_token_is_simply_not_signed_in(tmp_path, no_admin):
    from src.drive.auth import AuthManager

    assert AuthManager(token_path=tmp_path / "token.json").check_signin() is False


# ---------------------------------------------------------------------------
# handle_sync records its outcome
# ---------------------------------------------------------------------------

class _Scanner:
    """Nothing enabled, scan finished."""

    def get_enabled_setlist_count(self):
        return 0

    def has_scan_failures(self):
        return False

    def get_stats(self):
        return None

    def __getattr__(self, name):
        return lambda *a, **k: False


@pytest.fixture
def sync_app(tmp_path, monkeypatch):
    from sync import SyncApp

    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setenv("SYNCHOTIC_LIBRARY", str(library))
    waits = []
    for name in ("clear_screen", "print_header"):
        monkeypatch.setattr(f"src.app.sync_flow.{name}", lambda *a, **k: None)
    monkeypatch.setattr("src.app.sync_flow.wait_with_skip",
                        lambda *a, **k: waits.append(a))
    monkeypatch.setattr("src.app.sync_flow.rebuild_markers_from_disk",
                        lambda *a, **k: (0, 0))
    monkeypatch.setattr("src.app.sync_flow.purge_all_folders", lambda *a, **k: set())
    monkeypatch.setattr("src.app.sync_flow.compute_main_menu_cache",
                        lambda *a, **k: "cache")

    class _Keys:
        def __init__(self, on_key):
            pass

        def start(self):
            return self

        def stop(self):
            pass

    monkeypatch.setattr("src.ui.primitives.keys.KeyMonitor", _Keys)

    app = object.__new__(SyncApp)
    app.user_settings = UserSettings(tmp_path / "settings.json")
    app.user_settings.download_mode = DOWNLOAD_MODE_ANONYMOUS
    app.folders = []
    app.custom_folders = None
    app.drives_config = None
    app._background_scanner = _Scanner()
    app.folder_stats_cache = SimpleNamespace(invalidate=lambda fid: None)
    app.auth = SimpleNamespace(is_signed_in=False, is_available=False)
    monkeypatch.setattr(type(app), "_get_combined_drives_config", lambda self: None)
    monkeypatch.setattr(type(app), "_preflight_ok", lambda self: True)
    monkeypatch.setattr(type(app), "_scan_failure", lambda self: None)
    return app, waits


def test_nothing_to_do_is_done(sync_app):
    app, _ = sync_app
    app.handle_sync()
    assert app.last_sync_outcome == SYNC_DONE


def test_a_preflight_stop_is_blocked(sync_app, monkeypatch):
    app, _ = sync_app
    monkeypatch.setattr(type(app), "_preflight_ok", lambda self: False)

    app.handle_sync()

    assert app.last_sync_outcome == SYNC_BLOCKED


def test_dead_scans_are_failed(sync_app, monkeypatch):
    app, _ = sync_app
    monkeypatch.setattr(type(app), "_scan_failure",
                        lambda self: ("offline", ["Drive"]))
    monkeypatch.setattr("src.ui.widgets.display.sync_failed", lambda *a: None)

    app.handle_sync()

    assert app.last_sync_outcome == SYNC_FAILED


def test_the_menu_still_pauses_and_sync_once_does_not(sync_app):
    app, waits = sync_app

    app.handle_sync()
    assert len(waits) == 1

    app.handle_sync(pause_after=False)
    assert len(waits) == 1
