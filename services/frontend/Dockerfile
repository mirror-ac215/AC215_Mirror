# Stage 1: build the app
#------------------------
FROM node:24-slim AS build
WORKDIR /app

# Install dependencies first (cached unless package files change)
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Then copy the source and build for a plain Node server (Lovable defaults to Cloudflare)
COPY . .
ARG VITE_USE_MOCK_API=false
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_USE_MOCK_API=${VITE_USE_MOCK_API}
ENV NITRO_PRESET=node-server
RUN npm run build

# Stage 2: run the app
#------------------------
FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production PORT=3000

# Only the finished build comes across, no source, no build tools (smaller image)
COPY --from=build /app/.output ./.output

# Don't run as root, for security
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=30s --start-period=10s --retries=3 \
    CMD node -e "fetch('http://localhost:3000/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
CMD ["node", ".output/server/index.mjs"]