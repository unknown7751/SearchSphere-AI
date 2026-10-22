import sqlite3

from fastapi import APIRouter, Depends

from app.api.deps import get_conn, get_engine
from app.services.search_engine import SearchEngine

router = APIRouter(prefix="/index", tags=["index"])


@router.post("/rebuild")
def rebuild_index(engine: SearchEngine = Depends(get_engine), conn: sqlite3.Connection = Depends(get_conn)):
    """Rebuild the inverted index from the documents stored in SQLite."""
    stats = engine.rebuild(conn)
    return {"status": "rebuilt", "stats": stats}


@router.get("/check")
def check_index(engine: SearchEngine = Depends(get_engine), conn: sqlite3.Connection = Depends(get_conn)):
    """Run the index consistency checks (internal structure and agreement with the database)."""
    return engine.check(conn)
