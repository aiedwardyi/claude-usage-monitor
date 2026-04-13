# Changelog

## v0.1.3

### Fixed
- Status line truncated when extra usage is active - 5h section and context gauge were silently dropped when line exceeded display width (#6)
- Extra usage display now shows compact dollar amounts ($64/$105 instead of $63.82/$105.00)

### Added
- `CQB_MAX_WIDTH` env var to control maximum status line width (default 60) - segments are dropped by priority when the line overflows

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
