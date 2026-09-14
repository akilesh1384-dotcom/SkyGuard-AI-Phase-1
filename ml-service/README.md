# SkyGuard AI ML Service

This is an independent Python 3 service shell for the future SkyGuard anomaly-detection methodology. It intentionally does not implement anomaly detection, ML scoring, fault classification, or sensor-health prediction yet.

## Install

From the repository root:

```bash
cd ml-service
python -m pip install -r requirements.txt
```

## Configure

The service reads SkyGuard sensor data from:

```text
GET {SKYGUARD_API_URL}/ml/readings
```

Set the API base URL with:

```bash
export SKYGUARD_API_URL=http://localhost:80/api
```

The default is `http://localhost:80/api`, which uses the existing SkyGuard API through the workspace proxy.

Optional timeout configuration:

```bash
export SKYGUARD_API_TIMEOUT_SECONDS=10
```

## Run

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

From the `ml-service` directory, the service exposes:

- `GET /health` — returns `{"status": "ok"}`
- `GET /ml/status` — refreshes from SkyGuard and returns service status, loaded reading count, latest reading timestamp, and baseline initialization state

## Data contract

The client accepts exactly these four fields:

```json
{
  "timestamp": "2026-09-14T18:46:04Z",
  "temperature": 24.08,
  "humidity": 57.82,
  "pressure": 1013.24
}
```

Timestamps are normalized to timezone-aware UTC datetimes and readings are sorted chronologically after validation. Connection failures and invalid sensor data are logged, while the service keeps its last valid cache for status reporting.

## Future ML implementation

`app/ml_placeholders.py` contains explicit TODO-only placeholders for:

- feature engineering
- statistical detection
- ML detection
- score fusion
- fault classification
- sensor health

These currently return empty or `not_implemented` values and must not be interpreted as working ML.