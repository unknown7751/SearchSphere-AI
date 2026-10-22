import sqlite3
from typing import Iterator

from fastapi import Request

from app.database.connection import connect
from app.services.search_engine import SearchEngine


def get_engine(request: Request) -> SearchEngine:
    return request.app.state.engine


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(request.app.state.settings.database_path)
    try:
        yield conn
    finally:
        conn.close()


def make_snippet(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
