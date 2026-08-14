#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root/SMS"
npm ci
npm run build:packages
node ../examples/sms-platform/package-tour.mjs
