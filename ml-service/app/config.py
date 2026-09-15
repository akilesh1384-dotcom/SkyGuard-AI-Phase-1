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
    statistical_weight: float = 0.45
    ml_weight: float = 0.55
    diagnostic_frozen_consecutive: int = int(
        os.getenv("SKYGUARD_DIAGNOSTIC_FROZEN_CONSECUTIVE", "3")
    )
    diagnostic_frozen_tolerance: float = float(
        os.getenv("SKYGUARD_DIAGNOSTIC_FROZEN_TOLERANCE", "0.001")
    )
    diagnostic_expected_interval_seconds: float = float(
        os.getenv("SKYGUARD_DIAGNOSTIC_EXPECTED_INTERVAL_SECONDS", "1")
    )

    @property
    def readings_url(self) -> str:
        return f"{self.skyguard_api_url.rstrip('/')}/ml/readings"

    @property
    def ground_truth_url(self) -> str:
        return f"{self.skyguard_api_url.rstrip('/')}/ml/ground-truth"


settings = Settings()