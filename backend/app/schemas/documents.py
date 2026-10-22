from datetime import date

from pydantic import BaseModel, Field, field_validator


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=200_000)
    category: str = Field(min_length=1, max_length=100)
    source_url: str | None = Field(default=None, max_length=2048)
    published_at: date | None = None

    @field_validator("title", "text", "category")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("source_url")
    @classmethod
    def _http_url(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return v


class DocumentSummary(BaseModel):
    id: int
    external_id: str | None
    title: str
    category: str
    source_type: str
    source_url: str | None
    published_at: str | None
    ingested_at: str
    word_count: int
    indexed: bool
    snippet: str
    file_type: str | None = None
    source_name: str | None = None
    updated_at: str | None = None
    metadata: dict | None = None


class DocumentDetail(DocumentSummary):
    text: str


class DocumentPage(BaseModel):
    items: list[DocumentSummary]
    total: int
    page: int
    page_size: int
    total_pages: int
