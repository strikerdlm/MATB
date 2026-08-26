#!/bin/sh
set -eu

IMAGE=${1:-fac-isr-sms-edge:task6}
SUFFIX="$$"
DATA_VOLUME="sms-task6-data-$SUFFIX"
TLS_VOLUME="sms-task6-tls-$SUFFIX"
PACKAGE_VOLUME="sms-task6-packages-$SUFFIX"
NETWORK="sms-task6-internal-$SUFFIX"
CONTAINER="sms-task6-edge-$SUFFIX"
TLS_HOST=$(mktemp -d "/tmp/sms-task6-tls-$SUFFIX.XXXXXX")

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  docker volume rm "$DATA_VOLUME" "$TLS_VOLUME" "$PACKAGE_VOLUME" >/dev/null 2>&1 || true
  rm -rf "$TLS_HOST"
}
trap cleanup EXIT INT TERM

docker image inspect "$IMAGE" >/dev/null
docker volume create "$DATA_VOLUME" >/dev/null
docker volume create "$TLS_VOLUME" >/dev/null
docker volume create "$PACKAGE_VOLUME" >/dev/null
docker network create --internal "$NETWORK" >/dev/null

openssl req -x509 -newkey rsa:2048 -nodes -subj /CN=127.0.0.1 -addext subjectAltName=IP:127.0.0.1 -keyout "$TLS_HOST/server.key" -out "$TLS_HOST/server.crt" -days 1 >/dev/null 2>&1
cp "$TLS_HOST/server.crt" "$TLS_HOST/server-ca.crt"
openssl genpkey -algorithm ED25519 -out "$TLS_HOST/export.key"
docker run --rm --user 0:0 --entrypoint /bin/sh -v "$TLS_HOST:/source:ro" -v "$TLS_VOLUME:/tls" "$IMAGE" -c '
set -eu
cp /source/server.crt /source/server.key /source/server-ca.crt /source/export.key /tls/
chown 10001:10001 /tls/server.crt /tls/server.key /tls/server-ca.crt /tls/export.key
chmod 0400 /tls/server.key /tls/export.key
chmod 0444 /tls/server.crt /tls/server-ca.crt
'

# A privileged init must fail closed before touching data when a key is exposed.
docker run --rm --user 0:0 --entrypoint /bin/sh -v "$TLS_VOLUME:/tls" "$IMAGE" -c 'chmod 0644 /tls/server.key'
if docker run --rm --user 0:0 --read-only --network none --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER \
  -e SMS_DATABASE_URL=/var/lib/fac-isr/data/edge.sqlite \
  -e SMS_DATA_DIRECTORY=/var/lib/fac-isr/data \
  -e SMS_PACKAGE_DIRECTORY=/opt/sms/packages \
  -e SMS_TLS_CERT_PATH=/run/secrets/tls/server.crt \
  -e SMS_TLS_KEY_PATH=/run/secrets/tls/server.key \
  -e SMS_EXPORT_KEY_PATH=/run/secrets/tls/export.key \
  -v "$DATA_VOLUME:/var/lib/fac-isr" -v "$PACKAGE_VOLUME:/opt/sms/packages:ro" -v "$TLS_VOLUME:/run/secrets/tls:ro" \
  --entrypoint /opt/sms/bin/preflight "$IMAGE" init >/dev/null 2>&1; then
  printf '%s\n' "unsafe TLS key was accepted" >&2
  exit 1
fi
docker run --rm --user 0:0 --entrypoint /bin/sh -v "$TLS_VOLUME:/tls" "$IMAGE" -c 'chmod 0400 /tls/server.key'

docker run --rm --user 0:0 --read-only --network none --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER \
  -e SMS_DATABASE_URL=/var/lib/fac-isr/data/edge.sqlite \
  -e SMS_DATA_DIRECTORY=/var/lib/fac-isr/data \
  -e SMS_PACKAGE_DIRECTORY=/opt/sms/packages \
  -e SMS_TLS_CERT_PATH=/run/secrets/tls/server.crt \
  -e SMS_TLS_KEY_PATH=/run/secrets/tls/server.key \
  -e SMS_EXPORT_KEY_PATH=/run/secrets/tls/export.key \
  -v "$DATA_VOLUME:/var/lib/fac-isr" -v "$PACKAGE_VOLUME:/opt/sms/packages:ro" -v "$TLS_VOLUME:/run/secrets/tls:ro" \
  --entrypoint /opt/sms/bin/preflight "$IMAGE" init | grep -q 'initialized uid=10001 gid=10001'
data_contract=$(docker run --rm --user 10001:10001 --entrypoint /usr/bin/stat -v "$DATA_VOLUME:/var/lib/fac-isr" "$IMAGE" -c '%u:%g %a' /var/lib/fac-isr/data)
[ "$data_contract" = "10001:10001 700" ] || { printf 'unexpected initialized data contract: %s\n' "$data_contract" >&2; exit 1; }

docker run -d --name "$CONTAINER" --user 10001:10001 --read-only --network "$NETWORK" --cap-drop ALL \
  --security-opt no-new-privileges:true --pids-limit 256 --stop-timeout 15 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,uid=10001,gid=10001,mode=0700 \
  -e SMS_DEPLOYMENT_MODE=standalone -e SMS_BIND_ADDRESS=127.0.0.1 -e SMS_PORT=8443 \
  -e SMS_DATABASE_URL=/var/lib/fac-isr/data/edge.sqlite -e SMS_DATA_DIRECTORY=/var/lib/fac-isr/data \
  -e SMS_PACKAGE_DIRECTORY=/opt/sms/packages -e SMS_TLS_CERT_PATH=/run/secrets/tls/server.crt \
  -e SMS_TLS_KEY_PATH=/run/secrets/tls/server.key -e SMS_EXPORT_KEY_PATH=/run/secrets/tls/export.key \
  -e SMS_HEALTH_HOST=127.0.0.1 -e SMS_HEALTH_SERVERNAME=127.0.0.1 -e SMS_HEALTH_CA_PATH=/run/secrets/tls/server-ca.crt \
  -e SMS_EXPORT_KEY_ID=task6-controlled-export -e SMS_CONSOLE_DIRECTORY=/opt/sms/app/apps/console/dist \
  -e SMS_CONFIG_DIRECTORY=/etc/fac-isr-sms \
  -v "$DATA_VOLUME:/var/lib/fac-isr" -v "$PACKAGE_VOLUME:/opt/sms/packages:ro" -v "$TLS_VOLUME:/run/secrets/tls:ro" \
  "$IMAGE" >/dev/null

attempt=0
until docker exec "$CONTAINER" /opt/sms/bin/healthcheck --live >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then docker logs "$CONTAINER" >&2; exit 1; fi
  sleep 1
done

[ "$(docker inspect --format '{{.Config.User}}' "$CONTAINER")" = "10001:10001" ]
[ "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$CONTAINER")" = "true" ]
[ "$(docker network inspect --format '{{.Internal}}' "$NETWORK")" = "true" ]
docker exec "$CONTAINER" /opt/sms/bin/healthcheck --live | grep -q 'PASS installed edge live check'
docker exec "$CONTAINER" node -e '
const https=require("node:https");const r=https.get({host:"127.0.0.1",port:8443,path:"/readyz",rejectUnauthorized:false},x=>{let b="";x.on("data",c=>b+=c);x.on("end",()=>{const p=JSON.parse(b);if(x.statusCode!==503||p.technicalReady!==false||p.operationalReady!==false)process.exit(2)})});r.on("error",()=>process.exit(3));'

docker restart "$CONTAINER" >/dev/null
attempt=0
until docker exec "$CONTAINER" /opt/sms/bin/healthcheck --live >/dev/null 2>&1; do
  attempt=$((attempt + 1)); [ "$attempt" -lt 30 ] || exit 1; sleep 1
done
docker stop --time 15 "$CONTAINER" >/dev/null
[ "$(docker inspect --format '{{.State.ExitCode}}' "$CONTAINER")" = "0" ]
printf '%s\n' "OCI native smoke: PASS (init, TLS, UID/GID, read-only rootfs, internal network, mounts, health/readiness, restart, graceful shutdown)"
