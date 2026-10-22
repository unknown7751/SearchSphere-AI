# SearchSphere AI – backend (Phase 1: core IR engine)

FastAPI + SQLite + NLTK + NumPy. No API keys, cloud services, GPUs or Docker.

## Setup (Windows PowerShell, from `backend/`)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts\setup_nltk.py     # one-time NLTK data download (stored in data/nltk_data)
.\.venv\Scripts\python -m app.cli seed           # create SQLite DB, load 114 demo docs, build index
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Interactive API docs: <http://localhost:8000/docs>

## Maintenance commands

| Command | Purpose |
|---|---|
| `python -m app.cli init-db` | create the schema (idempotent) |
| `python -m app.cli seed` | load/update sample documents (idempotent) and rebuild the index |
| `python -m app.cli rebuild-index` | rebuild the inverted index from SQLite |
| `python -m app.cli check-index` | run index consistency checks |
| `python -m app.cli stats` | corpus / index statistics |
| `python -m pytest` | run all tests |

The seed documents in `data/seed_documents.json` are **sample/demo content written
locally**; they are not excerpts of real papers and contain no real citations.

## Configuration

Optional environment variables are listed in `.env.example` (database path, NLTK data
directory, CORS origins, wildcard expansion limit). Nothing secret is required.
