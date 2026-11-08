"""Ingredient checker: reads an INCI list and says what matters for you. Rules live in config/ingredient_rules.yaml."""
import json
import re
import time

import httpx
import yaml

from backend import config
from backend.products import ALIASES as AVOID_ALIASES, _avoided
from backend.rag.openbeautyfacts import search_products
from backend.rag.store import store

RULES = yaml.safe_load((config.ROOT / "config" / "ingredient_rules.yaml").read_text(encoding="utf-8"))
ALIASES = RULES["aliases"]
TOP_POSITIONS = 5
COSING_ENTRIES = "https://cosingchecker.com/api/v1/entries/"
EU_SECONDS_BUDGET = 8  # later ingredients are checked next time: results are cached
EU_REQUEST_GAP = 0.5   # the API allows 120 requests a minute
_last_eu_request = 0.0
_allergens: set[str] | None = None


GROUP_NAMES = {"en": {"retinoids": "retinoids", "ahas": "AHAs", "bha": "BHA", "benzoyl_peroxide": "benzoyl peroxide"},
               "fr": {"retinoids": "rétinoïdes", "ahas": "AHA", "bha": "BHA", "benzoyl_peroxide": "peroxyde de benzoyle"}}
DISPLAY = {"en": {}, "fr": {"fragrance": "parfum", "water": "eau", "denatured alcohol": "alcool dénaturé", "coconut oil": "huile de coco",
                            "cocoa butter": "beurre de cacao", "vitamin c": "vitamine C"}}


def normalize(name: str) -> str:
    """"Cocos Nucifera (Coconut) Oil*" -> "coconut oil", "PARFUM (Fragrance)" -> "fragrance", "Aqua 70%" -> "water"."""
    n = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", name.lower())
    n = re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", n)
    n = re.sub(r"[*†‡•+]", " ", n)
    n = re.sub(r"\s+", " ", n).strip(" .;:-/")
    return ALIASES.get(n, n)


def _tidy(name: str) -> str:
    """OCR and crowd-sourced lists run into batch codes and addresses: "parfum dope 12m t-no. 89057 ..."."""
    words = name.split()
    first = normalize(words[0]) if words else ""
    if len(words) > 1 and first in ("fragrance", "water"):  # nothing real starts with these
        return first
    return name if len(words) <= 6 and not re.search(r"\d{4,}", name) else ""


def parse_list(text: str) -> list[str]:
    """Splits an ingredient list into normalized names, in label order, without duplicates."""
    text = re.sub(r"^\s*(ingredients?|ingrédients?|inci|composition)\s*[:\-]\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"(\+/-|\bmay contain\b|\bpeut contenir\b).*$", "", text, flags=re.I | re.S)  # shade colorants, not the formula
    parts, depth, current = [], 0, ""
    for i, ch in enumerate(text):
        depth += ch in "(["
        depth -= ch in ")]"
        ends_name = ch == "." and text[i + 1:i + 2].isspace()  # crowd-sourced lists sometimes use full stops
        if (ch in ",;\n" or ends_name) and depth <= 0:
            parts.append(current)
            current, depth = "", 0
        else:
            current += ch
    parts.append(current)
    names = [_tidy(normalize(p)) for p in parts]
    return list(dict.fromkeys(n for n in names if n))


def position_of(index: int, total: int) -> dict:
    """Ingredients are listed by amount: the first 5 are usually most of the formula."""
    where = "top" if index < TOP_POSITIONS else "end" if index >= total * 2 / 3 else "middle"
    return {"index": index + 1, "total": total, "where": where}


POSITION_TEXT = {"top": {"en": "Near the top of the list, so there's a fair amount.", "fr": "Haut dans la liste, donc en quantité notable."},
                 "middle": {"en": "Mid-list.", "fr": "Au milieu de la liste."},
                 "end": {"en": "Near the end, so it's likely a small amount.", "fr": "En fin de liste, donc sans doute en petite quantité."}}


def _is_acne_prone(profile: dict) -> bool:
    concerns = " ".join(profile.get("concerns") or []).lower()
    return profile.get("skin_type") == "oily" or bool(re.search(r"acne|acné|breakout|bouton|blackhead|point", concerns))


def _matches(name: str, terms: list[str]) -> bool:
    return any(t == name or re.search(rf"\b{re.escape(t)}\b", name) for t in terms)


def fragrance_allergens() -> set[str]:
    """The EU allergen list already stored from CosIng."""
    global _allergens
    if _allergens is None:
        with store._conn() as c:
            rows = c.execute("""SELECT ch.text FROM chunks ch JOIN documents d ON d.id = ch.doc_id
                                WHERE d.title = 'EU fragrance allergens list'""").fetchall()
        _allergens = {m.lower().strip() for r in rows for m in re.findall(r"inci_name: ([^;\n]+)", r[0])}
    return _allergens


def _flag(name: str, category: str, severity: str, explanation: str, pos: dict, lang: str, label: str) -> dict:
    return {"ingredient": name, "category": category, "label": label, "severity": severity, "position": pos, "explanation": explanation}


def _category_flags(names: list[str], profile: dict, lang: str) -> list[dict]:
    flags, sensitive = [], bool(profile.get("sensitive"))
    for key, rule in RULES["categories"].items():
        if rule.get("applies_to") == "acne_prone" and not _is_acne_prone(profile):
            continue
        terms = rule["terms"] + (sorted(fragrance_allergens()) if key == "fragrance_and_allergens" else [])
        for i, name in enumerate(names):
            if not _matches(name, terms):
                continue
            pos = position_of(i, len(names))
            if name in rule.get("high_in_list_only", []) and pos["where"] != "top":
                continue
            severity = "amber" if rule.get("amber_if") == "sensitive" and sensitive else rule["severity"]
            flags.append(_flag(name, key, severity, rule["note"][lang], pos, lang, rule["label"][lang]))
    return flags


def _active_flags(names: list[str], lang: str) -> tuple[list[dict], set[str]]:
    flags, found = [], set()
    label = {"en": "Active to know", "fr": "Actif à connaître"}[lang]
    for key, active in RULES["actives_to_know"].items():
        for i, name in enumerate(names):
            if _matches(name, active["terms"]):
                found.add(key)
                flags.append(_flag(name, "actives_to_know", "info", active["explain"][lang], position_of(i, len(names)), lang, label))
    return flags, found


def _conflict_flags(found: set[str], lang: str) -> list[dict]:
    seen, flags = set(), []
    label = {"en": "Careful together", "fr": "Attention à l'association"}[lang]
    for rule in RULES["conflicts"]:
        if set(rule["pair"]) <= found and rule[lang] not in seen:
            seen.add(rule[lang])
            flags.append({"ingredient": " + ".join(GROUP_NAMES[lang][p] for p in rule["pair"]), "category": "actives_to_know", "label": label,
                          "severity": "amber", "position": None, "explanation": rule[lang]})
    return flags


def _avoid_flags(names: list[str], avoid: list[str], lang: str) -> list[dict]:
    flags = []
    label = {"en": "On your avoid list", "fr": "Sur ta liste à éviter"}[lang]
    text = {"en": "You told me to avoid this.", "fr": "Tu m'as dit d'éviter ça."}[lang]
    for i, name in enumerate(names):
        if _avoided(name, avoid):
            flags.append(_flag(name, "my_avoid_list", "red", text, position_of(i, len(names)), lang, label))
    return flags


# ---------- EU annexes ----------
def _eu_entry(name: str) -> dict | None:
    """Only exact names count: the API's text search also returns unrelated substances containing the words."""
    global _last_eu_request
    with store._conn() as c:
        c.execute("CREATE TABLE IF NOT EXISTS cosing_cache(name TEXT PRIMARY KEY, data TEXT, fetched_at REAL)")
        row = c.execute("SELECT data FROM cosing_cache WHERE name=?", (name,)).fetchone()
    if row:
        return json.loads(row[0])
    time.sleep(max(0, EU_REQUEST_GAP - (time.time() - _last_eu_request)))
    _last_eu_request = time.time()
    r = httpx.get(COSING_ENTRIES, params={"q": name, "per_page": 30}, timeout=6, headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    match = next((e for e in r.json().get("results", []) if _same_substance(name, e)), None)
    with store._conn() as c:
        c.execute("INSERT OR REPLACE INTO cosing_cache VALUES(?,?,?)", (name, json.dumps(match), time.time()))
    return match


def _same_substance(name: str, entry: dict) -> bool:
    names = [entry.get("inci_glossary_name"), entry.get("chemical_name"), entry.get("display_name")]
    for candidate in filter(None, names):
        lowered = candidate.lower()
        if lowered == name or re.search(rf"\({re.escape(name)}\)", lowered) or lowered.split(" and its ")[0].strip() == name:
            return True
    return False


def _eu_flags(names: list[str], lang: str) -> tuple[list[dict], int]:
    flags, checked, started = [], 0, time.time()
    todo = [(i, n) for i, n in enumerate(names) if n not in RULES["common_base"]]
    for i, name in todo:
        if time.time() - started > EU_SECONDS_BUDGET:
            break
        try:
            entry = _eu_entry(name)
        except (httpx.HTTPError, ValueError):
            break
        checked += 1
        if not entry:
            continue
        banned = entry.get("annex") == "II"
        text = ({"en": f"Listed in EU Annex II (entry {entry.get('entry_number')}): prohibited in EU cosmetics. The listing can be specific, so check the exact form.",
                 "fr": f"Annexe II de l'UE (entrée {entry.get('entry_number')}) : interdit dans les cosmétiques de l'UE. L'interdiction peut viser une forme précise."}
                if banned else
                {"en": f"Listed in EU Annex {entry.get('annex')} (entry {entry.get('entry_number')}): allowed within limits on amount or use, so a regulated ingredient, not a banned one.",
                 "fr": f"Annexe {entry.get('annex')} de l'UE (entrée {entry.get('entry_number')}) : autorisé dans certaines limites, donc réglementé, pas interdit."})[lang]
        label = {"en": "EU rules", "fr": "Règles UE"}[lang]
        flags.append(_flag(name, "eu_prohibited_or_restricted", "amber" if banned else "info", text, position_of(i, len(names)), lang, label))
    return flags, checked


def _verdict(flags: list[dict], total: int, profile: dict, lang: str) -> dict:
    red = [f["ingredient"] for f in flags if f["severity"] == "red"]
    amber = list(dict.fromkeys(f["ingredient"] for f in flags if f["severity"] == "amber"))
    fr = lang == "fr"
    if red:
        items = ", ".join(red[:3])
        return {"level": "red", "summary": f"Attention, ça contient {items}, {'qui sont' if len(red) > 1 else 'qui est'} sur ta liste à éviter, je passerais mon tour" if fr
                else f"Careful, this has {items}, {'which are' if len(red) > 1 else 'which is'} on your avoid list, so I'd skip it"}
    if amber:
        items = ", ".join(amber[:2])
        why = (" pour une peau sensible" if fr else " for sensitive skin") if profile.get("sensitive") else \
            (" pour une peau à tendance acnéique" if fr else " for acne-prone skin") if _is_acne_prone(profile) else ""
        return {"level": "amber", "summary": f"Pas de drame, mais garde un œil sur {items}{why}, teste d'abord sur une petite zone" if fr
                else f"Nothing scary, but keep an eye on {items}{why}, and patch test it first"}
    return {"level": "green", "summary": f"Cette liste de {total} ingrédients me semble bien pour toi" if fr
            else f"This list of {total} ingredients looks fine for you"}


def _merge(flags: list[dict], lang: str) -> list[dict]:
    """One line per ingredient: the most serious flag leads, the others add to its explanation."""
    order = {"red": 0, "amber": 1, "info": 2}
    flags = sorted(flags, key=lambda f: order[f["severity"]])
    merged: dict[str, dict] = {}
    for f in flags:
        first = merged.get(f["ingredient"])
        if first is None:
            merged[f["ingredient"]] = {**f, "also": []}
        elif f["explanation"] not in first["explanation"]:
            first["explanation"] += " " + f["explanation"]
            first["also"].append(f["category"])
    for f in merged.values():
        if f["position"]:
            f["explanation"] += " " + POSITION_TEXT[f["position"]["where"]][lang]
    return sorted(merged.values(), key=lambda f: (order[f["severity"]], (f["position"] or {}).get("index", 0)))


def check(text_or_names, profile: dict, lang: str = "en", eu: bool = True) -> dict:
    names = parse_list(text_or_names) if isinstance(text_or_names, str) else [normalize(n) for n in text_or_names]
    lang = lang if lang in ("en", "fr") else "en"
    actives, found = _active_flags(names, lang)
    flags = _avoid_flags(names, profile.get("avoid") or [], lang) + _category_flags(names, profile, lang) + actives + _conflict_flags(found, lang)
    eu_flags, checked = _eu_flags(names, lang) if eu else ([], 0)
    flags += eu_flags
    flags = _merge(flags, lang)
    for f in flags:
        f["ingredient"] = DISPLAY[lang].get(f["ingredient"], f["ingredient"])
    return {"ingredients": names, "flags": flags, "verdict_for_me": _verdict(flags, len(names), profile, lang),
            "eu_checked": checked, "eu_total": sum(n not in RULES["common_base"] for n in names)}


def lookup(query: str) -> dict | None:
    """A product by barcode or name, from Open Beauty Facts. Returns {name, brand, ingredients} or None."""
    query = query.strip()
    if re.fullmatch(r"\d{8,14}", query):
        try:
            r = httpx.get(f"https://world.openbeautyfacts.org/api/v2/product/{query}", timeout=8, headers={"User-Agent": config.USER_AGENT},
                          params={"fields": "product_name,brands,ingredients_text,ingredients_text_en"})
            r.raise_for_status()
            hits = [r.json().get("product") or {}]
        except (httpx.HTTPError, ValueError):
            return None
    else:
        hits = search_products(query, 5)
    for p in hits:
        ingredients = p.get("ingredients_text_en") or p.get("ingredients_text")
        if ingredients and p.get("product_name"):
            return {"name": p["product_name"], "brand": p.get("brands") or "", "ingredients": ingredients}
    return None
