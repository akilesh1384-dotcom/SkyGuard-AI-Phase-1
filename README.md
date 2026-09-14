# SkyGuard AI — Phase 1

SkyGuard AI is a live automatic weather station monitoring prototype for Smart India Hackathon problem SIH26073. It streams simulator-generated temperature, relative humidity, and atmospheric pressure readings to a responsive dashboard over WebSocket, while storing readings and simulator ground truth for later ML evaluation work.

## Run

Install workspace dependencies:

```bash
pnpm install
```

Run the API service:

```bash
pnpm --filter @workspace/api-server run dev
```

Run the dashboard in a second terminal:

```bash
pnpm --filter @workspace/skyguard-ai run dev
```

The managed workspace workflows start both services automatically. Open the root preview for the dashboard.

## API

The API is mounted under `/api`:

- `GET /api/healthz` — service health
- `GET /api/latest` — latest stored sensor reading
- `GET /api/history?limit=60` — recent readings, oldest to newest
- `GET /api/status` — simulator status, mode, client count, and storage count
- `POST /api/simulator/start` — start generation
- `POST /api/simulator/stop` — stop generation
- `POST /api/simulator/reset` — clear readings/events and restore the baseline
- `POST /api/simulator/mode` — set `{ "mode": "NORMAL" }` or another supported mode
- `/ws` — WebSocket stream for reading, status, and missing-data messages

Supported modes:

`NORMAL`, `TEMPERATURE_SPIKE`, `TEMPERATURE_DROP`, `HUMIDITY_SPIKE`, `PRESSURE_ANOMALY`, `FROZEN_SENSOR`, `GRADUAL_DRIFT`, `MISSING_DATA`, and `MULTIVARIATE_INCONSISTENCY`.

## Architecture

```text
SimulatorManager
      ↓
ingestReading()  ← future ESP32/BME280 or MQTT adapters can call this path
      ↓
managed PostgreSQL storage
      ↓
REST history/status + WebSocket live stream
      ↓
React dashboard
```

Every non-normal mode creates a ground-truth event with fault type, affected variable, start timestamp, and end timestamp. Readings are checked for required fields, numeric values, valid timestamps, duplicate timestamps, and basic physical sanity limits before insertion.

The workspace's shared server/database foundation is Express + Drizzle + managed PostgreSQL, so this project uses that existing persistent database rather than introducing a second SQLite runtime. The ingestion and processing boundary remains independent from the transport and database layer.

## Project structure

```text
artifacts/
  api-server/
    src/index.ts                 # HTTP + WebSocket server startup
    src/lib/skyguard.ts           # simulator, validation, persistence, broadcast
    src/routes/skyguard.ts        # REST monitoring and simulator controls
  skyguard-ai/
    src/App.tsx                   # live dashboard and controls
    src/index.css                 # visual theme and responsive styling

lib/
  api-spec/openapi.yaml           # REST contract source of truth
  api-client-react/               # generated React Query hooks
  api-zod/                        # generated server validation schemas
  db/src/schema/skyguard.ts       # readings and ground-truth tables
```

## Verification

The Phase 1 acceptance flow was exercised against the running app:

- dashboard opened with live telemetry
- three time-series charts updated through WebSocket
- temperature spike mode generated abnormal readings
- simulator stopped and restarted
- readings were persisted and returned by history
- reset cleared readings and returned to the baseline mode
- frontend and API type checks passed