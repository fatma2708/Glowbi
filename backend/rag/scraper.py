"""Polite scraper: RSS feeds + single pages -> clean article text -> chunks -> store.

Politeness rules: respects robots.txt, identifies itself with a User-Agent, waits between requests,
skips articles already eaten, and stores the source URL so every answer can cite it.
"""
import re
import time
import urllib.robotparser
from urllib.parse import urlparse

import feedparser
import httpx
import trafilatura
import yaml

from backend import config
from backend.rag.chunker import chunk_text, guess_category
from backend.rag.store import store

_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_request: dict[str, float] = {}


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": config.USER_AGENT}, timeout=20, follow_redirects=True)


def allowed(url: str, client: httpx.Client) -> bool:
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = client.get(base + "/robots.txt")
            if r.status_code in (401, 403) or r.status_code >= 500:
                rp.disallow_all = True  # blocked or down: we can't know the rules, so assume "no"
            else:
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            _robots_cache[base] = rp
        except httpx.HTTPError:
            _robots_cache[base] = None  # unreachable -> be safe, skip
    rp = _robots_cache[base]
    return rp is not None and rp.can_fetch(config.USER_AGENT, url)


def polite_get(url: str, client: httpx.Client) -> str | None:
    host = urlparse(url).netloc
    wait = config.SCRAPER_DELAY - (time.time() - _last_request.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.time()
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.text
    except httpx.HTTPError as e:
        print(f"  ✗ {url}: {e}")
        return None


def ingest_page(url: str, client: httpx.Client, source: str, category: str | None = None,
                title: str | None = None) -> int:
    if store.has(url):
        return 0
    if not allowed(url, client):
        print(f"  ⛔ robots.txt disallows {url}")
        return 0
    html = polite_get(url, client)
    if not html:
        return 0
    text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_precision=True)
    if not text or len(text) < 300:
        return 0
    meta = trafilatura.extract_metadata(html)
    title = title or (meta.title if meta and meta.title else url)
    category = category if category and category != "auto" else guess_category(title + " " + text)
    n = store.add_document(url, title, source, category, chunk_text(text))
    print(f"  🍪 {title[:70]} ({n} chunks, {category})")
    return n


def ingest_feed(feed: dict, client: httpx.Client, max_items: int) -> int:
    print(f"📰 {feed['name']}")
    if not allowed(feed["url"], client):
        print(f"  ⛔ robots.txt disallows {feed['url']}")
        return 0
    from backend.rag.databases import load_state, save_state
    state = load_state()
    backfill = int(feed.get("backfill_pages", 0))
    pages = [feed["url"]]
    if backfill and feed["url"] not in state.get("backfilled", []):
        sep = "&" if "?" in feed["url"] else "?"
        pages += [f"{feed['url']}{sep}paged={n}" for n in range(2, backfill + 1)]
        max_items = 10_000  # first run: eat the archive
    entries, seen_links = [], set()
    for page_url in pages:
        raw = polite_get(page_url, client)
        if not raw:
            break
        new = [e for e in feedparser.parse(raw).entries if e.get("link") not in seen_links]
        if not new:  # ran past the last page
            break
        seen_links.update(e.get("link") for e in new)
        entries += new
    if len(pages) > 1 and entries:  # a failed fetch must not cancel the backfill
        state.setdefault("backfilled", []).append(feed["url"])
        save_state(state)
    eaten = 0
    for entry in entries[:max_items]:
        link = entry.get("link")
        if not link or store.has(link):
            continue
        cat = feed.get("category") or "auto"
        # Some feeds ship the full article in content:encoded — use it and skip a request
        content = (entry.get("content") or [{}])[0].get("value") if entry.get("content") else None
        if content and len(content) > 1500:
            text = trafilatura.extract(content) or ""
            if len(text) > 300:
                if cat == "auto":
                    cat = guess_category(entry.get("title", "") + " " + text)
                eaten += store.add_document(link, entry.get("title", link), feed["name"], cat, chunk_text(text)) > 0
                print(f"  🍪 {entry.get('title', link)[:70]} (from feed)")
                continue
        eaten += ingest_page(link, client, feed["name"], cat, entry.get("title")) > 0
    return eaten


def sitemap_urls(sitemap_url: str, client: httpx.Client, include: str | None, limit: int, depth: int = 0) -> list[str]:
    """Read a sitemap (or sitemap index) and return the newest article URLs matching `include` (regex)."""
    xml = polite_get(sitemap_url, client)
    if not xml:
        return []
    entries = re.findall(r"<(sitemap|url)>\s*<loc>\s*([^<]+?)\s*</loc>(?:.*?<lastmod>([^<]+)</lastmod>)?",
                         xml, re.S)
    children = sorted([e for e in entries if e[0] == "sitemap"], key=lambda e: e[2], reverse=True)
    urls = [(e[1], e[2]) for e in entries if e[0] == "url"]
    if children and depth < 2:  # sitemap index: newest post-sitemaps first
        for _, loc, _ in children:
            if include and "post" not in loc and "article" not in loc and "blog" not in loc and len(children) > 3:
                continue
            urls += [(u, "") for u in sitemap_urls(loc, client, include, limit, depth + 1)]
            if len(urls) >= 2000:
                break
    if include:
        urls = [u for u in urls if re.search(include, u[0])]
    urls.sort(key=lambda u: u[1], reverse=True)
    return [u[0] for u in urls[:2000]]


def ingest_sitemap(sm: dict, client: httpx.Client, max_items: int) -> int:
    print(f"🗺️  {sm.get('name', sm['url'])}")
    if not allowed(sm["url"], client):
        print(f"  ⛔ robots.txt disallows {sm['url']}")
        return 0
    eaten = attempts = 0
    for url in sitemap_urls(sm["url"], client, sm.get("include"), max_items):
        if eaten >= max_items or attempts >= max_items * 3:
            break
        if store.has(url):  # already eaten: free skip, no request
            continue
        attempts += 1
        eaten += ingest_page(url, client, sm.get("name", urlparse(url).netloc), sm.get("category")) > 0
    return eaten


def test_source(url: str) -> None:
    """Dry run: check robots.txt + what text Glowbi would extract, without storing anything."""
    with _client() as client:
        ok = allowed(url, client)
        print(f"robots.txt allows {config.USER_AGENT!r}: {ok}")
        if not ok:
            return
        raw = polite_get(url, client)
        if not raw:
            return
        if "<rss" in raw[:500] or "<feed" in raw[:500]:
            feed = feedparser.parse(raw)
            print(f"RSS/Atom feed ✅  {len(feed.entries)} items. Latest:")
            for e in feed.entries[:5]:
                full = bool(e.get("content")) and len(e["content"][0].get("value", "")) > 1500
                print(f"  - {e.get('title')}  ({'full text in feed' if full else 'summary only'})\n    {e.get('link')}")
        elif "<urlset" in raw[:1000] or "<sitemapindex" in raw[:1000]:
            print("Sitemap ✅ newest URLs:", *sitemap_urls(url, client, None, 5), sep="\n  ")
        else:
            text = trafilatura.extract(raw, favor_precision=True) or ""
            meta = trafilatura.extract_metadata(raw)
            print(f"Page title: {meta.title if meta else '?'}\nExtracted {len(text)} chars "
                  f"({'OK ✅' if len(text) > 300 else 'too little ❌ (JS-rendered or paywalled?)'})")
            print("-" * 60 + "\n" + text[:700])


def load_sources() -> dict:
    with open(config.SOURCES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def feed_glowbi(max_items_per_feed: int | None = None, include_products: bool = True,
                force_databases: bool = False) -> dict:
    """One 'meal': pull fresh articles from every source + refresh databases that are due. Returns counts."""
    from backend.rag.databases import ingest_databases
    from backend.rag.openbeautyfacts import ingest_products

    _robots_cache.clear()  # re-read robots.txt each meal: rules change, and outages end
    sources = load_sources()
    limit = max_items_per_feed or sources.get("max_items_per_feed", 10)
    articles = 0
    with _client() as client:
        for feed in sources.get("rss_feeds") or []:
            articles += ingest_feed(feed, client, limit)
        for sm in sources.get("sitemaps") or []:
            articles += ingest_sitemap(sm, client, sm.get("max_items", limit))
        for page in sources.get("pages") or []:
            articles += ingest_page(page["url"], client, urlparse(page["url"]).netloc, page.get("category")) > 0
    products = 0
    obf = sources.get("open_beauty_facts") or {}
    if include_products and obf.get("enabled"):
        products = ingest_products(obf.get("search_terms", []), obf.get("products_per_term", 15))
    database_items = ingest_databases(sources.get("databases") or {}, force_databases) if include_products else 0
    return {"articles": int(articles), "products": products, "database_items": database_items}


def ingest_seed() -> int:
    """Load the hand-written starter knowledge in data/seed/*.md (works offline)."""
    n = 0
    for path in sorted(config.SEED_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        title, body = lines[0].lstrip("# ").strip(), "\n".join(lines[1:])
        cat = path.stem.split("_")[0]
        n += store.add_document(f"seed://{path.name}", title, "Glowbi starter notes", cat,
                                chunk_text(body, max_chars=450, overlap=0)) > 0
    return n
