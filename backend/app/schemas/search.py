from pydantic import BaseModel, Field, field_validator


def _strip_nonblank(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("must not be blank")
    return v


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    category: str | None = Field(default=None, max_length=100)
    explain: bool = Field(default=False, description="Include dot product, norms and per-term contributions")

    _q = field_validator("query")(_strip_nonblank)


class QueryAnalysis(BaseModel):
    original: str
    normalized: str
    tokens: list[str]
    stop_words_removed: list[str]
    index_terms: list[str]
    unknown_terms: list[str]


class MatchingTerm(BaseModel):
    """One query term found in a result document, with the quantities behind its score."""

    term: str
    word: str  # readable form of the index term
    tf: int
    df: int
    idf: float
    tfidf: float  # tf * idf: the term's weight in the document vector
    query_weight: float
    contribution: float  # query_weight * tfidf: the term's share of the dot product


class ScoreExplanation(BaseModel):
    dot_product: float
    query_norm: float
    document_norm: float
    term_contributions: dict[str, float]
    matching_terms: list[MatchingTerm] = []


class SearchResultItem(BaseModel):
    rank: int
    doc_id: int
    title: str
    category: str
    snippet: str
    score: float
    explanation: ScoreExplanation | None = None


class SearchResponse(BaseModel):
    query: QueryAnalysis
    query_vector: dict[str, float]
    results: list[SearchResultItem]
    total_results: int
    page: int
    page_size: int
    took_ms: float
    message: str | None = None


class BooleanSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    _q = field_validator("query")(_strip_nonblank)


class BooleanStep(BaseModel):
    step: int
    operation: str
    description: str
    result_size: int


class BooleanDocument(BaseModel):
    doc_id: int
    title: str
    category: str


class BooleanSearchResponse(BaseModel):
    query: str
    parsed_expression: str
    ast: dict
    index_terms: dict[str, list[str]]
    unknown_terms: list[str]
    matching_doc_ids: list[int]
    results: list[BooleanDocument]
    total_results: int
    page: int
    page_size: int
    steps: list[BooleanStep]
    took_ms: float


class TolerantSearchRequest(BaseModel):
    pattern: str = Field(min_length=1, max_length=100, description="One word; '*' matches zero or more characters")
    max_expansions: int | None = Field(default=None, ge=1, le=500)
    include_documents: bool = True

    _p = field_validator("pattern")(_strip_nonblank)


class MatchedTermOut(BaseModel):
    term: str
    index_term: str
    document_count: int
    doc_ids: list[int]


class TolerantSearchResponse(BaseModel):
    pattern: str
    kind: str
    strategy: str
    matched_term_count: int
    total_matches: int
    expansion_limit: int
    truncated: bool
    matched_terms: list[MatchedTermOut]
    documents: list[BooleanDocument]
    total_documents: int
    took_ms: float
    message: str | None = None


class Suggestion(BaseModel):
    term: str
    document_count: int


class SuggestionsResponse(BaseModel):
    prefix: str
    suggestions: list[Suggestion]
