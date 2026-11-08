"""Photos: skin and hair tips, ingredient labels, product fronts. Images stay in memory and go only to the vision model."""
import base64
import json
import re

import httpx

from backend import brain, config, ingredients, pet

PROMPT = """You help a beauty app read one photo. Reply with JSON only, with these keys:
"type": one of "skin", "hair", "product_label", "product_front", "other".
"observations": for skin or hair, up to 4 short phrases describing only what is visible in cosmetic terms
  (skin: shine, visible pores, dryness or flaking, redness, texture, dark spots; hair: frizz, curl pattern, dryness, split ends, scalp flakes).
"concerns": for skin or hair, zero to 4 matching cosmetic concerns from the allowed values below, based only on visible signs.
  These are not diagnoses. Skin values: oily, dry, redness, acne, blackheads, large pores, dark spots, dryness, dullness,
  fine lines, dark circles. Hair values: frizz, dryness, dandruff, oily roots, split ends.
  Never give a diagnosis or a disease name. Never guess age, ethnicity or gender. Never comment on attractiveness.
"medical": true only for skin or hair that shows something a doctor should see: open wounds, a changing or irregular mole,
  severe or painful-looking acne, a rash, patchy hair loss, or signs of infection. Otherwise false.
"remember": for skin or hair, the one most useful thing to save, as {"field": "skin_type"|"concerns"|"hair_concerns", "value": "...",
  "en": "your T-zone looks oily", "fr": "ta zone T a l'air grasse"}, or null. skin_type values: oily, dry, combination, normal.
  concerns values: acne, blackheads, large pores, dark spots, redness, dryness, dullness, fine lines, dark circles.
  hair_concerns values: frizz, dryness, dandruff, oily roots, split ends.
"ingredients": for product_label, the exact ingredient list as comma-separated text, copied character by character. Otherwise "".
"brand" and "product": for product_front, the brand and product name you can read. Otherwise "".
"""
ALLOWED = {"skin_type": {"oily", "dry", "combination", "normal"},
           "concerns": {"acne", "blackheads", "large pores", "dark spots", "redness", "dryness", "dullness", "fine lines", "dark circles"},
           "hair_concerns": {"frizz", "dryness", "dandruff", "oily roots", "split ends"}}
CONCERN_TYPES = {
    "skin": {
        "oily": ("cleanser", "moisturizer"),
        "dry": ("moisturizer", "cleanser"),
        "redness": ("cleanser", "moisturizer", "sunscreen"),
        "acne": ("cleanser", "serum", "moisturizer"),
        "blackheads": ("cleanser", "serum", "moisturizer"),
        "large pores": ("cleanser", "serum", "moisturizer"),
        "dark spots": ("serum", "sunscreen", "moisturizer"),
        "dryness": ("moisturizer", "serum"),
        "dullness": ("serum", "moisturizer", "sunscreen"),
        "fine lines": ("serum", "moisturizer", "sunscreen"),
        "dark circles": ("serum", "moisturizer"),
    },
    "hair": {
        "frizz": ("conditioner", "hair_care"),
        "dryness": ("conditioner", "hair_care"),
        "dandruff": ("shampoo",),
        "oily roots": ("shampoo",),
        "split ends": ("conditioner", "hair_care"),
    },
}
LINES = {
    "medical": {"en": "I can't judge that one from a photo, it's best to show it to a dermatologist",
                "fr": "Je ne peux pas juger ça sur une photo, mieux vaut le montrer à un dermatologue"},
    "other": {"en": "Cute photo, but I can only help with skin, hair or beauty products",
              "fr": "Jolie photo, mais je ne peux t'aider que pour la peau, les cheveux ou les produits de beauté"},
    "not_found": {"en": "I couldn't find {name}, can you photograph its ingredient list instead?",
                  "fr": "Je n'ai pas trouvé {name}, tu peux photographier sa liste d'ingrédients ?"},
    "no_list": {"en": "I can't read the ingredients on this one, can you try a sharper photo?",
                "fr": "Je n'arrive pas à lire les ingrédients, tu peux refaire une photo plus nette ?"},
    "busy": {"en": "Too many photos at once, give me a minute and try again",
             "fr": "Trop de photos d'un coup, laisse-moi une minute et réessaie"},
    "unavailable": {"en": "My photo reader isn't available right now, you can paste the ingredient list instead",
                    "fr": "Mon lecteur de photos n'est pas disponible, tu peux coller la liste d'ingrédients"},
}


def _ask(image: bytes, question: str) -> dict:
    data = base64.b64encode(image).decode()
    r = httpx.post(f"{config.OPENAI_BASE_URL}/chat/completions", timeout=45, headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                   json={"model": config.VISION_MODEL, "temperature": 0, "messages": [{"role": "user", "content": [
                       {"type": "text", "text": PROMPT + (f"\nThe user also asks: {question}" if question else "")},
                       {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}]}]})
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))


def _simple(kind: str, reply: str, emotion: str = "concerned") -> dict:
    return {"kind": kind, "reply": reply, "emotion": emotion, "products": [], "check": None, "offer": None, "observations": []}


def _offer(remember, profile: dict) -> dict | None:
    if not isinstance(remember, dict) or remember.get("value") not in ALLOWED.get(remember.get("field"), ()):
        return None
    current = profile.get(remember["field"])
    if current == remember["value"] or (isinstance(current, list) and remember["value"] in current):
        return None  # she already knows
    return {k: remember.get(k) for k in ("field", "value", "en", "fr")}


def _skin_or_hair(kind: str, found: dict, question: str, lang: str) -> dict:
    observations = [str(o) for o in found.get("observations") or []][:4]
    profile = pet.get()["profile"]
    allowed_concerns = ALLOWED["concerns" if kind == "skin" else "hair_concerns"]
    concerns = [str(c).lower() for c in found.get("concerns") or [] if str(c).lower() in allowed_concerns][:4]
    seen = ", ".join(observations) or kind
    types = []
    for concern in concerns:
        for product_type in CONCERN_TYPES[kind].get(concern, ()):
            if product_type not in types:
                types.append(product_type)
    if not types:
        types = ["cleanser", "moisturizer", "sunscreen"] if kind == "skin" else ["shampoo", "conditioner"]
    recommendations = ", ".join(types[:3])
    safety_note = ""
    if found.get("medical"):
        safety_note = (" Some visible features may need a professional examination, so do not diagnose them from this photo; "
                       "include a brief dermatologist recommendation while still describing the visible signs and safe next steps.")
    else:
        safety_note = (" This is an ordinary cosmetic photo assessment: do not add a dermatologist disclaimer or say you "
                       "cannot judge a photo.")
    message = (f"Photo assessment: first state what is visibly present, then recommend real {recommendations} products "
               f"from the catalog with links, and briefly explain what to look for. My {kind} photo shows: {seen}. "
               f"Possible visible cosmetic concerns: {', '.join(concerns) or 'none confirmed'}.{safety_note} "
               f"{question}").replace("  ", " ")
    done = brain.answer(message)
    return {"kind": kind, "reply": done["reply"], "emotion": done["emotion"], "products": done["products"], "check": None,
            "observations": observations, "concerns": concerns, "offer": _offer(found.get("remember"), profile), "pet": done["pet"]}


def checked(text: str, lang: str, product: str = "") -> dict:
    profile = pet.get()["profile"]
    result = ingredients.check(text, profile, lang)
    if not result["ingredients"]:
        return _simple("product_label", LINES["no_list"][lang])
    reply = result["verdict_for_me"]["summary"]
    emotion = {"red": "concerned", "amber": "thinking", "green": "happy"}[result["verdict_for_me"]["level"]]
    return {**_simple("product_label", reply, emotion), "check": {**result, "product": product}}


def _front(found: dict, lang: str) -> dict:
    name = f"{found.get('brand') or ''} {found.get('product') or ''}".strip()
    hit = ingredients.lookup(name) if name else None
    if not hit:
        return _simple("product_front", LINES["not_found"][lang].format(name=name or ("ce produit" if lang == "fr" else "this product")), "thinking")
    return {**checked(hit["ingredients"], lang, f"{hit['brand']} {hit['name']}".strip()), "kind": "product_front"}


def analyze(image: bytes, question: str = "", lang: str = "en") -> dict:
    lang = lang if lang in LINES["other"] else "en"
    try:
        found = _ask(image, question)
    except httpx.HTTPStatusError as e:
        print(f"[vision] {config.VISION_MODEL}: HTTP {e.response.status_code}")
        return _simple("busy" if e.response.status_code == 429 else "unavailable", LINES["busy" if e.response.status_code == 429 else "unavailable"][lang])
    except (httpx.HTTPError, ValueError, KeyError, IndexError, AttributeError) as e:
        print(f"[vision] failed: {e.__class__.__name__}")
        return _simple("unavailable", LINES["unavailable"][lang])
    kind = found.get("type")
    if kind in ("skin", "hair"):
        return _skin_or_hair(kind, found, question, lang)
    if kind == "product_label":
        return checked(found.get("ingredients") or "", lang)
    if kind == "product_front":
        return _front(found, lang)
    return _simple("other", LINES["other"][lang], "happy")
