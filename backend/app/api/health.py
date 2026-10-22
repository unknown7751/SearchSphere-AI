import sqlite3

from fastapi import APIRouter, Depends

from app.api.deps import get_conn, get_engine
from app.core.config import settings
from app.database import repository as repo
from app.services.search_engine import SearchEngine

router = APIRouter(tags=["health"])


@router.get("/health")
def health(engine: SearchEngine = Depends(get_engine), conn: sqlite3.Connection = Depends(get_conn)):
    stats = engine.index.stats()
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "documents": repo.count_documents(conn),
        "indexed_documents": stats["num_documents"],
        "vocabulary_size": stats["vocabulary_size"],
    }
