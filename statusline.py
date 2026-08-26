#!/usr/bin/env python3
"""
Claude Code statusline with 5h/7d quota tracking.

Shows: model, context gauge, tokens, git branch, 5h remaining%, 7d remaining%,
pace indicator, and reset countdown.

Designed for Claude Code on Windows, macOS, and Linux. Caches API responses to
the system temp directory for 5 minutes.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import threading
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


# Config home respects CLAUDE_CONFIG_DIR (set by tools like claude-swap),
# mirroring claude-code: CLAUDE_CONFIG_DIR if set, else ~/.claude.
def _config_home() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"

# Main config file (holds oauthAccount). Lives inside CLAUDE_CONFIG_DIR when set,
# else the legacy ~/.claude.json sibling. Mirrors claude-code's own lookup.
def _config_file() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) / ".claude.json" if env else Path.home() / ".claude.json"

# ── Configuration (env vars) ─────────────────────────────────────
# Set these in your shell profile or in Claude Code's settings.json env block.
# Values: "1" = show, "0" = hide
SHOW_CONTEXT_SIZE = os.environ.get("CQB_CONTEXT_SIZE", "0") == "1"
SHOW_TOKENS = os.environ.get("CQB_TOKENS", "1") == "1"
SHOW_PACE = os.environ.get("CQB_PACE", "0") == "1"
SHOW_RESET = os.environ.get("CQB_RESET", "1") == "1"
SHOW_DURATION = os.environ.get("CQB_DURATION", "1") == "1"
SHOW_BRANCH = os.environ.get("CQB_BRANCH", "1") == "1"
SHOW_COST = os.environ.get("CQB_COST", "0") == "1"
SHOW_REMAINING = os.environ.get("CQB_REMAINING", "1") == "1"
SHOW_BAR = os.environ.get("CQB_BAR", "1") == "1"
SHOW_EMAIL = os.environ.get("CQB_EMAIL", "0") == "1"
# Width budget: an explicit CQB_MAX_WIDTH first, then the real terminal width
# Claude Code exports as COLUMNS, then 80 for Claude Code older than v2.1.153,
# which does not set it. COLUMNS is the only source available: our stdout is
# captured rather than attached to the tty, so tput and get_terminal_size()
# both report a fallback size instead of the terminal's. Each candidate is
# skipped when empty, non-numeric, or non-positive (never blank the line).
MAX_WIDTH = 80
for _candidate in (os.environ.get("CQB_MAX_WIDTH"), os.environ.get("COLUMNS")):
    try:
        _width = int(_candidate)
    except (TypeError, ValueError):
        continue
    if _width > 0:
        MAX_WIDTH = _width
        break

# ── Read stdin ──────────────────────────────────────────────────
raw = sys.stdin.read().strip()
if not raw:
    print("Claude")
    sys.exit(0)

try:
    d = json.loads(raw)
except json.JSONDecodeError:
    print("Claude")
    sys.exit(0)

# ── ANSI colors ─────────────────────────────────────────────────
C = "\033[36m"   # cyan
G = "\033[32m"   # green
Y = "\033[33m"   # yellow
R = "\033[31m"   # red
D = "\033[2m"    # dim
N = "\033[0m"    # reset

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def strip_ansi(text):
    """Remove ANSI escape sequences to measure visible width."""
    return _ANSI_RE.sub("", text)


def color_pct(used_pct):
    """Color based on how much quota is USED (high = bad)."""
    if used_pct >= 90:
        return R
    if used_pct >= 70:
        return Y
    return G


# ── Parse session data ──────────────────────────────────────────
model = "Opus"
try:
    model = d["model"]["display_name"]
except (KeyError, TypeError):
    pass

ctx_pct_used = 0
ctx_size = 0
try:
    ctx_pct_used = int(d["context_window"]["used_percentage"] or 0)
    ctx_size = int(d["context_window"]["context_window_size"] or 0)
except (KeyError, TypeError, ValueError):
    pass

in_tok = 0
out_tok = 0
try:
    in_tok = d["context_window"]["total_input_tokens"] or 0
except (KeyError, TypeError):
    pass
try:
    out_tok = d["context_window"]["total_output_tokens"] or 0
except (KeyError, TypeError):
    pass

cost_usd = 0.0
duration_ms = 0
try:
    cost_usd = float(d["cost"]["total_cost_usd"] or 0)
except (KeyError, TypeError, ValueError):
    pass
try:
    duration_ms = int(d["cost"]["total_duration_ms"] or 0)
except (KeyError, TypeError, ValueError):
    pass

proj_dir = ""
proj_name = ""
try:
    proj_dir = d["workspace"]["project_dir"] or ""
    proj_name = os.path.basename(proj_dir)
except (KeyError, TypeError):
    pass

# Account email (only for Anthropic OAuth logins; API-key logins have no oauthAccount)
email = ""
if SHOW_EMAIL:
    try:
        cfg = json.loads(_config_file().read_text(encoding="utf-8"))
        email = cfg.get("oauthAccount", {}).get("emailAddress", "") or ""
    except Exception:
        pass

# ── Git branch ──────────────────────────────────────────────────
branch = ""
cwd = os.getcwd()
candidate_dirs = []
if proj_dir:
    candidate_dirs.append(proj_dir)
if cwd and cwd not in candidate_dirs:
    candidate_dirs.append(cwd)

for try_dir in candidate_dirs:
    if not try_dir:
        continue
    try:
        r = subprocess.run(
            ["git", "-C", try_dir, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0:
            branch = r.stdout.strip()
            if not proj_name:
                proj_name = os.path.basename(try_dir)
            break
    except Exception:
        pass

# ── Helpers ─────────────────────────────────────────────────────
def compact(n):
    n = float(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}m".replace(".0m", "m")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return str(int(n))


def format_duration(ms):
    if ms >= 3_600_000:
        return f"{ms // 3_600_000}h{(ms // 60_000) % 60}m"
    if ms >= 60_000:
        return f"{ms // 60_000}m{(ms // 1000) % 60}s"
    return f"{ms // 1000}s"


def format_reset(minutes, compact=False):
    """Format reset countdown.

    Carries a second unit so "(1d)" cannot silently mean 47h, and drops that
    unit when it is zero so exact boundaries stay "(2h)" / "(2d)". compact
    keeps only the largest unit, for when the line has to give something back.
    """
    if minutes is None:
        return ""
    m = int(minutes)
    if m >= 1440:
        d, h = m // 1440, (m % 1440) // 60
        return f" {D}({d}d{h}h){N}" if h and not compact else f" {D}({d}d){N}"
    if m >= 60:
        h, mm = m // 60, m % 60
        return f" {D}({h}h{mm}m){N}" if mm and not compact else f" {D}({h}h){N}"
    return f" {D}({m}m){N}"


def gauge_blocks(val):
    """Filled blocks (0-5) for a 0-100 percent gauge.

    Keeps round()'s banker's rounding for the exact .5 ties (10/30/50/70/90
    may land on either neighbour) and adds a single floor: from 10% upward
    the bar never renders fully depleted. round(0.5) -> 0 used to show an
    empty bar at 10% remaining, which reads as "nothing left".
    """
    v = min(100, max(0, val))
    return max(1, round(v / 20.0)) if v >= 10 else 0


def used_pct_str(used_pct):
    """Format used or remaining % with color."""
    if used_pct is None or used_pct == "--":
        return "--"
    used = int(used_pct)
    c = color_pct(used)
    val = 100 - used if SHOW_REMAINING else used
    val = max(0, min(100, val))  # clamp so the displayed number matches the bar fill
    if SHOW_BAR:
        filled = gauge_blocks(val)
        filled_chars = "\u25b0" * filled
        empty_chars = "\u25b1" * (5 - filled)
        bar = f"{c}{filled_chars}{empty_chars}{N} "
    else:
        bar = ""
    return f"{bar}{c}{val}%{N}"


def pace_indicator(used_pct, remain_min, window_min):
    """Show pace: positive = ahead (green), negative = over pace (red). Suppress within +/-10%."""
    if used_pct is None or remain_min is None:
        return ""
    try:
        used = int(used_pct)
        rmin = int(remain_min)
    except (ValueError, TypeError):
        return ""
    if rmin > window_min:
        return ""
    elapsed = window_min - rmin
    if elapsed <= 0:
        return ""
    expected = (elapsed * 100) // window_min
    delta = expected - used
    if delta > 10:
        return f" {G}+{delta}%{N}"
    if delta < -10:
        return f" {R}{delta}%{N}"
    return ""


# ── Quota API ───────────────────────────────────────────────────
# Cache is keyed per config home so swapping logins (CLAUDE_CONFIG_DIR) never
# serves another account's cached usage. Explicit CQB_CACHE_PATH still wins.
_cache_key = hashlib.sha1(
    str(_config_home()).encode(), usedforsecurity=False
).hexdigest()[:12]
CACHE_FILE = os.environ.get(
    "CQB_CACHE_PATH",
    os.path.join(tempfile.gettempdir(), f"claude-sl-usage-{_cache_key}.json"),
)
CACHE_TTL = 300  # 5 minutes
LOCK_FILE = CACHE_FILE + ".lock"


def get_oauth_token():
    """Read OAuth token from Claude Code's credential store."""
    # Env var override
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if tok:
        return tok
    # Credentials file (Linux/Windows and older macOS installs)
    cred_path = _config_home() / ".credentials.json"
    if cred_path.exists():
        try:
            creds = json.loads(cred_path.read_text(encoding="utf-8"))
            tok = creds.get("claudeAiOauth", {}).get("accessToken")
            if tok:
                return tok
        except Exception:
            pass
    # macOS Keychain: Claude Code stores credentials here, not in .credentials.json
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["security", "find-generic-password",
                 "-s", "Claude Code-credentials", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                creds = json.loads(result.stdout.strip())
                return creds.get("claudeAiOauth", {}).get("accessToken")
        except Exception:
            pass
    return None


def fetch_usage_sync():
    """Call Anthropic usage API and write cache. Run in background thread."""
    try:
        token = get_oauth_token()
        if not token:
            return

        import urllib.request

        req = urllib.request.Request(
            "https://api.anthropic.com/api/oauth/usage",
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        def parse_reset_minutes(iso_str):
            if not iso_str:
                return None
            try:
                from datetime import datetime, timezone
                # Handle various ISO formats
                iso_str = iso_str.replace("+00:00", "+0000").replace("Z", "+0000")
                # Strip fractional seconds
                if "." in iso_str:
                    base, rest = iso_str.split(".", 1)
                    tz_part = ""
                    for sep in ["+", "-"]:
                        if sep in rest:
                            idx = rest.index(sep)
                            tz_part = rest[idx:]
                            break
                    iso_str = base + tz_part
                dt = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S%z")
                now = datetime.now(timezone.utc)
                diff = (dt - now).total_seconds() / 60
                return max(0, int(diff))
            except Exception:
                return None

        cache_data = {
            "five_hour_used": data.get("five_hour", {}).get("utilization", 0),
            "seven_day_used": data.get("seven_day", {}).get("utilization", 0),
            "five_hour_reset_min": parse_reset_minutes(data.get("five_hour", {}).get("resets_at")),
            "seven_day_reset_min": parse_reset_minutes(data.get("seven_day", {}).get("resets_at")),
            "extra_enabled": data.get("extra_usage", {}).get("is_enabled", False),
            "extra_used": data.get("extra_usage", {}).get("used_credits", 0),
            "extra_limit": data.get("extra_usage", {}).get("monthly_limit", 0),
            "fetched_at": time.time(),
        }

        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cache_data, f)
        os.replace(tmp, CACHE_FILE)

    except Exception:
        pass  # Intentional: statusline must never fail visibly
    finally:
        try:
            os.unlink(LOCK_FILE)
        except OSError:
            pass


_fetch_thread = None

def read_cached_usage():
    """Read cached usage data, trigger background refresh if stale."""
    global _fetch_thread
    cache = None
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cache = json.load(f)
        except Exception:
            pass

    # Check if cache is stale
    now = time.time()
    fetched_at = (cache or {}).get("fetched_at", 0)
    is_stale = (now - fetched_at) > CACHE_TTL

    if is_stale:
        # Try to acquire lock (non-blocking)
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            # Fetch in background thread; joined at end of script
            t = threading.Thread(target=fetch_usage_sync)
            t.start()
            _fetch_thread = t
        except FileExistsError:
            # Another process is fetching; check if lock is stale (>30s)
            try:
                lock_age = now - os.path.getmtime(LOCK_FILE)
                if lock_age > 30:
                    os.unlink(LOCK_FILE)
            except OSError:
                pass

    if cache:
        # Adjust reset minutes for time elapsed since fetch
        elapsed_min = (now - cache.get("fetched_at", now)) / 60
        r5 = cache.get("five_hour_reset_min")
        r7 = cache.get("seven_day_reset_min")
        if r5 is not None:
            r5 = max(0, int(r5 - elapsed_min))
        if r7 is not None:
            r7 = max(0, int(r7 - elapsed_min))
        return {
            "u5": cache.get("five_hour_used"),
            "u7": cache.get("seven_day_used"),
            "r5": r5,
            "r7": r7,
            "extra_enabled": cache.get("extra_enabled", False),
            "extra_used": cache.get("extra_used", 0),
            "extra_limit": cache.get("extra_limit", 0),
        }

    return None


# ── Build output ────────────────────────────────────────────────
SEP = " \u2502 "  # │
DIAMOND = "\u25c6"  # ◆

# Context gauge (5 blocks)
ctx_remaining = 100 - ctx_pct_used
ctx_val = ctx_remaining if SHOW_REMAINING else ctx_pct_used
filled = gauge_blocks(ctx_val)
gauge = "\u25b0" * filled + "\u25b1" * (5 - filled)  # ▰▱

# Context size label
if ctx_size >= 1_000_000:
    ctx_label = f"{ctx_size // 1_000_000}M"
else:
    ctx_label = f"{ctx_size // 1000}K"

# Line 1: model, project, branch
line1_parts = [f"{C}{DIAMOND} {model}{N}"]

if proj_name:
    loc = f"{proj_name}/{branch}" if (branch and SHOW_BRANCH) else proj_name
    if len(loc) > 40:
        loc = loc[:39] + "\u2026"
    line1_parts.append(loc)

if SHOW_EMAIL and email:
    line1_parts.append(f"{D}{email}{N}")

line1 = SEP.join(line1_parts)

# Line 2: context gauge, quota, duration
# Each segment is (text, priority) - lower priority number = more important (dropped last).
# When the joined line exceeds MAX_WIDTH, the highest-numbered priorities are dropped first.
ctx_color = color_pct(ctx_pct_used)
ctx_str = f"{ctx_color}{gauge}{N} {ctx_val}%"
if SHOW_CONTEXT_SIZE:
    ctx_str += f" of {ctx_label}"

line2_segments = []  # list of (text, priority)
line2_segments.append((ctx_str, 2))

# Token counts
if SHOW_TOKENS and (in_tok or out_tok):
    line2_segments.append((f"\u2191{compact(in_tok)} \u2193{compact(out_tok)}", 4))

# Quota
quota_at = ()
quota_fallbacks = []
usage = read_cached_usage()
if usage:
    u5 = usage["u5"]
    u7 = usage["u7"]
    r5 = usage["r5"]
    r7 = usage["r7"]

    pace5 = pace_indicator(u5, r5, 300) if SHOW_PACE else ""
    pace7 = pace_indicator(u7, r7, 10080) if SHOW_PACE else ""
    quota5 = f"5h: {used_pct_str(u5)}{pace5}"
    quota7 = f"7d: {used_pct_str(u7)}{pace7}"
    reset5 = format_reset(r5) if SHOW_RESET else ""
    reset7 = format_reset(r7) if SHOW_RESET else ""

    quota_at = (len(line2_segments), len(line2_segments) + 1)
    line2_segments.append((quota5 + reset5, 1))
    line2_segments.append((quota7 + reset7, 1))
    if SHOW_RESET:
        quota_fallbacks = [
            (quota5 + format_reset(r5, compact=True),
             quota7 + format_reset(r7, compact=True)),
            (quota5, quota7),
        ]
else:
    if not get_oauth_token():
        line2_segments.append((f"5h: {D}no token{N}", 1))
        line2_segments.append((f"7d: {D}no token{N}", 1))
    else:
        line2_segments.append((f"5h: {D}--{N}", 1))
        line2_segments.append((f"7d: {D}--{N}", 1))

# Cost
if SHOW_COST and cost_usd > 0:
    line2_segments.append((f"{D}${cost_usd:.2f}{N}", 4))

# Duration
if SHOW_DURATION:
    line2_segments.append((f"{D}{format_duration(duration_ms)}{N}", 3))

# Drop lowest-priority segments until line fits within MAX_WIDTH
def build_line(segments):
    return SEP.join(text for text, _ in segments)

line2 = build_line(line2_segments)

# Give back countdown detail before sacrificing a whole segment: the gauge is
# the number you act on, and dropping one costs far more than the "(1d16h)" it
# was protecting. Second unit first, then the countdown entirely.
for narrower in quota_fallbacks:
    if len(strip_ansi(line2)) <= MAX_WIDTH:
        break
    for index, text in zip(quota_at, narrower):
        line2_segments[index] = (text, line2_segments[index][1])
    line2 = build_line(line2_segments)

while len(strip_ansi(line2)) > MAX_WIDTH and line2_segments:
    worst = max(range(len(line2_segments)), key=lambda i: line2_segments[i][1])
    line2_segments.pop(worst)
    line2 = build_line(line2_segments)

print(line1)
print(line2)

# Wait for background fetch to finish (max 8s) so cache gets written
if _fetch_thread is not None:
    _fetch_thread.join(timeout=8)
