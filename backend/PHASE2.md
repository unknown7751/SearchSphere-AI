# Phase 2 – Advanced IR, Evaluation and Document Ingestion

Everything here sits on top of the Phase 1 TF-IDF vector space model
(`tf` = raw count, `idf = ln((N+1)/(df+1)) + 1`, cosine ranking). All algorithms are
implemented by hand with NumPy; no sklearn, no external services.

| Concern | Module |
|---|---|
| Query expansion | `app/services/query_expansion.py` |
| Rocchio maths | `app/services/rocchio.py` |
| Retrieval modes (expanded / Rocchio / uniform interface) | `app/services/advanced_retrieval.py` |
| Metrics (P, R, F1, P@K, R@K, AP, MAP) | `app/services/metrics.py` |
| Running a mode and scoring it | `app/services/evaluation.py` |
| Upload extraction (TXT / PDF) | `app/services/ingestion.py` |
| Evaluation dataset tables + loader | `app/database/evaluation.py`, `data/evaluation_queries.json` |

---

## 1. Query expansion

**Motivation.** "machine learning" misses a document that says "training a model" but never
repeats the typed words. We add terms that the *best-matching documents* talk about.

**Algorithm** (deterministic, no LLM, no thesaurus – every added term is evidence from the corpus):

1. Rank the corpus with the original query.
2. Take the top `feedback_docs` (default 5) documents as pseudo-relevant set `F`.
3. For each term `t` not already in the query:
   `score(t) = Σ_{d∈F} cos(q,d)·tfidf(t,d)/‖d‖  /  Σ_{d∈F} cos(q,d)` – the centroid of the
   length-normalised document vectors, weighted by how well each document matched.
4. Keep `t` only if `df(t) ≥ 2` and `t` occurs in at least 2 documents of `F` (a single document is not evidence).
5. The best `max_expansion_terms` (default 5) are the *expanded terms* (ties alphabetical).
6. Expanded query vector = original vector + `expansion_weight · idf(t)` (default 0.5) per added term.

The response keeps the three things separate:

```
Original Query:        machine learning
Expanded Terms:        training, model, speed, performance, examples
Final Expanded Query:  machine learning training model speed performance examples
```

Terms are stored as Porter stems; `InvertedIndex.display_form()` maps a stem back to the most
common surface word (and re-analysing that word gives the same stem).

## 2. Relevance feedback

The user marks some results relevant (and optionally some non-relevant); the system uses the
*vectors of those documents* to build a better query.

Workflow: search → judge results → `POST /api/workbench/relevance-feedback` → better query vector → re-rank.
Pseudo-relevance feedback (`pseudo_feedback_docs=N`) assumes the top N results are relevant, which needs no human.

## 3. Rocchio

```
q_m = α·q0  +  (β / |Dr|) · Σ_{d∈Dr} d  −  (γ / |Dnr|) · Σ_{d∈Dnr} d
```

| Symbol | Meaning |
|---|---|
| `q0` | original query vector (TF-IDF weights) |
| `Dr`, `Dnr` | relevant / non-relevant documents (their TF-IDF vectors) |
| `α` (1.0) | weight of the original query |
| `β` (0.75) | weight of the relevant-document centroid |
| `γ` (0.15) | weight of the non-relevant-document centroid |
| `q_m` | the modified query vector that is ranked by cosine similarity |

> **Rocchio is not "adding the relevant words to the query".** The query, the relevant and the
> non-relevant documents are all vectors in the *same* TF-IDF space. Rocchio moves the query
> vector towards the relevant centroid and away from the non-relevant one; the new vector is
> compared with every document by cosine similarity, and *that* changes the ranking.

Conventions (reported in every response):

* `normalize=true` (default): `q0` and each document vector are scaled to unit length first
  (textbook formulation) so a long document cannot dominate the centroid. `normalize=false`
  applies the raw TF-IDF vectors exactly as written above.
* Negative components of `q_m` are clipped to 0 (the unclipped value is returned as `before_clipping`).
* Empty `Dr` or `Dnr` contributes nothing (no division by zero); zero vectors are legal; duplicate IDs
  are removed; a document in both sets → `400 invalid_rocchio_input`; unknown IDs → `404`; negative
  α/β/γ → `422`.

Worked example (raw vectors): `q0={a:1,b:2}`, `Dr={a:2,c:4},{c:2}`, `Dnr={b:4,d:2}`:
`a = 1 + 0.75/2·2 = 1.75`, `b = 2 − 0.15·4 = 1.40`, `c = 0.75/2·6 = 2.25`, `d = −0.15·2 = −0.30 → 0`.

## 4. Evaluation

For a ranked list and a set of relevant documents (the *retrieved set* for P/R/F1 is the top `k`):

| Metric | Formula |
|---|---|
| Precision | relevant retrieved / retrieved |
| Recall | relevant retrieved / total relevant |
| F1 | 2·P·R / (P + R) |
| Precision@K | relevant in top K / K (a ranking shorter than K is penalised) |
| Recall@K | relevant in top K / total relevant |
| Average Precision | (Σ P@rank at each relevant document) / total relevant – over the whole ranking |
| MAP | (1/Q) Σ AP(q) |

Every zero denominator gives 0.0; `K ≤ 0` is rejected (`422` from the API).

Example: ranking D1..D5, relevant {D1,D3,D5}: `AP = (1/1 + 2/3 + 3/5) / 3 = 0.7556`.
With APs 0.7556, 0.5, 0: `MAP = (0.7556 + 0.5 + 0) / 3 = 0.4185`.

**Dataset.** `data/evaluation_queries.json` holds 10 queries with hand-made binary judgments
(44 judgments) written against the stable `external_id`s of the sample corpus
(`seed-030` …). `python -m app.cli seed-evaluation` (also part of `seed`) resolves them to
database IDs and stores them in `evaluation_queries` / `relevance_judgments` (idempotent;
judgments cascade-delete with their document). The corpus has no document on relational database
normalisation, so no such query is included.

**Retrieval modes** for evaluation: `tfidf`, `expanded`, `rocchio`, `boolean` (Boolean needs an
explicit expression such as `sorting AND algorithms`, and returns documents in ID order).
`rocchio` mode uses `feedback_relevant_doc_ids` if given, otherwise pseudo-relevance feedback from the
top 3 baseline results – never the evaluation judgments – so MAP is not inflated by label leakage.

## 5. Document ingestion

```
upload → validate type/size → extract text (PDF: page by page) → normalise → duplicate check
       → store row → preprocess → update inverted index (TF/DF) → searchable immediately
```

* Types: `.txt` (UTF-8/UTF-16/BOM/Windows-1252 decoding; binary data rejected) and `.pdf` (PyMuPDF;
  if it is not installed the API returns `501 pdf_support_unavailable`; encrypted, malformed or
  text-less/scanned PDFs return `400`).
* Limits: 5 MB per file (`SEARCHSPHERE_MAX_UPLOAD_BYTES`), 200,000 characters of extracted text
  (`SEARCHSPHERE_MAX_DOCUMENT_CHARS`).
* Duplicates: SHA-256 of the case/whitespace-normalised text → `409 duplicate_document`
  (the existing project rule for duplicate `source_url` is unchanged).
* Metadata columns added to `documents` (auto-migrated on start-up): `file_type`, `source_name`,
  `updated_at`, `content_hash`, `metadata_json` (PDF page count / title / author). `ingested_at` is the creation time.
* Uploads use the same `SearchEngine.add_document` path as every other document, so deletion
  (`DELETE /api/documents/{id}`) removes the document from the index, TF/DF and all search modes.

## 6. API summary

| Method & path | Purpose |
|---|---|
| `POST /api/documents/upload` | multipart TXT/PDF ingestion (`file`, optional `title`, `category`) |
| `POST /api/search/expanded` | ranked search with query expansion (adds an `expansion` block) |
| `POST /api/search/rocchio` | ranked search with a Rocchio vector (adds a `rocchio` block) |
| `POST /api/search` with `"explain": true` | now also lists `matching_terms` (tf, df, idf, tfidf, query weight, contribution) |
| `POST /api/workbench/query-expansion` | candidate table, expanded vector, ranking before/after |
| `POST /api/workbench/rocchio` | formula, per-term arithmetic, cosine breakdown, ranking with rank change |
| `POST /api/workbench/relevance-feedback` | vector breakdown + ranking before/after (needs ≥1 judged doc) |
| `POST /api/workbench/evaluation` | counts, per-rank P/R, substituted formulas, AP steps |
| `POST /api/evaluation/run` | P, R, F1, P@K, R@K, AP for one query (judgments from the request or the dataset) |
| `POST /api/evaluation/map` | per-query AP and MAP (supplied queries or the whole dataset) |
| `GET /api/evaluation/dataset` | stored evaluation queries and judgments |

Errors keep the Phase 1 shape `{"error": {"code", "message", "details"}}`; no stack traces are returned.
