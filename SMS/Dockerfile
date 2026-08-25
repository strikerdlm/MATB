ARG NODE_IMAGE=node:22.23.2-bookworm-slim@sha256:a17d50af28002a160548bd4225b3cfcb12c5efcb171f79e68758f2885fb1b066
FROM --platform=linux/amd64 ${NODE_IMAGE}

ARG BUILD_COMMIT=unknown
LABEL org.opencontainers.image.title="FAC ISR SMS offline edge" \
      org.opencontainers.image.description="Headless, non-C2, offline safety-management edge runtime" \
      org.opencontainers.image.version="0.2.0-rc.1" \
      org.opencontainers.image.revision="${BUILD_COMMIT}" \
      org.opencontainers.image.source="https://github.com/strikerdlm/MATB"

ENV NODE_ENV=production \
    SMS_BIND_ADDRESS=127.0.0.1 \
    SMS_PORT=8443 \
    SMS_DATABASE_URL=/var/lib/fac-isr/data/edge.sqlite \
    SMS_DATA_DIRECTORY=/var/lib/fac-isr/data \
    SMS_PACKAGE_DIRECTORY=/opt/sms/packages \
    SMS_TLS_CERT_PATH=/run/secrets/tls/server.crt \
    SMS_TLS_KEY_PATH=/run/secrets/tls/server.key \
    SMS_EXPORT_KEY_PATH=/run/secrets/tls/export.key \
    SMS_EXPORT_KEY_ID=replace-with-institutional-key-id \
    SMS_DEPLOYMENT_MODE=standalone \
    SMS_CONSOLE_DIRECTORY=/opt/sms/app/apps/console/dist \
    SMS_CONFIG_DIRECTORY=/etc/fac-isr-sms

RUN groupadd --system --gid 10001 sms \
    && useradd --system --uid 10001 --gid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin sms \
    && mkdir -p /opt/sms/app /opt/sms/bin /opt/sms/packages /var/lib/fac-isr/data \
    && chown -R 10001:10001 /opt/sms /var/lib/fac-isr

COPY --chown=10001:10001 app /opt/sms/app
COPY entrypoint.sh /opt/sms/bin/entrypoint
COPY healthcheck.sh /opt/sms/bin/healthcheck
COPY preflight.sh /opt/sms/bin/preflight
RUN chmod 0555 /opt/sms/bin/entrypoint /opt/sms/bin/healthcheck /opt/sms/bin/preflight \
    && find /opt/sms/app -type d -exec chmod 0555 {} + \
    && find /opt/sms/app -type f -exec chmod 0444 {} +

WORKDIR /opt/sms/app
USER 10001:10001
EXPOSE 8443
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD ["/opt/sms/bin/healthcheck", "--live"]
ENTRYPOINT ["/opt/sms/bin/entrypoint"]
