#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO="${CLAUDE_USAGE_MONITOR_REPO:-aiedwardyi/claude-usage-monitor}"
REF="${CLAUDE_USAGE_MONITOR_REF:-v0.1.4}"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/${REF}"

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s\n' python
    return 0
  fi
  if command -v py >/dev/null 2>&1; then
    printf '%s\n' "py -3"
    return 0
  fi
  return 1
}

download_file() {
  local url="$1"
  local output="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$output"
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO "$output" "$url"
    return 0
  fi
  printf 'curl or wget is required for remote install\n' >&2
  return 1
}

PYTHON_CMD="$(find_python)" || {
  printf 'python3, python, or py -3 is required\n' >&2
  exit 1
}

if [[ -f "${SCRIPT_DIR}/install.py" ]]; then
  exec ${PYTHON_CMD} "${SCRIPT_DIR}/install.py" "$@"
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

for file in install.py statusline.py statusline.sh statusline.cmd; do
  download_file "${RAW_BASE}/${file}" "${TMP_DIR}/${file}"
done

exec ${PYTHON_CMD} "${TMP_DIR}/install.py" --source-dir "${TMP_DIR}" "$@"
