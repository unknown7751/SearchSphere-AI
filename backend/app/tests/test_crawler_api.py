"""Crawler HTTP API + the crawl -> store -> preprocess -> index -> search integration."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.database import crawl as crawl_db
from app.database.connection import connect
from app.main import create_app
from app.tests.crawler_fakes import FakeFetcher, FakeResolver, Page, html

SITE = "https://docs.test"


def site() -> dict:
    return {
        f"{SITE}/": Page(html("Search Handbook", "<p>Welcome to the handbook.</p><a href='/index'>index</a><a href='/rank'>rank</a><a href='/gone'>gone</a>")),
        f"{SITE}/index": Page(html("Inverted Index", "<p>The inverted index stores posting lists for every vocabulary term.</p>")),
        f"{SITE}/rank": Page(html("Ranking Models", "<p>Okapi saturation and cosine similarity rank candidates.</p>")),
    }


@pytest.fixture
def fetcher():
    return FakeFetcher(site())


@pytest.fixture
def resolver():
    return FakeResolver({"intranet.docs.test": ["10.9.9.9"], "evil.test": ["169.254.169.254"]})


@pytest.fixture
def cclient(tmp_path, fetcher, resolver):
    settings = Settings(database_path=tmp_path / "api.db", crawler_request_delay=0.0)
    with TestClient(create_app(settings, crawler_fetcher=fetcher, crawler_resolver=resolver, crawler_sleep=lambda s: None)) as c:
        yield c


def start(client, **body):
    body.setdefault("url", f"{SITE}/")
    return client.post("/api/crawler/start", json=body)


# ---------------------------------------------------------------------------- lifecycle
def test_start_status_results_flow(cclient):
    r = start(cclient, max_pages=10, max_depth=2)
    assert r.status_code == 202
    job = r.json()
    assert job["status"] == "queued" and job["seed_url"] == f"{SITE}/" and job["job_id"] >= 1
    assert (job["max_pages"], job["max_depth"], job["include_subdomains"], job["category"]) == (10, 2, False, "Crawled")

    # TestClient runs background tasks before returning, so the crawl has finished by now.
    status = cclient.get(f"/api/crawler/{job['job_id']}").json()
    assert status["status"] == "completed" and status["stop_reason"] == "queue_exhausted"
    assert (status["pages_discovered"], status["pages_crawled"], status["pages_failed"], status["pages_blocked"]) == (4, 3, 1, 0)
    assert status["progress"] == 1.0 and status["started_at"] and status["completed_at"]
    assert status["error_count"] == 1 and status["recent_errors"][0] == {
        "url": f"{SITE}/gone", "status": "failed", "access": "failed", "http_status": 404, "error": "HTTP 404"}

    results = cclient.get(f"/api/crawler/{job['job_id']}/results").json()
    assert results["total"] == 4 and results["job_id"] == job["job_id"]
    first = results["items"][0]
    assert first["url"] == f"{SITE}/" and first["title"] == "Search Handbook" and first["status"] == "indexed"
    assert first["access"] == "allowed" and first["depth"] == 0 and first["indexed"] and first["document_id"]
    assert first["http_status"] == 200 and first["content_type"] == "text/html" and first["content_length"] > 0

    only_failed = cclient.get(f"/api/crawler/{job['job_id']}/results", params={"status": "failed"}).json()
    assert [i["url"] for i in only_failed["items"]] == [f"{SITE}/gone"]
    paged = cclient.get(f"/api/crawler/{job['job_id']}/results", params={"page_size": 2, "page": 2}).json()
    assert len(paged["items"]) == 2 and paged["total"] == 4


def test_start_normalises_seed_and_applies_defaults(cclient):
    job = start(cclient, url="HTTPS://Docs.Test:443/#top").json()
    assert job["seed_url"] == f"{SITE}/" and job["max_pages"] == 10 and job["max_depth"] == 2 and job["timeout_seconds"] == 10


def test_history_lists_newest_first(cclient):
    ids = [start(cclient).json()["job_id"] for _ in range(3)]
    history = cclient.get("/api/crawler/history").json()
    assert [j["job_id"] for j in history["items"]] == ids[::-1] and history["total"] == 3
    assert cclient.get("/api/crawler/history", params={"page_size": 2}).json()["items"][1]["job_id"] == ids[1]


def test_unknown_job_is_404(cclient):
    for method, path in [("get", "/api/crawler/999"), ("get", "/api/crawler/999/results"), ("post", "/api/crawler/999/cancel")]:
        r = getattr(cclient, method)(path)
        assert r.status_code == 404 and r.json()["error"]["code"] == "crawl_job_not_found"
    assert cclient.get("/api/crawler/abc").status_code == 422


def test_cancel_finished_job_conflicts(cclient):
    job_id = start(cclient).json()["job_id"]
    r = cclient.post(f"/api/crawler/{job_id}/cancel")
    assert r.status_code == 409 and r.json()["error"]["code"] == "job_not_cancellable"


def test_cancel_queued_job_and_one_active_job_rule(cclient, tmp_path):
    conn = connect(cclient.app.state.settings.database_path)
    queued = crawl_db.create_job(conn, seed_url=f"{SITE}/", max_pages=5, max_depth=1, timeout_seconds=5, include_subdomains=False, category="C")
    r = start(cclient)  # another job is queued -> refused
    assert r.status_code == 409 and r.json()["error"]["code"] == "crawl_in_progress"
    c = cclient.post(f"/api/crawler/{queued}/cancel")
    assert c.status_code == 200 and c.json()["status"] == "cancelled" and c.json()["completed_at"]
    assert start(cclient).status_code == 202  # slot is free again
    conn.close()


def test_cancel_running_job_is_flagged(cclient):
    conn = connect(cclient.app.state.settings.database_path)
    job_id = crawl_db.create_job(conn, seed_url=f"{SITE}/", max_pages=5, max_depth=1, timeout_seconds=5, include_subdomains=False, category="C")
    crawl_db.mark_running(conn, job_id)
    body = cclient.post(f"/api/crawler/{job_id}/cancel").json()
    assert body["status"] == "running" and body["cancel_requested"] is True  # the worker stops at the next page boundary
    conn.close()


def test_restart_marks_unfinished_jobs_failed(tmp_path):
    settings = Settings(database_path=tmp_path / "restart.db")
    with TestClient(create_app(settings)):
        pass
    conn = connect(settings.database_path)
    job_id = crawl_db.create_job(conn, seed_url=f"{SITE}/", max_pages=5, max_depth=1, timeout_seconds=5, include_subdomains=False, category="C")
    conn.close()
    with TestClient(create_app(settings)) as c:
        body = c.get(f"/api/crawler/{job_id}").json()
        assert body["status"] == "failed" and "server stopped" in body["error"]


# ------------------------------------------------------------------------ validation
@pytest.mark.parametrize("body, field", [
    ({"url": f"{SITE}/", "max_pages": 0}, "max_pages"),
    ({"url": f"{SITE}/", "max_pages": 101}, "max_pages"),
    ({"url": f"{SITE}/", "max_pages": "many"}, "max_pages"),
    ({"url": f"{SITE}/", "max_depth": -1}, "max_depth"),
    ({"url": f"{SITE}/", "max_depth": 6}, "max_depth"),
    ({"url": f"{SITE}/", "timeout_seconds": 0}, "timeout_seconds"),
    ({"url": f"{SITE}/", "timeout_seconds": 31}, "timeout_seconds"),
    ({"url": ""}, "url"),
    ({"url": "   "}, "url"),
    ({}, "url"),
    ({"url": f"{SITE}/", "category": " "}, "category"),
    ({"url": f"{SITE}/", "ignore_robots": True}, "ignore_robots"),  # no way to switch protections off
    ({"url": f"{SITE}/", "allow_private": True}, "allow_private"),
    ({"url": f"{SITE}/", "follow_external": True}, "follow_external"),
])
def test_start_rejects_invalid_input(cclient, body, field):
    r = cclient.post("/api/crawler/start", json=body)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error" and any(d["field"] == field for d in r.json()["error"]["details"])
    assert cclient.get("/api/crawler/history").json()["total"] == 0


@pytest.mark.parametrize("url, code, reason", [
    ("http://localhost/", "url_blocked", "blocked_hostname"),
    ("http://localhost:8080/api/documents", "url_blocked", "blocked_hostname"),
    ("http://localhost:8000/api/documents", "url_blocked", "blocked_port"),  # this very server: refused on port AND host
    ("http://127.0.0.1/", "url_blocked", "loopback_address"),
    ("http://127.1/", "url_blocked", "loopback_address"),
    ("http://[::1]/", "url_blocked", "loopback_address"),
    ("http://0.0.0.0/", "url_blocked", "unspecified_address"),
    ("http://192.168.1.1/", "url_blocked", "private_address"),
    ("http://10.0.0.1/", "url_blocked", "private_address"),
    ("http://172.16.0.1/", "url_blocked", "private_address"),
    ("http://169.254.169.254/latest/meta-data/", "url_blocked", "metadata_endpoint"),
    ("http://metadata.google.internal/", "url_blocked", "blocked_hostname"),
    ("http://intranet.docs.test/", "url_blocked", "private_address"),  # name resolves to 10.9.9.9
    ("http://evil.test/", "url_blocked", "metadata_endpoint"),  # name resolves to the metadata IP
    ("file:///etc/passwd", "url_blocked", "unsupported_scheme"),
    ("ftp://example.com", "url_blocked", "unsupported_scheme"),
    ("javascript:alert(1)", "url_blocked", "unsupported_scheme"),
    ("data:text/html,hi", "url_blocked", "unsupported_scheme"),
    ("about:blank", "url_blocked", "unsupported_scheme"),
    ("chrome://settings", "url_blocked", "unsupported_scheme"),
    ("https://user:pw@docs.test/", "url_blocked", "credentials_in_url"),
    ("https://docs.test:22/", "url_blocked", "blocked_port"),
    ("docs.test/page", "invalid_url", "invalid_url"),
    ("http://", "invalid_url", "invalid_url"),
])
def test_start_rejects_dangerous_and_invalid_urls(cclient, fetcher, url, code, reason):
    r = start(cclient, url=url)
    assert r.status_code == 400, r.text
    err = r.json()["error"]
    assert err["code"] == code and err["details"]["reason"] == reason
    assert cclient.get("/api/crawler/history").json()["total"] == 0  # no job was even created
    assert fetcher.requests == []  # and nothing was requested


def test_unresolvable_seed_is_rejected(tmp_path, fetcher):
    settings = Settings(database_path=tmp_path / "d.db")
    with TestClient(create_app(settings, crawler_fetcher=fetcher, crawler_resolver=FakeResolver({"nx.test": []}))) as c:
        r = c.post("/api/crawler/start", json={"url": "https://nx.test/"})
        assert r.status_code == 400 and r.json()["error"]["details"]["reason"] == "unresolvable_host"


def test_validate_url_endpoint(cclient):
    ok = cclient.post("/api/crawler/validate-url", json={"url": f"{SITE}/a/../b#x"}).json()
    assert ok == {"url": f"{SITE}/a/../b#x", "normalized_url": f"{SITE}/b", "allowed": True, "status": "allowed", "reason": None, "message": None}
    blocked = cclient.post("/api/crawler/validate-url", json={"url": "http://169.254.169.254/"}).json()
    assert blocked["allowed"] is False and blocked["status"] == "blocked_by_security" and blocked["reason"] == "metadata_endpoint"
    assert "10.9.9.9" not in str(cclient.post("/api/crawler/validate-url", json={"url": "http://intranet.docs.test/"}).json())  # no internal-IP leak
    invalid = cclient.post("/api/crawler/validate-url", json={"url": "nonsense"}).json()
    assert invalid["allowed"] is False and invalid["status"] == "invalid"
    assert cclient.get("/api/crawler/history").json()["total"] == 0


# --------------------------------------------------------------- redirect security (API level)
def test_redirect_to_private_target_is_reported_as_blocked(cclient, fetcher):
    fetcher.pages[f"{SITE}/"] = Page(html("Home", "<a href='/jump'>jump</a> hello there"))
    fetcher.pages[f"{SITE}/jump"] = Page(status=302, location="http://169.254.169.254/latest/meta-data/")
    fetcher.pages["http://169.254.169.254/latest/meta-data/"] = Page(html("Creds", "AWS secret keys"))
    job_id = start(cclient).json()["job_id"]
    status = cclient.get(f"/api/crawler/{job_id}").json()
    assert status["status"] == "completed" and status["pages_blocked"] == 1
    items = {i["url"]: i for i in cclient.get(f"/api/crawler/{job_id}/results").json()["items"]}
    assert items[f"{SITE}/jump"]["status"] == "blocked_by_security" and items[f"{SITE}/jump"]["access"] == "blocked_by_security"
    assert "metadata" in items[f"{SITE}/jump"]["error"]
    assert "http://169.254.169.254/latest/meta-data/" not in fetcher.requests
    assert cclient.post("/api/search", json={"query": "AWS secret keys"}).json()["total_results"] == 0


def test_robots_blocked_page_is_reported(cclient, fetcher):
    fetcher.pages[f"{SITE}/robots.txt"] = Page("User-agent: *\nDisallow: /rank\n", content_type="text/plain")
    job_id = start(cclient).json()["job_id"]
    items = {i["url"]: i for i in cclient.get(f"/api/crawler/{job_id}/results").json()["items"]}
    assert items[f"{SITE}/rank"]["status"] == "blocked_by_robots" and items[f"{SITE}/rank"]["access"] == "blocked_by_robots"
    assert f"{SITE}/rank" not in fetcher.requests
    assert cclient.get(f"/api/crawler/{job_id}").json()["pages_blocked"] == 1


# ----------------------------------------------------------------- integration with search
def test_crawled_pages_are_searchable_with_crawl_metadata(cclient):
    job_id = start(cclient).json()["job_id"]
    body = cclient.post("/api/search", json={"query": "posting lists vocabulary"}).json()
    assert body["total_results"] == 1
    hit = body["results"][0]
    assert hit["title"] == "Inverted Index" and hit["source_type"] == "crawled" and hit["source_url"] == f"{SITE}/index"
    assert hit["category"] == "Crawled" and hit["score"] > 0

    # The document API exposes the full crawl provenance for the frontend.
    doc = cclient.get(f"/api/documents/{hit['doc_id']}").json()
    assert doc["source_type"] == "crawled" and doc["source_url"] == f"{SITE}/index" and doc["indexed"] is True
    assert doc["metadata"]["crawl_job_id"] == job_id and doc["metadata"]["http_status"] == 200
    assert doc["metadata"]["content_type"] == "text/html" and doc["metadata"]["crawled_at"]
    listed = cclient.get("/api/documents", params={"source_type": "crawled"}).json()
    assert listed["total"] == 3

    # Other retrieval models see it too (Boolean, tolerant, index admin).
    boolean = cclient.post("/api/search/boolean", json={"query": "inverted AND index"}).json()
    assert [r["source_type"] for r in boolean["results"]] == ["crawled"]
    assert cclient.get("/api/index/check").json()["consistent"] is True


def test_search_results_distinguish_crawled_from_other_sources(cclient):
    cclient.post("/api/documents", json={"title": "Index Notes", "text": "my own inverted index notes", "category": "Notes"})
    start(cclient)
    results = cclient.post("/api/search", json={"query": "inverted index"}).json()["results"]
    assert {r["source_type"] for r in results} == {"user", "crawled"}
    assert {r["source_url"] for r in results if r["source_type"] == "user"} == {None}


def test_recrawl_through_the_api_does_not_duplicate(cclient):
    start(cclient)
    total = cclient.get("/api/documents").json()["total"]
    second = start(cclient).json()["job_id"]
    assert cclient.get("/api/documents").json()["total"] == total
    items = cclient.get(f"/api/crawler/{second}/results").json()["items"]
    assert {i["status"] for i in items if i["http_status"] == 200} == {"unchanged"}


def test_deleting_a_crawled_document_removes_it_from_search(cclient):
    start(cclient)
    hit = cclient.post("/api/search", json={"query": "posting lists"}).json()["results"][0]
    assert cclient.delete(f"/api/documents/{hit['doc_id']}").status_code == 204
    assert cclient.post("/api/search", json={"query": "posting lists"}).json()["total_results"] == 0
    assert cclient.get("/api/index/check").json()["consistent"] is True


def test_existing_phase_endpoints_still_work_after_a_crawl(cclient):
    start(cclient)
    assert cclient.get("/api/health").status_code == 200
    assert cclient.post("/api/search", json={"query": "cosine"}).json()["total_results"] == 1
    assert cclient.post("/api/search/expanded", json={"query": "cosine"}).status_code == 200
    paths = cclient.get("/openapi.json").json()["paths"]
    for p in ("/api/crawler/start", "/api/crawler/{job_id}", "/api/crawler/{job_id}/results", "/api/crawler/{job_id}/cancel",
              "/api/crawler/validate-url", "/api/crawler/history"):
        assert p in paths
