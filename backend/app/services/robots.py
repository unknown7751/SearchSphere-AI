"""robots.txt policy for the crawler (parsing by the standard library's ``RobotFileParser``).

Policy when robots.txt cannot be read normally (conservative, documented in PHASE3.md):

=====================================  =========================================================
robots.txt response                    Decision
=====================================  =========================================================
200 with a body                        rules apply
404 / 410 / other 4xx except 401, 403  no rules exist -> everything is allowed
401 / 403                              access restricted -> everything is disallowed
5xx, timeout, connection error,        cannot tell -> everything is disallowed (we never guess
unsafe redirect, oversized, non-text   that a site is open to crawling)
=====================================  =========================================================

``Crawl-delay`` is honoured (capped).  The standard-library parser implements the original
exclusion standard: it does not understand ``*`` / ``$`` wildcards inside paths.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

MAX_CRAWL_DELAY = 5.0  # seconds; larger Crawl-delay values are capped so a job cannot stall


@dataclass
class RobotsFile:
    """Result of fetching an origin's robots.txt: ``status`` is None when it could not be fetched."""

    status: int | None
    body: str = ""
    problem: str | None = None


@dataclass
class _Rules:
    parser: RobotFileParser | None  # None -> use ``allow_all``
    allow_all: bool
    reason: str

    def can_fetch(self, agent: str, url: str) -> bool:
        return self.allow_all if self.parser is None else self.parser.can_fetch(agent, url)

    def crawl_delay(self, agent: str) -> float | None:
        if self.parser is None:
            return None
        delay = self.parser.crawl_delay(agent)
        return min(float(delay), MAX_CRAWL_DELAY) if delay is not None else None


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    reason: str


class RobotsPolicy:
    """Caches one rule set per origin; ``fetch(robots_url)`` supplies the (already validated) response."""

    def __init__(self, fetch: Callable[[str], RobotsFile], user_agent_token: str):
        self._fetch = fetch
        self._agent = user_agent_token
        self._cache: dict[str, _Rules] = {}

    def _rules_for(self, origin: str) -> _Rules:
        rules = self._cache.get(origin)
        if rules is None:
            try:
                rules = self._interpret(self._fetch(origin + "/robots.txt"))
            except Exception as exc:  # any failure to fetch means "unknown" -> disallow
                rules = _Rules(None, False, f"robots.txt could not be fetched ({type(exc).__name__}); treating the site as disallowed")
            self._cache[origin] = rules
        return rules

    @staticmethod
    def _interpret(file: RobotsFile) -> _Rules:
        if file.status is None:
            return _Rules(None, False, file.problem or "robots.txt unavailable; treating the site as disallowed")
        if file.status == 200:
            parser = RobotFileParser()
            parser.parse(file.body.splitlines())
            return _Rules(parser, False, "robots.txt rules apply")
        if file.status in (401, 403):
            return _Rules(None, False, f"robots.txt returned HTTP {file.status}; treating the site as disallowed")
        if 400 <= file.status < 500:
            return _Rules(None, True, f"no robots.txt (HTTP {file.status}); everything is allowed")
        return _Rules(None, False, f"robots.txt returned HTTP {file.status}; treating the site as disallowed")

    @staticmethod
    def origin_of(url: str) -> str:
        p = urlsplit(url)
        return f"{p.scheme}://{p.netloc}"

    def check(self, url: str) -> RobotsDecision:
        rules = self._rules_for(self.origin_of(url))
        if rules.can_fetch(self._agent, url):
            return RobotsDecision(True, rules.reason)
        if rules.parser is not None:
            return RobotsDecision(False, "disallowed by robots.txt")
        return RobotsDecision(False, rules.reason)

    def cached_crawl_delay(self, url: str) -> float | None:
        """Crawl-delay for an origin whose robots.txt is already cached (never triggers a fetch)."""
        rules = self._cache.get(self.origin_of(url))
        return rules.crawl_delay(self._agent) if rules else None
