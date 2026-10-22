import ipaddress
import socket

import pytest

from app.services.url_validator import (
    UrlRejected,
    classify_ip,
    host_in_scope,
    normalize_url,
    parse_ip_literal,
    resolve_destination,
    validate_url,
)
from app.tests.crawler_fakes import PUBLIC_IP, FakeResolver


def code_of(fn, *args, **kwargs) -> str:
    with pytest.raises(UrlRejected) as exc:
        fn(*args, **kwargs)
    return exc.value.code


# ------------------------------------------------------------------ normalisation
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://example.com", "https://example.com/"),
        ("HTTPS://Example.COM/Path", "https://example.com/Path"),  # host lower-cased, path case kept
        ("https://example.com/page#section", "https://example.com/page"),  # fragment dropped
        ("https://example.com:443/a", "https://example.com/a"),  # default port dropped
        ("http://example.com:80/a", "http://example.com/a"),
        ("http://example.com:8080/a", "http://example.com:8080/a"),  # non-default kept
        ("https://example.com./a", "https://example.com/a"),  # trailing dot
        ("https://example.com/a/./b/../c", "https://example.com/a/c"),  # dot segments
        ("https://example.com/%7euser/%2e%2e/x", "https://example.com/x"),  # escaped dots/unreserved decoded first
        ("https://example.com/a%2fb", "https://example.com/a%2Fb"),  # reserved escapes kept, upper-cased
        ("https://example.com/café", "https://example.com/caf%C3%A9"),  # non-ASCII escaped
        ("https://example.com/docs/", "https://example.com/docs/"),  # trailing slash is significant
        ("https://example.com/docs", "https://example.com/docs"),
        ("https://example.com?x=1", "https://example.com/?x=1"),
        ("https://example.com/?", "https://example.com/"),  # empty query dropped
        ("https://bücher.example/", "https://xn--bcher-kva.example/"),  # IDN -> punycode
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_normalize_is_idempotent():
    once = normalize_url("HTTPS://Example.com:443/a/../b/%7Efoo/?q=a%20b#frag".replace(" ", ""))
    assert normalize_url(once) == once


def test_relative_urls_resolve_against_base():
    base = "https://example.com/docs/guide/index.html"
    assert normalize_url("../api/", base) == "https://example.com/docs/api/"
    assert normalize_url("/root", base) == "https://example.com/root"
    assert normalize_url("//cdn.example.com/x", base) == "https://cdn.example.com/x"
    assert normalize_url("page2.html#top", base) == "https://example.com/docs/guide/page2.html"
    assert normalize_url("?p=2", base) == "https://example.com/docs/guide/index.html?p=2"


def test_distinct_urls_stay_distinct():
    assert normalize_url("https://example.com/a?x=1&y=2") != normalize_url("https://example.com/a?y=2&x=1")
    assert normalize_url("https://example.com/Docs") != normalize_url("https://example.com/docs")
    assert normalize_url("http://example.com/") != normalize_url("https://example.com/")


@pytest.mark.parametrize(
    "url, code",
    [
        ("file:///etc/passwd", "unsupported_scheme"),
        ("ftp://example.com/x", "unsupported_scheme"),
        ("javascript:alert(1)", "unsupported_scheme"),
        ("data:text/html,<h1>x</h1>", "unsupported_scheme"),
        ("about:blank", "unsupported_scheme"),
        ("chrome://settings", "unsupported_scheme"),
        ("gopher://example.com/", "unsupported_scheme"),
        ("mailto:a@example.com", "unsupported_scheme"),
        ("example.com/page", "invalid_url"),  # no scheme at all
        ("", "invalid_url"),
        ("   ", "invalid_url"),
        ("http://", "invalid_url"),
        ("https://user:pass@example.com/", "credentials_in_url"),
        ("http://example.com@127.0.0.1/", "credentials_in_url"),  # classic host-confusion trick
        ("http://example.com\\@127.0.0.1/", "invalid_url"),
        ("http://exa mple.com/", "invalid_url"),
        ("http://example.com/\x00", "invalid_url"),
        ("https://example.com:99999/", "invalid_url"),
        ("https://example.com:abc/", "invalid_url"),
        ("https://example.com:22/", "blocked_port"),
        ("http://example.com:6379/", "blocked_port"),
        ("https://" + "a" * 3000 + ".com/", "url_too_long"),
        ("https://%31%32%37.0.0.1/", "invalid_url"),  # percent-encoded host
    ],
)
def test_normalize_rejects(url, code):
    assert code_of(normalize_url, url) == code


# ------------------------------------------------------------------ IP classification
@pytest.mark.parametrize(
    "ip, reason",
    [
        ("127.0.0.1", "loopback_address"),
        ("127.255.255.254", "loopback_address"),
        ("::1", "loopback_address"),
        ("0.0.0.0", "unspecified_address"),
        ("::", "unspecified_address"),
        ("10.0.0.1", "private_address"),
        ("10.255.255.255", "private_address"),
        ("172.16.0.1", "private_address"),
        ("172.31.255.255", "private_address"),
        ("192.168.1.1", "private_address"),
        ("fc00::1", "private_address"),
        ("fd12:3456::1", "private_address"),
        ("169.254.1.1", "link_local_address"),
        ("fe80::1", "link_local_address"),
        ("169.254.169.254", "metadata_endpoint"),
        ("169.254.170.2", "metadata_endpoint"),
        ("fd00:ec2::254", "metadata_endpoint"),
        ("168.63.129.16", "metadata_endpoint"),  # Azure WireServer is not in any private range
        ("224.0.0.1", "multicast_address"),
        ("ff02::1", "multicast_address"),
        ("100.64.0.1", "reserved_address"),  # carrier-grade NAT
        ("::ffff:127.0.0.1", "loopback_address"),  # IPv4-mapped IPv6 must be judged by the wrapped address
        ("::ffff:10.1.2.3", "private_address"),
        ("::ffff:169.254.169.254", "metadata_endpoint"),
        ("64:ff9b::7f00:1", "loopback_address"),  # NAT64-wrapped loopback
        ("2002:7f00:1::", "loopback_address"),  # 6to4-wrapped loopback
    ],
)
def test_classify_blocks(ip, reason):
    assert classify_ip(ipaddress.ip_address(ip)) == reason


@pytest.mark.parametrize("ip", ["192.0.0.1", "240.0.0.1", "198.18.0.1", "192.0.2.1", "2001:db8::1", "2001:0:4136:e378::1"])
def test_classify_blocks_other_non_public_ranges(ip):
    assert classify_ip(ipaddress.ip_address(ip)) is not None  # label depends on Python's range tables; blocked either way


@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "172.32.0.1", "172.15.255.255"])
def test_classify_allows_public(ip):
    assert classify_ip(ipaddress.ip_address(ip)) is None


@pytest.mark.parametrize(
    "host, expected",
    [
        ("127.0.0.1", "127.0.0.1"),
        ("2130706433", "127.0.0.1"),  # decimal
        ("0x7f000001", "127.0.0.1"),  # hex
        ("0x7f.0.0.1", "127.0.0.1"),
        ("0177.0.0.1", "127.0.0.1"),  # octal
        ("127.1", "127.0.0.1"),  # short form
        ("[::1]", "::1"),
        ("example.com", None),
        ("1example.com", None),
    ],
)
def test_ip_literal_notations(host, expected):
    ip = parse_ip_literal(host)
    assert (str(ip) if ip else None) == expected


@pytest.mark.parametrize("host", ["2130706433", "0x7f.0.0.1", "0177.0.0.1", "127.1", "[::1]", "[::ffff:7f00:1]"])
def test_obfuscated_loopback_forms_are_blocked(host):
    assert code_of(validate_url, f"http://{host}/") == "loopback_address"


def test_invalid_numeric_host_is_rejected():
    assert code_of(validate_url, "http://999.999.999.999/") == "invalid_url"
    assert code_of(validate_url, "http://4294967296/") == "invalid_url"


# --------------------------------------------------------------------- validate_url
@pytest.mark.parametrize(
    "url, code",
    [
        ("http://localhost/", "blocked_hostname"),
        ("http://LOCALHOST:8080/", "blocked_hostname"),
        ("http://localhost./", "blocked_hostname"),
        ("http://foo.localhost/", "blocked_hostname"),
        ("http://127.0.0.1/", "loopback_address"),
        ("http://127.0.0.1:8080/admin", "loopback_address"),
        ("http://0.0.0.0/", "unspecified_address"),
        ("http://[::1]/", "loopback_address"),
        ("http://192.168.1.1/", "private_address"),
        ("http://10.0.0.1/", "private_address"),
        ("http://172.16.5.4/", "private_address"),
        ("http://[fd00::1]/", "private_address"),
        ("http://169.254.169.254/latest/meta-data/", "metadata_endpoint"),
        ("http://169.254.10.10/", "link_local_address"),
        ("http://[fe80::1]/", "link_local_address"),
        ("http://metadata.google.internal/computeMetadata/v1/", "blocked_hostname"),
        ("http://intranet/", "blocked_hostname"),  # single label
        ("http://printer.local/", "blocked_hostname"),
        ("http://db.internal/", "blocked_hostname"),
        ("file:///etc/passwd", "unsupported_scheme"),
        ("ftp://example.com", "unsupported_scheme"),
        ("javascript:alert(1)", "unsupported_scheme"),
    ],
)
def test_validate_rejects_dangerous_urls(url, code):
    assert code_of(validate_url, url, FakeResolver()) == code


def test_security_codes_are_flagged_as_security():
    with pytest.raises(UrlRejected) as exc:
        validate_url("http://10.0.0.1/", FakeResolver())
    assert exc.value.is_security
    with pytest.raises(UrlRejected) as exc:
        validate_url("not a url", FakeResolver())
    assert not exc.value.is_security


def test_public_url_passes_and_reports_addresses():
    v = validate_url("https://Docs.Example.com/a#x", FakeResolver())
    assert (v.url, v.host, v.port, v.addresses) == ("https://docs.example.com/a", "docs.example.com", 443, (PUBLIC_IP,))
    assert v.origin == "https://docs.example.com"


def test_ip_literal_never_uses_dns():
    resolver = FakeResolver()
    validate_url("http://93.184.216.34/", resolver)
    assert resolver.calls == []


# The core lesson: a harmless-looking *name* is only as safe as the address it resolves to.
@pytest.mark.parametrize(
    "answers, code",
    [
        (["127.0.0.1"], "loopback_address"),
        (["192.168.0.10"], "private_address"),
        (["169.254.169.254"], "metadata_endpoint"),
        (["::1"], "loopback_address"),
        (["::ffff:10.0.0.1"], "private_address"),
        ([PUBLIC_IP, "10.0.0.5"], "private_address"),  # one bad record among good ones is enough
        (["10.0.0.5", PUBLIC_IP], "private_address"),
    ],
)
def test_hostname_resolving_to_internal_address_is_blocked(answers, code):
    resolver = FakeResolver({"looks-innocent.example.com": answers})
    assert code_of(validate_url, "https://looks-innocent.example.com/", resolver) == code


def test_dns_failures():
    assert code_of(validate_url, "https://nxdomain.example.com/", FakeResolver({"nxdomain.example.com": []})) == "unresolvable_host"

    def boom(host, port):
        raise socket.gaierror(-2, "Name or service not known")

    assert code_of(validate_url, "https://nxdomain.example.com/", boom) == "unresolvable_host"
    with pytest.raises(socket.gaierror):  # resolve_destination leaves DNS errors to the caller
        resolve_destination("nxdomain.example.com", 443, boom)


# ------------------------------------------------------------------------ scope
def test_scope_policy():
    assert host_in_scope("docs.example.com", "docs.example.com")
    assert host_in_scope("www.example.com", "example.com")  # www is equivalent
    assert host_in_scope("example.com", "www.example.com")
    assert not host_in_scope("blog.example.com", "example.com")  # subdomains need an explicit opt-in
    assert host_in_scope("blog.example.com", "example.com", include_subdomains=True)
    assert not host_in_scope("evilexample.com", "example.com", include_subdomains=True)
    assert not host_in_scope("example.com.evil.com", "example.com", include_subdomains=True)
    assert not host_in_scope("other.org", "example.com")
