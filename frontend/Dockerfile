# syntax=docker/dockerfile:1.7

# -----------------------------------------------------------------------------
# Voxel Ledger frontend image.
#
# This Dockerfile builds *only* the prod image: Node build stage produces the
# Vite `dist/` bundle, then nginx serves it. The dev container uses the stock
# `node:20-alpine` image directly from docker-compose with a bind-mounted
# source tree, so there is no `dev` stage here.
#
# Build context is the repo root (we need the workspace `pnpm-lock.yaml`).
# -----------------------------------------------------------------------------

ARG NODE_VERSION=20-alpine
ARG NGINX_VERSION=1.27-alpine

FROM node:${NODE_VERSION} AS builder
WORKDIR /repo
RUN corepack enable
# Copy workspace manifests first for better layer caching.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json frontend/package.json
RUN pnpm install --frozen-lockfile
# Now copy the rest of the frontend source and build.
COPY frontend ./frontend
WORKDIR /repo/frontend
RUN pnpm build

FROM nginx:${NGINX_VERSION} AS runtime
RUN apk add --no-cache wget
# Strip the default site; ours is mounted in by docker-compose. We keep a
# minimal fallback config so a `docker run` of just this image still serves
# static assets without proxying.
COPY ops/nginx/frontend-fallback.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /repo/frontend/dist /usr/share/nginx/html
EXPOSE 80
