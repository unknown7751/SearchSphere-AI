"""Phase 2 request / response models: expansion, Rocchio, evaluation, ingestion."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.search import SearchRequest, SearchResponse, _strip_nonblank

DocId = Annotated[int, Field(ge=1)]
Mode = Literal["tfidf", "expanded", "rocchio", "boolean"]


# ------------------------------------------------------------------ shared request pieces
class RocchioParams(BaseModel):
    alpha: float = Field(default=1.0, ge=0, le=10, description="Weight of the original query vector")
    beta: float = Field(default=0.75, ge=0, le=10, description="Weight of the relevant-document centroid")
    gamma: float = Field(default=0.15, ge=0, le=10, description="Weight of the non-relevant-document centroid")
    normalize: bool = Field(default=True, description="L2-normalise q0 and the document vectors before combining")


class FeedbackSets(BaseModel):
    relevant_doc_ids: list[DocId] = Field(default_factory=list, max_length=100)
    non_relevant_doc_ids: list[DocId] = Field(default_factory=list, max_length=100)


class ExpansionParams(BaseModel):
    feedback_docs: int = Field(default=5, ge=1, le=20, description="Top-ranked documents mined for expansion terms")
    max_expansion_terms: int = Field(default=5, ge=1, le=20)
    expansion_weight: float = Field(default=0.5, gt=0, le=5, description="Weight of an added term relative to a typed term")


# ------------------------------------------------------------------ search modes
class ExpansionTermOut(BaseModel):
    term: str
    display: str
    score: float
    support: int
    document_frequency: int
    idf: float
    selected: bool


class ExpansionOut(BaseModel):
    original_query: str
    original_terms: list[str]
    feedback_doc_ids: list[int]
    expanded_terms: list[ExpansionTermOut]
    final_expanded_query: str
    expansion_weight: float
    expanded_query_vector: dict[str, float]
    message: str | None = None


class ExpandedSearchRequest(SearchRequest, ExpansionParams):
    pass


class ExpandedSearchResponse(SearchResponse):
    expansion: ExpansionOut


class RocchioSummaryOut(BaseModel):
    original_query: str
    alpha: float
    beta: float
    gamma: float
    normalized: bool
    relevant_documents: list[int]
    non_relevant_documents: list[int]
    pseudo_feedback: bool
    top_positive_terms: list[dict]
    top_negative_terms: list[dict]
    updated_query_terms: list[str]
    updated_query_vector: dict[str, float]


class RocchioSearchRequest(SearchRequest, RocchioParams, FeedbackSets):
    pseudo_feedback_docs: int = Field(
        default=0, ge=0, le=20, description="With no relevant IDs, treat the top-N baseline results as relevant"
    )


class RocchioSearchResponse(SearchResponse):
    rocchio: RocchioSummaryOut


# ------------------------------------------------------------------ workbench: expansion / rocchio / feedback
class QueryExpansionRequest(ExpansionParams):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)

    _q = field_validator("query")(_strip_nonblank)


class RocchioRequest(RocchioParams, FeedbackSets):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)
    vector_terms: int = Field(default=15, ge=1, le=100, description="How many vector components to return")
    pseudo_feedback_docs: int = Field(default=0, ge=0, le=20)

    _q = field_validator("query")(_strip_nonblank)


class RelevanceFeedbackRequest(RocchioRequest):
    pass


# ------------------------------------------------------------------ evaluation
class RetrievalOptionsIn(RocchioParams):
    mode: Mode = "tfidf"
    top_k: int = Field(default=10, ge=1, le=100)
    pseudo_feedback_docs: int = Field(
        default=3, ge=0, le=20, description="Rocchio mode: top-N baseline results used as pseudo-relevant feedback"
    )


class EvaluationRunRequest(RetrievalOptionsIn):
    query: str = Field(min_length=1, max_length=500)
    relevant_doc_ids: list[DocId] | None = Field(
        default=None, max_length=500, description="Judged relevant IDs; omit to use the stored dataset judgments"
    )
    feedback_relevant_doc_ids: list[DocId] = Field(default_factory=list, max_length=100)
    feedback_non_relevant_doc_ids: list[DocId] = Field(default_factory=list, max_length=100)

    _q = field_validator("query")(_strip_nonblank)


class JudgedQuery(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    relevant_doc_ids: list[DocId] = Field(min_length=1, max_length=500)

    _q = field_validator("query")(_strip_nonblank)


class EvaluationMapRequest(RetrievalOptionsIn):
    queries: list[JudgedQuery] | None = Field(
        default=None, min_length=1, max_length=50, description="Omit to evaluate every query of the stored dataset"
    )


class EvaluationMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    precision_at_k: float
    recall_at_k: float
    average_precision: float


class EvaluationRunResponse(EvaluationMetrics):
    query: str
    mode: str
    top_k: int
    relevance_source: Literal["request", "dataset"]
    relevant_doc_ids: list[int]
    retrieved_doc_ids: list[int]
    relevant_retrieved_doc_ids: list[int]
    total_ranked: int
    took_ms: float


class PerQueryEvaluation(EvaluationMetrics):
    query: str
    relevance_source: Literal["request", "dataset"]
    relevant_doc_ids: list[int]
    retrieved_doc_ids: list[int]
    relevant_retrieved_doc_ids: list[int]
    total_ranked: int
    ap_steps: list[dict]


class EvaluationMapResponse(BaseModel):
    mode: str
    top_k: int
    query_count: int
    mean_average_precision: float
    mean_precision_at_k: float
    mean_recall_at_k: float
    map_calculation: str
    formula: str
    per_query: list[PerQueryEvaluation]
    took_ms: float


class DatasetQueryOut(BaseModel):
    id: int
    query: str
    description: str | None
    relevant_doc_ids: list[int]


class EvaluationDatasetResponse(BaseModel):
    query_count: int
    queries: list[DatasetQueryOut]


# ------------------------------------------------------------------ ingestion
class UploadResponse(BaseModel):
    document_id: int
    title: str
    file_type: str
    category: str
    source_name: str
    word_count: int
    token_count: int
    indexed: bool
    created_at: str
    metadata: dict = Field(default_factory=dict)
    location: str

