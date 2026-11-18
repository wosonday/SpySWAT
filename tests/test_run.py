"""Tests for SWATRun (a tiny python script acts as the SWAT executable)."""
import subprocess
import sys
import time

import pytest

from spyswat.swat_calib.run import SWATRun

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX script as fake exe")


def make_exe(path, body: str):
    path.write_text(f"#!{sys.executable}\n{body}\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def tx(tmp_path):
    d = tmp_path / "tx"
    d.mkdir()
    (d / "file.cio").write_text("x\n")
    return d


def test_missing_exe_gives_clear_error(tx, tmp_path):
    with pytest.raises(FileNotFoundError, match="SWAT executable not found"):
        SWATRun(tmp_path / "nope.exe").run(tx)


def test_missing_file_cio(tmp_path):
    (tmp_path / "e").mkdir()
    with pytest.raises(RuntimeError, match="file.cio"):
        SWATRun(tmp_path / "x").run(tmp_path / "e")


@posix_only
def test_success_and_capture(tx, tmp_path):
    exe = make_exe(tmp_path / "ok", "print('hello')")
    res = SWATRun(exe).run(tx, capture_output=True)
    assert res.returncode == 0 and "hello" in res.stdout
    assert SWATRun(exe).run(tx) is None


@posix_only
def test_nonzero_exit_raises_called_process_error(tx, tmp_path):
    exe = make_exe(tmp_path / "bad", "import sys; sys.exit(3)")
    with pytest.raises(subprocess.CalledProcessError) as ei:
        SWATRun(exe).run(tx)
    assert ei.value.returncode == 3


@posix_only
def test_stdin_is_not_inherited(tx, tmp_path):
    # would block forever on an inherited terminal/pipe; with DEVNULL it reads EOF at once
    exe = make_exe(tmp_path / "reader", "import sys; sys.stdin.read()")
    t0 = time.perf_counter()
    SWATRun(exe).run(tx, timeout=20)
    assert time.perf_counter() - t0 < 15


@posix_only
def test_timeout_kills_child(tx, tmp_path):
    pidfile = tmp_path / "pid"
    exe = make_exe(tmp_path / "sleeper",
                   f"import os, time\nopen({str(pidfile)!r}, 'w').write(str(os.getpid()))\ntime.sleep(60)")
    t0 = time.perf_counter()
    with pytest.raises(subprocess.TimeoutExpired):
        SWATRun(exe).run(tx, timeout=1)
    assert time.perf_counter() - t0 < 20
    # the child must be gone (reaped by SWATRun): /proc entry disappears on Linux
    import os
    pid = int(pidfile.read_text())
    if os.path.isdir("/proc"):
        assert not os.path.exists(f"/proc/{pid}")


def test_kill_uses_taskkill_tree_on_windows(monkeypatch):
    from spyswat.swat_calib.run import run as run_mod
    calls = []

    class FakeProc:
        pid = 4321
        killed = False
        def poll(self):
            return None
        def kill(self):
            self.killed = True
        def communicate(self, timeout=None):
            return "", ""

    monkeypatch.setattr(run_mod.sys, "platform", "win32")
    monkeypatch.setattr(run_mod.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)))
    proc = FakeProc()
    SWATRun._kill(proc)
    assert calls[0][0] == ["taskkill", "/F", "/T", "/PID", "4321"]
    assert calls[0][1]["timeout"] > 0
    assert proc.killed   # Popen.kill() is still the fallback


def test_kill_does_not_call_taskkill_on_posix(monkeypatch):
    from spyswat.swat_calib.run import run as run_mod
    calls = []

    class FakeProc:
        pid = 1
        def poll(self): return None
        def kill(self): pass
        def communicate(self, timeout=None): return "", ""

    monkeypatch.setattr(run_mod.sys, "platform", "linux")
    monkeypatch.setattr(run_mod.subprocess, "run", lambda *a, **k: calls.append(a))
    SWATRun._kill(FakeProc())
    assert calls == []


def test_kill_skips_taskkill_when_process_already_finished(monkeypatch):
    from spyswat.swat_calib.run import run as run_mod
    calls = []

    class Done:
        pid = 99
        def poll(self): return 0
        def kill(self): calls.append("kill")
        def communicate(self, timeout=None): return "", ""

    monkeypatch.setattr(run_mod.sys, "platform", "win32")
    monkeypatch.setattr(run_mod.subprocess, "run", lambda *a, **k: calls.append("taskkill"))
    SWATRun._kill(Done())
    assert calls == []
