#!/usr/bin/env bash
# Launcher for claude-statusline (Windows/Git Bash compatible)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONIOENCODING=utf-8 python "$SCRIPT_DIR/statusline.py"
