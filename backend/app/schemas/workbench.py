from pydantic import BaseModel, Field, field_validator


class PreprocessRequest(BaseModel):
    text: str = Field(max_length=50_000)


class PreprocessResponse(BaseModel):
    original: str
    normalized: str
    tokens: list[str]
    stop_words_removed: list[str]
    tokens_without_stopwords: list[str]
    stemmed_tokens: list[str]
    lemmatized_tokens: list[str]
    index_terms: list[str]
    index_form: str


class IncidenceMatrixRequest(BaseModel):
    terms: list[str] = Field(min_length=1, max_length=50)
    document_ids: list[int] | None = Field(default=None, max_length=50)

    @field_validator("terms")
    @classmethod
    def _terms(cls, v: list[str]) -> list[str]:
        v = [t.strip() for t in v]
        if any(not t or len(t) > 100 for t in v):
            raise ValueError("terms must be non-empty and at most 100 characters")
        return v


class IncidenceTermRow(BaseModel):
    term: str
    index_terms: list[str]
    document_frequency: int
    row: list[int]


class IncidenceDocument(BaseModel):
    doc_id: int
    title: str


class IncidenceMatrixResponse(BaseModel):
    documents: list[IncidenceDocument]
    rows: list[IncidenceTermRow]
    ignored_terms: list[str]


class PostingOut(BaseModel):
    doc_id: int
    tf: int
    title: str | None = None


class InvertedIndexTermResponse(BaseModel):
    query: str
    term: str
    document_frequency: int
    postings: list[PostingOut]
    stats: dict


class VocabularyEntry(BaseModel):
    term: str
    document_frequency: int


class InvertedIndexListResponse(BaseModel):
    prefix: str | None
    terms: list[VocabularyEntry]
    total_terms: int
    page: int
    page_size: int
    stats: dict


class TfidfRequest(BaseModel):
    document_ids: list[int] = Field(min_length=1, max_length=20)
    query: str | None = Field(default=None, max_length=500)
    top_n: int = Field(default=10, ge=1, le=50)


class TermWeight(BaseModel):
    term: str
    tf: int
    df: int
    idf: float
    tfidf: float


class TfidfDocument(BaseModel):
    doc_id: int
    title: str
    vector_size: int
    top_terms: list[TermWeight]
    query_term_weights: list[TermWeight]


class TfidfResponse(BaseModel):
    num_documents: int
    formulas: dict[str, str]
    query_terms: list[TermWeight] | None
    unknown_terms: list[str]
    documents: list[TfidfDocument]


class CosineRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    document_ids: list[int] | None = Field(default=None, max_length=50)
    top_k: int = Field(default=5, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def _q(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class CosineDocument(BaseModel):
    rank: int
    doc_id: int
    title: str
    dot_product: float
    query_norm: float
    document_norm: float
    cosine: float
    term_contributions: dict[str, float]
    document_vector_shared_terms: dict[str, float]


class CosineResponse(BaseModel):
    query_terms: list[str]
    query_vector: dict[str, float]
    unknown_terms: list[str]
    formula: str
    documents: list[CosineDocument]
    took_ms: float
