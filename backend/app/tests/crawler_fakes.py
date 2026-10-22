"""Deterministic stand-ins for the network: no test touches the internet or real DNS."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.http_fetcher import FetchError, FetchResponse

PUBLIC_IP = "93.184.216.34"  # a genuine global address, used as "the internet" in fakes


@dataclass
class Page:
    body: str | bytes = ""
    status: int = 200
    content_type: str | None = "text/html"
    location: str | None = None
    charset: str | None = None


def html(title: str = "", body: str = "", head: str = "") -> str:
    return f"<html><head><title>{title}</title>{head}</head><body>{body}</body></html>"


def redirect(location: str, status: int = 302) -> Page:
    return Page(status=status, location=location, content_type="text/html")


class FakeResolver:
    """host -> addresses; any host not listed resolves to a public address."""

    def __init__(self, table: dict[str, list[str]] | None = None, default: list[str] | None = None):
        self.table = table or {}
        self.default = default if default is not None else [PUBLIC_IP]
        self.calls: list[str] = []

    def __call__(self, host: str, port: int) -> list[str]:
        self.calls.append(host)
        if host in self.table and isinstance(self.table[host], Exception):
            raise self.table[host]
        return list(self.table.get(host, self.default))


@dataclass
class FakeFetcher:
    """Serves pages from a dict keyed by normalised URL; anything else is HTTP 404."""

    pages: dict[str, Page | FetchError] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)
    on_get: object = None  # optional callback(url) run before each response

    def get(self, url, *, timeout, max_bytes, accept=None) -> FetchResponse:
        self.requests.append(url)
        if self.on_get:
            self.on_get(url)
        page = self.pages.get(url, Page("Not found", status=404))
        if isinstance(page, Exception):
            raise page
        body = page.body.encode("utf-8") if isinstance(page.body, str) else page.body
        resp = FetchResponse(url=url, status_code=page.status, content_type=page.content_type,
                             charset=page.charset, location=page.location)
        if page.status in (301, 302, 303, 307, 308):
            return resp
        if accept is not None and page.content_type not in accept:
            resp.body_skipped = True
            return resp
        if len(body) > max_bytes:
            raise FetchError("too_large", "The response is larger than the limit.")
        resp.body = body
        return resp

    def close(self) -> None:
        pass
