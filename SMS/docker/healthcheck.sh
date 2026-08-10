#!/bin/sh
set -eu

exec node /opt/sms/app/scripts/edge-healthcheck.mjs "${1:---self-test}"
