"""Tolerant retrieval: prefix and wildcard lookup over the dictionary.

``*`` means "zero or more characters". The dictionary searched is the *surface*
vocabulary (normalised, unstemmed words such as ``computer``) so that patterns like
``comput*r`` behave as users expect; every matched word is mapped back to its index
term, and the documents returned are the ones that actually contain that exact word.

Lookup strategies (the difference matters in a viva):

* prefix   ``mach*``      one trailing ``*``. The sorted dictionary lets us binary-search
                          the range of words starting with ``mach`` -> O(log V + k).
* wildcard ``comput*r``   any other ``*`` placement. We still binary-search the range of
                          the literal prefix (``comput``) when there is one, then filter
                          that range with the full pattern. A leading ``*`` (``*ing``) has
                          no prefix to narrow on, so the whole dictionary is scanned
                          -> O(V). (Permuterm / k-gram indexes remove that scan; not
                          needed at this corpus size.)
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass, field

from app.services.inverted_index import InvertedIndex

_VALID_PATTERN = re.compile(r"^(?:[^\W_]|\*)+$", re.UNICODE)


class PatternError(ValueError):
    pass


@dataclass
class MatchedTerm:
    term: str  # dictionary word that matched
    index_term: str  # its stem/lemma as stored in the inverted index
    doc_ids: list[int]


@dataclass
class TolerantResult:
    pattern: str
    kind: str  # exact | prefix | wildcard
    strategy: str
    matched_terms: list[MatchedTerm]
    total_matches: int  # before the expansion limit
    truncated: bool
    doc_ids: list[int] = field(default_factory=list)


def normalize_pattern(pattern: str) -> str:
    pattern = unicodedata.normalize("NFKC", pattern or "").lower().strip()
    if not pattern:
        raise PatternError("Pattern is empty.")
    if not _VALID_PATTERN.match(pattern):
        raise PatternError("Pattern must be a single word containing letters, digits and '*' only.")
    if not pattern.replace("*", ""):
        raise PatternError("Pattern must contain at least one literal character.")
    return re.sub(r"\*+", "*", pattern)


class TolerantRetriever:
    def __init__(self, index: InvertedIndex, default_limit: int = 50):
        self.index = index
        self.default_limit = default_limit

    def _prefix_range(self, vocab: list[str], prefix: str) -> list[str]:
        lo = bisect.bisect_left(vocab, prefix)
        hi = bisect.bisect_left(vocab, prefix + "\U0010ffff")
        return vocab[lo:hi]

    def expand(self, pattern: str) -> tuple[str, str, str, list[str]]:
        """Return (normalised pattern, kind, strategy, matching dictionary words alphabetically)."""
        pattern = normalize_pattern(pattern)
        vocab = self.index.surface_vocabulary()
        if "*" not in pattern:
            found = [pattern] if self.index.surface_term(pattern) is not None else []
            return pattern, "exact", "dictionary lookup", found
        prefix, _, _ = pattern.partition("*")
        if pattern == prefix + "*":
            return pattern, "prefix", "binary search of sorted dictionary", self._prefix_range(vocab, prefix)
        regex = re.compile("^" + ".*".join(re.escape(p) for p in pattern.split("*")) + "$")
        if prefix:
            candidates, strategy = self._prefix_range(vocab, prefix), "binary search on literal prefix, then pattern filter"
        else:
            candidates, strategy = vocab, "full dictionary scan (leading wildcard)"
        return pattern, "wildcard", strategy, [w for w in candidates if regex.match(w)]

    def search(self, pattern: str, max_expansions: int | None = None) -> TolerantResult:
        limit = max_expansions or self.default_limit
        pattern, kind, strategy, words = self.expand(pattern)
        ranked = sorted(words, key=lambda w: (-len(self.index.surface_doc_ids(w)), w))
        kept = ranked[:limit]
        matched = [
            MatchedTerm(w, self.index.surface_term(w) or w, self.index.surface_doc_ids(w)) for w in kept
        ]
        doc_ids: set[int] = set()
        for m in matched:
            doc_ids.update(m.doc_ids)
        return TolerantResult(
            pattern=pattern,
            kind=kind,
            strategy=strategy,
            matched_terms=matched,
            total_matches=len(words),
            truncated=len(words) > len(kept),
            doc_ids=sorted(doc_ids),
        )

    def suggest(self, prefix: str, limit: int = 8) -> list[tuple[str, int]]:
        """Autocomplete: dictionary words starting with ``prefix`` as (word, doc count), most frequent first."""
        prefix = _last_word(prefix)
        if not prefix:
            return []
        words = self._prefix_range(self.index.surface_vocabulary(), prefix)
        scored = [(w, len(self.index.surface_doc_ids(w))) for w in words]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:limit]


def _last_word(text: str) -> str:
    """Lowercase/NFKC the last (possibly partial) word of ``text`` without stop-word removal or stemming."""
    words = unicodedata.normalize("NFKC", text or "").lower().split()
    return re.sub(r"[\W_]", "", words[-1]) if words else ""
