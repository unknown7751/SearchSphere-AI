"""Text preprocessing pipeline shared by documents and queries.

Stages (each one is inspectable through :meth:`Preprocessor.analyze`):

1. Unicode normalisation (NFKC) + lowercasing
2. Punctuation removal (every non-word character becomes a space; repeated
   spaces collapse). Numbers and Unicode letters are kept.
3. Tokenisation (NLTK ``word_tokenize``)
4. Stop-word removal (NLTK English list)
5. Stemming (Porter)
6. Lemmatisation (WordNet; noun first, then verb if the noun lemma is unchanged)

``PreprocessConfig.index_form`` chooses which of stem/lemma is stored in the
inverted index. The *same* configuration is applied to documents and queries.

NLTK resources are never downloaded here; run ``python scripts/setup_nltk.py``.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer, WordNetLemmatizer
from nltk.tokenize import word_tokenize

from app.core.config import settings

nltk.data.path.insert(0, str(settings.nltk_data_dir))

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


class NLPResourceError(RuntimeError):
    """Raised when required NLTK data is missing."""


@dataclass(frozen=True)
class PreprocessConfig:
    index_form: str = "stem"  # "stem" or "lemma"
    remove_stopwords: bool = True

    def __post_init__(self):
        if self.index_form not in ("stem", "lemma"):
            raise ValueError("index_form must be 'stem' or 'lemma'")


@dataclass
class PreprocessResult:
    original: str
    normalized: str
    tokens: list[str]
    stop_words_removed: list[str]
    tokens_without_stopwords: list[str]
    stemmed_tokens: list[str]
    lemmatized_tokens: list[str]
    index_terms: list[str] = field(default_factory=list)  # what goes into the inverted index

    @property
    def surface_terms(self) -> list[str]:
        """Normalised, stop-word-free tokens before stemming (aligned with index_terms)."""
        return self.tokens_without_stopwords


class Preprocessor:
    def __init__(self, config: PreprocessConfig | None = None):
        self.config = config or PreprocessConfig()
        self._stemmer = PorterStemmer()
        self._lemmatizer = WordNetLemmatizer()
        self._stem_cache: dict[str, str] = {}
        self._lemma_cache: dict[str, str] = {}
        try:
            self._stopwords = frozenset(stopwords.words("english"))
            self._lemmatizer.lemmatize("tests")
            word_tokenize("resource check", preserve_line=True)
        except LookupError as exc:
            raise NLPResourceError(
                "Required NLTK resources are missing. Run: python scripts/setup_nltk.py"
            ) from exc

    # -- individual stages -------------------------------------------------
    @staticmethod
    def normalize(text: str) -> str:
        text = unicodedata.normalize("NFKC", text or "").lower()
        return _NON_WORD.sub(" ", text).strip()

    def tokenize(self, text: str) -> list[str]:
        normalized = self.normalize(text)
        if not normalized:
            return []
        return [t for t in word_tokenize(normalized, preserve_line=True) if _NON_WORD.sub("", t)]

    def is_stopword(self, token: str) -> bool:
        return token in self._stopwords

    def stem(self, token: str) -> str:
        if token not in self._stem_cache:
            self._stem_cache[token] = self._stemmer.stem(token)
        return self._stem_cache[token]

    def lemmatize(self, token: str) -> str:
        if token not in self._lemma_cache:
            lemma = self._lemmatizer.lemmatize(token, "n")
            if lemma == token:
                lemma = self._lemmatizer.lemmatize(token, "v")
            self._lemma_cache[token] = lemma
        return self._lemma_cache[token]

    # -- full pipeline -----------------------------------------------------
    def analyze(self, text: str) -> PreprocessResult:
        original = text or ""
        normalized = self.normalize(original)
        tokens = self.tokenize(original)
        if self.config.remove_stopwords:
            kept = [t for t in tokens if t not in self._stopwords]
            removed = [t for t in tokens if t in self._stopwords]
        else:
            kept, removed = list(tokens), []
        stemmed = [self.stem(t) for t in kept]
        lemmatized = [self.lemmatize(t) for t in kept]
        index_terms = stemmed if self.config.index_form == "stem" else lemmatized
        return PreprocessResult(original, normalized, tokens, removed, kept, stemmed, lemmatized, list(index_terms))

    def index_terms(self, text: str) -> list[str]:
        return self.analyze(text).index_terms
