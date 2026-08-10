# syntax=docker/dockerfile:1.7

ARG NODE_IMAGE=node:22.23.2-bookworm-slim@sha256:a17d50af28002a160548bd4225b3cfcb12c5efcb171f79e68758f2885fb1b066

FROM --platform=linux/amd64 ${NODE_IMAGE} AS build
WORKDIR /opt/build
ENV NODE_ENV=development \
    npm_config_audit=false \
    npm_config_fund=false \
    npm_config_update_notifier=false

COPY package.json package-lock.json tsconfig.json tsconfig.base.json ./
COPY packages ./packages
COPY apps ./apps
COPY tools ./tools
RUN npm ci --ignore-scripts
RUN npm run build
RUN npm prune --omit=dev --ignore-scripts

FROM --platform=linux/amd64 ${NODE_IMAGE} AS runtime
ARG BUILD_COMMIT=unknown
LABEL org.opencontainers.image.title="FAC ISR SMS offline edge" \
      org.opencontainers.image.description="Headless, non-C2, offline safety-management edge runtime" \
      org.opencontainers.image.revision="${BUILD_COMMIT}" \
      org.opencontainers.image.source="https://github.com/strikerdlm/MATB"

ENV NODE_ENV=production \
    SMS_BIND_ADDRESS=0.0.0.0 \
    SMS_PORT=8443 \
    SMS_DATABASE_URL=/var/lib/fac-isr/data/edge.sqlite \
    SMS_PACKAGE_DIRECTORY=/opt/sms/packages \
    SMS_TLS_CERT_PATH=/run/secrets/tls/server.crt \
    SMS_TLS_KEY_PATH=/run/secrets/tls/server.key

RUN groupadd --system --gid 10001 sms \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin sms \
    && mkdir -p /opt/sms/app/apps/edge-api /opt/sms/app/packages /opt/sms/app/scripts /opt/sms/bin /opt/sms/console /opt/sms/packages /var/lib/fac-isr/data \
    && chown -R 10001:10001 /opt/sms /var/lib/fac-isr

WORKDIR /opt/sms/app
COPY --from=build --chown=10001:10001 /opt/build/node_modules ./node_modules
COPY --from=build --chown=10001:10001 /opt/build/package.json ./package.json
COPY --from=build --chown=10001:10001 /opt/build/apps/edge-api/package.json ./apps/edge-api/package.json
COPY --from=build --chown=10001:10001 /opt/build/apps/edge-api/dist ./apps/edge-api/dist
COPY --from=build --chown=10001:10001 /opt/build/packages/evidence/package.json ./packages/evidence/package.json
COPY --from=build --chown=10001:10001 /opt/build/packages/evidence/dist ./packages/evidence/dist
COPY --from=build --chown=10001:10001 /opt/build/packages/safety-kernel/package.json ./packages/safety-kernel/package.json
COPY --from=build --chown=10001:10001 /opt/build/packages/safety-kernel/dist ./packages/safety-kernel/dist
COPY --from=build --chown=10001:10001 /opt/build/packages/telemetry/package.json ./packages/telemetry/package.json
COPY --from=build --chown=10001:10001 /opt/build/packages/telemetry/dist ./packages/telemetry/dist
COPY --from=build --chown=10001:10001 /opt/build/apps/console/dist /opt/sms/console
COPY --chown=10001:10001 scripts/start-edge.mjs scripts/edge-healthcheck.mjs /opt/sms/app/scripts/
COPY docker/entrypoint.sh /opt/sms/bin/entrypoint
COPY docker/healthcheck.sh /opt/sms/bin/healthcheck
RUN chmod 0555 /opt/sms/bin/entrypoint /opt/sms/bin/healthcheck \
    && chmod 0444 /opt/sms/app/scripts/*.mjs \
    && find /opt/sms/app /opt/sms/console -type d -exec chmod 0555 {} + \
    && find /opt/sms/app /opt/sms/console -type f -exec chmod 0444 {} +

USER 10001:10001
EXPOSE 8443
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["/opt/sms/bin/healthcheck", "--live"]
ENTRYPOINT ["/opt/sms/bin/entrypoint"]
