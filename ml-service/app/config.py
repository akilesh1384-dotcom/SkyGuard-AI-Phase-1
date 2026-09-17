from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the independent ML service."""

    skyguard_api_url: str = os.getenv(
        "SKYGUARD_API_URL",
        "http://localhost:80/api",
    )
    request_timeout_seconds: float = float(
        os.getenv("SKYGUARD_API_TIMEOUT_SECONDS", "10")
    )
    rolling_window: int = 20
    baseline_size: int = 60
    anomaly_threshold: float = 0.75
    multivariate_threshold: float = float(
        os.getenv("SKYGUARD_MULTIVARIATE_THRESHOLD", "0.95")
    )
    statistical_weight: float = 0.45
    ml_weight: float = 0.55
    diagnostic_frozen_consecutive: int = int(
        os.getenv("SKYGUARD_DIAGNOSTIC_FROZEN_CONSECUTIVE", "3")
    )
    diagnostic_frozen_tolerance: float = float(
        os.getenv("SKYGUARD_DIAGNOSTIC_FROZEN_TOLERANCE", "0.001")
    )
    # Physical ESP32 telemetry is sent about every 2 seconds. The missing-data
    # detector applies a 1.5x tolerance, so normal network jitter is allowed
    # up to roughly 3 seconds instead of being mistaken for packet loss.
    diagnostic_expected_interval_seconds: float = float(
        os.getenv("SKYGUARD_DIAGNOSTIC_EXPECTED_INTERVAL_SECONDS", "2")
    )

    @property
    def readings_url(self) -> str:
        return f"{self.skyguard_api_url.rstrip('/')}/ml/readings"

    @property
    def ground_truth_url(self) -> str:
        return f"{self.skyguard_api_url.rstrip('/')}/ml/ground-truth"


settings = Settings()
