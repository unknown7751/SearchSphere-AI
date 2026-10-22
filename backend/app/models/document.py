from dataclasses import dataclass

SOURCE_TYPES = ("seed", "user", "crawled")


@dataclass
class Document:
    id: int
    external_id: str | None
    title: str
    text: str
    category: str
    source_type: str
    source_url: str | None
    published_at: str | None
    ingested_at: str
    word_count: int
    indexed: bool
    file_type: str | None = None
    source_name: str | None = None
    updated_at: str | None = None
    content_hash: str | None = None
    metadata_json: str | None = None
