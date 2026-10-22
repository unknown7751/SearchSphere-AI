import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.inverted_index import InvertedIndex
from app.services.preprocessing import Preprocessor

# A tiny hand-checkable corpus of already-normalised terms (no NLTK involved).
#   doc 1: machine x2, learning            doc 4: java, programming, python
#   doc 2: machine, hardware               doc 5: security
#   doc 3: python, programming             doc 6: learning, python
SMALL_CORPUS = {
    1: ["machine", "learning", "machine"],
    2: ["machine", "hardware"],
    3: ["python", "programming"],
    4: ["java", "programming", "python"],
    5: ["security"],
    6: ["learning", "python"],
}


def build_index(corpus: dict[int, list[str]] = SMALL_CORPUS) -> InvertedIndex:
    index = InvertedIndex()
    for doc_id, terms in corpus.items():
        index.add_document(doc_id, terms)
    return index


@pytest.fixture
def small_index() -> InvertedIndex:
    return build_index()


@pytest.fixture(scope="session")
def preprocessor() -> Preprocessor:
    return Preprocessor()


API_DOCS = [
    ("Python Programming", "Python is a programming language for data analysis.", "Programming"),
    ("Java Programming", "Java is a programming language running on the virtual machine.", "Programming"),
    ("Machine Learning", "Machine learning algorithms learn patterns from data.", "AI/ML"),
    ("Computer Hardware", "Computer hardware includes the processor and memory. Every machine needs hardware.", "Computer Science"),
    ("Network Security", "Network security protects computers against attacks.", "Cybersecurity"),
]


@pytest.fixture
def api_settings(tmp_path) -> Settings:
    return Settings(database_path=tmp_path / "test.db")


@pytest.fixture
def client(api_settings):
    """TestClient over a fresh temporary SQLite DB holding API_DOCS as documents 1..5."""
    with TestClient(create_app(api_settings)) as c:
        for title, text, category in API_DOCS:
            r = c.post("/api/documents", json={"title": title, "text": text, "category": category})
            assert r.status_code == 201, r.text
        yield c
