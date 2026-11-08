"""Beauty databases -> knowledge chunks. All sources here are open/licensed for reuse (see config/sources.yaml).

Each connector runs at most every `refresh_days` (tracked in data/feed_state.json) so the 12-hour background
feeder doesn't re-download big datasets.
"""
import csv
import gzip
import html
import json
import re
import time
import xml.etree.ElementTree as ET
import zlib

import httpx

from backend import config
from backend.rag.store import store

STATE_PATH = config.DATA_DIR / "feed_state.json"


# ---------------------------------------------------------------- state helpers
def load_state() -> dict:
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}


def save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def due(name: str, refresh_days: float) -> bool:
    last = load_state().get("databases", {}).get(name, 0)
    return time.time() - last > refresh_days * 86400


def mark_done(name: str):
    state = load_state()
    state.setdefault("databases", {})[name] = time.time()
    save_state(state)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": config.USER_AGENT}, timeout=60, follow_redirects=True)


def _clean_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


# ---------------------------------------------------------------- Open Beauty Facts (ODbL)
OBF_DUMP = "https://static.openbeautyfacts.org/data/openbeautyfacts-products.jsonl.gz"


def _obf_text(p: dict) -> tuple[str, str] | None:
    name = (p.get("product_name") or p.get("product_name_en") or p.get("product_name_fr") or "").strip()
    ingredients = (p.get("ingredients_text_en") or p.get("ingredients_text") or p.get("ingredients_text_fr") or "").strip()
    if not name or len(ingredients) < 20:
        return None
    title = f"{name} — {p.get('brands') or 'unknown brand'}"
    text = (f"Product: {name}\nBrand: {p.get('brands') or '?'}\nCategories: {p.get('categories') or '?'}\n"
            f"Labels: {p.get('labels') or '-'}\nIngredients (INCI): {ingredients[:1500]}")
    return title, text


def obf_dump(max_products: int = 3000, countries: list[str] | None = None) -> int:
    """Streams the nightly JSONL export and stops after `max_products` usable products (no full download)."""
    added = seen = 0

    def handle(line: bytes) -> bool:  # returns True when we have enough
        nonlocal added, seen
        if not line.strip():
            return False
        seen += 1
        try:
            p = json.loads(line)
        except ValueError:
            return False
        if countries and not set(countries) & set(p.get("countries_tags") or []):
            return False
        item = _obf_text(p)
        if item:
            url = f"https://world.openbeautyfacts.org/product/{p.get('code')}"
            meta = {"brand": p.get("brands"), "product_url": url, "image_url": None, "price": None, "source": "Open Beauty Facts"}
            added += store.add_document(url, item[0], "Open Beauty Facts", "products", [item[1]], meta) > 0
        return added >= max_products

    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    buf = b""
    with _client() as c, c.stream("GET", OBF_DUMP) as r:
        r.raise_for_status()
        for chunk in r.iter_bytes(1 << 16):
            buf += d.decompress(chunk)
            *lines, buf = buf.split(b"\n")
            if any(handle(line) for line in lines):
                print(f"  🧴 Open Beauty Facts dump: {added} products (scanned {seen})")
                return added
    for line in (buf + d.flush()).split(b"\n"):
        if handle(line):
            break
    print(f"  🧴 Open Beauty Facts dump: {added} products (scanned {seen}, end of file)")
    return added


# ---------------------------------------------------------------- EU CosIng via CosIng Checker API (CC BY 4.0)
COSING_API = "https://cosingchecker.com/api/v1"


def cosing_ingredients(names: list[str]) -> int:
    """Official EU ingredient data: INCI name, functions, description, restrictions."""
    added = 0
    with _client() as c:
        for name in names:
            try:
                r = c.get(f"{COSING_API}/ingredients/", params={"q": name, "per_page": 30})
                if r.status_code == 429:
                    time.sleep(60)
                    r = c.get(f"{COSING_API}/ingredients/", params={"q": name, "per_page": 30})
                r.raise_for_status()
                results = r.json().get("results", [])
            except (httpx.HTTPError, ValueError) as e:
                print(f"  ✗ CosIng '{name}': {e}")
                continue
            if not results:
                continue
            q = name.upper()
            best = next((x for x in results if (x.get("inci_name") or "").upper() == q), None) or \
                min(results, key=lambda x: len(x.get("inci_name") or "x" * 999))
            inci = best.get("inci_name") or name
            funcs = ", ".join(best.get("functions") or [best.get("function") or "?"]).lower()
            text = (f"Cosmetic ingredient: {inci} (also searched as '{name}')\n"
                    f"What it does in cosmetics (EU CosIng functions): {funcs}\n"
                    f"Description: {best.get('description') or '-'}\n"
                    f"EU restriction: {best.get('restriction') or 'none listed in the inventory'}\n"
                    f"CAS: {best.get('cas_number') or '-'}")
            url = "https://cosingchecker.com" + (best.get("url") or f"/ingredients/{best.get('slug')}/")
            added += store.add_document(url, f"Ingredient: {inci.title()}", "EU CosIng (via CosIng Checker, CC BY 4.0)",
                                        "ingredients", [text]) > 0
            time.sleep(0.6)  # API limit is 120 requests/minute
        # The 26+ EU-regulated fragrance allergens (useful for "I'm allergic to fragrance")
        try:
            r = c.get(f"{COSING_API}/allergens/", params={"per_page": 100})
            r.raise_for_status()
            data = r.json()
            items = data.get("results", data) if isinstance(data, dict) else data
            lines = []
            for a in items if isinstance(items, list) else []:
                fields = {k: v for k, v in a.items() if isinstance(v, (str, int)) and k not in ("id", "slug", "url")}
                lines.append("; ".join(f"{k}: {v}" for k, v in fields.items()))
            if lines:
                text = ("EU-regulated fragrance allergens. Products must list these on the label above certain "
                        "concentrations. People with fragrance allergy should check labels for them:\n" + "\n".join(lines))
                from backend.rag.chunker import chunk_text
                added += store.add_document("https://cosingchecker.com/allergens/", "EU fragrance allergens list",
                                            "EU CosIng (via CosIng Checker, CC BY 4.0)", "ingredients",
                                            chunk_text(text, 900, 0)) > 0
        except (httpx.HTTPError, ValueError, AttributeError) as e:
            print(f"  ✗ CosIng allergens: {e}")
    print(f"  🧪 CosIng: {added} ingredient entries")
    return added


# ---------------------------------------------------------------- MedlinePlus (US NLM, free, attribute MedlinePlus.gov)
MEDLINE_WS = "https://wsearch.nlm.nih.gov/ws/query"


def medlineplus(terms: list[str], lang: str = "en") -> int:
    """Trustworthy medical basics for skin/hair/nail conditions, so Glowbi knows when to say 'see a dermatologist'."""
    db = "healthTopicsSpanish" if lang == "es" else "healthTopics"
    added = 0
    with _client() as c:
        for term in terms:
            try:
                r = c.get(MEDLINE_WS, params={"db": db, "term": term, "rettype": "brief", "retmax": 2,
                                              "tool": "glowbi"})
                r.raise_for_status()
                root = ET.fromstring(r.text)
            except (httpx.HTTPError, ET.ParseError) as e:
                print(f"  ✗ MedlinePlus '{term}': {e}")
                continue
            for doc in root.iter("document"):
                fields = {}
                for ct in doc.findall("content"):
                    fields.setdefault(ct.get("name"), "".join(ct.itertext()))
                title = _clean_html(fields.get("title", term))
                summary = _clean_html(fields.get("FullSummary", ""))
                if len(summary) < 200:
                    continue
                from backend.rag.chunker import chunk_text
                added += store.add_document(doc.get("url"), f"{title} (MedlinePlus)", "MedlinePlus.gov",
                                            "skin-health", chunk_text(f"{title}\n{summary}")) > 0
            time.sleep(1.0)  # NLM asks for max ~85 requests/minute
    print(f"  🩺 MedlinePlus: {added} topics")
    return added


# ---------------------------------------------------------------- Makeup API (free, no key; product data is a few years old)
MAKEUP_API = "https://makeup-api.herokuapp.com/api/v1/products.json"


def _makeup_meta(p: dict, url: str) -> dict:
    image = p.get("image_link")
    return {"brand": p.get("brand"), "product_url": p.get("product_link") or url, "price": p.get("price"), "source": "Makeup API",
            "image_url": ("https:" + image) if image and image.startswith("//") else image}


def backfill_meta(product_types: list[str]) -> dict:
    """Adds meta to products stored before the column existed. Open Beauty Facts images stay lazy (see products.py)."""
    done = {"Open Beauty Facts": 0, "Makeup API": 0, "local": 0}
    with store._conn() as c:
        rows = c.execute("""SELECT d.url, d.source, ch.text FROM documents d JOIN chunks ch ON ch.doc_id = d.id
                            WHERE d.category IN ('products', 'makeup') AND d.meta IS NULL GROUP BY d.id""").fetchall()
    for url, source, text in rows:
        brand = re.search(r"^Brand: (.*)$", text, re.M)
        if source == "Open Beauty Facts":
            store.set_meta(url, {"brand": brand.group(1) if brand else None, "product_url": url, "image_url": None, "price": None, "source": source})
            done[source] += 1
        elif url.startswith("local://"):  # Sephora CSV: no image or page, so "View" is a search
            name = re.search(r"^Product: (.*)$", text, re.M)
            query = f"{brand.group(1) if brand else ''} {name.group(1) if name else ''}".strip().replace(" ", "+")
            store.set_meta(url, {"brand": brand.group(1) if brand else None, "image_url": None, "price": None, "source": source,
                                 "product_url": f"https://www.sephora.com/search?keyword={query}"})
            done["local"] += 1
    with _client() as c:
        for ptype in product_types:
            r = c.get(MAKEUP_API, params={"product_type": ptype})
            r.raise_for_status()
            for p in r.json():
                url = p.get("product_link") or p.get("product_api_url") or f"makeup-api://{p.get('id')}"
                if store.has(url):
                    store.set_meta(url, _makeup_meta(p, url))
                    done["Makeup API"] += 1
            time.sleep(1.0)
    return done


def makeup_api(product_types: list[str], per_type: int = 60) -> int:
    added = 0
    with _client() as c:
        for ptype in product_types:
            try:
                r = c.get(MAKEUP_API, params={"product_type": ptype})
                r.raise_for_status()
                products = r.json()[:per_type]
            except (httpx.HTTPError, ValueError) as e:
                print(f"  ✗ Makeup API '{ptype}': {e}")
                continue
            for p in products:
                desc = _clean_html(p.get("description") or "")
                if not p.get("name") or len(desc) < 40:
                    continue
                shades = [s.get("colour_name") for s in (p.get("product_colors") or []) if s.get("colour_name")]
                text = (f"Makeup product: {p['name'].strip()} by {p.get('brand') or '?'}\n"
                        f"Type: {p.get('product_type')} {('(' + p['category'] + ')') if p.get('category') else ''}\n"
                        f"Price: {p.get('price') or '?'} {p.get('currency') or ''} | Rating: {p.get('rating') or '-'}\n"
                        f"Tags: {', '.join(p.get('tag_list') or []) or '-'}\n"
                        f"Shades: {len(shades)} ({', '.join(shades[:8])}{'…' if len(shades) > 8 else ''})\n"
                        f"Description: {desc[:1200]}")
                url = p.get("product_link") or p.get("product_api_url") or f"makeup-api://{p.get('id')}"
                added += store.add_document(url, f"{p['name'].strip()} — {p.get('brand')}", "Makeup API",
                                            "makeup", [text], _makeup_meta(p, url)) > 0
    print(f"  💄 Makeup API: {added} products")
    return added


# ---------------------------------------------------------------- Local CSV (e.g. Kaggle Sephora dataset)
def local_csv(path: str, columns: dict, source: str, category: str = "products", limit: int = 5000) -> int:
    """Generic loader. `columns` maps our fields -> CSV headers, e.g. Kaggle 'Sephora Products and Skincare
    Reviews' product_info.csv: {id: product_id, name: product_name, brand: brand_name, ingredients: ingredients,
    highlights: highlights, category: secondary_category, price: price_usd, rating: rating}"""
    p = config.ROOT / path
    if not p.exists():
        print(f"  ⏭️  {path} not found (download it first, see README)")
        return 0
    opener = gzip.open if p.suffix == ".gz" else open
    added = 0
    with opener(p, "rt", encoding="utf-8", errors="replace") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i >= limit:
                break
            get = lambda k: (row.get(columns.get(k, ""), "") or "").strip()
            name, ingredients = get("name"), get("ingredients")
            ingredients = re.sub(r"^\[|\]$|^'|'$", "", ingredients).replace("', '", " ")
            if not name:
                continue
            text = "\n".join(f"{label}: {val}" for label, val in [
                ("Product", name), ("Brand", get("brand")), ("Category", get("category")),
                ("Price", get("price")), ("Rating", get("rating")),
                ("Highlights", re.sub(r"[\[\]']", "", get("highlights"))),
                ("Ingredients", ingredients[:1500])] if val)
            uid = get("id") or f"{i}"
            query = f"{get('brand')} {name}".strip().replace(" ", "+")
            meta = {"brand": get("brand"), "image_url": None, "price": get("price") or None, "source": source,
                    "product_url": f"https://www.sephora.com/search?keyword={query}"}
            added += store.add_document(f"local://{source}/{uid}", f"{name} — {get('brand')}", source,
                                        category, [text], meta) > 0
    print(f"  📄 {source}: {added} rows")
    return added


# ---------------------------------------------------------------- orchestrator
def ingest_databases(cfg: dict, force: bool = False) -> int:
    total = 0
    jobs = {
        "open_beauty_facts_dump": lambda c: obf_dump(c.get("max_products", 3000), c.get("countries")),
        "cosing": lambda c: cosing_ingredients(c.get("ingredients", [])),
        "medlineplus": lambda c: medlineplus(c.get("terms", [])),
        "makeup_api": lambda c: makeup_api(c.get("product_types", []), c.get("per_type", 60)),
    }
    for name, job in jobs.items():
        c = cfg.get(name) or {}
        if not c.get("enabled"):
            continue
        if not force and not due(name, c.get("refresh_days", 30)):
            continue
        print(f"🗄️  {name}")
        try:
            total += job(c)
            mark_done(name)
        except Exception as e:  # one broken source never stops the others
            print(f"  ✗ {name} failed: {e}")
    for c in cfg.get("local_csv") or []:
        key = f"csv:{c['path']}"
        if c.get("enabled", True) and (force or due(key, c.get("refresh_days", 3650))):
            total += local_csv(c["path"], c["columns"], c.get("source", c["path"]), c.get("category", "products"),
                               c.get("limit", 5000))
            mark_done(key)
    return total
