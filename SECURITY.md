# Security

## Supported versions

The latest tagged release and the current `main` branch are supported.

## Runtime behavior

At runtime, `claude-usage-monitor` does the following:

- Reads session JSON from Claude Code on `stdin`
- Reads `~/.claude/.credentials.json` (or `$CLAUDE_CONFIG_DIR/.credentials.json` when set) only to access `claudeAiOauth.accessToken`, unless `CLAUDE_CODE_OAUTH_TOKEN` is already set
- Runs `git rev-parse --abbrev-ref HEAD` in the current project to show the active branch
- Writes a cache file and lock file in your system temp directory:
  `claude-sl-usage-<hash>.json` and its matching `.lock`
- Makes an HTTPS request to `https://api.anthropic.com/api/oauth/usage`

It does not install dependencies, ship analytics, or send repository contents, prompts, or local files to any service other than Anthropic's usage endpoint.

## Installer behavior

The installers copy these files into `~/.claude/plugins/claude-usage-monitor`:

- `statusline.py`
- `statusline.sh`
- `statusline.cmd`

They also update `~/.claude/settings.json` to point `statusLine.command` at the installed launcher and create `settings.json.bak` before overwriting an existing settings file.

## Reporting a vulnerability

For sensitive issues, use GitHub's private vulnerability reporting flow if it is enabled for this repository. For non-sensitive bugs, open a normal issue with steps to reproduce.
