#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

umask 077

: "${SMS_TLS_CERT_PATH:?SMS_TLS_CERT_PATH is required}"
: "${SMS_TLS_KEY_PATH:?SMS_TLS_KEY_PATH is required}"
: "${SMS_DATABASE_URL:?SMS_DATABASE_URL is required}"
: "${SMS_PACKAGE_DIRECTORY:?SMS_PACKAGE_DIRECTORY is required}"

if [ ! -r "$SMS_TLS_CERT_PATH" ]; then
  echo "TLS certificate is not readable: $SMS_TLS_CERT_PATH" >&2
  exit 78
fi
if [ ! -r "$SMS_TLS_KEY_PATH" ]; then
  echo "TLS private key is not readable: $SMS_TLS_KEY_PATH" >&2
  exit 78
fi

key_mode="$(stat -c '%a' "$SMS_TLS_KEY_PATH")"
if [ "$key_mode" != "400" ] && [ "$key_mode" != "600" ]; then
  echo "TLS private key permissions must be 0400 or 0600; found $key_mode" >&2
  exit 78
fi

if [ ! -d "$SMS_PACKAGE_DIRECTORY" ] || [ ! -r "$SMS_PACKAGE_DIRECTORY" ]; then
  echo "read-only package directory is unavailable: $SMS_PACKAGE_DIRECTORY" >&2
  exit 78
fi

exec node /opt/sms/app/scripts/start-edge.mjs
