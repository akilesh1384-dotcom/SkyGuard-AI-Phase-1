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

    @property
    def readings_url(self) -> str:
        return f"{self.skyguard_api_url.rstrip('/')}/ml/readings"


settings = Settings()