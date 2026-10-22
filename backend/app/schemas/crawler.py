from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Hard caps: a request can lower these but never exceed them.
MAX_PAGES_LIMIT = 100
MAX_DEPTH_LIMIT = 5
MAX_TIMEOUT_LIMIT = 30.0

JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
ResultStatus = Literal[
    "indexed", "updated", "unchanged", "duplicate_content", "blocked_by_robots", "blocked_by_security", "skipped", "failed"
]
Access = Literal["allowed", "blocked_by_robots", "blocked_by_security", "failed"]


class _Strict(BaseModel):
    # Unknown fields are errors: there is no `ignore_robots`-style switch to smuggle in.
    model_config = ConfigDict(extra="forbid")


class CrawlStartRequest(_Strict):
    url: str = Field(min_length=1, max_length=2048, description="Seed URL (http or https)")
    max_pages: int = Field(default=10, ge=1, le=MAX_PAGES_LIMIT, description="Maximum number of pages to fetch")
    max_depth: int = Field(default=2, ge=0, le=MAX_DEPTH_LIMIT, description="Link hops from the seed (0 = seed only)")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=MAX_TIMEOUT_LIMIT, description="Per-request timeout")
    include_subdomains: bool = Field(default=False, description="Also follow subdomains of the seed host")
    category: str = Field(default="Crawled", min_length=1, max_length=100)

    @field_validator("url", "category")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class ValidateUrlRequest(_Strict):
    url: str = Field(min_length=1, max_length=4096)


class ValidateUrlResponse(BaseModel):
    url: str
    normalized_url: str | None
    allowed: bool
    status: Literal["allowed", "blocked_by_security", "invalid"]
    reason: str | None = None  # stable code, e.g. "private_address"
    message: str | None = None


class CrawlError(BaseModel):
    url: str
    status: str
    access: str
    http_status: int | None = None
    error: str


class CrawlJob(BaseModel):
    job_id: int
    seed_url: str
    status: JobStatus
    max_pages: int
    max_depth: int
    timeout_seconds: float
    include_subdomains: bool
    category: str
    pages_discovered: int
    pages_crawled: int
    pages_failed: int
    pages_blocked: int
    pages_skipped: int
    progress: float = Field(description="processed URLs / discovered URLs (1.0 once the job has ended)")
    cancel_requested: bool
    stop_reason: str | None = None
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class CrawlJobDetail(CrawlJob):
    error_count: int
    recent_errors: list[CrawlError]


class CrawlHistory(BaseModel):
    items: list[CrawlJob]
    total: int
    page: int
    page_size: int


class CrawlResultItem(BaseModel):
    url: str
    final_url: str | None
    title: str | None
    status: ResultStatus
    access: Access
    depth: int
    http_status: int | None
    content_type: str | None
    content_length: int | None
    document_id: int | None
    indexed: bool
    error: str | None
    crawled_at: str


class CrawlResultsPage(BaseModel):
    job_id: int
    items: list[CrawlResultItem]
    total: int
    page: int
    page_size: int
