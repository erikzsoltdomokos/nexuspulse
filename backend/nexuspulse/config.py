"""Runtime configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing env vars win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    riot_api_key: str = field(default_factory=lambda: os.environ.get("RIOT_API_KEY", ""))
    # Platform routing value (e.g. euw1, na1, kr) used for Summoner-v4 / League-v4.
    riot_platform: str = field(default_factory=lambda: os.environ.get("RIOT_PLATFORM", "euw1"))
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("NEXUSPULSE_DATA_DIR", BACKEND_DIR / "data"))
    )
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", ""))
    # Riot development-key defaults: 20 requests / 1 s and 100 requests / 120 s.
    rate_limits: tuple[tuple[int, float], ...] = ((20, 1.0), (100, 120.0))
    inflection_delta: float = field(
        default_factory=lambda: float(os.environ.get("NEXUSPULSE_INFLECTION_DELTA", "0.08"))
    )
    auto_bootstrap: bool = field(
        default_factory=lambda: os.environ.get("NEXUSPULSE_AUTO_BOOTSTRAP", "1") == "1"
    )

    @property
    def model_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'nexuspulse.db').as_posix()}"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.model_dir.mkdir(parents=True, exist_ok=True)
