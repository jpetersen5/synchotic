"""Check the WezTerm host config in a real WezTerm window on Windows: the
terminal people actually run Synchotic in.

Needs the interactive desktop (a window to drag and click), so it runs through
a scheduled task: scripts/run_windows_wezterm.sh <host>. Reads the WezTerm the
launcher downloaded, with packaging/macos/wezterm.lua (the config every
platform's launcher installs) and the app's own input line.

  drag     120 resizes at drag speed: no process spawned by the config, the
           window answers straight after, and the size it ends at is saved
  ctrl_v   Ctrl+V pastes a long line into the input prompt
  right    so does a right click

Writes result.json next to this script's --out folder; exit 1 on any failure.
"""

import argparse
import ctypes
import faulthandler
import json
import os
import random
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
SWP_NOZORDER, SWP_NOACTIVATE, SWP_ASYNCWINDOWPOS = 0x4, 0x10, 0x4000
MAX_FROZEN = 30  # seconds a drag may leave the window not answering


def gui_path() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "Synchotic" / "Data" / "wezterm" / "wezterm-gui.exe"


class Term:
    """A WezTerm window running `command`."""

    def __init__(self, lua, out, command):
        self.size_file = out / "window.txt"
        env = dict(os.environ, SYNCHOTIC_WINDOW_FILE=str(self.size_file))
        self.proc = subprocess.Popen(
            [str(gui_path()), "--config-file", str(lua), "start", "--always-new-process",
             "--cwd", str(out), "--", *command], env=env)
        self.hwnd = None
        for _ in range(120):
            self.hwnd = self._find()
            if self.hwnd:
                break
            time.sleep(0.25)
        if not self.hwnd:
            raise RuntimeError("WezTerm opened no window")
        time.sleep(4)

    def _find(self):
        found = []

        def each(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.proc.pid and user32.IsWindowVisible(hwnd):
                found.append(hwnd)
            return True
        user32.EnumWindows(WNDENUMPROC(each), 0)
        return found[0] if found else None

    def rect(self):
        r = wintypes.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return r

    def focus(self):
        user32.keybd_event(0x12, 0, 0, 0)  # a tap on Alt lets SetForegroundWindow through
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.5)

    @staticmethod
    def key(vk, mods=()):
        for m in mods:
            user32.keybd_event(m, 0, 0, 0)
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        for m in mods:
            user32.keybd_event(m, 0, 2, 0)

    def right_click_middle(self):
        r = self.rect()
        user32.SetCursorPos((r.left + r.right) // 2, (r.top + r.bottom) // 2)
        time.sleep(0.2)
        user32.mouse_event(0x0008, 0, 0, 0, 0)
        user32.mouse_event(0x0010, 0, 0, 0, 0)

    def close(self):
        self.proc.terminate()


def drag(lua, out):
    term = Term(lua, out, ["cmd.exe", "/k", "echo hello"])
    import psutil
    spawned, stop = set(), []

    def watch():
        while not stop:
            try:
                for p in psutil.Process(term.proc.pid).children(recursive=True):
                    if p.name().lower() in ("cmd.exe", "conhost.exe"):
                        spawned.add(p.pid)
            except psutil.Error:
                pass
            time.sleep(0.002)
    spawned_before = set()
    threading.Thread(target=watch, daemon=True).start()
    spawned_before |= spawned  # the shell the window started with

    r = term.rect()
    x, y, w0, h0 = r.left, r.top, r.right - r.left, r.bottom - r.top
    random.seed(2)
    # Async, so a window that stops answering costs time here, not a hang.
    for _ in range(120):
        user32.SetWindowPos(term.hwnd, 0, x, y, max(w0 + random.randint(-300, 300), 400),
                            max(h0 + random.randint(-200, 200), 300),
                            SWP_NOZORDER | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)
        time.sleep(0.016)
    user32.SetWindowPos(term.hwnd, 0, x, y, w0, h0,
                        SWP_NOZORDER | SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)
    # How long until the window answers again after the last resize.
    t = time.time()
    user32.SendMessageTimeoutW(term.hwnd, 0, 0, 0, 0, MAX_FROZEN * 1000, ctypes.byref(wintypes.DWORD()))
    frozen = time.time() - t
    time.sleep(3.5)  # a size is saved once it has held for a tick
    stop.append(1)
    saved = term.size_file.read_text().split() if term.size_file.is_file() else None
    term.close()
    problems = []
    if spawned - spawned_before:
        problems.append(f"{len(spawned - spawned_before)} processes spawned during the drag")
    if frozen >= MAX_FROZEN:
        problems.append(f"the window was still not answering {frozen:.0f}s after the drag")
    if not saved or len(saved) != 2:
        problems.append(f"the size was not saved: {term.size_file} holds {saved!r}")
    return {"frozen_after_drag": round(frozen, 2), "spawned": len(spawned - spawned_before),
            "saved": saved, "problems": problems}


def paste(lua, out, how):
    text = "PASTED-" + "x" * 40 + "-END"
    got = out / f"got_{how}.txt"
    got.unlink(missing_ok=True)
    ui = Path(__file__).resolve().parents[1] / "vendor" / "chotic-ui"
    child = out / f"paste_{how}.py"
    child.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(ui)!r})\n"
        "from chotic_ui.primitives.keyboard_input import input_with_esc\n"
        "line = input_with_esc('  URL: ')\n"
        f"open({str(got)!r}, 'w', encoding='utf-8').write(line or '')\n"
        "import time; time.sleep(1)\n", encoding="utf-8")
    subprocess.run(["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{text}'"],
                   check=True)
    term = Term(lua, out, [sys.executable, str(child)])
    term.focus()
    if how == "ctrl_v":
        term.key(0x56, mods=(0x11,))
    else:
        term.right_click_middle()
    time.sleep(1)
    term.key(0x0D)
    for _ in range(40):
        if got.exists():
            break
        time.sleep(0.25)
    result = got.read_text(encoding="utf-8") if got.exists() else None
    term.close()
    return {"got": result, "problems": [] if result == text else
            [f"the line got {result!r}, wanted {text!r}"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lua", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    # A window that never answers must fail the check, not hang it.
    faulthandler.dump_traceback_later(240, exit=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, run in (("drag", lambda: drag(args.lua, out)),
                      ("ctrl_v", lambda: paste(args.lua, out, "ctrl_v")),
                      ("right_click", lambda: paste(args.lua, out, "right"))):
        try:
            results[name] = run()
        except Exception as e:
            results[name] = {"problems": [f"{type(e).__name__}: {e}"]}
    (out / "result.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    failed = [n for n, r in results.items() if r["problems"]]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
