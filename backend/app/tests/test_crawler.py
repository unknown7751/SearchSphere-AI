"""Crawler service tests: a fake fetcher and fake DNS make every scenario deterministic."""
import pytest

from app.database import crawl as crawl_db
from app.database import repository as repo
from app.database.connection import connect
from app.database.schema import init_db
from app.services.crawler import (
    MAX_QUERY_VARIANTS_PER_PATH,
    Crawler,
    CrawlConfig,
    has_skipped_extension,
    is_crawl_trap,
)
from app.services.http_fetcher import FetchError
from app.services.search_engine import SearchEngine
from app.services.url_validator import normalize_url
from app.tests.crawler_fakes import PUBLIC_IP, FakeFetcher, FakeResolver, Page, html, redirect

SITE = "https://docs.test"


def link(*paths: str) -> str:
    return "".join(f'<a href="{p}">x</a>' for p in paths)


def basic_site() -> dict:
    return {
        f"{SITE}/": Page(html("Home", "<p>Welcome to the information retrieval handbook.</p>" + link("/a", "/b", "/a#frag"))),
        f"{SITE}/a": Page(html("Inverted Index", "<p>An inverted index maps every term to a posting list.</p>" + link("/", "/a/deep", "/b"))),
        f"{SITE}/b": Page(html("Ranking", "<p>Cosine similarity ranks documents by angle.</p>")),
        f"{SITE}/a/deep": Page(html("Deep Page", "<p>Zeppelin hangars are very deep inside.</p>")),
    }


class Env:
    def __init__(self, tmp_path, preprocessor, pages=None, resolver=None):
        self.conn = connect(tmp_path / "crawl.db")
        init_db(self.conn)
        self.engine = SearchEngine(preprocessor=preprocessor)
        self.fetcher = FakeFetcher(pages if pages is not None else basic_site())
        self.resolver = resolver or FakeResolver()
        self.sleeps: list[float] = []

    def crawl(self, seed=f"{SITE}/", *, max_pages=20, max_depth=2, include_subdomains=False, category="Crawled",
              run=True, **overrides) -> int:
        seed = normalize_url(seed)
        job_id = crawl_db.create_job(self.conn, seed_url=seed, max_pages=max_pages, max_depth=max_depth,
                                     timeout_seconds=5, include_subdomains=include_subdomains, category=category)
        settings = dict(delay=0.0, max_response_bytes=1_000_000, max_redirects=5, max_duration=300.0,
                        max_discovered=1000, max_document_chars=200_000)
        settings.update(overrides)
        clock = settings.pop("clock", None)
        config = CrawlConfig(seed_url=seed, max_pages=max_pages, max_depth=max_depth, timeout=5,
                             include_subdomains=include_subdomains, category=category, **settings)
        kwargs = {"clock": clock} if clock else {}
        self.crawler = Crawler(self.conn, self.engine, self.fetcher, config, resolver=self.resolver,
                               sleep=self.sleeps.append, **kwargs)
        if run:
            self.crawler.run(job_id)
        return job_id

    def job(self, job_id):
        return crawl_db.get_job(self.conn, job_id)

    def results(self, job_id) -> dict:
        rows, _ = crawl_db.list_results(self.conn, job_id, limit=1000, offset=0)
        return {r["url"]: r for r in rows}

    def search_ids(self, query: str) -> list[int]:
        analysis = self.engine.preprocessor.analyze(query)
        ranking = self.engine.ranker.rank(analysis.index_terms)
        return [s.doc_id for s in ranking.ranked] if ranking else []


@pytest.fixture
def env(tmp_path, preprocessor):
    e = Env(tmp_path, preprocessor)
    yield e
    e.conn.close()


@pytest.fixture
def make_env(tmp_path, preprocessor):
    made = []

    def factory(pages=None, resolver=None):
        e = Env(tmp_path / f"e{len(made)}", preprocessor, pages, resolver)
        made.append(e)
        return e

    yield factory
    for e in made:
        e.conn.close()


# ------------------------------------------------------------------------ happy path
def test_crawl_stores_indexes_and_reports(env):
    job_id = env.crawl()
    job = env.job(job_id)
    assert job["status"] == "completed" and job["stop_reason"] == "queue_exhausted"
    assert (job["pages_discovered"], job["pages_crawled"], job["pages_failed"], job["pages_blocked"]) == (4, 4, 0, 0)
    assert job["started_at"] and job["completed_at"] and job["error"] is None

    res = env.results(job_id)
    assert list(res) == [f"{SITE}/", f"{SITE}/a", f"{SITE}/b", f"{SITE}/a/deep"]  # breadth-first, deterministic
    home = res[f"{SITE}/"]
    assert (home["status"], home["access"], home["depth"], home["http_status"], home["title"]) == ("indexed", "allowed", 0, 200, "Home")
    assert home["indexed"] and home["document_id"] and home["content_type"] == "text/html" and home["content_length"] > 0
    assert res[f"{SITE}/a/deep"]["depth"] == 2

    doc = repo.get_document(env.conn, res[f"{SITE}/a"]["document_id"])
    assert doc.source_type == "crawled" and doc.source_url == f"{SITE}/a" and doc.indexed and doc.category == "Crawled"
    assert doc.title == "Inverted Index" and doc.file_type == "html"
    import json
    meta = json.loads(doc.metadata_json)
    assert meta["crawl_job_id"] == job_id and meta["http_status"] == 200 and meta["content_type"] == "text/html"
    assert meta["crawled_at"] and meta["depth"] == 1 and meta["host"] == "docs.test"

    assert env.engine.check(env.conn)["consistent"]
    assert env.search_ids("posting list") == [doc.id]


def test_crawled_pages_flow_through_the_normal_pipeline(env):
    """Extraction -> document row -> preprocessing (stemming) -> inverted index -> TF-IDF ranking."""
    job_id = env.crawl()
    deep = env.results(job_id)[f"{SITE}/a/deep"]["document_id"]
    assert env.search_ids("zeppelins hangar") == [deep]  # plural/stemmed query matches the crawled text
    assert env.engine.index.has_document(deep)


def test_every_url_requested_once(env):
    env.crawl()
    pages = [u for u in env.fetcher.requests if not u.endswith("robots.txt")]
    assert sorted(pages) == sorted(set(pages)) and len(pages) == 4  # '/a#frag', cycles etc. never refetched
    assert env.fetcher.requests.count(f"{SITE}/robots.txt") == 1  # robots.txt cached per origin


# ------------------------------------------------------------------------ bounds
def test_max_depth_zero_crawls_only_the_seed(env):
    job_id = env.crawl(max_depth=0)
    assert list(env.results(job_id)) == [f"{SITE}/"]
    assert env.job(job_id)["pages_discovered"] == 1


def test_max_depth_one(env):
    job_id = env.crawl(max_depth=1)
    assert set(env.results(job_id)) == {f"{SITE}/", f"{SITE}/a", f"{SITE}/b"}
    assert f"{SITE}/a/deep" not in env.fetcher.requests


def test_max_pages_bounds_fetches(env):
    job_id = env.crawl(max_pages=2)
    job = env.job(job_id)
    assert len([u for u in env.fetcher.requests if not u.endswith("robots.txt")]) == 2
    assert job["pages_crawled"] == 2 and job["status"] == "completed" and job["stop_reason"] == "max_pages_reached"


def test_cycles_and_self_links_terminate(make_env):
    e = make_env({f"{SITE}/": Page(html("Loop", "text one" + link("/", "/x"))), f"{SITE}/x": Page(html("X", "text two" + link("/", "/x", "/")))})
    assert e.job(e.crawl(max_depth=5))["pages_crawled"] == 2


def test_duration_limit(env):
    ticks = iter(range(0, 10_000, 100))  # every clock read advances 100 s
    job_id = env.crawl(max_duration=250.0, clock=lambda: next(ticks))
    assert env.job(job_id)["stop_reason"] == "max_duration_reached"
    assert env.job(job_id)["pages_crawled"] < 4


def test_discovered_cap(make_env):
    pages = {f"{SITE}/": Page(html("Hub", "hub text" + link(*[f"/p{i}" for i in range(50)])))}
    pages.update({f"{SITE}/p{i}": Page(html(f"P{i}", f"unique body number {i} zebra")) for i in range(50)})
    e = make_env(pages)
    job = e.job(e.crawl(max_pages=100, max_depth=1, max_discovered=10))
    assert job["pages_discovered"] == 10 and job["pages_crawled"] == 10


@pytest.mark.parametrize(
    "url, trap",
    [
        ("https://x.test/a/b/c", False),
        ("https://x.test/" + "/".join(f"s{i}" for i in range(13)), True),  # too deep
        ("https://x.test/a/b/a/b/a/b", True),  # repeating segments
        ("https://x.test/cal/2024/01/01", False),
        ("https://x.test/p?" + "&".join(f"k{i}=v" for i in range(9)), True),  # too many params
        ("https://x.test/p?q=" + "z" * 300, True),
        ("https://x.test/p?page=2&sort=asc", False),
    ],
)
def test_trap_heuristics(url, trap):
    assert is_crawl_trap(url) is trap


@pytest.mark.parametrize("url, skipped", [("https://x.test/a.pdf", True), ("https://x.test/A.JPG", True), ("https://x.test/a.html", False),
                                          ("https://x.test/dir.v1/page", False), ("https://x.test/a", False)])
def test_extension_filter(url, skipped):
    assert has_skipped_extension(url) is skipped


def test_query_parameter_explosion_is_limited(make_env):
    pages = {f"{SITE}/": Page(html("Home", "home text" + link(*[f"/list?page={i}" for i in range(30)])))}
    pages.update({f"{SITE}/list?page={i}": Page(html(f"L{i}", f"listing body {i} xylophone")) for i in range(30)})
    e = make_env(pages)
    job = e.job(e.crawl(max_depth=1))
    assert job["pages_crawled"] == 1 + MAX_QUERY_VARIANTS_PER_PATH


def test_binary_links_are_not_even_requested(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "some text" + link("/f.pdf", "/pic.png", "/a.zip", "/real")))})
    e.fetcher.pages[f"{SITE}/real"] = Page(html("Real", "real page content"))
    e.crawl()
    assert [u for u in e.fetcher.requests if not u.endswith("robots.txt")] == [f"{SITE}/", f"{SITE}/real"]


# ----------------------------------------------------------------------- scope policy
def test_other_hosts_are_not_followed(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("https://other.test/x", "https://docs.test.evil.test/", "/ok"))),
                  f"{SITE}/ok": Page(html("Ok", "fine page"))})
    job_id = e.crawl()
    assert set(e.results(job_id)) == {f"{SITE}/", f"{SITE}/ok"}
    assert all("other.test" not in u and "evil" not in u for u in e.fetcher.requests)


def test_subdomains_only_when_enabled(make_env):
    pages = {f"{SITE}/": Page(html("Home", "hello" + link("https://blog.docs.test/p"))),
             "https://blog.docs.test/p": Page(html("Blog", "blog post text"))}
    off = make_env(pages)
    assert set(off.results(off.crawl())) == {f"{SITE}/"}
    on = make_env(pages)
    assert set(on.results(on.crawl(include_subdomains=True))) == {f"{SITE}/", "https://blog.docs.test/p"}


def test_www_is_equivalent_to_bare_host(make_env):
    e = make_env({"https://example.test/": Page(html("Home", "hi" + link("https://www.example.test/about"))),
                  "https://www.example.test/about": Page(html("About", "about us"))})
    assert len(e.results(e.crawl("https://example.test/"))) == 2


# ------------------------------------------------------------------------- robots.txt
ROBOTS = "User-agent: *\nDisallow: /private/\nDisallow: /secret\n"


def test_robots_disallowed_pages_are_never_fetched(make_env):
    pages = {f"{SITE}/robots.txt": Page(ROBOTS, content_type="text/plain"),
             f"{SITE}/": Page(html("Home", "welcome" + link("/private/x", "/secret", "/secret/more", "/public"))),
             f"{SITE}/public": Page(html("Public", "public page")),
             f"{SITE}/private/x": Page(html("Priv", "should never be stored")),
             f"{SITE}/secret": Page(html("Sec", "should never be stored"))}
    e = make_env(pages)
    job_id = e.crawl()
    res = e.results(job_id)
    assert res[f"{SITE}/private/x"]["status"] == "blocked_by_robots" and res[f"{SITE}/private/x"]["access"] == "blocked_by_robots"
    assert res[f"{SITE}/secret"]["status"] == "blocked_by_robots" and res[f"{SITE}/public"]["status"] == "indexed"
    assert f"{SITE}/private/x" not in e.fetcher.requests and f"{SITE}/secret" not in e.fetcher.requests
    assert e.job(job_id)["pages_blocked"] == 3 and e.job(job_id)["pages_crawled"] == 2
    assert not e.search_ids("stored") and repo.count_documents(e.conn) == 2


def test_robots_disallow_all_blocks_the_seed(make_env):
    e = make_env({f"{SITE}/robots.txt": Page("User-agent: *\nDisallow: /\n", content_type="text/plain"), **basic_site()})
    job_id = e.crawl()
    assert e.results(job_id)[f"{SITE}/"]["status"] == "blocked_by_robots"
    assert e.job(job_id)["status"] == "completed" and repo.count_documents(e.conn) == 0
    assert e.fetcher.requests == [f"{SITE}/robots.txt"]


@pytest.mark.parametrize("robots, blocked", [
    (Page("nope", status=404), False), (Page("gone", status=410), False),
    (Page("x", status=403), True), (Page("x", status=500), True), (Page("x", status=503), True),
    (FetchError("timeout", "timed out"), True), (FetchError("connection_error", "refused"), True),
    (FetchError("too_large", "huge"), True),
])
def test_robots_failure_policy(make_env, robots, blocked):
    e = make_env({f"{SITE}/robots.txt": robots, **basic_site()})
    first = e.results(e.crawl(max_depth=0))[f"{SITE}/"]
    assert (first["status"] == "blocked_by_robots") is blocked
    assert (f"{SITE}/" in e.fetcher.requests) is (not blocked)


def test_robots_redirect_to_private_address_fails_closed(make_env):
    e = make_env({f"{SITE}/robots.txt": redirect("http://127.0.0.1/robots.txt"), **basic_site()})
    assert e.results(e.crawl())[f"{SITE}/"]["status"] == "blocked_by_robots"
    assert not any("127.0.0.1" in u for u in e.fetcher.requests)


def test_crawl_delay_is_honoured(make_env):
    pages = {f"{SITE}/robots.txt": Page("User-agent: *\nCrawl-delay: 3\n", content_type="text/plain"), **basic_site()}
    e = make_env(pages)
    now = [0.0]
    e.sleeps.clear()

    def sleep(s):
        e.sleeps.append(s)
        now[0] += s

    seed = normalize_url(f"{SITE}/")
    job_id = crawl_db.create_job(e.conn, seed_url=seed, max_pages=3, max_depth=1, timeout_seconds=5, include_subdomains=False, category="Crawled")
    cfg = CrawlConfig(seed, 3, 1, 5, False, "Crawled", delay=0.5, max_response_bytes=10**6, max_redirects=5, max_duration=300, max_discovered=100, max_document_chars=10**5)
    Crawler(e.conn, e.engine, e.fetcher, cfg, resolver=e.resolver, sleep=sleep, clock=lambda: now[0]).run(job_id)
    assert e.sleeps and all(abs(s - 3.0) < 1e-9 for s in e.sleeps)  # robots Crawl-delay (3 s) beats the 0.5 s default


def test_default_politeness_delay(env):
    ticks = [0.0]
    env.sleeps.clear()

    def sleep(s):
        env.sleeps.append(s)
        ticks[0] += s

    seed = normalize_url(f"{SITE}/")
    job_id = crawl_db.create_job(env.conn, seed_url=seed, max_pages=4, max_depth=2, timeout_seconds=5, include_subdomains=False, category="Crawled")
    cfg = CrawlConfig(seed, 4, 2, 5, False, "Crawled", delay=1.0, max_response_bytes=10**6, max_redirects=5, max_duration=300, max_discovered=100, max_document_chars=10**5)
    Crawler(env.conn, env.engine, env.fetcher, cfg, resolver=env.resolver, sleep=sleep, clock=lambda: ticks[0]).run(job_id)
    assert len(env.sleeps) == len(env.fetcher.requests) - 1 and all(abs(s - 1.0) < 1e-9 for s in env.sleeps)


# --------------------------------------------------------------------------- security
def test_url_resolving_to_private_address_is_blocked(make_env):
    """The page URL looks fine; only the *resolved destination* reveals it is internal."""
    resolver = FakeResolver({"intranet.docs.test": ["10.0.0.7"]})
    pages = {f"{SITE}/": Page(html("Home", "welcome" + link("https://intranet.docs.test/admin", "/ok"))),
             f"{SITE}/ok": Page(html("Ok", "an ok page")),
             "https://intranet.docs.test/admin": Page(html("Admin", "internal secrets"))}
    e = make_env(pages, resolver)
    job_id = e.crawl(include_subdomains=True)
    res = e.results(job_id)
    assert res["https://intranet.docs.test/admin"]["status"] == "blocked_by_security"
    assert res["https://intranet.docs.test/admin"]["access"] == "blocked_by_security"
    assert "private" in res["https://intranet.docs.test/admin"]["error"]
    assert "https://intranet.docs.test/admin" not in e.fetcher.requests
    assert not any("intranet" in u for u in e.fetcher.requests)  # not even robots.txt
    assert e.job(job_id)["pages_blocked"] == 1 and not e.search_ids("secrets")


@pytest.mark.parametrize("seed, reason", [
    ("http://127.0.0.1/", "loopback"), ("http://localhost/", "internal host"), ("http://192.168.1.1/", "private"),
    ("http://10.0.0.1/", "private"), ("http://169.254.169.254/latest/meta-data/", "metadata"),
])
def test_dangerous_seed_is_never_requested(make_env, seed, reason):
    e = make_env({})
    # Bypass the API validation on purpose: the crawler itself must refuse.
    job_id = crawl_db.create_job(e.conn, seed_url=seed, max_pages=5, max_depth=1, timeout_seconds=5, include_subdomains=False, category="C")
    cfg = CrawlConfig(seed, 5, 1, 5, False, "C", 0.0, 10**6, 5, 300, 100, 10**5)
    Crawler(e.conn, e.engine, e.fetcher, cfg, resolver=e.resolver, sleep=lambda s: None).run(job_id)
    row = e.results(job_id)[seed]
    assert row["status"] == "blocked_by_security" and reason in row["error"]
    assert e.fetcher.requests == [] and e.job(job_id)["pages_blocked"] == 1


@pytest.mark.parametrize("target, reason", [
    ("http://127.0.0.1/", "loopback"),
    ("http://127.0.0.1:8080/admin", "loopback"),
    ("http://localhost/", "internal host"),
    ("http://169.254.169.254/latest/meta-data/iam/", "metadata"),
    ("http://10.0.0.1/", "private"),
    ("http://192.168.0.1/", "private"),
    ("http://[::1]/", "loopback"),
    ("http://2130706433/", "loopback"),
    ("file:///etc/passwd", "scheme"),
    ("gopher://docs.test/", "scheme"),
    ("http://user:pw@docs.test/", "credentials"),
    ("https://rebind.example/", "private"),  # a public-looking name that resolves to an internal address
])
def test_redirect_to_internal_destination_is_blocked(make_env, target, reason):
    resolver = FakeResolver({"rebind.example": ["192.168.50.5"]})
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/go"))), f"{SITE}/go": redirect(target),
                  target: Page(html("PWNED", "internal data"))}, resolver)
    job_id = e.crawl()
    row = e.results(job_id)[f"{SITE}/go"]
    assert row["status"] == "blocked_by_security" and reason in row["error"], row
    assert target not in e.fetcher.requests
    assert e.results(job_id)[f"{SITE}/"]["status"] == "indexed"  # the crawl carried on
    assert not e.search_ids("internal data")


def test_every_redirect_hop_is_revalidated(make_env):
    """safe -> safe -> safe -> private: the check happens at the last hop, not just the first."""
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/h1"))), f"{SITE}/h1": redirect("/h2"),
                  f"{SITE}/h2": redirect("/h3"), f"{SITE}/h3": redirect("http://10.1.1.1/")})
    row = e.results(e.crawl())[f"{SITE}/h1"]
    assert row["status"] == "blocked_by_security" and f"{SITE}/h3" in e.fetcher.requests


def test_redirect_to_robots_disallowed_url_is_blocked(make_env):
    pages = {f"{SITE}/robots.txt": Page(ROBOTS, content_type="text/plain"),
             f"{SITE}/": Page(html("Home", "hello" + link("/go"))), f"{SITE}/go": redirect("/private/x"),
             f"{SITE}/private/x": Page(html("Priv", "secret"))}
    e = make_env(pages)
    row = e.results(e.crawl())[f"{SITE}/go"]
    assert row["status"] == "blocked_by_robots" and f"{SITE}/private/x" not in e.fetcher.requests


def test_redirect_loop_is_cut_off(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/a"))), f"{SITE}/a": redirect("/b"), f"{SITE}/b": redirect("/a")})
    row = e.results(e.crawl())[f"{SITE}/a"]
    assert row["status"] == "failed" and "redirects" in row["error"]
    assert len(e.fetcher.requests) < 15


def test_same_scope_redirect_is_followed_and_stored_under_final_url(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/old"))), f"{SITE}/old": redirect("/new", 301),
                  f"{SITE}/new": Page(html("New Page", "moved content walrus"))})
    job_id = e.crawl()
    row = e.results(job_id)[f"{SITE}/old"]
    assert row["status"] == "indexed" and row["final_url"] == f"{SITE}/new"
    doc = repo.get_document(e.conn, row["document_id"])
    assert doc.source_url == f"{SITE}/new"
    import json
    assert json.loads(doc.metadata_json)["requested_url"] == f"{SITE}/old"


def test_redirect_outside_scope_is_skipped(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/out"))), f"{SITE}/out": redirect("https://elsewhere.test/page"),
                  "https://elsewhere.test/page": Page(html("Else", "other site"))})
    row = e.results(e.crawl())[f"{SITE}/out"]
    assert row["status"] == "skipped" and "scope" in row["error"]
    assert "https://elsewhere.test/page" not in e.fetcher.requests


def test_two_urls_redirecting_to_one_page_store_it_once(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/x", "/y"))), f"{SITE}/x": redirect("/final"),
                  f"{SITE}/y": redirect("/final"), f"{SITE}/final": Page(html("Final", "single page"))})
    job_id = e.crawl()
    res = e.results(job_id)
    assert res[f"{SITE}/x"]["status"] == "indexed" and res[f"{SITE}/y"]["status"] == "skipped"
    assert repo.count_documents(e.conn) == 2


# ----------------------------------------------------------------------------- errors
def test_failures_do_not_stop_the_crawl(make_env):
    pages = {f"{SITE}/": Page(html("Home", "hello" + link("/404", "/500", "/slow", "/ssl", "/dns", "/big", "/ok"))),
             f"{SITE}/500": Page("boom", status=500), f"{SITE}/slow": FetchError("timeout", "The request timed out."),
             f"{SITE}/ssl": FetchError("ssl_error", "TLS/SSL negotiation or certificate verification failed."),
             f"{SITE}/dns": FetchError("dns_failure", "The host name could not be resolved."),
             f"{SITE}/big": Page("x" * 5000), f"{SITE}/ok": Page(html("Ok", "survivor page"))}
    e = make_env(pages)
    job_id = e.crawl(max_response_bytes=1000)
    res = e.results(job_id)
    assert res[f"{SITE}/404"]["status"] == "failed" and res[f"{SITE}/404"]["error"] == "HTTP 404" and res[f"{SITE}/404"]["http_status"] == 404
    assert res[f"{SITE}/500"]["error"] == "HTTP 500"
    assert "timed out" in res[f"{SITE}/slow"]["error"] and "TLS" in res[f"{SITE}/ssl"]["error"]
    assert "resolved" in res[f"{SITE}/dns"]["error"] and "larger" in res[f"{SITE}/big"]["error"]
    assert res[f"{SITE}/ok"]["status"] == "indexed"
    job = e.job(job_id)
    assert job["status"] == "completed" and job["pages_failed"] == 6 and job["pages_crawled"] == 2


def test_unsupported_content_types_are_skipped_without_download(make_env):
    pages = {f"{SITE}/": Page(html("Home", "hello" + link("/img", "/bin", "/video", "/none", "/json", "/xhtml"))),
             f"{SITE}/img": Page(b"\x89PNG", content_type="image/png"),
             f"{SITE}/bin": Page(b"\x00\x01", content_type="application/octet-stream"),
             f"{SITE}/video": Page(b"", content_type="video/mp4"), f"{SITE}/none": Page("text", content_type=None),
             f"{SITE}/json": Page("{}", content_type="application/json"),
             f"{SITE}/xhtml": Page("<html><body><p>xhtml body text</p></body></html>", content_type="application/xhtml+xml")}
    e = make_env(pages)
    job_id = e.crawl()
    res = e.results(job_id)
    for name in ("img", "bin", "video", "none", "json"):
        assert res[f"{SITE}/{name}"]["status"] == "skipped" and "content type" in res[f"{SITE}/{name}"]["error"].lower()
    assert res[f"{SITE}/xhtml"]["status"] == "indexed"
    assert e.job(job_id)["pages_skipped"] == 5 and e.job(job_id)["pages_failed"] == 0


def test_unexpected_exception_is_contained(make_env, monkeypatch):
    e = make_env()
    real = e.engine.store_crawled

    def flaky(conn, **kw):
        if kw["url"].endswith("/b"):
            raise RuntimeError("disk exploded")
        return real(conn, **kw)

    monkeypatch.setattr(e.engine, "store_crawled", flaky)
    job_id = e.crawl()
    res = e.results(job_id)
    assert res[f"{SITE}/b"]["status"] == "failed" and "Internal error" in res[f"{SITE}/b"]["error"]
    assert "disk exploded" not in str(res)  # internals are not leaked
    assert e.job(job_id)["status"] == "completed" and e.job(job_id)["pages_crawled"] == 3


def test_crash_outside_a_page_marks_job_failed(make_env, monkeypatch):
    e = make_env()
    job_id = e.crawl(run=False)
    monkeypatch.setattr(crawl_db, "update_counters", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db gone")))
    e.crawler.run(job_id)
    job = e.job(job_id)
    assert job["status"] == "failed" and job["stop_reason"] == "error" and "internal error" in job["error"] and "db gone" not in job["error"]


# ------------------------------------------------------------------ document handling
def test_noindex_page_is_skipped_but_links_followed(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/n"))),
                  f"{SITE}/n": Page(html("N", "private words" + link("/after"), head='<meta name="robots" content="noindex">')),
                  f"{SITE}/after": Page(html("After", "reached anyway"))})
    res = e.results(e.crawl())
    assert res[f"{SITE}/n"]["status"] == "skipped" and "noindex" in res[f"{SITE}/n"]["error"]
    assert res[f"{SITE}/after"]["status"] == "indexed"


def test_nofollow_page_links_are_ignored(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/a"), head='<meta name="robots" content="nofollow">')),
                  f"{SITE}/a": Page(html("A", "page a"))})
    assert list(e.results(e.crawl())) == [f"{SITE}/"]


def test_empty_pages_are_skipped(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "<script>only();</script><a href='/a'></a>")), f"{SITE}/a": Page(html("A", "real text here"))})
    res = e.results(e.crawl())
    assert res[f"{SITE}/"]["status"] == "skipped" and "No extractable text" in res[f"{SITE}/"]["error"]
    assert res[f"{SITE}/a"]["status"] == "indexed"


def test_identical_content_at_different_urls_is_stored_once(make_env):
    same = html("Same", "exactly the same words on both pages")
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/copy1", "/copy2"))), f"{SITE}/copy1": Page(same), f"{SITE}/copy2": Page(same)})
    job_id = e.crawl()
    res = e.results(job_id)
    assert res[f"{SITE}/copy1"]["status"] == "indexed" and res[f"{SITE}/copy2"]["status"] == "duplicate_content"
    assert res[f"{SITE}/copy2"]["document_id"] == res[f"{SITE}/copy1"]["document_id"]
    assert repo.count_documents(e.conn) == 2 and e.engine.check(e.conn)["consistent"]


def test_recrawl_unchanged_does_not_duplicate_or_reindex(make_env):
    e = make_env()
    first = e.results(e.crawl())
    count = repo.count_documents(e.conn)
    second_id = e.crawl()
    second = e.results(second_id)
    assert {r["status"] for r in second.values()} == {"unchanged"}
    assert {u: r["document_id"] for u, r in second.items()} == {u: r["document_id"] for u, r in first.items()}
    assert repo.count_documents(e.conn) == count and e.engine.check(e.conn)["consistent"]
    import json
    meta = json.loads(repo.get_document(e.conn, second[f"{SITE}/a"]["document_id"]).metadata_json)
    assert meta["crawl_job_id"] == second_id  # metadata was refreshed


def test_recrawl_changed_page_updates_and_reindexes(make_env):
    e = make_env()
    first = e.results(e.crawl())
    doc_id = first[f"{SITE}/b"]["document_id"]
    assert e.search_ids("cosine") == [doc_id]
    e.fetcher.pages[f"{SITE}/b"] = Page(html("Ranking v2", "<p>BM25 saturates term frequency.</p>"))
    second = e.results(e.crawl())
    assert second[f"{SITE}/b"]["status"] == "updated" and second[f"{SITE}/b"]["document_id"] == doc_id
    assert e.search_ids("saturates") == [doc_id] and e.search_ids("cosine") == []
    assert repo.get_document(e.conn, doc_id).title == "Ranking v2" and repo.count_documents(e.conn) == 4
    assert e.engine.check(e.conn)["consistent"]


def test_crawled_url_clashing_with_a_user_document_is_skipped(make_env):
    e = make_env()
    e.engine.add_document(e.conn, title="Mine", text="my own note", category="Notes", source_type="user", source_url=f"{SITE}/b")
    res = e.results(e.crawl())
    assert res[f"{SITE}/b"]["status"] == "skipped" and "non-crawled" in res[f"{SITE}/b"]["error"]
    assert repo.find_by_source_url(e.conn, f"{SITE}/b").source_type == "user"


def test_long_text_is_truncated(make_env):
    e = make_env({f"{SITE}/": Page(html("Long", "<p>" + "word " * 500 + "</p>"))})
    res = e.results(e.crawl(max_document_chars=100))
    import json
    doc = repo.get_document(e.conn, res[f"{SITE}/"]["document_id"])
    assert len(doc.text) <= 100 and json.loads(doc.metadata_json)["truncated"] is True


def test_title_falls_back_to_url(make_env):
    e = make_env({f"{SITE}/": Page("<html><body>no title at all</body></html>")})
    doc = repo.get_document(e.conn, e.results(e.crawl())[f"{SITE}/"]["document_id"])
    assert doc.title == f"{SITE}/"


def test_custom_category(make_env):
    e = make_env()
    e.crawl(category="Handbook")
    assert repo.category_counts(e.conn) == {"Handbook": 4}


# ------------------------------------------------------------------------ job control
def test_status_transitions_are_persisted(make_env):
    e = make_env()
    seen = []
    e.fetcher.on_get = lambda url: seen.append(e.job(job_id)["status"])
    job_id = e.crawl(run=False)
    assert e.job(job_id)["status"] == "queued" and e.job(job_id)["started_at"] is None
    e.crawler.run(job_id)
    assert set(seen) == {"running"}
    assert e.job(job_id)["status"] == "completed" and e.job(job_id)["completed_at"]


def test_progress_counters_are_visible_while_running(make_env):
    e = make_env()
    snapshots = []
    e.fetcher.on_get = lambda url: snapshots.append(e.job(job_id)["pages_crawled"])
    job_id = e.crawl(run=False)
    e.crawler.run(job_id)
    non_robots = [s for u, s in zip(e.fetcher.requests, snapshots)]
    assert non_robots == sorted(non_robots) and non_robots[-1] >= 3  # monotonically growing


def test_cancel_while_running_stops_at_page_boundary(make_env):
    e = make_env()

    def cancel_on_second_page(url):
        if url == f"{SITE}/a":
            crawl_db.request_cancel(e.conn, job_id)

    e.fetcher.on_get = cancel_on_second_page
    job_id = e.crawl(run=False)
    e.crawler.run(job_id)
    job = e.job(job_id)
    assert job["status"] == "cancelled" and job["stop_reason"] == "cancelled" and job["completed_at"]
    assert f"{SITE}/b" not in e.fetcher.requests and f"{SITE}/a/deep" not in e.fetcher.requests
    assert job["pages_crawled"] == 2  # seed and the in-flight page finished; nothing after the flag


def test_cancel_queued_job_never_runs(make_env):
    e = make_env()
    job_id = e.crawl(run=False)
    assert crawl_db.request_cancel(e.conn, job_id) == "cancelled"
    e.crawler.run(job_id)
    assert e.job(job_id)["status"] == "cancelled" and e.fetcher.requests == []


def test_cancel_finished_job_is_refused(env):
    job_id = env.crawl()
    assert crawl_db.request_cancel(env.conn, job_id) is None
    assert env.job(job_id)["status"] == "completed"


def test_terminal_state_cannot_be_overwritten(env):
    job_id = env.crawl()
    crawl_db.finish_job(env.conn, job_id, "failed", stop_reason="error", error="late")
    assert env.job(job_id)["status"] == "completed"


def test_unfinished_jobs_are_failed_at_startup(env):
    queued = env.crawl(run=False)
    running = env.crawl(run=False)
    assert crawl_db.mark_running(env.conn, running)
    done = env.crawl()
    assert crawl_db.interrupt_unfinished(env.conn) == 2
    assert [env.job(j)["status"] for j in (queued, running, done)] == ["failed", "failed", "completed"]
    assert "stopped" in env.job(queued)["error"] and not crawl_db.has_active_job(env.conn)


def test_deleting_a_crawled_document_keeps_the_result_row(env):
    job_id = env.crawl()
    doc_id = env.results(job_id)[f"{SITE}/b"]["document_id"]
    env.engine.delete_document(env.conn, doc_id)
    row = env.results(job_id)[f"{SITE}/b"]
    assert row["document_id"] is None and row["status"] == "indexed"


def test_results_pagination_and_filter(make_env):
    e = make_env({f"{SITE}/": Page(html("Home", "hello" + link("/a", "/b", "/missing"))), f"{SITE}/a": Page(html("A", "aaa")), f"{SITE}/b": Page(html("B", "bbb"))})
    job_id = e.crawl()
    page, total = crawl_db.list_results(e.conn, job_id, limit=2, offset=0)
    assert (len(page), total) == (2, 4)
    failed, n = crawl_db.list_results(e.conn, job_id, limit=10, offset=0, status="failed")
    assert n == 1 and failed[0]["url"] == f"{SITE}/missing"
    errors, count = crawl_db.recent_errors(e.conn, job_id)
    assert count == 1 and errors[0]["error"] == "HTTP 404"
