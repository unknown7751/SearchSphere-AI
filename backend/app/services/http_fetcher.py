"""Safe single-request HTTP fetching for the crawler.

Security properties of :class:`SafeFetcher`:

* **Destination pinning.**  The socket is opened by our own connection class.  It resolves the
  host, requires every address to be public (``url_validator.resolve_destination``) and then
  connects to that *validated IP address*.  There is no second, independent DNS lookup between
  validation and connection, so a DNS-rebinding answer cannot swap in a private address.  TLS
  still uses the original host name for SNI and certificate verification.
* **No redirects here.**  ``allow_redirects=False``: every hop is returned to the crawler, which
  re-validates it (scheme, destination, robots.txt) before following it.
* **No proxies, no ambient credentials.**  Environment proxies/netrc are ignored (a proxy would
  make the *proxy* the destination and bypass the IP checks); cookies are never stored.
* **Bounded.**  Connect/read timeouts plus an overall deadline, a decoded-size cap (also protects
  against compression bombs) and a content-type allow-list checked *before* the body is read.

Remaining limitation (documented in PHASE3.md): host-name resolution itself uses the OS resolver
and cannot be given a timeout from Python.
"""
from __future__ import annotations

import http.cookiejar
import socket
import time
from dataclasses import dataclass, field
from typing import Protocol, Sequence

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NameResolutionError, NewConnectionError
from urllib3.util.connection import create_connection as _create_connection

from app.services.url_validator import Resolver, UrlRejected, resolve_destination

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class FetchError(Exception):
    """A request that failed for a reason other than a security rejection."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class FetchResponse:
    url: str
    status_code: int
    content_type: str | None = None  # lower-cased media type without parameters
    charset: str | None = None
    location: str | None = None  # Location header (raw) for redirects
    body: bytes = b""
    body_skipped: bool = False  # content type was not in ``accept`` so the body was not downloaded
    headers: dict[str, str] = field(default_factory=dict)


class Fetcher(Protocol):
    """What the crawler needs from an HTTP client (tests substitute a deterministic fake)."""

    def get(self, url: str, *, timeout: float, max_bytes: int, accept: Sequence[str] | None = None) -> FetchResponse: ...

    def close(self) -> None: ...


# --------------------------------------------------------------------- pinned connections
def _pinned_socket(conn: HTTPConnection, resolver: Resolver | None) -> socket.socket:
    """Open a socket to a validated public IP (replaces urllib3's ``_new_conn`` lookup)."""
    host = conn._dns_host  # the name from the URL (not the proxy)
    try:
        addresses = resolve_destination(host, conn.port, resolver)  # raises UrlRejected for non-public targets
    except socket.gaierror as exc:
        raise NameResolutionError(conn.host, conn, exc) from exc
    except UrlRejected as exc:
        if exc.code == "unresolvable_host":
            raise NameResolutionError(conn.host, conn, socket.gaierror(exc.message)) from exc
        raise
    last_error: OSError | None = None
    for ip in addresses:
        try:
            return _create_connection(
                (ip, conn.port), conn.timeout, source_address=conn.source_address, socket_options=conn.socket_options
            )
        except OSError as exc:  # socket.timeout is a subclass of OSError
            last_error = exc
    if isinstance(last_error, socket.timeout):
        raise ConnectTimeoutError(conn, f"Connection to {conn.host} timed out (connect timeout={conn.timeout})")
    raise NewConnectionError(conn, f"Failed to establish a new connection: {last_error}")


def _make_connection_classes(resolver: Resolver | None):
    class PinnedHTTPConnection(HTTPConnection):
        def _new_conn(self) -> socket.socket:
            return _pinned_socket(self, resolver)

    class PinnedHTTPSConnection(HTTPSConnection):
        def _new_conn(self) -> socket.socket:
            return _pinned_socket(self, resolver)

    class PinnedHTTPPool(HTTPConnectionPool):
        ConnectionCls = PinnedHTTPConnection

    class PinnedHTTPSPool(HTTPSConnectionPool):
        ConnectionCls = PinnedHTTPSConnection

    return PinnedHTTPPool, PinnedHTTPSPool


class PinnedAdapter(HTTPAdapter):
    """requests adapter whose connections go through :func:`_pinned_socket`."""

    def __init__(self, resolver: Resolver | None = None):
        self._pools = _make_connection_classes(resolver)
        super().__init__(max_retries=0, pool_connections=4, pool_maxsize=2)

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {"http": self._pools[0], "https": self._pools[1]}


# ------------------------------------------------------------------------------ fetcher
class SafeFetcher:
    """Performs one validated GET request per call; see the module docstring."""

    def __init__(self, user_agent: str, resolver: Resolver | None = None):
        self.session = requests.Session()
        self.session.trust_env = False  # ignore HTTP(S)_PROXY, .netrc and REQUESTS_CA_BUNDLE tricks
        self.session.proxies = {}
        self.session.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))  # accept/send no cookies
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                "Accept-Language": "en",
            }
        )
        adapter = PinnedAdapter(resolver)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def close(self) -> None:
        self.session.close()

    def get(self, url: str, *, timeout: float, max_bytes: int, accept: Sequence[str] | None = None) -> FetchResponse:
        deadline = time.monotonic() + timeout * 2  # overall cap; socket timeouts alone allow slow-drip responses
        try:
            response = self.session.get(
                url, timeout=(min(timeout, 5.0), timeout), allow_redirects=False, stream=True, verify=True
            )
        except UrlRejected:
            raise
        except requests.exceptions.SSLError as exc:
            raise FetchError("ssl_error", "TLS/SSL negotiation or certificate verification failed.") from exc
        except requests.exceptions.Timeout as exc:
            raise FetchError("timeout", "The request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            if _is_dns_failure(exc):
                raise FetchError("dns_failure", "The host name could not be resolved.") from exc
            raise FetchError("connection_error", "The connection failed.") from exc
        except requests.exceptions.RequestException as exc:
            raise FetchError("request_error", f"The request failed ({type(exc).__name__}).") from exc

        try:
            content_type, charset = _parse_content_type(response.headers.get("Content-Type"))
            result = FetchResponse(
                url=url,
                status_code=response.status_code,
                content_type=content_type,
                charset=charset,
                location=response.headers.get("Location"),
                headers={k.lower(): v for k, v in response.headers.items()},
            )
            if response.status_code in REDIRECT_STATUSES or response.status_code >= 400:
                return result  # the body of a redirect or an error page is irrelevant
            if accept is not None and content_type not in accept:
                result.body_skipped = True
                return result
            declared = response.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                raise FetchError("too_large", f"The response is larger than the {max_bytes}-byte limit.")
            chunks, size = [], 0
            try:
                for chunk in response.iter_content(chunk_size=16384):
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError("too_large", f"The response is larger than the {max_bytes}-byte limit.")
                    if time.monotonic() > deadline:
                        raise FetchError("timeout", "The response took too long to download.")
                    chunks.append(chunk)
            except requests.exceptions.Timeout as exc:
                raise FetchError("timeout", "The request timed out while reading the response.") from exc
            except requests.exceptions.RequestException as exc:
                raise FetchError("connection_error", "The response could not be read completely.") from exc
            result.body = b"".join(chunks)
            return result
        finally:
            response.close()


def _is_dns_failure(exc: BaseException) -> bool:
    seen = 0
    while exc is not None and seen < 8:
        if isinstance(exc, (NameResolutionError, socket.gaierror)):
            return True
        args = getattr(exc, "args", ())
        nxt = getattr(exc, "reason", None) or (args[0] if args and isinstance(args[0], BaseException) else None)
        exc, seen = nxt or exc.__cause__, seen + 1
    return False


def _parse_content_type(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    media, *params = [p.strip() for p in value.split(";")]
    charset = None
    for p in params:
        if p.lower().startswith("charset="):
            charset = p.split("=", 1)[1].strip().strip("\"'").lower() or None
    return media.lower() or None, charset


__all__ = ["FetchError", "FetchResponse", "Fetcher", "SafeFetcher", "PinnedAdapter", "REDIRECT_STATUSES"]
