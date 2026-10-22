"""Application settings, read from environment variables (see .env.example)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"


def _env_list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "SearchSphere AI"
    version: str = "0.1.0"
    database_path: Path = field(
        default_factory=lambda: Path(os.getenv("SEARCHSPHERE_DB_PATH", str(DATA_DIR / "searchsphere.db")))
    )
    nltk_data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("SEARCHSPHERE_NLTK_DIR", str(DATA_DIR / "nltk_data")))
    )
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list(
            "SEARCHSPHERE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
        )
    )
    wildcard_expansion_limit: int = int(os.getenv("SEARCHSPHERE_WILDCARD_LIMIT", "50"))


settings = Settings()
