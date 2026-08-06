FROM node:20-alpine

WORKDIR /app

# Copy the committed lock with the manifest. Repository policy intentionally
# uses npm install (not npm ci) in Docker while still requiring lockfile-based
# resolution for reproducible local images.
COPY package.json package-lock.json ./

RUN npm install && npm ls --depth=0

COPY . .
RUN chown -R node:node /app
USER node

EXPOSE 3000

CMD ["npm", "run", "dev"]
