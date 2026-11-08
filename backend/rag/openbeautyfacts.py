"""Open Beauty Facts: open, crowd-sourced database of cosmetics (ingredients, categories, labels).
Licence: ODbL — free to reuse with attribution. API docs: https://openbeautyfacts.github.io/openbeautyfacts-server/
"""
import time

import httpx

from backend import config
from backend.rag.store import store

API = "https://world.openbeautyfacts.org/cgi/search.pl"
FIELDS = "code,product_name,brands,categories,ingredients_text,ingredients_text_en,labels,quantity,url"


def product_image(code: str) -> str | None:
    """Fetched only when a product is about to be shown; the caller caches the result."""
    try:
        r = httpx.get(f"https://world.openbeautyfacts.org/api/v2/product/{code}", timeout=4,
                      params={"fields": "image_front_url,image_front_small_url"}, headers={"User-Agent": config.USER_AGENT})
        r.raise_for_status()
        p = r.json().get("product") or {}
        return p.get("image_front_small_url") or p.get("image_front_url")
    except (httpx.HTTPError, ValueError) as e:
        print(f"[products] no image for {code}: {e}")
        return None


def search_products(term: str, page_size: int = 10) -> list[dict]:
    params = {"search_terms": term, "search_simple": 1, "action": "process", "json": 1,
              "page_size": page_size, "fields": FIELDS}
    try:
        r = httpx.get(API, params=params, headers={"User-Agent": config.USER_AGENT}, timeout=20)
        r.raise_for_status()
        return r.json().get("products", [])
    except (httpx.HTTPError, ValueError) as e:
        print(f"  ✗ Open Beauty Facts '{term}': {e}")
        return []


def product_to_text(p: dict) -> tuple[str, str] | None:
    name = (p.get("product_name") or "").strip()
    ingredients = (p.get("ingredients_text_en") or p.get("ingredients_text") or "").strip()
    if not name or not ingredients:
        return None
    title = f"{name} — {p.get('brands', 'unknown brand')}"
    text = (f"Product: {name}\nBrand: {p.get('brands', '?')}\nCategories: {p.get('categories', '?')}\n"
            f"Size: {p.get('quantity', '?')}\nLabels: {p.get('labels', '-')}\nIngredients (INCI): {ingredients}")
    return title, text


def ingest_products(terms: list[str], per_term: int = 15) -> int:
    added = 0
    for term in terms:
        print(f"🧴 Open Beauty Facts: {term}")
        for p in search_products(term, per_term):
            item = product_to_text(p)
            if not item:
                continue
            url = p.get("url") or f"https://world.openbeautyfacts.org/product/{p.get('code')}"
            meta = {"brand": p.get("brands"), "product_url": url, "image_url": None, "price": None, "source": "Open Beauty Facts"}
            added += store.add_document(url, item[0], "Open Beauty Facts", "products", [item[1]], meta) > 0
        time.sleep(config.SCRAPER_DELAY)
    return added


def live_lookup(product_query: str) -> list[dict]:
    """Called at chat time when the user asks about a specific product."""
    out = []
    for p in search_products(product_query, 3):
        item = product_to_text(p)
        if item:
            url = p.get("url") or f"https://world.openbeautyfacts.org/product/{p.get('code')}"
            out.append({"text": item[1], "url": url, "title": item[0], "source": "Open Beauty Facts",
                        "category": "products", "score": 1.0})
    return out
