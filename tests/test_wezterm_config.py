"""The WezTerm host config runs on the thread that draws the window.

'window-resized' fires for every size a drag passes through, and a process
spawned in it (os.execute) cost about 0.2 s an event on Windows: dragging the
window froze the machine for seconds. The real-window check is
scripts/run_windows_wezterm.sh; this keeps the cause out between runs.
"""

import re
from pathlib import Path

LUA = (Path(__file__).resolve().parents[1] / "packaging" / "macos" / "wezterm.lua").read_text()
CODE = "\n".join(line.split("--")[0] for line in LUA.splitlines())


def test_the_config_spawns_no_process():
    assert not re.search(r"os\.execute|io\.popen|wezterm\.run_child_process|background_child_process", CODE)


def test_nothing_runs_on_every_resize():
    assert "window-resized" not in CODE


def test_the_launcher_makes_the_folder_the_config_writes_to(tmp_path, monkeypatch):
    import launcher

    target = tmp_path / "deep" / "window.txt"
    monkeypatch.setattr(launcher, "window_state_file", lambda: target)
    env = launcher.host_environment()
    assert target.parent.is_dir()
    assert env["SYNCHOTIC_WINDOW_FILE"] == str(target)
