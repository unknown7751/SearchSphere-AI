"""A real in-memory inverted index.

Structures (all built by :meth:`InvertedIndex.add_document`):

* ``_postings``  term -> {doc_id: tf}          (the inverted index proper)
* ``_forward``   doc_id -> {term: tf}          (lets us delete a document and build
                                                document vectors without a corpus scan)
* ``_surface``   surface form -> {doc_ids}     (unstemmed dictionary used only by
                                                tolerant/wildcard retrieval, with
                                                ``_surface_term`` mapping each surface
                                                form to its index term)

The forward and surface maps are *derived* from the same ``add_document`` call and
are validated against the postings by :meth:`check_consistency`; the SQLite database
remains the source of truth and the whole structure can be rebuilt from it at any time.

Postings are exposed as sorted unique doc-id lists (needed for merge-based Boolean
operations); the vocabulary is exposed alphabetically sorted.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence


class DuplicateDocumentError(ValueError):
    pass


@dataclass(frozen=True)
class Posting:
    doc_id: int
    tf: int


class InvertedIndex:
    def __init__(self) -> None:
        self.version = 0
        self.clear()

    def clear(self) -> None:
        self._postings: dict[str, dict[int, int]] = {}
        self._forward: dict[int, dict[str, int]] = {}
        self._doc_length: dict[int, int] = {}
        self._surface: dict[str, set[int]] = {}
        self._surface_term: dict[str, str] = {}
        self._doc_surfaces: dict[int, set[str]] = {}
        self._sorted_vocab: list[str] | None = None
        self._sorted_surface: list[str] | None = None
        self._doc_id_cache: dict[str, list[int]] = {}
        self._all_ids_cache: list[int] | None = None
        self.version += 1

    # ------------------------------------------------------------------ updates
    def add_document(self, doc_id: int, terms: Sequence[str], surface_terms: Sequence[str] | None = None) -> None:
        """Index a document. ``terms`` are index terms; ``surface_terms`` (same length) the unstemmed forms."""
        if doc_id in self._forward:
            raise DuplicateDocumentError(f"Document {doc_id} is already indexed")
        surfaces = list(terms) if surface_terms is None else list(surface_terms)
        if len(surfaces) != len(terms):
            raise ValueError("surface_terms must be aligned with terms")
        pairs = dict(zip(surfaces, terms))
        for s, t in pairs.items():  # validate before mutating anything
            if self._surface_term.get(s, t) != t:
                raise ValueError(f"Surface form {s!r} maps to conflicting terms")

        counts = Counter(terms)
        for term, tf in counts.items():
            self._postings.setdefault(term, {})[doc_id] = tf
            self._doc_id_cache.pop(term, None)
        for s, t in pairs.items():
            self._surface.setdefault(s, set()).add(doc_id)
            self._surface_term[s] = t
        self._forward[doc_id] = dict(counts)
        self._doc_length[doc_id] = len(terms)
        self._doc_surfaces[doc_id] = set(pairs)
        self._touch()

    def remove_document(self, doc_id: int) -> bool:
        if doc_id not in self._forward:
            return False
        for term in self._forward.pop(doc_id):
            plist = self._postings[term]
            del plist[doc_id]
            if not plist:
                del self._postings[term]
            self._doc_id_cache.pop(term, None)
        for s in self._doc_surfaces.pop(doc_id):
            docs = self._surface[s]
            docs.discard(doc_id)
            if not docs:
                del self._surface[s]
                del self._surface_term[s]
        del self._doc_length[doc_id]
        self._touch()
        return True

    def _touch(self) -> None:
        self._sorted_vocab = None
        self._sorted_surface = None
        self._all_ids_cache = None
        self.version += 1

    # ------------------------------------------------------------------ lookups
    @property
    def num_docs(self) -> int:
        return len(self._forward)

    def has_document(self, doc_id: int) -> bool:
        return doc_id in self._forward

    def all_doc_ids(self) -> list[int]:
        if self._all_ids_cache is None:
            self._all_ids_cache = sorted(self._forward)
        return self._all_ids_cache

    def vocabulary(self) -> list[str]:
        if self._sorted_vocab is None:
            self._sorted_vocab = sorted(self._postings)
        return self._sorted_vocab

    def doc_ids(self, term: str) -> list[int]:
        """Sorted unique document IDs containing ``term`` (empty list if unknown)."""
        cached = self._doc_id_cache.get(term)
        if cached is None:
            cached = sorted(self._postings.get(term, ()))
            if term in self._postings:
                self._doc_id_cache[term] = cached
        return cached

    def postings(self, term: str) -> list[Posting]:
        plist = self._postings.get(term, {})
        return [Posting(d, plist[d]) for d in self.doc_ids(term)]

    def df(self, term: str) -> int:
        return len(self._postings.get(term, ()))

    def tf(self, term: str, doc_id: int) -> int:
        return self._postings.get(term, {}).get(doc_id, 0)

    def term_freqs(self, doc_id: int) -> dict[str, int]:
        return dict(self._forward.get(doc_id, {}))

    def doc_length(self, doc_id: int) -> int:
        return self._doc_length.get(doc_id, 0)

    # surface-form dictionary (used for prefix / wildcard retrieval)
    def surface_vocabulary(self) -> list[str]:
        if self._sorted_surface is None:
            self._sorted_surface = sorted(self._surface)
        return self._sorted_surface

    def surface_doc_ids(self, surface: str) -> list[int]:
        return sorted(self._surface.get(surface, ()))

    def surface_term(self, surface: str) -> str | None:
        return self._surface_term.get(surface)

    # ------------------------------------------------------------------ inspection
    def inspect(self, term: str) -> dict:
        return {
            "term": term,
            "document_frequency": self.df(term),
            "postings": [{"doc_id": p.doc_id, "tf": p.tf} for p in self.postings(term)],
        }

    def stats(self) -> dict:
        total_tokens = sum(self._doc_length.values())
        return {
            "num_documents": self.num_docs,
            "vocabulary_size": len(self._postings),
            "surface_vocabulary_size": len(self._surface),
            "total_postings": sum(len(p) for p in self._postings.values()),
            "total_tokens": total_tokens,
            "average_document_length": (total_tokens / self.num_docs) if self.num_docs else 0.0,
        }

    # ------------------------------------------------------------------ consistency
    def check_consistency(self) -> list[str]:
        """Return a list of human-readable problems (empty list means consistent)."""
        problems: list[str] = []
        vocab = self.vocabulary()
        if vocab != sorted(set(vocab)):
            problems.append("vocabulary is not sorted/unique")
        for term, plist in self._postings.items():
            if not plist:
                problems.append(f"term {term!r} has an empty postings list")
            ids = self.doc_ids(term)
            if ids != sorted(set(ids)) or len(ids) != len(plist):
                problems.append(f"postings of {term!r} are not sorted/unique")
            for d, tf in plist.items():
                if tf <= 0:
                    problems.append(f"term {term!r} doc {d} has non-positive tf {tf}")
                if d not in self._forward:
                    problems.append(f"term {term!r} references unknown doc {d}")
                elif self._forward[d].get(term) != tf:
                    problems.append(f"tf mismatch for term {term!r} doc {d}")
        for d, terms in self._forward.items():
            for term, tf in terms.items():
                if self._postings.get(term, {}).get(d) != tf:
                    problems.append(f"forward entry ({d}, {term!r}) missing from postings")
            if sum(terms.values()) != self._doc_length.get(d):
                problems.append(f"doc {d}: length does not equal sum of tf")
        for s, docs in self._surface.items():
            term = self._surface_term.get(s)
            if term is None:
                problems.append(f"surface {s!r} has no term mapping")
                continue
            for d in docs:
                if term not in self._forward.get(d, {}):
                    problems.append(f"surface {s!r} doc {d} lacks term {term!r}")
                if s not in self._doc_surfaces.get(d, ()):
                    problems.append(f"surface {s!r} doc {d} missing from document surface set")
        for d, surfaces in self._doc_surfaces.items():
            for s in surfaces:
                if d not in self._surface.get(s, ()):
                    problems.append(f"doc {d} surface {s!r} missing from surface dictionary")
        if set(self._doc_length) != set(self._forward) or set(self._doc_surfaces) != set(self._forward):
            problems.append("per-document maps disagree on the document set")
        return problems
