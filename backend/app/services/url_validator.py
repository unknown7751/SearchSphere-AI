"""URL parsing, normalisation and SSRF-safe destination validation for the crawler.

Two different questions are answered here, and the difference matters:

1. *Is this URL string acceptable?*  (:func:`normalize_url`) - scheme, credentials, port,
   length, hostname blocklist.  This is only a syntactic filter.
2. *Where would a connection actually go?*  (:func:`resolve_destination`) - the host name is
   resolved to IP addresses and **every** address must be public.  ``http://example.com``
   looks harmless, but ``example.com`` may resolve to ``192.168.x.x``; only the resolved
   address says where the request would really land.

``resolve_destination`` is used twice: by :func:`validate_url` before a request is planned
and by the HTTP connection layer (``http_fetcher``) at connect time, where the *validated IP
itself* is used for the socket.  That removes the validate-then-resolve-again gap that DNS
rebinding relies on.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import string
from dataclasses import dataclass
from typing import Callable, Sequence
from urllib.parse import urljoin, urlsplit

ALLOWED_SCHEMES = ("http", "https")
DEFAULT_PORTS = {"http": 80, "https": 443}
# Only conventional web ports are crawlable: a crawler that can be pointed at any port of a
# public host is a (small) port scanner.
ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})
MAX_URL_LENGTH = 2048

# ---------------------------------------------------------------------------- error type
# Rejections that mean "this destination is dangerous or forbidden" (reported as
# ``blocked_by_security``).  Everything else is a plain failure (bad URL, unresolvable host).
SECURITY_CODES = frozenset(
    {
        "unsupported_scheme",
        "credentials_in_url",
        "blocked_hostname",
        "blocked_port",
        "loopback_address",
        "unspecified_address",
        "link_local_address",
        "private_address",
        "multicast_address",
        "metadata_endpoint",
        "reserved_address",
    }
)


class UrlRejected(Exception):
    """A URL that must not be requested.  ``code`` is stable and machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def is_security(self) -> bool:
        return self.code in SECURITY_CODES


# ---------------------------------------------------------------------- IP classification
# Cloud metadata services.  Most of these are also link-local/private, but naming them gives
# a precise error and also covers metadata addresses that are *not* in a private range.
_METADATA_IPS = frozenset(
    ipaddress.ip_address(a)
    for a in (
        "169.254.169.254",  # AWS / Azure / GCP / OpenStack / DigitalOcean ...
        "169.254.170.2",    # AWS ECS task metadata
        "100.100.100.200",  # Alibaba Cloud
        "168.63.129.16",    # Azure WireServer (a public-looking address)
        "192.0.0.192",      # Oracle Cloud
        "fd00:ec2::254",    # AWS IPv6 metadata
    )
)
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_IPV4_COMPATIBLE = ipaddress.ip_network("::/96")
_TEREDO = ipaddress.ip_network("2001::/32")


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 address merely wraps (mapped, 6to4, NAT64, IPv4-compatible)."""
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip.sixtofour is not None:
        return ip.sixtofour
    if ip in _NAT64 or ip in _IPV4_COMPATIBLE:
        return ipaddress.IPv4Address(ip.packed[-4:])
    return None


def classify_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return a reason code if ``ip`` is not a public unicast address, else ``None``.

    Blocked: loopback, unspecified, link-local (incl. 169.254.0.0/16), private (10/8,
    172.16/12, 192.168/16, fc00::/7), multicast, cloud-metadata addresses and every other
    non-global range (CGNAT, documentation, benchmarking, reserved ...).  IPv6 addresses that
    merely wrap an IPv4 address (``::ffff:127.0.0.1``, 6to4, NAT64) are judged by the wrapped
    address, so they cannot be used to smuggle a private IPv4 destination past the check.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.is_loopback:
            return "loopback_address"
        if ip.is_unspecified:
            return "unspecified_address"
        embedded = _embedded_ipv4(ip)
        if embedded is not None:
            return classify_ip(embedded)
        if ip in _TEREDO:
            return "reserved_address"
    if ip in _METADATA_IPS:
        return "metadata_endpoint"
    if ip.is_loopback:
        return "loopback_address"
    if ip.is_unspecified:
        return "unspecified_address"
    if ip.is_link_local:
        return "link_local_address"
    if ip.is_multicast:
        return "multicast_address"
    if ip.is_private:
        return "private_address"
    if not ip.is_global:
        return "reserved_address"
    return None


_IP_MESSAGES = {
    "loopback_address": "loopback addresses are not allowed",
    "unspecified_address": "unspecified addresses (0.0.0.0 / ::) are not allowed",
    "link_local_address": "link-local addresses are not allowed",
    "private_address": "private network addresses are not allowed",
    "multicast_address": "multicast addresses are not allowed",
    "metadata_endpoint": "cloud metadata endpoints are not allowed",
    "reserved_address": "reserved or non-public addresses are not allowed",
}

_NUMERIC_HOST = re.compile(r"^(0x[0-9a-f]*|\d+)(\.(0x[0-9a-f]*|\d+)){0,3}$", re.IGNORECASE)


def _parse_loose_ipv4(host: str) -> ipaddress.IPv4Address:
    """Parse the legacy ``inet_aton`` forms an OS resolver accepts: ``2130706433``,
    ``0x7f.1``, ``0177.0.0.1``, ``127.1``.  Attackers use them to dodge string checks."""
    parts = host.split(".")
    values = []
    for p in parts:
        try:
            if p.lower().startswith("0x"):
                values.append(int(p[2:] or "0", 16))
            elif len(p) > 1 and p.startswith("0"):
                values.append(int(p, 8))
            else:
                values.append(int(p, 10))
        except ValueError as exc:
            raise UrlRejected("invalid_url", "The host is not a valid IP address.") from exc
    *head, last = values
    if any(v > 255 for v in head) or last >= 256 ** (5 - len(parts)):
        raise UrlRejected("invalid_url", "The host is not a valid IP address.")
    number = last
    for i, v in enumerate(head):
        number |= v << (8 * (3 - i))
    return ipaddress.IPv4Address(number)


def parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Return the IP address if ``host`` is an IP literal (in any notation), else ``None``."""
    bare = host.strip("[]")
    try:
        return ipaddress.ip_address(bare.split("%", 1)[0])
    except ValueError:
        pass
    if _NUMERIC_HOST.match(host):
        return _parse_loose_ipv4(host)
    return None


# --------------------------------------------------------------------- hostname blocklist
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost", "ip6-localhost", "ip6-loopback", "localhost.localdomain",
        "metadata", "metadata.google.internal", "instance-data", "kubernetes", "kubernetes.default",
    }
)
_BLOCKED_SUFFIXES = (
    ".localhost", ".local", ".internal", ".localdomain", ".home.arpa", ".lan", ".intranet",
    ".corp", ".private", ".home", ".svc", ".cluster.local",
)


def check_hostname(host: str) -> None:
    """Reject obviously internal host *names* (``localhost``, ``intranet``, ``*.internal`` ...).

    This is a cheap early filter only; the real protection is checking the resolved IPs.
    """
    if host in _BLOCKED_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
        raise UrlRejected("blocked_hostname", f"The host {host!r} is an internal host name.")
    if "." not in host:
        raise UrlRejected("blocked_hostname", f"The host {host!r} is a single-label (internal) host name.")


# ----------------------------------------------------------------------- name resolution
Resolver = Callable[[str, int], Sequence[str]]


def system_resolver(host: str, port: int) -> list[str]:
    """Resolve ``host`` with the operating system resolver; returns IP strings."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0].split("%", 1)[0] for info in infos]


def resolve_destination(host: str, port: int, resolver: Resolver | None = None) -> list[str]:
    """Return the public IP addresses ``host`` maps to, or raise :class:`UrlRejected`.

    * IP literals (any notation) are classified directly, without DNS.
    * Host names are resolved and **all** returned addresses must be public: a name with one
      public and one private A record is rejected, because the connection layer could pick
      either.
    * ``socket.gaierror`` is not caught here: callers decide whether a DNS failure is a
      validation error (:func:`validate_url`) or a connection error (the HTTP layer).
    """
    literal = parse_ip_literal(host)
    if literal is not None:
        addresses = [str(literal)]
    else:
        check_hostname(host)
        addresses = list(dict.fromkeys((resolver or system_resolver)(host, port)))
        if not addresses:
            raise UrlRejected("unresolvable_host", f"The host {host!r} could not be resolved.")
    for text in addresses:
        try:
            ip = ipaddress.ip_address(text)
        except ValueError as exc:
            raise UrlRejected("unresolvable_host", f"The host {host!r} resolved to an invalid address.") from exc
        reason = classify_ip(ip)
        if reason:
            subject = "The address" if literal is not None else f"The host {host!r} resolves to an address that"
            raise UrlRejected(reason, f"{subject} is blocked: {_IP_MESSAGES[reason]}.")
    return addresses


# ------------------------------------------------------------------------ normalisation
_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
_PATH_SAFE = frozenset("/:@!$&'()*+,;=")
_QUERY_SAFE = frozenset("/?:@!$&'()*+,;=")
_HEX = frozenset(string.hexdigits)
_FORBIDDEN = re.compile(r"[\x00-\x20\x7f\\]")  # control characters, whitespace and backslashes


def _normalize_percent(text: str, safe: frozenset[str]) -> str:
    """Upper-case percent escapes, decode escaped unreserved characters, escape illegal ones."""
    out: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "%" and i + 2 < len(text) and text[i + 1] in _HEX and text[i + 2] in _HEX:
            ch = chr(int(text[i + 1 : i + 3], 16))
            out.append(ch if ch in _UNRESERVED else "%" + text[i + 1 : i + 3].upper())
            i += 3
        elif c in _UNRESERVED or c in safe:
            out.append(c)
            i += 1
        else:
            out.append("".join(f"%{b:02X}" for b in c.encode("utf-8", "replace")))
            i += 1
    return "".join(out)


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 section 5.2.4: resolve ``.`` and ``..`` segments."""
    segments = path.split("/")
    out: list[str] = []
    for i, seg in enumerate(segments):
        last = i == len(segments) - 1
        if seg == ".":
            if last:
                out.append("")
        elif seg == "..":
            if len(out) > 1:
                out.pop()
            if last:
                out.append("")
        else:
            out.append(seg)
    result = "/".join(out)
    return result if result.startswith("/") else "/" + result


def normalize_url(url: str, base: str | None = None) -> str:
    """Return the canonical form of an http(s) URL, or raise :class:`UrlRejected`.

    Normalisation: relative URLs are resolved against ``base``; scheme and host are lower-cased;
    internationalised host names become punycode; a trailing dot and default ports are removed;
    the fragment is dropped; percent-escapes are normalised; ``.``/``..`` segments are
    resolved; an empty path becomes ``/``.

    Deliberately *not* done, because it can change the meaning of a URL: stripping the trailing
    slash of non-root paths (``/docs`` and ``/docs/`` may differ), re-ordering or removing
    query parameters, and lower-casing the path.

    Rejected: other schemes (``file:``, ``ftp:``, ``javascript:``, ``data:`` ...), embedded
    credentials (``user:pass@host``), whitespace/control characters/backslashes, over-long
    URLs, missing hosts and ports outside :data:`ALLOWED_PORTS`.
    """
    if not isinstance(url, str):
        raise UrlRejected("invalid_url", "The URL must be a string.")
    url = url.strip()
    if base:
        url = urljoin(base, url)
    if not url:
        raise UrlRejected("invalid_url", "The URL is empty.")
    if len(url) > MAX_URL_LENGTH:
        raise UrlRejected("url_too_long", f"The URL is longer than {MAX_URL_LENGTH} characters.")
    if _FORBIDDEN.search(url):
        raise UrlRejected("invalid_url", "The URL contains whitespace, control characters or backslashes.")
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise UrlRejected("invalid_url", "The URL is malformed.") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        if not scheme:
            raise UrlRejected("invalid_url", "The URL must start with http:// or https://.")
        raise UrlRejected("unsupported_scheme", f"The scheme {scheme!r} is not supported; only http and https are allowed.")
    if not parts.netloc:
        raise UrlRejected("invalid_url", "The URL has no host.")
    if "@" in parts.netloc:
        raise UrlRejected("credentials_in_url", "URLs containing credentials (user:password@host) are not allowed.")
    try:
        port = parts.port
        host = parts.hostname
    except ValueError as exc:
        raise UrlRejected("invalid_url", "The URL has an invalid port or host.") from exc
    if not host or "%" in host:
        raise UrlRejected("invalid_url", "The URL has an invalid host.")
    host = host.rstrip(".")
    if not host:
        raise UrlRejected("invalid_url", "The URL has an invalid host.")
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise UrlRejected("invalid_url", "The host name is not a valid internationalised domain name.") from exc
    if port is not None and not 0 < port < 65536:
        raise UrlRejected("invalid_url", "The port is out of range.")
    effective_port = port or DEFAULT_PORTS[scheme]
    if effective_port not in ALLOWED_PORTS:
        raise UrlRejected("blocked_port", f"Port {effective_port} is not allowed (allowed: {sorted(ALLOWED_PORTS)}).")

    netloc = f"[{host}]" if ":" in host else host
    if port is not None and port != DEFAULT_PORTS[scheme]:
        netloc += f":{port}"
    path = _remove_dot_segments(_normalize_percent(parts.path, _PATH_SAFE)) if parts.path else "/"
    query = _normalize_percent(parts.query, _QUERY_SAFE)
    return f"{scheme}://{netloc}{path}" + (f"?{query}" if query else "")


# --------------------------------------------------------------------------- validation
@dataclass(frozen=True)
class ValidatedUrl:
    """A URL that passed every check, with the public addresses it resolved to."""

    url: str
    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...]

    @property
    def origin(self) -> str:
        return f"{self.scheme}://{self.host}" + (f":{self.port}" if self.port != DEFAULT_PORTS[self.scheme] else "")


def validate_url(url: str, resolver: Resolver | None = None, *, base: str | None = None) -> ValidatedUrl:
    """Full validation of a URL *and its network destination*; raises :class:`UrlRejected`.

    Steps: normalise (scheme/credentials/port/length) -> hostname blocklist -> resolve the host
    -> require every resolved address to be public.  Call this for the seed URL, for every
    queued URL and for **every redirect target**.
    """
    normalized = normalize_url(url, base)
    parts = urlsplit(normalized)
    host = parts.hostname or ""
    port = parts.port or DEFAULT_PORTS[parts.scheme]
    try:
        addresses = resolve_destination(host, port, resolver)
    except socket.gaierror as exc:
        raise UrlRejected("unresolvable_host", f"The host {host!r} could not be resolved (DNS failure).") from exc
    return ValidatedUrl(normalized, parts.scheme, host, port, tuple(addresses))


def host_in_scope(host: str, seed_host: str, include_subdomains: bool = False) -> bool:
    """Crawl-scope policy: the seed's own host (``www.`` is treated as equivalent), and
    optionally its subdomains.  Other sites are never followed."""
    def bare(h: str) -> str:
        return h[4:] if h.startswith("www.") else h

    host, seed = bare(host), bare(seed_host)
    return host == seed or (include_subdomains and host.endswith("." + seed))
