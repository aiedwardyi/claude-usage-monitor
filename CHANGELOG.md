# Changelog

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
