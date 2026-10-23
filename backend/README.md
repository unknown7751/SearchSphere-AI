# SearchSphere AI – backend (Phase 1: core IR engine, Phase 2: advanced IR + evaluation + ingestion, Phase 3: secure web crawler)

FastAPI + SQLite + NLTK + NumPy (+ PyMuPDF for PDF upload, Requests + BeautifulSoup for the crawler). No API keys, cloud services, GPUs or Docker.
Phase 2 algorithms (query expansion, Rocchio, evaluation metrics, ingestion) are documented in [PHASE2.md](PHASE2.md).
The web crawler (architecture, security model, limits, limitations) is documented in [PHASE3.md](PHASE3.md).

## Setup (Windows PowerShell, from `backend/`)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts\setup_nltk.py     # one-time NLTK data download (stored in data/nltk_data)
.\.venv\Scripts\python -m app.cli seed           # create SQLite DB, load 114 demo docs + evaluation dataset, build index
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Interactive API docs: <http://localhost:8000/docs>

The Next.js frontend (Phase 4) lives in `../frontend`; see [../frontend/README.md](../frontend/README.md). It needs this API running on port 8000.

## Maintenance commands

| Command | Purpose |
|---|---|
| `python -m app.cli init-db` | create the schema (idempotent) |
| `python -m app.cli seed` | load/update sample documents and the evaluation dataset (idempotent) and rebuild the index |
| `python -m app.cli seed-evaluation` | load evaluation queries + relevance judgments only |
| `python -m app.cli rebuild-index` | rebuild the inverted index from SQLite |
| `python -m app.cli check-index` | run index consistency checks |
| `python -m app.cli stats` | corpus / index statistics |
| `python -m pytest` | run all tests |

The seed documents in `data/seed_documents.json` are **sample/demo content written
locally**; they are not excerpts of real papers and contain no real citations.

## Configuration

Optional environment variables are listed in `.env.example` (database path, NLTK data
directory, CORS origins, wildcard expansion limit, upload size and text-length limits, crawler user agent / delay / size / duration limits). Nothing secret is required.
