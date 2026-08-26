#!/bin/sh
set -eu

ARTIFACT=${SMS_LINUX_BUNDLE_PATH:-${1:-}}
[ "$(uname -s)" = "Linux" ] || { printf '%s\n' "native Linux evidence requires Linux" >&2; exit 1; }
[ -f "$ARTIFACT" ] || { printf '%s\n' "SMS_LINUX_BUNDLE_PATH must reference the generated Linux release tarball" >&2; exit 1; }
[ "$(basename "$ARTIFACT")" = "fac-isr-sms-0.2.0-rc.1-linux-x64.tar.gz" ] || { printf '%s\n' "native Linux evidence requires the exact production artifact name" >&2; exit 1; }

ROOT=$(mktemp -d "${TMPDIR:-/tmp}/sms-linux-native.XXXXXX")
cleanup() {
  find "$ROOT" -type f -exec chmod u+w {} + 2>/dev/null || true
  rm -rf "$ROOT"
}
trap cleanup EXIT INT TERM

mkdir "$ROOT/extract"
tar -xzf "$ARTIFACT" -C "$ROOT/extract" --no-same-owner
BUNDLE="$ROOT/extract/fac-isr-sms"
CTL="$BUNDLE/install/linux/smsctl"
"$CTL" install --root "$ROOT/host" --bundle "$BUNDLE" --test-mode >/dev/null
CURRENT="$ROOT/host/opt/fac-isr-sms/current"
[ -L "$CURRENT" ]
[ "$("$CURRENT/runtime/bin/node" --version)" = "v22.23.2" ]
[ -f "$CURRENT/inventory.json" ] && [ -f "$CURRENT/inventory.tsv" ]
printf '%s' 'preserve-on-uninstall' > "$ROOT/host/var/lib/fac-isr-sms/data/operator-marker"
"$CTL" uninstall --root "$ROOT/host" --test-mode >/dev/null
[ ! -e "$ROOT/host/opt/fac-isr-sms" ]
[ "$(cat "$ROOT/host/var/lib/fac-isr-sms/data/operator-marker")" = "preserve-on-uninstall" ]
printf '%s\n' "Linux native candidate smoke: PASS (exact artifact, install, Node 22.23.2, inventory, data-preserving uninstall)"
