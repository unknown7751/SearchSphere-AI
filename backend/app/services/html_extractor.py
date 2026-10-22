"""HTML -> title, visible text, headings and links (BeautifulSoup, stdlib ``html.parser``).

Goal: useful text for technical/documentation pages, not a perfect rendering.  JavaScript is
never executed, so content that only exists after client-side rendering is not extracted.
The extracted text is normalised with the same ``normalize_text`` used for uploaded files; the
usual tokenise/stop-word/stem pipeline then runs when the document is indexed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from app.services.ingestion import normalize_text
from app.services.url_validator import UrlRejected, normalize_url

# Elements whose content is never visible prose.
_DROP = ("script", "style", "noscript", "template", "svg", "canvas", "iframe", "object", "embed", "head")
# Boilerplate that repeats on every page of a site (links inside them are still followed).
_NOISE = ("nav", "footer", "aside")
TITLE_MAX = 300
MAX_HEADINGS = 50


@dataclass
class ExtractedPage:
    title: str
    text: str
    headings: list[dict] = field(default_factory=list)  # [{"level": 2, "text": "..."}]
    links: list[str] = field(default_factory=list)  # normalised absolute http(s) URLs, document order, unique
    description: str | None = None
    noindex: bool = False
    nofollow: bool = False


def _robots_directives(soup: BeautifulSoup) -> set[str]:
    out: set[str] = set()
    for meta in soup.find_all("meta"):
        if (meta.get("name") or "").lower() in ("robots", "searchsphere", "searchspherebot"):
            out.update(t.strip().lower() for t in (meta.get("content") or "").split(","))
    return out


def extract_page(html: bytes | str, base_url: str, *, charset: str | None = None, max_links: int = 200) -> ExtractedPage:
    """Parse ``html`` (fetched from ``base_url``).  Never raises on malformed markup."""
    if isinstance(html, bytes):
        soup = BeautifulSoup(html, "html.parser", from_encoding=charset)
    else:
        soup = BeautifulSoup(html, "html.parser")

    directives = _robots_directives(soup)
    base = base_url
    base_tag = soup.find("base", href=True)
    if base_tag:
        try:
            base = normalize_url(base_tag["href"], base_url)
        except UrlRejected:
            pass

    # Links first: navigation menus are noise for the text but valuable for discovery.
    links: dict[str, None] = {}
    for a in soup.find_all("a", href=True):
        if "nofollow" in [r.lower() for r in (a.get("rel") or [])]:
            continue
        try:
            links.setdefault(normalize_url(a["href"].strip(), base), None)
        except UrlRejected:
            continue  # mailto:, javascript:, tel:, bad ports, credentials ... are simply not followed
        if len(links) >= max_links:
            break

    title_tag = soup.find("title")
    title = " ".join(title_tag.get_text(" ").split()) if title_tag else ""
    description = None
    for meta in soup.find_all("meta"):
        if (meta.get("name") or "").lower() == "description" and meta.get("content"):
            description = " ".join(meta["content"].split())[:500] or None
            break

    for tag in soup(_DROP):
        tag.decompose()
    for tag in soup(_NOISE):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": "navigation"}):
        tag.decompose()
    for tag in soup.find_all(attrs={"hidden": True}):
        tag.decompose()

    headings = []
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = " ".join(h.get_text(" ").split())
        if text:
            headings.append({"level": int(h.name[1]), "text": text[:200]})
            if len(headings) >= MAX_HEADINGS:
                break

    if not title and headings:
        title = headings[0]["text"]
    text = normalize_text((soup.body or soup).get_text("\n"))
    return ExtractedPage(
        title=(title or "")[:TITLE_MAX],
        text=text,
        headings=headings,
        links=list(links),
        description=description,
        noindex="noindex" in directives or "none" in directives,
        nofollow="nofollow" in directives or "none" in directives,
    )
