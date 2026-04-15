# Changelog

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
