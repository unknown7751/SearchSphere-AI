"""The real requests/urllib3 stack against a throw-away local HTTP server.

The production SSRF policy is NOT relaxed.  Instead the fake DNS answers with a *public* address and
the final TCP connect is redirected to the local server, so these tests exercise the genuine
validate-then-connect path and can assert exactly which IP the socket was asked to open.
"""
import gzip
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.database import crawl as crawl_db
from app.database.connection import connect
from app.database.schema import init_db
from app.services import http_fetcher
from app.services.crawler import Crawler, CrawlConfig
from app.services.http_fetcher import FetchError, SafeFetcher
from app.services.search_engine import SearchEngine
from app.services.url_validator import UrlRejected
from app.tests.crawler_fakes import PUBLIC_IP, FakeResolver

HTML = b"<html><head><title>Local</title></head><body><p>hello from the local test server</p></body></html>"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, status, body=b"", ctype="text/html; charset=utf-8", headers=None, length=True):
        self.send_response(status)
        if ctype:
            self.send_header("Content-Type", ctype)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if length:
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path
        self.server.seen.append((path, dict(self.headers)))
        if path == "/page":
            self._send(200, HTML)
        elif path == "/redirect":
            self._send(302, b"moved", headers={"Location": "http://127.0.0.1/secret"})
        elif path == "/image":
            self._send(200, b"\x89PNG" * 1000, ctype="image/png")
        elif path == "/declared-big":
            self._send(200, b"x" * 5000)
        elif path == "/stream-big":
            self._send(200, b"y" * 5000, length=False)
        elif path == "/gzip-bomb":
            self._send(200, gzip.compress(b"z" * 200_000), headers={"Content-Encoding": "gzip"})
        elif path == "/slow":
            time.sleep(3)
            self._send(200, HTML)
        elif path == "/cookie":
            self._send(200, HTML, headers={"Set-Cookie": "session=abc"})
        else:
            self._send(404, b"nope")


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.seen = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def connects(monkeypatch, server):
    """Replace only the raw TCP connect; record the (ip, port) the pinned connection asked for."""
    asked = []
    real = http_fetcher._create_connection

    def fake_connect(address, *args, **kwargs):
        asked.append(address)
        return real(("127.0.0.1", server.server_address[1]), *args, **kwargs)

    monkeypatch.setattr(http_fetcher, "_create_connection", fake_connect)
    return asked


@pytest.fixture
def fetcher():
    f = SafeFetcher("TestBot/1.0", FakeResolver())
    yield f
    f.close()


def get(fetcher, path, **kw):
    kw.setdefault("timeout", 5)
    kw.setdefault("max_bytes", 100_000)
    kw.setdefault("accept", ("text/html",))
    return fetcher.get(f"http://site.test{path}", **kw)


def test_fetch_html_connects_to_the_validated_ip(fetcher, server, connects):
    r = get(fetcher, "/page")
    assert (r.status_code, r.content_type, r.charset) == (200, "text/html", "utf-8") and r.body == HTML
    assert connects == [(PUBLIC_IP, 80)]  # the socket target is the validated address, not the host name
    assert server.seen[0][1]["Host"] == "site.test" and server.seen[0][1]["User-Agent"] == "TestBot/1.0"


def test_redirects_are_returned_not_followed(fetcher, server, connects):
    r = get(fetcher, "/redirect")
    assert r.status_code == 302 and r.location == "http://127.0.0.1/secret" and r.body == b""
    assert len(connects) == 1 and [p for p, _ in server.seen] == ["/redirect"]


def test_unwanted_content_type_body_is_not_downloaded(fetcher, connects):
    r = get(fetcher, "/image")
    assert r.content_type == "image/png" and r.body_skipped and r.body == b""


def test_404_is_returned_for_the_crawler_to_judge(fetcher, connects):
    assert get(fetcher, "/missing").status_code == 404


def test_size_limits(fetcher, connects):
    with pytest.raises(FetchError) as e:
        get(fetcher, "/declared-big", max_bytes=1000)
    assert e.value.code == "too_large"
    with pytest.raises(FetchError) as e:
        get(fetcher, "/stream-big", max_bytes=1000)  # no Content-Length: enforced while streaming
    assert e.value.code == "too_large"
    with pytest.raises(FetchError) as e:
        get(fetcher, "/gzip-bomb", max_bytes=10_000)  # limit applies to the *decompressed* size
    assert e.value.code == "too_large"
    assert get(fetcher, "/declared-big", max_bytes=10_000).body == b"x" * 5000


def test_timeout(fetcher, connects):
    start = time.monotonic()
    with pytest.raises(FetchError) as e:
        get(fetcher, "/slow", timeout=1)
    assert e.value.code == "timeout" and time.monotonic() - start < 3


def test_cookies_are_never_kept(fetcher, server, connects):
    get(fetcher, "/cookie")
    get(fetcher, "/page")
    assert all("Cookie" not in headers for _, headers in server.seen)
    assert len(fetcher.session.cookies) == 0


def test_environment_proxies_are_ignored(fetcher, server, connects, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://203.0.113.9:3128")
    monkeypatch.setenv("http_proxy", "http://203.0.113.9:3128")
    assert get(fetcher, "/page").status_code == 200
    assert connects == [(PUBLIC_IP, 80)]  # a proxy would have been the connect target


# -------------------------------------------------------------- connect-time protection
@pytest.mark.parametrize("answer, code", [
    (["127.0.0.1"], "loopback_address"), (["10.1.2.3"], "private_address"),
    (["169.254.169.254"], "metadata_endpoint"), ([PUBLIC_IP, "192.168.0.9"], "private_address"),
])
def test_private_resolution_at_connect_time_is_refused(server, connects, answer, code):
    f = SafeFetcher("TestBot/1.0", FakeResolver({"site.test": answer}))
    with pytest.raises(UrlRejected) as e:
        f.get("http://site.test/page", timeout=5, max_bytes=1000, accept=("text/html",))
    assert e.value.code == code and connects == [] and server.seen == []  # no socket was ever opened
    f.close()


def test_ip_literal_urls_are_refused_by_the_connection_layer_too(server, connects):
    f = SafeFetcher("TestBot/1.0", FakeResolver())
    for host in ("127.0.0.1", "169.254.169.254", "[::1]", "2130706433"):
        with pytest.raises(UrlRejected):
            f.get(f"http://{host}/", timeout=5, max_bytes=1000)
    assert connects == []
    f.close()


def test_dns_failure_is_a_fetch_error(server, connects):
    f = SafeFetcher("TestBot/1.0", FakeResolver({"gone.test": []}))
    with pytest.raises(FetchError) as e:
        f.get("http://gone.test/", timeout=5, max_bytes=1000)
    assert e.value.code == "dns_failure"
    f.close()


def test_connection_failure_is_a_fetch_error(monkeypatch):
    def refuse(address, *a, **k):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(http_fetcher, "_create_connection", refuse)
    f = SafeFetcher("TestBot/1.0", FakeResolver())
    with pytest.raises(FetchError) as e:
        f.get("http://site.test/", timeout=5, max_bytes=1000)
    assert e.value.code == "connection_error"
    f.close()


def test_dns_rebinding_is_defeated(tmp_path, preprocessor, server, connects):
    """The DNS answer changes between validation and connection: public first, internal afterwards.

    The crawler's own validation always sees the public answer.  The connection layer resolves
    again (answers: robots.txt -> public, page -> 127.0.0.1) and refuses to connect to what it
    validated as internal, instead of blindly trusting the earlier check.  A design that validated
    first and then let the HTTP library resolve on its own would have reached 127.0.0.1.
    """
    later_answers = iter([[PUBLIC_IP], ["127.0.0.1"], ["127.0.0.1"], ["127.0.0.1"]])

    def rebinding_resolver(host, port):
        return next(later_answers)

    conn = connect(tmp_path / "r.db")
    init_db(conn)
    seed = "http://rebind.test/"
    job_id = crawl_db.create_job(conn, seed_url=seed, max_pages=3, max_depth=1, timeout_seconds=5, include_subdomains=False, category="C")
    cfg = CrawlConfig(seed, 3, 1, 5, False, "C", 0.0, 10**6, 5, 300, 100, 10**5)
    fetcher = SafeFetcher("TestBot/1.0", rebinding_resolver)  # what the socket layer sees
    Crawler(conn, SearchEngine(preprocessor=preprocessor), fetcher, cfg, resolver=FakeResolver(), sleep=lambda s: None).run(job_id)
    rows, _ = crawl_db.list_results(conn, job_id, limit=10, offset=0)
    assert rows[0]["status"] == "blocked_by_security" and "loopback" in rows[0]["error"]
    assert connects == [(PUBLIC_IP, 80)]  # only the robots.txt connection (validated public) was ever opened
    assert [p for p, _ in server.seen] == ["/robots.txt"]
    fetcher.close()
    conn.close()


def test_full_crawl_over_real_http(tmp_path, preprocessor, server, connects):
    """Crawler + SafeFetcher + requests/urllib3 + local server: robots.txt (404), page, extraction, index."""
    conn = connect(tmp_path / "f.db")
    init_db(conn)
    engine = SearchEngine(preprocessor=preprocessor)
    seed = "http://site.test/page"
    job_id = crawl_db.create_job(conn, seed_url=seed, max_pages=3, max_depth=1, timeout_seconds=5, include_subdomains=False, category="C")
    cfg = CrawlConfig(seed, 3, 1, 5, False, "C", 0.0, 10**6, 5, 300, 100, 10**5)
    fetcher = SafeFetcher("TestBot/1.0", FakeResolver())
    Crawler(conn, engine, fetcher, cfg, resolver=FakeResolver(), sleep=lambda s: None).run(job_id)
    job = crawl_db.get_job(conn, job_id)
    assert job["status"] == "completed" and job["pages_crawled"] == 1
    assert [p for p, _ in server.seen] == ["/robots.txt", "/page"]
    ranking = engine.ranker.rank(engine.preprocessor.analyze("local test server").index_terms)
    assert len(ranking.ranked) == 1
    fetcher.close()
    conn.close()
