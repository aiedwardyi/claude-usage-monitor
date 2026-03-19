#!/usr/bin/env python3
"""
Claude Code statusline with 5h/7d quota tracking.

Shows: model, context gauge, tokens, git branch, 5h remaining%, 7d remaining%,
pace indicator, and reset countdown.

Designed for Windows (Git Bash). Caches API responses to /tmp for 5 minutes.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import threading
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

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

# ── Git branch ──────────────────────────────────────────────────
branch = ""
FALLBACK_REPO = os.path.expanduser("~/Desktop/ai-dev-team")
for try_dir in [proj_dir, FALLBACK_REPO]:
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


def format_reset(minutes):
    """Format reset countdown."""
    if minutes is None:
        return ""
    m = int(minutes)
    if m >= 1440:
        return f" {D}({m // 1440}d){N}"
    if m >= 60:
        return f" {D}({m // 60}h){N}"
    return f" {D}({m}m){N}"


def remaining_pct_str(used_pct):
    """Format remaining % with color."""
    if used_pct is None or used_pct == "--":
        return "--"
    used = int(used_pct)
    remaining = 100 - used
    c = color_pct(used)
    return f"{c}{remaining}%{N}"


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
CACHE_FILE = os.path.join(tempfile.gettempdir(), "claude-sl-usage.json")
CACHE_TTL = 300  # 5 minutes
LOCK_FILE = os.path.join(tempfile.gettempdir(), "claude-sl-usage.lock")


def get_oauth_token():
    """Read OAuth token from Claude Code's credential store."""
    # Env var override
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if tok:
        return tok
    # Credentials file
    cred_path = Path.home() / ".claude" / ".credentials.json"
    if cred_path.exists():
        try:
            creds = json.loads(cred_path.read_text(encoding="utf-8"))
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
        pass
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
filled = round(min(100, max(0, ctx_remaining)) / 100.0 * 5)
gauge = "\u25b0" * filled + "\u25b1" * (5 - filled)  # ▰▱

# Context size label
if ctx_size >= 1_000_000:
    ctx_label = f"{ctx_size // 1_000_000}M"
else:
    ctx_label = f"{ctx_size // 1000}K"

# Line 1: model, project, branch
line1_parts = [f"{C}{DIAMOND} {model}{N}"]

if proj_name:
    loc = f"{proj_name}/{branch}" if branch else proj_name
    if len(loc) > 40:
        loc = loc[:39] + "\u2026"
    line1_parts.append(loc)

line1 = SEP.join(line1_parts)

# Line 2: context gauge, quota, duration
ctx_color = color_pct(ctx_pct_used)
line2_parts = [f"{ctx_color}{gauge}{N} {ctx_remaining}%"]

# Token counts
if in_tok or out_tok:
    line2_parts.append(f"\u2191{compact(in_tok)} \u2193{compact(out_tok)}")

# Quota
usage = read_cached_usage()
if usage:
    u5 = usage["u5"]
    u7 = usage["u7"]
    r5 = usage["r5"]
    r7 = usage["r7"]

    line2_parts.append(f"5h: {remaining_pct_str(u5)}{format_reset(r5)}")
    line2_parts.append(f"7d: {remaining_pct_str(u7)}{format_reset(r7) if u7 is not None and int(u7) >= 70 else ''}")

    # Extra usage (only show when 5h is nearly exhausted)
    if usage["extra_enabled"] and u5 is not None and int(u5) >= 80:
        eu = int(usage["extra_used"])
        el = int(usage["extra_limit"])
        line2_parts.append(f"${eu / 100:.2f}/${el / 100:.2f}")
else:
    line2_parts.append(f"5h: {D}--{N}")
    line2_parts.append(f"7d: {D}--{N}")

# Duration
line2_parts.append(f"{D}{format_duration(duration_ms)}{N}")

line2 = SEP.join(line2_parts)

print(line1)
print(line2)

# Wait for background fetch to finish (max 8s) so cache gets written
if _fetch_thread is not None:
    _fetch_thread.join(timeout=8)
