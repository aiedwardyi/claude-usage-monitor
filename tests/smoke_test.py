#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parent.parent
STATUSLINE_PY = ROOT / "statusline.py"
STATUSLINE_SH = ROOT / "statusline.sh"
STATUSLINE_CMD = ROOT / "statusline.cmd"


def run(command, stdin_text=""):
    env = os.environ.copy()
    env["CQB_TOKENS"] = "0"
    env["CQB_RESET"] = "0"
    env["CQB_DURATION"] = "0"
    env["CQB_BRANCH"] = "0"
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    proc = subprocess.run(
        command,
        input=stdin_text,
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=env,
        timeout=20,
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


def smoke_windows_launcher_path_fallback():
    if os.name != "nt":
        return

    with tempfile.TemporaryDirectory() as tmp:
        fake_bash = pathlib.Path(tmp) / "bash.cmd"
        fake_bash.write_text("@echo off\r\necho Claude\r\n", encoding="utf-8")

        env = os.environ.copy()
        env["PATH"] = tmp + os.pathsep + env.get("PATH", "")
        env["ProgramFiles"] = str(pathlib.Path(tmp) / "missing-program-files")
        env["ProgramFiles(x86)"] = str(pathlib.Path(tmp) / "missing-program-files-x86")
        env["LocalAppData"] = str(pathlib.Path(tmp) / "missing-local-app-data")

        proc = subprocess.run(
            ["cmd", "/c", str(STATUSLINE_CMD)],
            input="",
            text=True,
            capture_output=True,
            cwd=ROOT,
            env=env,
            timeout=20,
        )
        assert_ok(proc, "statusline.cmd path fallback")
        if proc.stdout.strip() != "Claude":
            raise AssertionError(f"unexpected statusline.cmd fallback output:\n{proc.stdout}")


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


def main():
    smoke_statusline_py()
    smoke_empty_stdin()
    smoke_unix_launcher()
    smoke_windows_launcher()
    smoke_windows_launcher_path_fallback()
    print("smoke tests passed")


if __name__ == "__main__":
    main()
