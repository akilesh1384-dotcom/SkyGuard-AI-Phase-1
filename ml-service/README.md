# SkyGuard AI ML Service

This is an independent Python 3 service for SkyGuard ML Layer 1. It consumes
readings and simulator ground-truth events from the existing SkyGuard API.
Layer 1 implements causal feature engineering, baseline initialization,
statistical scoring, Isolation Forest scoring, normalized score fusion, and
measured evaluation metrics.

It does not implement SHAP, sensor-health prediction, Edge AI, deep learning,
calibrated confidence, or fault-type classification yet.

## Install

From the repository root:

```bash
cd ml-service
python -m pip install -r requirements.txt
```

## Configure

The service reads data from the existing SkyGuard API:

```text
GET {SKYGUARD_API_URL}/ml/readings
GET {SKYGUARD_API_URL}/ml/ground-truth
```

Set the API base URL with:

```bash
export SKYGUARD_API_URL=http://localhost:80/api
```

The default is `http://localhost:80/api`, which uses the existing SkyGuard API
through the workspace proxy.

Optional timeout configuration:

```bash
export SKYGUARD_API_TIMEOUT_SECONDS=10
```

## Run

From the `ml-service` directory:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Endpoints:

- `GET /health` — returns `{"status": "ok"}`
- `GET /ml/status` — refreshes readings and reports baseline state
- `GET /ml/analyze?limit=200` — returns chronological Layer 1 anomaly results
- `GET /ml/evaluation` — calculates measured metrics against ground truth

## Baseline

The baseline uses the first 60 validated readings that do not fall inside a
known simulator ground-truth event. Readings in an open-ended event are treated
as faulty until that event ends.

Until 60 valid normal readings are available:

```json
{
  "status": "collecting_baseline",
  "baseline_progress": 42,
  "baseline_initialized": false,
  "results": []
}
```

After 60 valid normal readings are available, the baseline is used to fit the
Isolation Forest. Feature rows whose current reading or causal history
contains a known fault are excluded from model training.

## Feature engineering

The prototype uses a causal rolling window of 20 previous readings. It never
uses future observations for the current row.

For each scoreable reading, the exact feature list is:

### Raw

- `temperature`
- `humidity`
- `pressure`

### Temporal

- `temperature_delta`
- `humidity_delta`
- `pressure_delta`

### Rolling

- `temperature_rolling_mean`
- `temperature_rolling_std`
- `humidity_rolling_mean`
- `humidity_rolling_std`
- `pressure_rolling_mean`
- `pressure_rolling_std`

### Multivariate

- `temperature_normalized_deviation`
- `humidity_normalized_deviation`
- `pressure_normalized_deviation`
- `temperature_humidity_relationship`
- `temperature_pressure_relationship`
- `humidity_pressure_relationship`

The normalized deviations use the previous-window median and a robust scale
based on `1.4826 * MAD`, falling back to rolling standard deviation when
necessary. The first 20 readings are not scoreable because they do not have a
complete causal window.

## Detectors and score fusion

The statistical detector uses robust deviation from the rolling baseline and
change relative to rolling variability. Its normalized score is in `[0, 1]`,
with the prototype decision threshold:

```text
statistical_score >= 0.75 → anomaly
```

The ML detector is an `sklearn.ensemble.IsolationForest` configured with:

```text
n_estimators = 100
random_state = 42
contamination = "auto"
```

Isolation Forest's `decision_function` is higher for normal observations. The
service reverses that direction and normalizes the result against the minimum
and maximum decision values observed on the clean fitted baseline:

```text
ml_score = clip((baseline_max_decision - decision) /
                (baseline_max_decision - baseline_min_decision), 0, 1)
```

This is an anomaly score, not a probability or calibrated confidence.

Both detector outputs are already normalized before fusion:

```text
final_score = 0.45 * statistical_score + 0.55 * ml_score
```

The final prototype threshold is:

```text
final_score >= 0.75 → anomaly
```

## Example `/ml/analyze` response

```json
{
  "status": "ready",
  "baseline_progress": 60,
  "baseline_required": 60,
  "baseline_initialized": true,
  "results": [
    {
      "timestamp": "2026-09-14T18:46:24Z",
      "statistical_score": 0.812,
      "ml_score": 0.771,
      "final_score": 0.78945,
      "is_anomaly": true,
      "reasons": [
        "temperature_deviation",
        "isolation_forest"
      ]
    }
  ]
}
```

The example is illustrative; the service does not fabricate results and
returns values calculated from the current readings.

## Example `/ml/evaluation` response

```json
{
  "status": "insufficient_labeled_data",
  "message": "At least 60 valid normal readings are required before evaluation can run.",
  "baseline_progress": 12,
  "baseline_required": 60,
  "baseline_initialized": false,
  "total_readings": 2279,
  "evaluated_readings": 0,
  "labeled_readings": 0,
  "metrics": null,
  "by_fault_type": {}
}
```

This is the current cold-start response shape. Counts change as the simulator
produces data. Once the baseline is initialized, metrics are generated from
current predictions and current ground truth. If there is no ground truth, no
baseline, or no scoreable data, the endpoint returns
`status: "insufficient_labeled_data"` and does not invent metrics.

## Tests

Run the Layer 1 test suite with:

```bash
cd ml-service
pytest -q
```

The tests cover feature calculation, future-leakage prevention, baseline
initialization, statistical scoring, Isolation Forest score bounds, score
fusion, ground-truth exclusion, and evaluation metrics.