FROM node:20-alpine

WORKDIR /app

# Copy the committed lock with the manifest. Repository policy intentionally
# uses npm install (not npm ci) in Docker while still requiring lockfile-based
# resolution for reproducible local images.
ARG NPM_CONFIG_REGISTRY=https://mirrors.cloud.tencent.com/npm/
COPY package.json package-lock.json ./

RUN cp package-lock.json /tmp/package-lock.before && \
    npm install --ignore-scripts --registry "$NPM_CONFIG_REGISTRY" && \
    node -e "const fs=require('fs'); const before=JSON.stringify(JSON.parse(fs.readFileSync('/tmp/package-lock.before','utf8'))); const after=JSON.stringify(JSON.parse(fs.readFileSync('package-lock.json','utf8'))); if (before !== after) { console.error('package-lock.json changed semantically'); process.exit(1); }" && \
    npm ls --depth=0

COPY . .
RUN chown -R node:node /app
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/ >/dev/null || exit 1

CMD ["npm", "run", "dev"]
