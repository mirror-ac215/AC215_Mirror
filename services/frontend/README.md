# frontend

Mirror's web app: patient sign-in, consent, chat with the expression readout, crisis prompt, and the clinician dashboard. Started from our Lovable prototype; models and the api-gateway are not wired in yet (MS2 Part B / MS3).

**Tech:** React 19 + TanStack Start (server-side rendering), built with Vite and packaged by Nitro for a plain Node server. Uses **npm**, not uv (this is the one JavaScript service).

## Run for development (hot reload)

```bash
npm ci
npm run dev
```

## Run in Docker (production build)

```bash
docker build -t mirror-frontend .
docker run --rm -p 3000:3000 mirror-frontend
```

Open http://localhost:3000.

## Notes

- `NITRO_PRESET=node-server` in the Dockerfile switches the build from Lovable's default (Cloudflare) to a plain Node server.
- Multi-stage image: stage 1 installs and builds, stage 2 keeps only `.output` and runs as the non-root `node` user.
- `node_modules/` and `.output/` are never committed; `package-lock.json` is.
- Port: 3000. Health check: `GET /health`.
- Why Node, not nginx: TanStack Start renders pages on the server (SSR) and serves /health from code. nginx is like a librarian that hands you a ready book from the shelf but doesn't write it (can't run the code) meanwhile Node can run the code and because it does it can also answer /health with {"status": "ok"}

## Talking to the backend

- All backend calls live in `src/lib/api/client.ts` (screens never call `fetch` directly). Shapes in `src/lib/api/types.ts` mirror `docs/contracts/api-gateway.openapi.yaml`.
- `VITE_USE_MOCK_API=true` (default) uses `src/lib/api/mock.ts`: replies stream word by word, and a demo crisis phrase opens the 988 dialog. The real safety check lives in the api-gateway, never in the browser.
- `VITE_API_BASE_URL` points at the api-gateway (default `http://localhost:8000`). Copy `.env.example` to `.env.local` to change these.
- `VITE_` values are baked in at **build** time and visible in the browser, so never put secrets in them.
