from app.services.html_extractor import extract_page

BASE = "https://docs.example.com/guide/intro.html"

PAGE = """<!doctype html>
<html><head>
  <title>  Intro   to  Search </title>
  <meta name="description" content="A short   description">
  <style>.x { color: red }</style>
  <script>var secret = "SCRIPTWORD";</script>
</head><body>
  <nav><a href="/menu">Menu</a> NAVWORD</nav>
  <h1>Information Retrieval</h1>
  <p>An <b>inverted</b> index maps terms to documents.</p>
  <noscript>NOSCRIPTWORD</noscript>
  <h2>Ranking</h2><p>TF-IDF weights terms.</p>
  <a href="page2.html#top">next</a>
  <a href="/abs/path?x=1">abs</a>
  <a href="https://other.example.org/x">external</a>
  <a href="mailto:a@b.c">mail</a><a href="javascript:void(0)">js</a><a href="tel:123">tel</a>
  <a href="page2.html">dup</a>
  <a href="/private" rel="nofollow">nf</a>
  <footer>FOOTERWORD</footer>
</body></html>"""


def test_title_text_headings_description():
    page = extract_page(PAGE, BASE)
    assert page.title == "Intro to Search"
    assert "inverted index maps terms to documents" in " ".join(page.text.split())
    assert "TF-IDF weights terms." in page.text
    assert [(h["level"], h["text"]) for h in page.headings] == [(1, "Information Retrieval"), (2, "Ranking")]
    assert page.description == "A short description"


def test_noise_is_removed():
    text = extract_page(PAGE, BASE).text
    for noise in ("SCRIPTWORD", "NOSCRIPTWORD", "NAVWORD", "FOOTERWORD", "color: red"):
        assert noise not in text


def test_links_are_resolved_normalised_deduplicated():
    links = extract_page(PAGE, BASE).links
    assert links == [
        "https://docs.example.com/menu",  # nav links are harvested even though nav text is dropped
        "https://docs.example.com/guide/page2.html",  # fragment removed, duplicate collapsed
        "https://docs.example.com/abs/path?x=1",
        "https://other.example.org/x",
    ]  # mailto/javascript/tel and rel=nofollow are dropped


def test_base_tag_changes_relative_resolution():
    html = '<html><head><base href="https://cdn.example.com/x/"></head><body><a href="a.html">a</a>text</body></html>'
    assert extract_page(html, BASE).links == ["https://cdn.example.com/x/a.html"]


def test_title_falls_back_to_first_heading():
    assert extract_page("<body><h2>Only heading</h2><p>text</p></body>", BASE).title == "Only heading"
    assert extract_page("<body>just text</body>", BASE).title == ""


def test_meta_robots_directives():
    p = extract_page('<head><meta name="robots" content="NoIndex, nofollow"></head><body>x</body>', BASE)
    assert p.noindex and p.nofollow
    p = extract_page('<head><meta name="robots" content="index,follow"></head><body>x</body>', BASE)
    assert not p.noindex and not p.nofollow
    assert extract_page('<meta name="robots" content="none"><body>x</body>', BASE).noindex


def test_malformed_html_does_not_raise():
    page = extract_page("<html><body><p>Unclosed <b>bold <a href='/x'>link<div>text", BASE)
    assert "Unclosed" in page.text and page.links == ["https://docs.example.com/x"]
    assert extract_page("", BASE).text == ""
    assert extract_page(b"\x00\xff\xfe garbage <<<>>>", BASE).text is not None


def test_charset_is_honoured_for_bytes():
    body = "<html><head><title>Café</title></head><body>crème brûlée</body></html>".encode("latin-1")
    page = extract_page(body, BASE, charset="iso-8859-1")
    assert page.title == "Café" and "crème" in page.text
    utf8 = extract_page("<body>naïve</body>".encode("utf-8"), BASE)
    assert "naïve" in utf8.text


def test_link_cap():
    html = "<body>" + "".join(f'<a href="/p{i}">x</a>' for i in range(50)) + "</body>"
    assert len(extract_page(html, BASE, max_links=10).links) == 10
