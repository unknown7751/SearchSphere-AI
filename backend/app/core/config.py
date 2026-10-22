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
    version: str = "0.3.0"
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
    # Upload limits (documented in README): 5 MB per file, 200,000 characters of extracted text.
    max_upload_bytes: int = int(os.getenv("SEARCHSPHERE_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    max_document_chars: int = int(os.getenv("SEARCHSPHERE_MAX_DOCUMENT_CHARS", "200000"))
    # Crawler (Phase 3). Per-job limits (max_pages, max_depth, timeout) are request fields with hard caps in
    # app/schemas/crawler.py; these are the global safety rails.
    crawler_user_agent: str = os.getenv(
        "SEARCHSPHERE_CRAWLER_USER_AGENT", "SearchSphereBot/1.0 (+educational IR project; honours robots.txt)"
    )
    crawler_request_delay: float = float(os.getenv("SEARCHSPHERE_CRAWLER_DELAY", "0.5"))  # seconds between requests
    crawler_max_response_bytes: int = int(os.getenv("SEARCHSPHERE_CRAWLER_MAX_BYTES", str(2 * 1024 * 1024)))
    crawler_max_redirects: int = int(os.getenv("SEARCHSPHERE_CRAWLER_MAX_REDIRECTS", "5"))
    crawler_max_duration: float = float(os.getenv("SEARCHSPHERE_CRAWLER_MAX_DURATION", "300"))  # seconds per job
    crawler_max_discovered: int = int(os.getenv("SEARCHSPHERE_CRAWLER_MAX_DISCOVERED", "1000"))  # queued URLs per job


settings = Settings()
