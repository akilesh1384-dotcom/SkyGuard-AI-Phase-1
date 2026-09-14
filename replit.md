# SkyGuard AI

Live automatic weather station monitoring with a simulator, persistent readings, and a WebSocket dashboard.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 8080)
- `pnpm --filter @workspace/skyguard-ai run dev` — run the dashboard
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env: `DATABASE_URL` — Postgres connection string

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5 + WebSocket (`ws`)
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

- `artifacts/skyguard-ai/src/App.tsx` — live dashboard, charts, controls, and WebSocket consumer
- `artifacts/api-server/src/lib/skyguard.ts` — simulator modes, validation, ingestion, persistence, and broadcast
- `artifacts/api-server/src/routes/skyguard.ts` — monitoring and simulator REST endpoints
- `lib/api-spec/openapi.yaml` — REST contract source of truth
- `lib/db/src/schema/skyguard.ts` — sensor readings and simulator ground-truth tables

## Architecture decisions

- The simulator and ingestion path are separate so future ESP32/BME280 or MQTT adapters can call the same validation/storage boundary.
- WebSocket messages are additive to the REST contract: REST hydrates history and status, then WebSocket messages keep the dashboard current.
- Ground-truth events are created when a fault mode starts and closed when it changes, stops, or resets.
- The existing workspace uses managed PostgreSQL and Drizzle, so SkyGuard uses that shared persistence foundation instead of adding a second database runtime.

## Product

SkyGuard AI Phase 1 shows live temperature, humidity, and pressure telemetry; renders three time-series charts; exposes simulator controls; and stores sensor readings plus anomaly ground truth for future ML evaluation.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- WebSocket preview routing requires `/ws` in the API artifact's path list.
- Run API codegen after changing `lib/api-spec/openapi.yaml`.
- The simulator starts in `SIMULATING` mode when the API server boots.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
