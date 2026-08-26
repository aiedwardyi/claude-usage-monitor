# Changelog

## Unreleased

### Fixed
- The status line now sizes itself to the terminal instead of a hardcoded 80 columns. Claude Code exports the real width as `COLUMNS` (v2.1.153+), which is the only source available since our stdout is captured rather than attached to the tty, so `tput cols` and `get_terminal_size()` both report a fallback. A 98-column terminal was losing 18 columns and dropping token counts that had room to render. `CQB_MAX_WIDTH` still wins when set, and 80 remains the fallback when `COLUMNS` is absent.
- Narrow terminals now give up countdown detail instead of a whole quota gauge. The overflow loop drops entire segments, so at 40 columns the 5h gauge disappeared to protect eight characters of `(1d16h)`. The percentage is the number you act on, and it still tells you when you are nearly empty, so the countdown now sheds first: the second unit, then the countdown entirely, and only then does a segment go. At 40 columns both gauges now fit where one used to, and at 80 the token counts survive.
- Reset countdowns now carry a second unit, so a 7d window resetting in 40h25m reads `(1d16h)` instead of `(1d)`. Flooring to a single unit gave the 7-day window seven possible values across seven days and understated the countdown by up to 23h, which reads as far less quota time than is actually left. The finer unit is dropped when it is zero, so exact boundaries stay `(2h)` / `(2d)`, and countdowns under an hour are unchanged.
- Windows hosts with WSL installed no longer get a `bash "C:/..."` statusLine command that cannot run. `shutil.which("bash")` walks `PATH` while `CreateProcess` searches `System32` first, so a Git Bash on `PATH` masked the WSL bash at `C:\\Windows\\System32\\bash.exe` that actually ran the command. The old `bash -c "exit 0"` probe only rejected the distro-less WSL stub: with a distro installed it returned 0, the gate passed, and the emitted command then failed with `No such file or directory` because WSL cannot resolve a `C:/...` path (it needs `/mnt/c/...`). The installer wrote that command into `settings.json` before the launcher check ran, so the install exited 1 but left the broken command behind, and anyone who restarted Claude Code past the error got a blank statusline. The probe now checks that the installed `statusline.sh` is readable through the same bare-name `["bash", ...]` invocation the emitted command uses, feeding the path on stdin so a directory name containing `$(...)` or a backtick is read literally rather than executed, so affected hosts fall back to the direct `python.exe statusline.py` command that already works.

## v0.2.0

### Added
- `CQB_EMAIL` segment showing the logged-in account email (#19)

### Fixed
- Context gauge now honors `CQB_REMAINING`, so it flips with the 5h and 7d gauges instead of always counting down (#18)
- Credentials, email, and usage cache now come from the `CLAUDE_CONFIG_DIR` login instead of only the default config path (#20, #22)
- Read the OAuth token from the macOS login Keychain when it is missing from the credentials file, so the statusline works on a stock macOS install (#24)

## v0.1.6

### Fixed
- On Windows, when bash was not on PATH the installer wrote a bare `.cmd` path into `settings.json`. On Claude Code 2.1.x that command field is parsed bash-style (backslashes are eaten as escapes, `.cmd` is not a PE binary), so the spawn silently produced no output and the statusline never rendered. The installer now falls back to a direct `<sys.executable> <install_dir>/statusline.py` command with both paths normalised to forward slashes, which Claude Code parses and executes correctly. The emitted command includes `-X utf8` so Python decodes the stdin payload as UTF-8 (the `.cmd` wrapper set this via environment); without it a non-ASCII workspace path rendered as mojibake or blanked the line. The fallback aborts with a clear message if either path contains a space or any other character outside the ordinary path set of letters, digits, and `/ : . _ -` (an all-users Python install at `C:\Program Files\Python313`, a profile name like `C:\Users\O'Connor`, or an install dir like `C:\Tools\R&D`), since the tokeniser would not parse the unquoted command literally and would reintroduce the silent failure. Non-ASCII path characters are allowed because the tokeniser treats them literally. The bash-on-PATH form is unchanged.
- `verify_install` and `build_verify_command` now exercise and print the same python-fallback shape, so the launcher check matches what gets written into `settings.json` on Windows hosts without bash.

## v0.1.5

### Fixed
- On Windows, the installer wrote a bare `.cmd` path into `settings.json`. That works when Claude Code spawns the statusLine through cmd or PowerShell, but on hosts that spawn it through a bash-style shell (e.g. Git Bash) `.cmd` is not recognised as executable and the statusline silently went blank. The installer now probes `bash -c "exit 0"` at install time and writes `bash "<install-dir>/statusline.sh"` when the probe succeeds, falling back to the bare `.cmd` path otherwise. Works under cmd, PowerShell, and bash (#10, #11).
- The in-process launcher check (`verify_install`) and the printed verification hint (`build_verify_command`) now derive their bash argument from the same helper as the installed command, so the verification cannot pass while the configured statusLine would fail at runtime, and the printed hint is runnable as-is under cmd/PowerShell.

## v0.1.4

### Fixed
- Piped PowerShell installer (`irm .../install.ps1 | iex`) failed immediately on PS 5.1 and 7 with `Cannot bind argument to parameter 'Path' because it is null` because `$MyInvocation.MyCommand.Path` is unset when the script has no associated file. The installer now resolves its own path defensively and falls through to the remote-download branch when no local checkout is detected (#8).
- Local-checkout fast path now handles checkouts whose paths contain PowerShell wildcard characters (e.g. `[`, `]`) correctly via `[IO.Path]::GetDirectoryName` and `Test-Path -LiteralPath`.

### Added
- Windows smoke test that exercises the piped `irm | iex` invocation and asserts the null-path regression cannot return.

## v0.1.3

### Fixed
- Status line truncated when extra usage was active - 5h section and context gauge were silently dropped when line exceeded display width (#6)

### Changed
- Removed extra usage dollar display ($X/$Y) - most users are trying to avoid extra usage, not track it
- Added `CQB_MAX_WIDTH` env var (default 80) - low-priority segments (tokens, duration) are dropped gracefully when the line overflows instead of breaking the display
- Added `CQB_CACHE_PATH` env var to override cache file location (used internally for test isolation)

## v0.1.2

### Changed
- Default to remaining % (fuel gauge) for all metrics - context, 5h, and 7d now all count down consistently. Set `CQB_REMAINING=0` to restore used % for quotas.

## v0.1.1

### Added
- Visual progress bar for 5h/7d quotas (on by default, disable with `CQB_BAR=0`)
- Clear `no token` message when OAuth credentials are missing instead of silent `--`

## v0.1.0

Initial release.

- 5h/7d quota tracking with color-coded percentages
- Context window usage gauge
- Token counts, reset countdowns, session duration
- One-command install for Windows, macOS, and Linux
- Configurable segments via environment variables
- `CQB_REMAINING` option to show remaining % instead of used %
