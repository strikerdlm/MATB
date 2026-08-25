#!/bin/sh
set -eu

SERVICE_UID=10001
SERVICE_GID=10001

fail() {
  printf '%s\n' "$*" >&2
  exit 78
}

: "${SMS_DATA_DIRECTORY:=${SMS_DATABASE_URL%/*}}"
: "${SMS_PACKAGE_DIRECTORY:?SMS_PACKAGE_DIRECTORY is required}"
: "${SMS_TLS_CERT_PATH:?SMS_TLS_CERT_PATH is required}"
: "${SMS_TLS_KEY_PATH:?SMS_TLS_KEY_PATH is required}"
: "${SMS_EXPORT_KEY_PATH:?SMS_EXPORT_KEY_PATH is required}"

validate_regular() {
  [ -f "$1" ] && [ ! -L "$1" ] || fail "$2 is missing, non-regular, or symbolic"
}

validate_tls() {
  validate_regular "$SMS_TLS_CERT_PATH" "TLS certificate"
  validate_regular "$SMS_TLS_KEY_PATH" "TLS private key"
  key_mode=$(stat -c '%a' "$SMS_TLS_KEY_PATH")
  [ "$key_mode" = "400" ] || [ "$key_mode" = "600" ] || fail "TLS private key permissions must be 0400 or 0600; found $key_mode"
  key_owner=$(stat -c '%u:%g' "$SMS_TLS_KEY_PATH")
  [ "$key_owner" = "$SERVICE_UID:$SERVICE_GID" ] || fail "TLS private key ownership must be $SERVICE_UID:$SERVICE_GID; found $key_owner"
  cert_owner=$(stat -c '%u:%g' "$SMS_TLS_CERT_PATH")
  [ "$cert_owner" = "$SERVICE_UID:$SERVICE_GID" ] || fail "TLS certificate ownership must be $SERVICE_UID:$SERVICE_GID; found $cert_owner"
  validate_regular "$SMS_EXPORT_KEY_PATH" "export private key"
  export_mode=$(stat -c '%a' "$SMS_EXPORT_KEY_PATH")
  [ "$export_mode" = "400" ] || [ "$export_mode" = "600" ] || fail "export private key permissions must be 0400 or 0600; found $export_mode"
  export_owner=$(stat -c '%u:%g' "$SMS_EXPORT_KEY_PATH")
  [ "$export_owner" = "$SERVICE_UID:$SERVICE_GID" ] || fail "export private key ownership must be $SERVICE_UID:$SERVICE_GID; found $export_owner"
  if [ -n "${SMS_TLS_CLIENT_CA_PATH:-}" ]; then
    validate_regular "$SMS_TLS_CLIENT_CA_PATH" "TLS client CA"
  fi
  if [ -n "${SMS_HEALTH_CLIENT_CERT_PATH:-}" ] || [ -n "${SMS_HEALTH_CLIENT_KEY_PATH:-}" ]; then
    : "${SMS_HEALTH_CLIENT_CERT_PATH:?health client certificate and key must be configured together}"
    : "${SMS_HEALTH_CLIENT_KEY_PATH:?health client certificate and key must be configured together}"
    validate_regular "$SMS_HEALTH_CLIENT_CERT_PATH" "health client certificate"
    validate_regular "$SMS_HEALTH_CLIENT_KEY_PATH" "health client private key"
    health_mode=$(stat -c '%a' "$SMS_HEALTH_CLIENT_KEY_PATH")
    [ "$health_mode" = "400" ] || [ "$health_mode" = "600" ] || fail "health client private key permissions must be 0400 or 0600; found $health_mode"
    health_owner=$(stat -c '%u:%g' "$SMS_HEALTH_CLIENT_KEY_PATH")
    [ "$health_owner" = "$SERVICE_UID:$SERVICE_GID" ] || fail "health client private key ownership must be $SERVICE_UID:$SERVICE_GID; found $health_owner"
  fi
}

validate_packages() {
  [ -d "$SMS_PACKAGE_DIRECTORY" ] && [ ! -L "$SMS_PACKAGE_DIRECTORY" ] && [ -r "$SMS_PACKAGE_DIRECTORY" ] || fail "read-only package directory is unavailable or unsafe"
  package_mode=$(stat -c '%a' "$SMS_PACKAGE_DIRECTORY")
  case "$package_mode" in
    *[2367]|*[2367][0-7]) fail "package directory must not be group/other writable" ;;
  esac
}

COMMAND=${1:-runtime}
if [ "$#" -gt 0 ]; then shift; fi
case "$COMMAND" in
  init)
    [ "$(id -u)" -eq 0 ] || fail "OCI init requires the privileged root path"
    validate_tls
    validate_packages
    [ ! -L "$SMS_DATA_DIRECTORY" ] || fail "data directory cannot be a symbolic link"
    mkdir -p "$SMS_DATA_DIRECTORY"
    chown -R "$SERVICE_UID:$SERVICE_GID" "$SMS_DATA_DIRECTORY"
    chmod 0700 "$SMS_DATA_DIRECTORY"
    printf 'initialized uid=%s gid=%s data=%s\n' "$SERVICE_UID" "$SERVICE_GID" "$SMS_DATA_DIRECTORY"
    ;;
  runtime)
    [ "$(id -u)" -eq "$SERVICE_UID" ] && [ "$(id -g)" -eq "$SERVICE_GID" ] || fail "permanent OCI runtime must execute as UID 10001 and GID 10001"
    validate_tls
    validate_packages
    [ -d "$SMS_DATA_DIRECTORY" ] && [ ! -L "$SMS_DATA_DIRECTORY" ] || fail "initialized data directory is unavailable"
    [ "$(stat -c '%u:%g' "$SMS_DATA_DIRECTORY")" = "$SERVICE_UID:$SERVICE_GID" ] || fail "data ownership must be $SERVICE_UID:$SERVICE_GID"
    data_mode=$(stat -c '%a' "$SMS_DATA_DIRECTORY")
    [ "$data_mode" = "700" ] || fail "data permissions must be 0700; found $data_mode"
    if [ "$#" -gt 0 ]; then exec "$@"; fi
    exec node /opt/sms/app/scripts/start-edge.mjs
    ;;
  *) fail "usage: preflight init | preflight runtime [command ...]" ;;
esac
