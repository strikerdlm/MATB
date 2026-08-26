#!/bin/sh
set -eu

umask 077

: "${SMS_TLS_CERT_PATH:?SMS_TLS_CERT_PATH is required}"
: "${SMS_TLS_KEY_PATH:?SMS_TLS_KEY_PATH is required}"
: "${SMS_DATABASE_URL:?SMS_DATABASE_URL is required}"
: "${SMS_PACKAGE_DIRECTORY:?SMS_PACKAGE_DIRECTORY is required}"

exec /opt/sms/bin/preflight runtime "$@"
