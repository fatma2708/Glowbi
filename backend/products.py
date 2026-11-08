"""Grounded product recommendations: find real products, keep the model to them, and turn them into cards."""
import html
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote_plus

from backend.rag.openbeautyfacts import product_image, product_to_text, search_products
from backend.rag.store import store

MAX_NOTES, MAX_CARDS = 6, 3

# Each type: words that ask for it, and words that must appear in the product's name, category or makeup type.
# Open Beauty Facts is mostly French, and full of soaps and toothpaste, so this filter does the heavy lifting.
TYPES = {
    "cleanser": (r"cleanser|face wash|nettoyant|démaquillant|micellar|micellaire", r"cleanser|face wash|nettoyant visage|gel nettoyant|mousse nettoyante|démaquillant|micellar|micellaire"),
    "sunscreen": (r"sunscreen|\bspf\b|sun cream|white cast|crème solaire|écran solaire|protection solaire", r"sunscreen|\bspf\b|solaire"),
    "moisturizer": (r"moisturi[sz]er|hydratante?|face cream|crème visage", r"moisturi|hydratant|crèmes pour le visage|face cream"),
    "serum": (r"\bs[eé]rum", r"\bs[eé]rum"),
    "toner": (r"\btoner|lotion tonique", r"\btoner|lotion tonique"),
    "shampoo": (r"shampoo|shampoing|shampooing", r"shampoo|shampoing|shampooing"),
    "conditioner": (r"conditioner|après.shampoing", r"conditioner|après.shampoing|soins cheveux"),
    "hair_care": (r"frizz|frisott|curl|boucl|hair mask|masque cheveux", r"conditioner|après.shampoing|soins cheveux|masques? (pour )?cheveux|hair mask|curl|boucl"),
    "mascara": (r"mascara", r"mascara"), "foundation": (r"foundation|fond de teint", r"foundation|fond de teint"),
    "lipstick": (r"lipstick|rouge à lèvres", r"lipstick|rouge à lèvres"), "blush": (r"\bblush", r"\bblush"),
    "eyeliner": (r"eyeliner", r"eyeliner"), "eyeshadow": (r"eyeshadow|fard à paupières", r"eyeshadow|fards? à paupières"),
    "nail_polish": (r"nail polish|vernis", r"nail.polish|vernis"),
}
# No product named: go by what they want to fix
CONCERNS = [(r"blackhead|acne|breakout|\bpores?\b|\bpimple|points? noirs?|boutons?\b", ["cleanser", "serum", "moisturizer"]),
            (r"dry skin|hydrat|peau sèche", ["moisturizer", "serum"])]
ASKS = re.compile(r"recommend|suggest|\bbest\b|which product|what product|what should i (use|buy|try)|something for|a product|"
                  r"conseill|recommand|meilleur|quel produit|quoi utiliser|que dois.je (utiliser|acheter)", re.I)
BLOCKED = re.compile(r"dentifrice|toothpaste|papier toilette|lessive|vaisselle|pour (les )?mains|hand wash|rasoir|\bwc\b|b[eé]b[eé]|baby|enfant|"
                     r"\bkids?\b|pediatric|ongles|dissolvant|nail polish remover|\bpieds?\b|\bfeet\b|\bfoot\b|scholl", re.I)
NOT_FOR_FACE = re.compile(r"shampo|après.shampoing|douche|shower|\bcheveux\b", re.I)
FACE_TYPES = {"cleanser", "sunscreen", "moisturizer", "serum", "toner"}
MAKEUP_TYPES = {"mascara", "foundation", "lipstick", "blush", "eyeliner", "eyeshadow", "nail_polish"}
CJK = re.compile(r"[\u3000-\u9fff\uac00-\ud7af]")
PARENT_COMPANIES = {"henkel", "unilever", "beiersdorf", "procter & gamble", "p&g", "johnson & johnson", "colgate-palmolive"}
ATTRIBUTES = {"vegan": r"vegan|végan", "organic": r"organic|\bbio\b", "cruelty free": r"cruelty.free"}
FRAGRANCE = r"fragrance|parfum|perfume|aroma|linalool|limonene|citronellol|geraniol|eugenol|coumarin|citral|essential oils?|huiles? essentielles?"
ALIASES = {"fragrance": FRAGRANCE, "parfum": FRAGRANCE, "essential oils": FRAGRANCE, "perfume": FRAGRANCE}

# Brands the model likes to reach for, on top of every brand in the store
KNOWN_BRANDS = """CeraVe|La Roche-Posay|The Ordinary|Paula's Choice|Neutrogena|Cetaphil|Kose|Olay|L'Oréal|L'Oreal|Vichy|Bioderma|Avène|Avene|
Nivea|Garnier|Eucerin|Clinique|Estée Lauder|Dove|Aveeno|Vanicream|Bioré|Biore|Eucerin|Drunk Elephant|Tatcha|Kiehl's|Beauty of Joseon|COSRX|
Innisfree|Isntree|Anessa|Supergoop|EltaMD|Dr Jart|Laneige|Sulwhasoo|Maybelline|NYX|Fenty|Revlon|MAC|Shiseido|Lancôme|Lancome|Mr. Reliable|Curlsmith|
Shea Moisture|SheaMoisture|Olaplex|Moroccanoil|Mielle|Cantu|Ouai|Briogeo""".replace("\n", "")
NAME_WORDS = re.compile(r"[A-ZÀ-Ý][\w'’&.-]*|\d+%?")
SAFE_CAPS = {"Vitamin", "Hyaluronic", "Salicylic", "Glycolic", "Azelaic", "Retinol", "Niacinamide", "SPF", "UV", "UVA", "UVB", "AHA", "BHA", "PHA", "EU", "US"}
GENERIC_BRANDS = {"unknown brand", "bio", "marque", "sans", "soin", "soins", "beauty", "skin", "hair", "care", "nature"}


def asks_for_products(message: str) -> bool:
    m = message.lower()
    return bool(ASKS.search(m) or any(re.search(words, m) for words, _ in TYPES.values()))


def _wanted_types(message: str) -> list[str]:
    m = message.lower()
    found = [t for t, (words, _) in TYPES.items() if re.search(words, m)]
    if found:
        return found
    for pattern, types in CONCERNS:
        if re.search(pattern, m):
            return types
    return []


def _field(text: str, label: str) -> str:
    match = re.search(rf"^{label}: (.*)$", text, re.M)
    return match.group(1) if match else ""


def _ingredients(text: str) -> str:
    """The real ingredient list, if this product has one. Text like "fragrance-free" elsewhere mustn't count."""
    inci = _field(text, r"Ingredients(?: \(INCI\))?")
    if inci:
        return inci
    match = re.search(r"\bingredients?:\s*(.{30,})", text, re.I | re.S)
    return match.group(1) if match else ""


def _avoided(ingredients: str, avoid: list[str]) -> bool:
    return any(re.search(ALIASES.get(a.lower().strip(), re.escape(a.strip())), ingredients, re.I) for a in avoid if a.strip())


def _brand(brands: str) -> str:
    """Open Beauty Facts lists parent companies first: "Henkel, Schwarzkopf" should read Schwarzkopf."""
    names = [b.strip() for b in brands.split(",") if b.strip()]
    return next((b for b in names if b.lower() not in PARENT_COMPANIES), names[0] if names else "")


def find(message: str, profile: dict) -> list[dict]:
    """Up to 6 real products for this question, without anything on the avoid list."""
    if not asks_for_products(message):
        return []
    types = _wanted_types(message)
    if not types:
        return []
    needs = "|".join(TYPES[t][1] for t in types)
    skincare = not set(types) & MAKEUP_TYPES
    face = set(types) <= FACE_TYPES
    attributes = [p for word, p in ATTRIBUTES.items() if word in message.lower()]
    avoid = profile.get("avoid") or []

    def keep(row: dict) -> bool:
        text = row["text"]
        if CJK.search(row["title"]) or (skincare and row["category"] == "makeup"):
            return False
        name = row["title"].partition(" — ")[0]  # not the brand: "La Boucle" isn't a curly hair product
        label = " ".join((name, _field(text, "Categories"), _field(text, "Category"), _field(text, "Type")))
        if BLOCKED.search(label) or not re.search(needs, label, re.I) or (face and NOT_FOR_FACE.search(label)):
            return False
        if not all(re.search(a, " ".join((_field(text, "Tags"), _field(text, "Labels"), row["title"])), re.I) for a in attributes):
            return False
        return not _avoided(_ingredients(text), avoid)

    query = f"{message} {profile.get('skin_type') or ''}"
    found = store.products(query, keep, MAX_NOTES)
    if not found:
        live_rows = []
        for product_type in types:
            search_term = {
                "cleanser": "facial cleanser",
                "moisturizer": "facial moisturizer",
                "sunscreen": "facial sunscreen",
                "serum": "facial serum",
                "toner": "facial toner",
                "shampoo": "shampoo",
                "conditioner": "hair conditioner",
                "hair_care": "hair care",
            }.get(product_type, product_type)
            for raw in search_products(search_term, 6):
                item = product_to_text(raw)
                if not item:
                    continue
                url = raw.get("url") or f"https://world.openbeautyfacts.org/product/{raw.get('code')}"
                live_rows.append({
                    "text": item[1], "title": item[0], "source": "Open Beauty Facts",
                    "category": "products", "url": url,
                    "meta": {"brand": raw.get("brands"), "product_url": url, "image_url": None,
                             "price": None, "source": "Open Beauty Facts"},
                })
        found = [row for row in live_rows if keep(row)][:MAX_NOTES]
    recommendations = []
    for row in found:
        name, _, title_brand = row["title"].partition(" — ")
        meta = row["meta"]
        ingredients = _ingredients(row["text"])
        recommendations.append({**row, "name": html.unescape(name).strip(),
                                 "brand": _brand(meta.get("brand") or title_brand),
                                 "ingredients": ingredients, "check_label": bool(avoid) and not ingredients})
    return recommendations


def notes(products: list[dict]) -> str:
    if not products:
        return "(none: describe the type of product instead)"
    lines = ["Recommend the one or two that fit best. Your reply must include their [P#] markers, right after you mention them."]
    for i, p in enumerate(products, 1):
        key = ", ".join(x.strip() for x in p["ingredients"].split(",")[:8]) or "not listed"
        lines.append(f"[P{i}] {p['name']} by {p['brand']} | key ingredients: {key}")
    return "\n".join(lines)


def strip_markers(text: str) -> str:
    return re.sub(r"\s*[\[(]\s*P\d\s*[\])]", "", text)


def _allowed_words(products: list[dict], message: str, profile_names: list[str]) -> str:
    return " ".join([message, *profile_names, *(f"{p['name']} {p['brand']}" for p in products)]).lower()


def _brands() -> str:
    names = {b for b in store.product_brands() if len(b) >= 4 and b.lower() not in GENERIC_BRANDS}
    return "|".join([KNOWN_BRANDS, *sorted((re.escape(b) for b in names), key=len, reverse=True)])


_brand_re: re.Pattern | None = None
_logged: set[str] = set()


def _log_once(name: str, why: str):  # guard runs on every streamed piece
    if name not in _logged:
        _logged.add(name)
        print(f"[guard] removed '{name}' ({why})")


def guard(text: str, products: list[dict], message: str, names: list[str], lang: str = "en") -> str:
    """Anti-hallucination: a brand or product name that isn't in the notes (or the question) gets dropped."""
    global _brand_re
    if _brand_re is None:
        _brand_re = re.compile(rf"(?<![\w-])(?:{_brands()})(?![\w-])(?:\s+(?:[A-ZÀ-Ý][\w'’&.-]*|\d+%?))*")
    allowed = _allowed_words(products, message, names)
    mentioned = _allowed_words(products, message, [])
    swap = "un produit comme celui-ci" if lang == "fr" else "a product like this"

    def check(m: re.Match) -> str:
        if m.group(0).lower() in allowed or m.group(0).split()[0].lower() in allowed:
            return m.group(0)
        _log_once(m.group(0), "not in the product notes")
        return swap

    text = _brand_re.sub(check, text)

    def check_run(m: re.Match) -> str:  # unknown brands: two or more capitalized words in a row
        words = m.group(0).split()
        if m.start() == 0 or set(words) & SAFE_CAPS or all(w.lower() in allowed for w in words) or \
                any(w.lower().strip(".,") in mentioned.split() for w in words):
            return m.group(0)
        _log_once(m.group(0), "looks like a product name")
        return swap

    text = re.sub(r"(?<![\w-])[A-ZÀ-Ý][\w'’&.-]+(?:\s+[A-ZÀ-Ý][\w'’&.-]+)+", check_run, text)
    return re.sub(rf"\b(?:the|a|an|this|that|your|le|la|les|un|une|ce|cette)\s+(?={swap})", "", text, flags=re.I)


def _why(text: str, marker: str) -> str:
    for clause in re.split(r"(?<=[,;!?])\s+", text):
        if marker in clause:
            return strip_markers(clause).strip(" ,;")
    return ""


def _image(p: dict) -> str | None:
    meta = p["meta"]
    if meta.get("image_url") or meta.get("image_checked") or p["source"] != "Open Beauty Facts":
        return meta.get("image_url")
    meta["image_checked"] = True
    meta["image_url"] = product_image(p["url"].rstrip("/").rsplit("/", 1)[-1])
    store.set_meta(p["url"], meta)  # fetched once, then cached
    return meta["image_url"]


def cards(text: str, products: list[dict]) -> list[dict]:
    """Products she actually referred to, by marker or by name, in reply order."""
    picked = []
    for n in dict.fromkeys(int(x) for x in re.findall(r"[\[(]\s*P(\d)\s*[\])]", text)):
        if 1 <= n <= len(products):
            picked.append((products[n - 1], _why(text, f"P{n}")))
    for p in products:
        if p["name"].lower() in text.lower() and not any(p is q for q, _ in picked):
            picked.append((p, _why(text, p["name"])))
    # the rest of the row: next closest matches, which passed the same filters
    picked += [(p, "") for p in products if not any(p is q for q, _ in picked)]
    picked = picked[:MAX_CARDS]
    with ThreadPoolExecutor(max_workers=MAX_CARDS) as pool:
        images = list(pool.map(lambda item: _image(item[0]), picked))
    out = []
    for (p, why), image in zip(picked, images):
        meta = p["meta"]
        out.append({"name": p["name"], "brand": p["brand"], "image_url": image, "url": meta.get("product_url") or p["url"],
                    "buy_url": "https://www.google.com/search?tbm=shop&q=" + quote_plus(f"{p['brand']} {p['name']}"), "why": why,
                    "price": meta.get("price"), "check_label": p["check_label"], "source": p["source"]})
    return out
