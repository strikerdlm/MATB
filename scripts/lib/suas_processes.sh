#!/usr/bin/env bash
# Small, side-effect-free process helpers shared by the offline sUAS scripts.

set -euo pipefail

require_command() {
  local command_name="${1:?command name required}"
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "required command not found: $command_name" >&2
    return 127
  }
}

validate_port() {
  local value="${1:-}"
  if [[ ! "$value" =~ ^[0-9]+$ ]] || (( value < 1 || value > 65535 )); then
    echo "port must be an integer between 1 and 65535: $value" >&2
    return 2
  fi
}

port_in_use() {
  local bind="${1:?bind required}"
  local port="${2:?port required}"
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn "sport = :$port" 2>/dev/null | awk -v address="$bind" -v port="$port" '$4 ~ (address ":" port "$" || $4 ~ ("\\[" address "\\]:" port "$")) { found=1 } END { exit found ? 0 : 1 }'
    return $?
  fi
  if [[ "$bind" == "127.0.0.1" || "$bind" == "localhost" ]]; then
    (exec 3<>"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1 && return 0
  fi
  return 1
}

wait_http() {
  local url="${1:?url required}"
  local attempts="${2:-60}"
  local count=0
  while (( count < attempts )); do
    if curl --fail --silent --show-error --max-time 1 "$url" >/dev/null 2>&1; then
      return 0
    fi
    count=$((count + 1))
    sleep 0.2
  done
  echo "timed out waiting for $url" >&2
  return 1
}

terminate_pid() {
  local pid="${1:-}"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  kill -0 "$pid" 2>/dev/null || return 0
  kill -TERM -- "$pid" 2>/dev/null || true
  for _ in {1..50}; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.1
  done
  echo "process $pid did not exit after SIGTERM" >&2
  return 1
}
