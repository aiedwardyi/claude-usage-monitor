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

    On posix we always use bash. On Windows we use bash when a working bash
    is on PATH so Claude Code installs that spawn statusLine through a
    bash-style shell (e.g. Git Bash) still render. Hosts without a working
    bash fall back to a direct `python.exe statusline.py` invocation via
    `_windows_python_command`, because Claude Code on Windows cannot spawn
    a `.cmd` file via the statusLine command field (its tokeniser parses
    the field bash-style: backslashes are eaten as escapes, and `.cmd` is
    not a PE binary).

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


def _to_posix(path: str | Path) -> str:
    """Force forward slashes in a path string.

    Claude Code on Windows parses statusLine.command bash-style, so any
    backslash in an emitted path is eaten as an escape character and the
    resulting command silently fails to spawn. Routing every Windows path
    we emit through this helper keeps that invariant in one place.
    """
    return str(path).replace("\\", "/")


def _bash_script_arg(install_dir: Path) -> str:
    """Path to statusline.sh for use as a bash argument.

    On Windows bash treats `\\` as an escape when parsing its own command
    line, so the installed statusLine command and the verification command
    both use forward slashes. Normalising in one place keeps the three call
    sites (launcher, printed verify hint, in-process verify) consistent so
    what gets tested in verify_install matches what is written into
    settings.json and what is shown to the user.
    """
    sh_path = str(install_dir / "statusline.sh")
    if os.name == "nt":
        sh_path = _to_posix(sh_path)
    return sh_path


# Path punctuation safe to emit in an unquoted, bash-tokenised command. With
# the ASCII letters and digits (checked separately) this covers every standard
# Windows install path (`C:/Users/<name>/AppData/.../python.exe` and
# `~/.claude/plugins/claude-usage-monitor/statusline.py`). Non-ASCII characters
# are allowed too because Claude Code's bash-style tokeniser treats them
# literally. Allowlisting means a stray space, quote, `&`, `;`, or `(` can
# never slip through the way it could with a denylist. Backslashes never reach
# the check because _to_posix has already turned them into forward slashes.
_LAUNCHER_SAFE_PUNCT = "/:._-"


def _windows_python_command(install_dir: Path) -> str:
    """Direct `python.exe statusline.py` invocation for Windows without bash.

    Claude Code on Windows parses statusLine.command bash-style: backslashes
    in paths are eaten as escape characters, quoting paths does not survive
    the tokeniser, and `.cmd` files won't spawn as PE binaries. So we emit
    two forward-slash, unquoted paths separated by a single space.

    The `-X utf8` flag puts Python in UTF-8 mode so it decodes the stdin
    payload as UTF-8, matching the `PYTHONUTF8=1` the `.cmd` wrapper sets.
    Without it the default Windows locale (cp1252) mangles or fails to decode
    a payload with non-ASCII workspace data, which blanks the statusline.

    Raises SystemExit if `sys.executable` or the install directory contains an
    ASCII character outside the alphanumerics and `_LAUNCHER_SAFE_PUNCT` (a
    space, quote, `&`, `;`, `(`, and so on), because the tokeniser would not
    parse the unquoted command literally and would silently leave the
    statusline blank -- the exact failure mode this fallback exists to fix. An
    all-users Python install (`C:\\Program Files\\Python313`) trips on the
    space; a profile like `C:\\Users\\O'Connor` on the quote; an install dir
    like `C:\\Tools\\R&D` on the ampersand. Either way the user should install
    Git Bash (so the bash launcher form is used) or reinstall under a path made
    of ordinary characters.
    """
    py = _to_posix(sys.executable)
    script = _to_posix(install_dir / "statusline.py")
    bad = sorted(
        {c for c in py + script
         if ord(c) < 128 and not c.isalnum() and c not in _LAUNCHER_SAFE_PUNCT}
    )
    if bad:
        raise SystemExit(
            f"Cannot emit the Windows python fallback: a path contains {bad!r}, "
            "which Claude Code's bash-style statusLine tokeniser does not parse "
            "literally, so the command would be mangled and the statusline "
            "would stay blank.\n"
            f"  python: {py}\n"
            f"  script: {script}\n"
            "Install Git Bash (the installer will then use the bash launcher "
            "form), or reinstall Python or the plugin under a path made of "
            "ordinary characters (letters, digits, and / : . _ -)."
        )
    return f"{py} -X utf8 {script}"


def build_status_command(install_dir: Path) -> str:
    # No posix fallback below: _use_bash_launcher() returns False only on
    # Windows, so the trailing python-command return always handles that case.
    if _use_bash_launcher():
        sh_arg = _bash_script_arg(install_dir)
        if os.name == "nt":
            # Hard-quote with double quotes so cmd / PowerShell parse the path
            # as one argument across spaces, and bash receives it intact.
            return f'bash "{sh_arg}"'
        return f"bash {shlex.quote(sh_arg)}"
    return _windows_python_command(install_dir)


def build_verify_command(install_dir: Path) -> str:
    if _use_bash_launcher():
        sh_arg = _bash_script_arg(install_dir)
        if os.name == "nt":
            return f'printf "" | bash "{sh_arg}"'
        return f"printf '' | bash {shlex.quote(sh_arg)}"
    return f"type nul | {_windows_python_command(install_dir)}"


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
    # the configured statusLine command would actually fail at runtime. Using
    # _bash_script_arg keeps the path normalisation identical to the command
    # we write, so verification and configuration can't silently diverge.
    if _use_bash_launcher():
        command = ["bash", _bash_script_arg(install_dir)]
    else:
        # No _to_posix here: the list form goes straight to the OS, not through
        # the bash-style tokeniser, so backslashes resolve fine.
        command = [sys.executable, "-X", "utf8", str(install_dir / "statusline.py")]

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
