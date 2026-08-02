#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_tmp="$(mktemp -d)"
cleanup() { rm -rf -- "$test_tmp"; }
trap cleanup EXIT

[[ -n "$test_tmp" && "$test_tmp" == "${TMPDIR:-/tmp}"/* && "$test_tmp" != "/" ]]
bash -n "$repo_root/scripts/install_suas.sh"
bash -n "$repo_root/scripts/run_suas.sh"
bash -n "$repo_root/scripts/lib/suas_processes.sh"

help_text="$(bash "$repo_root/scripts/run_suas.sh" --help)"
[[ "$help_text" == *"--backend-port"* ]]
[[ "$help_text" == *"--frontend-port"* ]]
[[ "$help_text" == *"127.0.0.1"* ]]

error_file="$test_tmp/error.txt"
if bash "$repo_root/scripts/run_suas.sh" --backend-port not-a-port 2>"$error_file"; then
  echo "invalid port unexpectedly succeeded" >&2
  exit 1
fi
grep -q "port must be an integer" "$error_file"

if bash "$repo_root/scripts/run_suas.sh" --data-dir / 2>"$error_file"; then
  echo "unsafe data directory unexpectedly accepted" >&2
  exit 1
fi
grep -q "unsafe data directory" "$error_file"

echo "sUAS shell contract tests passed"
