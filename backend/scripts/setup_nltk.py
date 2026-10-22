"""Download the NLTK resources SearchSphere AI needs (run once, explicitly).

The application never downloads anything at startup. Resources are stored in
``backend/data/nltk_data`` (git-ignored) so setup is reproducible and local.

Usage (from backend/):  python scripts/setup_nltk.py
"""
import sys
from pathlib import Path

import nltk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402

# word_tokenize(preserve_line=True) is used, so the punkt sentence model is not needed.
RESOURCES = ["stopwords", "wordnet", "omw-1.4"]


def main() -> int:
    target = settings.nltk_data_dir
    target.mkdir(parents=True, exist_ok=True)
    ok = True
    for res in RESOURCES:
        print(f"Downloading {res} ...")
        ok &= bool(nltk.download(res, download_dir=str(target), quiet=True))
    print("NLTK resources ready." if ok else "Some NLTK downloads FAILED.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
