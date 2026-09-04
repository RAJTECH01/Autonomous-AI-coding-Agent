# syntax=docker/dockerfile:1.7
###############################################################################
# Edge reverse proxy - TLS termination and request routing.
#
# Configuration is baked in rather than bind-mounted, so the image is immutable
# and a rollback restores the routing rules along with the code. The only things
# mounted at run time are TLS certificates (secrets, never in an image) and the
# ACME webroot.
#
# HTTP vs HTTPS is chosen at run time, not build time, via
# NGINX_ENVSUBST_TEMPLATE_DIR:
#   /etc/nginx/templates/http   plaintext 8080          (development)
#   /etc/nginx/templates/tls    8080 redirect + 8443    (production)
#
# Base image is nginx-unprivileged: the worker processes run as uid 101, and
# every writable path lives under /tmp, so the container can run read-only.
###############################################################################

ARG NGINX_VERSION=1.27

FROM nginxinc/nginx-unprivileged:${NGINX_VERSION}-alpine AS production

USER root

# Remove the stock server block; ours arrives from the rendered template.
RUN rm -f /etc/nginx/conf.d/default.conf

COPY nginx.conf   /etc/nginx/nginx.conf
COPY snippets/    /etc/nginx/snippets/
COPY templates/   /etc/nginx/templates/

# ACME webroot for HTTP-01 renewal. Owned by nginx so a certbot sidecar sharing
# the volume can write into it.
RUN mkdir -p /var/www/certbot /etc/nginx/certs \
    && chown -R 101:101 /var/www/certbot /etc/nginx/certs /etc/nginx/snippets /etc/nginx/templates

# Validate the shipped configuration at build time so a syntax error fails the
# build instead of the deploy.
#
# The templates are not yet rendered here (no PUBLIC_HOSTNAME, no certificates,
# and the upstream hostnames do not resolve), so `nginx -t` is run against the
# main config with a stub server block. This proves nginx.conf and the snippets
# parse; the rendered server blocks are validated at container start by nginx's
# own entrypoint.
RUN printf 'server { listen 8080; location / { return 200; } }\n' > /etc/nginx/conf.d/_buildcheck.conf \
    && nginx -t \
    && rm -f /etc/nginx/conf.d/_buildcheck.conf

USER 101

# 8080 plaintext (redirect or dev), 8443 TLS. Published as 80/443 by the host.
EXPOSE 8080 8443

ENV NGINX_ENVSUBST_TEMPLATE_DIR=/etc/nginx/templates/tls \
    NGINX_ENVSUBST_OUTPUT_DIR=/etc/nginx/conf.d \
    PUBLIC_HOSTNAME=localhost

# Probes the proxy's own listener, which answers without touching an upstream, so
# an unhealthy backend does not mark the proxy unhealthy too. Upstream health is
# tracked by their own health checks.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/healthz"]

STOPSIGNAL SIGQUIT

CMD ["nginx", "-g", "daemon off;"]
