#!/usr/bin/env python3
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parent.parent
INSTALL_PY = ROOT / "install.py"
INSTALL_SH = ROOT / "install.sh"
INSTALL_PS1 = ROOT / "install.ps1"
STATUSLINE_PY = ROOT / "statusline.py"
STATUSLINE_SH = ROOT / "statusline.sh"
STATUSLINE_CMD = ROOT / "statusline.cmd"


def run(command, stdin_text="", extra_env=None):
    env = os.environ.copy()
    env["CQB_TOKENS"] = "0"
    env["CQB_RESET"] = "0"
    env["CQB_DURATION"] = "0"
    env["CQB_BRANCH"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    env.pop("CQB_BAR", None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        command,
        input=stdin_text,
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=env,
        timeout=20,
        encoding="utf-8",
    )
    return proc


def assert_ok(proc, label):
    if proc.returncode != 0:
        raise AssertionError(
            f"{label} failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )


def assert_contains(text, expected, label):
    if expected not in text:
        raise AssertionError(f"{label} missing {expected!r}\noutput:\n{text}")


def smoke_statusline_py():
    payload = {
        "model": {"display_name": "Opus"},
        "context_window": {
            "used_percentage": 25,
            "context_window_size": 200000,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        },
        "cost": {"total_cost_usd": 0, "total_duration_ms": 0},
        "workspace": {"project_dir": str(ROOT)},
    }
    proc = run([sys.executable, str(STATUSLINE_PY)], json.dumps(payload))
    assert_ok(proc, "statusline.py")
    assert_contains(proc.stdout, "Opus", "statusline.py")
    assert_contains(proc.stdout, "75%", "statusline.py")


def smoke_empty_stdin():
    proc = run([sys.executable, str(STATUSLINE_PY)], "")
    assert_ok(proc, "statusline.py empty stdin")
    if proc.stdout.strip() != "Claude":
        raise AssertionError(f"unexpected empty-stdin output:\n{proc.stdout}")


def smoke_unix_launcher():
    if os.name == "nt":
        return
    bash = shutil_which("bash")
    if not bash:
        raise AssertionError("bash not found")
    proc = run([bash, str(STATUSLINE_SH)], "")
    assert_ok(proc, "statusline.sh")
    if proc.stdout.strip() != "Claude":
        raise AssertionError(f"unexpected statusline.sh output:\n{proc.stdout}")


def smoke_windows_launcher():
    if os.name != "nt":
        return
    proc = run(["cmd", "/c", str(STATUSLINE_CMD)], "")
    assert_ok(proc, "statusline.cmd")
    if proc.stdout.strip() != "Claude":
        raise AssertionError(f"unexpected statusline.cmd output:\n{proc.stdout}")


def shutil_which(name):
    import shutil
    return shutil.which(name)


def smoke_installer():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        install_dir = tmp_path / "install-target"
        settings_path = tmp_path / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps({"theme": "dark", "statusLine": {"command": "old-command"}}, indent=2)
            + "\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [
                sys.executable,
                str(INSTALL_PY),
                "--source-dir",
                str(ROOT),
                "--install-dir",
                str(install_dir),
                "--settings-path",
                str(settings_path),
            ],
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=30,
        )
        assert_ok(proc, "install.py")

        for filename in ("statusline.py", "statusline.sh", "statusline.cmd"):
            if not (install_dir / filename).exists():
                raise AssertionError(f"install.py did not copy {filename}")

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if settings.get("theme") != "dark":
            raise AssertionError("install.py did not preserve existing settings")

        command = settings.get("statusLine", {}).get("command", "")
        # On Windows the installer prefers the bash-form launcher when bash is
        # on PATH (works under cmd, PowerShell, and bash) and falls back to the
        # bare `.cmd` path otherwise.
        if os.name == "nt":
            expected_fragment = "statusline.sh" if shutil.which("bash") else "statusline.cmd"
        else:
            expected_fragment = "statusline.sh"
        if expected_fragment not in command:
            raise AssertionError(f"unexpected installed command: {command}")

        backup_path = settings_path.with_suffix(".json.bak")
        if not backup_path.exists():
            raise AssertionError("install.py did not create a settings backup")


def smoke_unix_install_wrapper():
    if os.name == "nt":
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        install_dir = tmp_path / "install-target"
        settings_path = tmp_path / "settings.json"
        proc = subprocess.run(
            [
                "bash",
                str(INSTALL_SH),
                "--skip-verify",
                "--install-dir",
                str(install_dir),
                "--settings-path",
                str(settings_path),
            ],
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=30,
        )
        assert_ok(proc, "install.sh")

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        command = settings.get("statusLine", {}).get("command", "")
        if "statusline.sh" not in command:
            raise AssertionError(f"unexpected install.sh command: {command}")


def smoke_windows_install_wrapper():
    if os.name != "nt":
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        install_dir = tmp_path / "install-target"
        settings_path = tmp_path / "settings.json"
        proc = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(INSTALL_PS1),
                "-SkipVerify",
                "-InstallDir",
                str(install_dir),
                "-SettingsPath",
                str(settings_path),
            ],
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=30,
        )
        assert_ok(proc, "install.ps1")

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        command = settings.get("statusLine", {}).get("command", "")
        expected_fragment = "statusline.sh" if shutil.which("bash") else "statusline.cmd"
        if expected_fragment not in command:
            raise AssertionError(f"unexpected install.ps1 command: {command}")


def smoke_windows_install_pipe():
    # Regression: piped `irm install.ps1 | iex` invocation.
    # When the installer is piped through Invoke-Expression it has no associated
    # script file, so $MyInvocation.MyCommand.Path is unset. Splitting that path
    # used to throw "Cannot bind argument to parameter 'Path' ..." before any
    # work could happen. We pipe a Get-Content-loaded copy through
    # Invoke-Expression to reproduce that context, stub Invoke-WebRequest so the
    # check stays offline, and assert the null-path error never reappears.
    if os.name != "nt":
        return

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ps1", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(INSTALL_PS1.read_text(encoding="utf-8"))
        script_copy = tmp.name

    try:
        # Escape single quotes for embedding in a PS single-quoted literal.
        script_copy_ps = script_copy.replace("'", "''")
        # install.ps1 sets $ErrorActionPreference = 'Stop' at the top, so the
        # stub throw (and any other terminating error inside the script) is a
        # terminating error from PowerShell's perspective. Wrap the iex in
        # try/catch so we can capture the failure mode for assertion.
        ps_command = (
            "function Invoke-WebRequest { throw 'stubbed for tests' }; "
            f"$s = Get-Content -Raw -LiteralPath '{script_copy_ps}'; "
            "try { $s | Invoke-Expression } "
            "catch { [Console]::Error.WriteLine($_.Exception.Message) }"
        )
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                ps_command,
            ],
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=60,
        )

        combined = (proc.stdout or "") + (proc.stderr or "")
        if "Cannot bind argument to parameter 'Path'" in combined:
            raise AssertionError(
                "piped install.ps1 regressed to null-path error\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
    finally:
        try:
            os.unlink(script_copy)
        except OSError:
            pass


def smoke_build_status_command():
    # build_status_command picks the form written into settings.json:
    #   - posix: always `bash <shell-quoted-path-to-statusline.sh>`
    #   - nt + bash on PATH: `bash "<install_dir-with-forward-slashes>/statusline.sh"`
    #     (works under cmd, PowerShell, and bash; needed for hosts where
    #     Claude Code spawns statusLine through a bash shell that does not
    #     recognise `.cmd`)
    #   - nt + no bash: path to `<install_dir>\statusline.cmd` fallback
    import importlib.util
    from types import SimpleNamespace
    from unittest import mock

    spec = importlib.util.spec_from_file_location("_install_under_test", INSTALL_PY)
    install_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(install_mod)

    # PureWindowsPath str() produces backslashes, so the nt branch genuinely
    # exercises (and the assertion can detect) the forward-slash normalization.
    nt_install_dir = pathlib.PureWindowsPath(
        r"C:\Users\test\.claude\plugins\claude-usage-monitor"
    )
    posix_install_dir = pathlib.PurePosixPath(
        "/home/test/.claude/plugins/claude-usage-monitor"
    )

    bash_present = lambda name: r"C:\Program Files\Git\bin\bash.exe" if name == "bash" else None
    bash_absent = lambda name: None

    # nt + bash on PATH -> bash form, forward slashes, double-quoted.
    with mock.patch.object(install_mod, "os", SimpleNamespace(name="nt")), \
         mock.patch.object(install_mod.shutil, "which", bash_present):
        cmd = install_mod.build_status_command(nt_install_dir)
        if not cmd.startswith('bash "') or not cmd.endswith('/statusline.sh"'):
            raise AssertionError(f"nt+bash should produce bash-form, got: {cmd}")
        if "\\" in cmd:
            raise AssertionError(f"nt+bash command should use forward slashes, got: {cmd}")

    # nt without bash -> bare `.cmd` fallback.
    with mock.patch.object(install_mod, "os", SimpleNamespace(name="nt")), \
         mock.patch.object(install_mod.shutil, "which", bash_absent):
        cmd = install_mod.build_status_command(nt_install_dir)
        if not cmd.endswith("statusline.cmd"):
            raise AssertionError(f"nt without bash should fall back to .cmd, got: {cmd}")
        if cmd.startswith("bash"):
            raise AssertionError(f"nt without bash should not invoke bash, got: {cmd}")

    # posix -> always bash form (shlex.quote, never depends on which()).
    with mock.patch.object(install_mod, "os", SimpleNamespace(name="posix")), \
         mock.patch.object(install_mod.shutil, "which", bash_absent):
        cmd = install_mod.build_status_command(posix_install_dir)
        if not cmd.startswith("bash "):
            raise AssertionError(f"posix should always use bash form, got: {cmd}")
        if "statusline.sh" not in cmd:
            raise AssertionError(f"posix command should reference statusline.sh, got: {cmd}")


def smoke_bar_toggle():
    import re
    import time as _time

    payload = {
        "model": {"display_name": "Opus"},
        "context_window": {
            "used_percentage": 25,
            "context_window_size": 200000,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        },
        "cost": {"total_cost_usd": 0, "total_duration_ms": 0},
        "workspace": {"project_dir": str(ROOT)},
    }
    stdin = json.dumps(payload)
    ansi_re = re.compile(r"\033\[[0-9;]*m")

    with tempfile.TemporaryDirectory() as tmp:
        cache_file = os.path.join(tmp, "test-cache.json")
        cache_data = json.dumps({
            "five_hour_used": 30,
            "seven_day_used": 50,
            "five_hour_reset_min": 120,
            "seven_day_reset_min": 4320,
            "extra_enabled": False,
            "extra_used": 0,
            "extra_limit": 0,
            "fetched_at": _time.time(),
        })
        pathlib.Path(cache_file).write_text(cache_data, encoding="utf-8")

        cache_env = {"CQB_CACHE_PATH": cache_file}

        # Bar on by default: should have bar chars for context + 5h + 7d
        proc = run([sys.executable, str(STATUSLINE_PY)], stdin, extra_env=cache_env)
        assert_ok(proc, "bar on (default)")
        clean = ansi_re.sub("", proc.stdout)
        bar_on_count = clean.count("\u25b0") + clean.count("\u25b1")

        # Bar off: should have fewer bar chars (only context gauge)
        proc = run([sys.executable, str(STATUSLINE_PY)], stdin, extra_env={**cache_env, "CQB_BAR": "0"})
        assert_ok(proc, "bar off")
        clean = ansi_re.sub("", proc.stdout)
        bar_off_count = clean.count("\u25b0") + clean.count("\u25b1")

        if bar_on_count <= bar_off_count:
            raise AssertionError(
                f"default bar should have more chars: on={bar_on_count}, off={bar_off_count}"
            )


def smoke_overflow():
    import re
    import time as _time

    payload = {
        "model": {"display_name": "Opus"},
        "context_window": {
            "used_percentage": 25,
            "context_window_size": 200000,
            "total_input_tokens": 5000,
            "total_output_tokens": 3000,
        },
        "cost": {"total_cost_usd": 0, "total_duration_ms": 300000},
        "workspace": {"project_dir": str(ROOT)},
    }
    stdin = json.dumps(payload)
    ansi_re = re.compile(r"\033\[[0-9;]*m")

    with tempfile.TemporaryDirectory() as tmp:
        cache_file = os.path.join(tmp, "test-cache.json")
        cache_data = json.dumps({
            "five_hour_used": 85,
            "seven_day_used": 40,
            "five_hour_reset_min": 120,
            "seven_day_reset_min": 4320,
            "extra_enabled": True,
            "extra_used": 6382,
            "extra_limit": 10500,
            "fetched_at": _time.time(),
        })
        pathlib.Path(cache_file).write_text(cache_data, encoding="utf-8")

        cache_env = {"CQB_CACHE_PATH": cache_file}

        # With a tight max width, 5h and 7d must survive, lower-priority segments get dropped
        proc = run(
            [sys.executable, str(STATUSLINE_PY)],
            stdin,
            extra_env={**cache_env, "CQB_MAX_WIDTH": "40", "CQB_DURATION": "1"},
        )
        assert_ok(proc, "overflow")
        clean = ansi_re.sub("", proc.stdout)
        assert_contains(clean, "5h:", "overflow (5h present)")
        assert_contains(clean, "7d:", "overflow (7d present)")

        # Duration should be dropped to fit at tight width
        if "5m" in clean:
            raise AssertionError(
                f"overflow: duration should be dropped at width 40\noutput:\n{clean}"
            )

        # With unlimited width, all segments should appear
        proc = run(
            [sys.executable, str(STATUSLINE_PY)],
            stdin,
            extra_env={**cache_env, "CQB_MAX_WIDTH": "200", "CQB_DURATION": "1"},
        )
        assert_ok(proc, "no overflow")
        clean = ansi_re.sub("", proc.stdout)
        assert_contains(clean, "5m", "no overflow (duration present)")


def main():
    smoke_statusline_py()
    smoke_empty_stdin()
    smoke_unix_launcher()
    smoke_windows_launcher()
    smoke_installer()
    smoke_unix_install_wrapper()
    smoke_windows_install_wrapper()
    smoke_windows_install_pipe()
    smoke_build_status_command()
    smoke_bar_toggle()
    smoke_overflow()
    print("smoke tests passed")


if __name__ == "__main__":
    main()
