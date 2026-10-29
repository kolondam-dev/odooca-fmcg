FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-fund
COPY . .
# Safe default: locked live shell. Demo requires an explicit build argument.
ARG PWA_BUILD_MODE=live
RUN case "$PWA_BUILD_MODE" in live) npm run build ;; demo) npm run build:demo ;; staging) npm run build:staging ;; *) exit 1 ;; esac \
    && cp -r "dist/$PWA_BUILD_MODE" /app/site

FROM node:24-alpine
ENV NODE_ENV=production PORT=8080 PWA_DIST=/app/site
WORKDIR /app
COPY --from=build --chown=node:node /app/site ./site
COPY --chown=node:node hosting/server.mjs ./hosting/server.mjs
USER node
EXPOSE 8080
CMD ["node", "hosting/server.mjs"]
