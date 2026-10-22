import pytest

from app.services.robots import MAX_CRAWL_DELAY, RobotsFile, RobotsPolicy

ORIGIN = "https://example.com"
RULES = """User-agent: *
Disallow: /private/
Disallow: /tmp
Allow: /private/public.html

User-agent: SearchSphereBot
Disallow: /bot-only/
Crawl-delay: 2
"""


def policy(file: RobotsFile | Exception, calls: list | None = None) -> RobotsPolicy:
    def fetch(url):
        if calls is not None:
            calls.append(url)
        if isinstance(file, Exception):
            raise file
        return file

    return RobotsPolicy(fetch, "SearchSphereBot")


def test_rules_for_our_agent_apply():
    p = policy(RobotsFile(200, RULES))
    assert p.check(f"{ORIGIN}/index.html").allowed
    assert not p.check(f"{ORIGIN}/bot-only/x").allowed
    assert p.check(f"{ORIGIN}/private/secret").allowed  # the generic group is ignored: a specific group exists


def test_generic_group_applies_without_specific_group():
    # The standard-library parser applies the FIRST matching rule in file order (RFC 9309 says longest
    # match), so an Allow exception must precede the broader Disallow.  The reverse order errs on the
    # side of not crawling (documented limitation).
    p = policy(RobotsFile(200, "User-agent: *\nAllow: /private/public.html\nDisallow: /private/\n"))
    assert not p.check(f"{ORIGIN}/private/secret").allowed
    assert p.check(f"{ORIGIN}/private/public.html").allowed
    reverse = policy(RobotsFile(200, "User-agent: *\nDisallow: /private/\nAllow: /private/public.html\n"))
    assert not reverse.check(f"{ORIGIN}/private/public.html").allowed
    assert p.check(f"{ORIGIN}/other").allowed
    assert p.check(f"{ORIGIN}/private/secret").reason == "disallowed by robots.txt"


def test_crawl_delay_is_read_and_capped():
    p = policy(RobotsFile(200, RULES))
    assert p.cached_crawl_delay(f"{ORIGIN}/") is None  # not fetched yet: never triggers a fetch
    p.check(f"{ORIGIN}/")
    assert p.cached_crawl_delay(f"{ORIGIN}/") == 2.0
    big = policy(RobotsFile(200, "User-agent: *\nCrawl-delay: 9999\n"))
    big.check(f"{ORIGIN}/")
    assert big.cached_crawl_delay(f"{ORIGIN}/") == MAX_CRAWL_DELAY


def test_disallow_everything():
    p = policy(RobotsFile(200, "User-agent: *\nDisallow: /\n"))
    assert not p.check(f"{ORIGIN}/").allowed


@pytest.mark.parametrize("status", [404, 410, 400, 429])
def test_missing_robots_allows_everything(status):
    assert policy(RobotsFile(status)).check(f"{ORIGIN}/anything").allowed


@pytest.mark.parametrize("status", [401, 403, 500, 502, 503])
def test_restricted_or_failing_robots_blocks_everything(status):
    decision = policy(RobotsFile(status)).check(f"{ORIGIN}/anything")
    assert not decision.allowed and str(status) in decision.reason


def test_unreachable_robots_blocks_everything():
    decision = policy(RobotsFile(None, problem="robots.txt unreachable (timeout)")).check(f"{ORIGIN}/x")
    assert not decision.allowed and "unreachable" in decision.reason
    assert not policy(RuntimeError("boom")).check(f"{ORIGIN}/x").allowed  # a crashing fetch must fail closed


def test_rules_are_cached_per_origin():
    calls: list[str] = []
    p = policy(RobotsFile(404), calls)
    for path in ("/a", "/b", "/c"):
        p.check(f"{ORIGIN}{path}")
    p.check("https://other.example.com/a")
    p.check("http://example.com/a")  # different scheme = different origin
    assert calls == [
        "https://example.com/robots.txt",
        "https://other.example.com/robots.txt",
        "http://example.com/robots.txt",
    ]
