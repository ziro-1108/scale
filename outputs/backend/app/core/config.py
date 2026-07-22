from functools import lru_cache
import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def load_env_file() -> None:
    env_path = BACKEND_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


class Settings:
    app_name: str = os.getenv("APP_NAME", "SCALE")
    database_url: str = os.getenv("DATABASE_URL", "")
    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "API_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    storage_dir: Path = Path(os.getenv("STORAGE_DIR", str(BACKEND_ROOT / "storage")))
    measurement_result_url: str = os.getenv(
        "MEASUREMENT_RESULT_URL",
        "http://measurement-server.local/tasks/{task_id}",
    )
    measurement_image_url: str = os.getenv(
        "MEASUREMENT_IMAGE_URL",
        "http://measurement-server.local/tasks/{task_id}/image",
    )
    worker_poll_interval_seconds: float = float(
        os.getenv("WORKER_POLL_INTERVAL_SECONDS", "3")
    )
    worker_batch_size: int = int(os.getenv("WORKER_BATCH_SIZE", "50"))
    worker_concurrency: int = int(os.getenv("WORKER_CONCURRENCY", "10"))

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def thumbnails_dir(self) -> Path:
        return self.storage_dir / "thumbnails"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required. Use a Cloud MySQL SQLAlchemy URL.")
    if not settings.database_url.startswith("mysql+"):
        raise RuntimeError("Only Cloud MySQL SQLAlchemy URLs are supported.")
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.thumbnails_dir.mkdir(parents=True, exist_ok=True)
    return settings
