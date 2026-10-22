"""Command-line maintenance tasks.

    python -m app.cli init-db         create the SQLite schema (idempotent)
    python -m app.cli seed            load the sample corpus (idempotent) and rebuild the index
    python -m app.cli seed-evaluation load evaluation queries + relevance judgments (idempotent)
    python -m app.cli rebuild-index   rebuild the inverted index from the database
    python -m app.cli check-index     verify index consistency (exit code 1 on problems)
    python -m app.cli stats           print corpus and index statistics
"""
from __future__ import annotations

import argparse
import json
import sys

from app.core.config import settings
from app.database import repository as repo
from app.database.connection import connect
from app.database.evaluation import seed_evaluation
from app.database.schema import init_db
from app.database.seed import seed_database
from app.services.search_engine import SearchEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("command", choices=["init-db", "seed", "seed-evaluation", "rebuild-index", "check-index", "stats"])
    args = parser.parse_args(argv)

    conn = connect(settings.database_path)
    try:
        init_db(conn)
        if args.command == "init-db":
            print("Database initialised.")
            return 0

        if args.command == "seed":
            print("Seed:", json.dumps(seed_database(conn)))
            print("Evaluation:", json.dumps(seed_evaluation(conn)))

        if args.command == "seed-evaluation":
            print("Evaluation:", json.dumps(seed_evaluation(conn)))
            return 0

        engine = SearchEngine(wildcard_limit=settings.wildcard_expansion_limit)
        if args.command in ("seed", "rebuild-index"):
            print("Index:", json.dumps(engine.rebuild(conn)))
            return 0

        engine.rebuild(conn)  # check-index / stats operate on a fresh build of the DB contents
        result = engine.check(conn)
        if args.command == "check-index":
            print(json.dumps(result, indent=2))
            return 0 if result["consistent"] else 1
        print(json.dumps({"documents": repo.count_documents(conn), "categories": repo.category_counts(conn), "index": result["stats"]}, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
