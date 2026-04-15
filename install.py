#!/usr/bin/env python3
"""Install claude-usage-monitor into the local Claude Code config."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path


RUNTIME_FILES = ("statusline.py", "statusline.sh", "statusline.cmd")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install claude-usage-monitor into ~/.claude and update settings.json."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory that contains the runtime files.",
    )
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=Path.home() / ".claude" / "plugins" / "claude-usage-monitor",
        help="Where to copy the runtime files.",
    )
    parser.add_argument(
        "--settings-path",
        type=Path,
        default=Path.home() / ".claude" / "settings.json",
        help="Claude Code settings.json path to update.",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip the post-install launcher smoke test.",
    )
    return parser.parse_args()


def ensure_runtime_files(source_dir: Path) -> None:
    missing = [name for name in RUNTIME_FILES if not (source_dir / name).exists()]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(f"missing runtime files in {source_dir}: {joined}")


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve()


def copy_runtime_files(source_dir: Path, install_dir: Path) -> list[Path]:
    install_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in RUNTIME_FILES:
        src = (source_dir / name).resolve()
        dst = install_dir / name
        if src != dst.resolve():
            shutil.copy2(src, dst)
        if name.endswith(".sh") or name.endswith(".py"):
            current_mode = dst.stat().st_mode
            dst.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        copied.append(dst)
    return copied


def _use_bash_launcher() -> bool:
    """Whether the installed statusLine launcher should run via bash.

    On posix we always use bash. On Windows we use bash when a working bash is
    on PATH so Claude Code installs that spawn statusLine through a bash-style
    shell (e.g. Git Bash, where `.cmd` is not executable and the command
    silently produces no output) still render. Hosts without a working bash
    fall back to the bare `.cmd` launcher, which works under cmd and
    PowerShell.

    The probe (`bash -c "exit 0"`) is necessary because the WSL stub at
    `C:\\Windows\\System32\\bash.exe` is on PATH on most modern Windows installs
    but errors at invocation time when no Linux distro is installed.
    """
    if os.name != "nt":
        return True
    if not shutil.which("bash"):
        return False
    try:
        result = subprocess.run(
            ["bash", "-c", "exit 0"],
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def build_status_command(install_dir: Path) -> str:
    if _use_bash_launcher():
        sh_path = str(install_dir / "statusline.sh")
        if os.name == "nt":
            # Hard-quote with double quotes and forward-slash the path so bash
            # (which treats `\` as an escape) and cmd / PowerShell (which need
            # a quoted argument across spaces) all parse it the same way.
            posix_path = sh_path.replace("\\", "/")
            return f'bash "{posix_path}"'
        return f"bash {shlex.quote(sh_path)}"
    return str(install_dir / "statusline.cmd")


def build_verify_command(install_dir: Path) -> str:
    if _use_bash_launcher():
        return f"printf '' | bash {shlex.quote(str(install_dir / 'statusline.sh'))}"
    return f'type nul | "{install_dir / "statusline.cmd"}"'


def load_settings(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""

    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}, raw

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"could not parse {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")

    return data, raw


def update_settings(settings_path: Path, install_dir: Path) -> tuple[Path | None, str]:
    data, raw_before = load_settings(settings_path)

    status_line = data.get("statusLine")
    if status_line is None:
        status_line = {}
    if not isinstance(status_line, dict):
        raise SystemExit(f"{settings_path} has a non-object statusLine value")

    status_line["type"] = "command"
    status_line["command"] = build_status_command(install_dir)
    status_line["padding"] = 0
    data["statusLine"] = status_line

    rendered = json.dumps(data, indent=2) + "\n"
    backup_path = None

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_before and raw_before != rendered:
        backup_path = settings_path.with_suffix(settings_path.suffix + ".bak")
        backup_path.write_text(raw_before, encoding="utf-8")

    settings_path.write_text(rendered, encoding="utf-8")
    return backup_path, status_line["command"]


def verify_install(install_dir: Path) -> tuple[bool, str]:
    # Exercise the same launcher shape that update_settings will write into
    # settings.json, so a "Launcher check: passed" line can't be reported when
    # the configured statusLine command would actually fail at runtime.
    if _use_bash_launcher():
        command = ["bash", str(install_dir / "statusline.sh")]
    else:
        command = ["cmd", "/c", str(install_dir / "statusline.cmd")]

    try:
        proc = subprocess.run(
            command,
            input="",
            text=True,
            capture_output=True,
            timeout=15,
        )
    except Exception as exc:
        return False, str(exc)

    output = proc.stdout.strip()
    if proc.returncode != 0:
        return False, proc.stderr.strip() or output or f"exit code {proc.returncode}"
    if output != "Claude":
        return False, output or "unexpected empty output"
    return True, output


def main() -> int:
    args = parse_args()
    source_dir = normalize_path(args.source_dir)
    install_dir = normalize_path(args.install_dir)
    settings_path = normalize_path(args.settings_path)

    ensure_runtime_files(source_dir)
    copied = copy_runtime_files(source_dir, install_dir)
    backup_path, command = update_settings(settings_path, install_dir)

    verify_ok = None
    verify_detail = ""
    if not args.skip_verify:
        verify_ok, verify_detail = verify_install(install_dir)

    print("Installed claude-usage-monitor")
    print(f"Install dir: {install_dir}")
    print(f"Settings file: {settings_path}")
    print(f"Status line command: {command}")
    print("Files:")
    for path in copied:
        print(f"  - {path}")
    if backup_path is not None:
        print(f"Backup: {backup_path}")
    print("Verify:")
    print(f"  {build_verify_command(install_dir)}")

    if verify_ok is True:
        print("Launcher check: passed")
    elif verify_ok is False:
        print(f"Launcher check: failed ({verify_detail})")
        return 1

    print("Next step: restart Claude Code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
