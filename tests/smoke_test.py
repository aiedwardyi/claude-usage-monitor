#!/usr/bin/env python3
import json
import os
import pathlib
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
    paths = os.environ.get("PATH", "").split(os.pathsep)
    exts = [""]
    if os.name == "nt":
        exts = os.environ.get("PATHEXT", ".EXE").split(os.pathsep)
    for directory in paths:
        if not directory:
            continue
        for ext in exts:
            candidate = pathlib.Path(directory) / f"{name}{ext}"
            if candidate.exists():
                return str(candidate)
    return None


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
        expected_fragment = "statusline.cmd" if os.name == "nt" else "statusline.sh"
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
        if "statusline.cmd" not in command:
            raise AssertionError(f"unexpected install.ps1 command: {command}")


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

    # Write a temp cache so quota data is available
    cache_file = os.path.join(tempfile.gettempdir(), "claude-sl-usage.json")
    cache_backup = None
    if os.path.exists(cache_file):
        cache_backup = pathlib.Path(cache_file).read_text(encoding="utf-8")
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

    try:
        # Bar off: count bar chars - only context gauge should have them
        proc = run([sys.executable, str(STATUSLINE_PY)], stdin)
        assert_ok(proc, "bar off")
        clean = ansi_re.sub("", proc.stdout)
        bar_off_count = clean.count("\u25b0") + clean.count("\u25b1")

        # Bar on: should have more bar chars (context gauge + two quota bars)
        proc = run([sys.executable, str(STATUSLINE_PY)], stdin, extra_env={"CQB_BAR": "1"})
        assert_ok(proc, "bar on")
        clean = ansi_re.sub("", proc.stdout)
        bar_on_count = clean.count("\u25b0") + clean.count("\u25b1")

        if bar_on_count <= bar_off_count:
            raise AssertionError(
                f"CQB_BAR=1 should add bar chars: off={bar_off_count}, on={bar_on_count}"
            )
    finally:
        # Restore original cache
        if cache_backup is not None:
            pathlib.Path(cache_file).write_text(cache_backup, encoding="utf-8")
        elif os.path.exists(cache_file):
            os.unlink(cache_file)


def main():
    smoke_statusline_py()
    smoke_empty_stdin()
    smoke_unix_launcher()
    smoke_windows_launcher()
    smoke_installer()
    smoke_unix_install_wrapper()
    smoke_windows_install_wrapper()
    smoke_bar_toggle()
    print("smoke tests passed")


if __name__ == "__main__":
    main()
