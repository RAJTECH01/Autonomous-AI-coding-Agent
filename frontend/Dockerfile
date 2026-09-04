# syntax=docker/dockerfile:1.7
###############################################################################
# Frontend image - React 18 + TypeScript + Vite.
#
#   --target production    static build served by unprivileged nginx (default)
#   --target development    Vite dev server with HMR
#
# The production image contains no Node.js runtime, no node_modules and no
# source: only the compiled bundle plus nginx. That is roughly 60 MB instead of
# ~500 MB, and it removes the entire npm dependency tree from the runtime attack
# surface.
#
# No secrets and no build ARGs carrying configuration. The app talks to
# same-origin /api/v1/* and the reverse proxy decides where that goes, so there
# is no API URL to bake in - which also means no rebuild per environment.
###############################################################################

ARG NODE_VERSION=20
ARG NGINX_VERSION=1.27


# =============================================================================
# Stage: deps - install from the lockfile only
# =============================================================================
FROM node:${NODE_VERSION}-alpine AS deps

WORKDIR /app

# package.json + package-lock.json only, so this layer is cached until the
# dependencies actually change.
# `npm ci` (not `npm install`) installs exactly what the lockfile pins and fails
# if package.json and the lockfile disagree, which keeps builds reproducible.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund


# =============================================================================
# Stage: build - type-check and bundle
# =============================================================================
FROM node:${NODE_VERSION}-alpine AS build

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NODE_ENV=production

# `npm run build` is `tsc && vite build`: a type error fails the image build
# rather than shipping a broken bundle.
RUN npm run build \
    && test -f dist/index.html \
    || (echo "FATAL: vite build produced no dist/index.html" >&2 && exit 1)


# =============================================================================
# Stage: production - static assets on unprivileged nginx
# =============================================================================
FROM nginxinc/nginx-unprivileged:${NGINX_VERSION}-alpine AS production

# The nginx-unprivileged image already runs as uid 101 (nginx) and listens on
# 8080. Switch to root only to copy files, then drop back.
USER root

RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

RUN chown -R 101:101 /usr/share/nginx/html \
    && nginx -t

USER 101

EXPOSE 8080

# wget is present in the nginx alpine image, so no extra package is needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/healthz"]

# nginx's own entrypoint handles config templating; "daemon off" keeps it in the
# foreground as PID 1 so it receives SIGTERM/SIGQUIT directly.
CMD ["nginx", "-g", "daemon off;"]


# =============================================================================
# Stage: development - Vite dev server with hot module replacement
# =============================================================================
FROM node:${NODE_VERSION}-alpine AS development

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NODE_ENV=development \
    VITE_PROXY_TARGET=http://backend:8000

# node:alpine ships an unprivileged `node` user (uid 1000).
RUN chown -R node:node /app
USER node

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:5173/"]

# --host 0.0.0.0 is required for the port to be reachable from outside the
# container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
