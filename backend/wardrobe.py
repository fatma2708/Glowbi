"""What the pet can wear and how it unlocks. The SVG art lives in frontend/wardrobe.js, keyed by these ids."""
from backend import pet


def item(id, slot, en, fr, level=1, price=0):
    return {"id": id, "slot": slot, "en": en, "fr": fr, "level": level, "price": price}


ITEMS = [
    item("bow", "head", "Bow", "Noeud"),
    item("flower", "head", "Flower clip", "Barrette fleur"),
    item("towel", "head", "Towel headband", "Bandeau serviette"),
    item("beret", "head", "Beret", "Béret", price=30),
    item("cat_ears", "head", "Cat ears", "Oreilles de chat", price=40),
    item("bunny_ears", "head", "Bunny ears", "Oreilles de lapin", price=40),
    item("daisy_crown", "head", "Daisy crown", "Couronne de marguerites", price=50),
    item("sun_hat", "head", "Sun hat", "Chapeau de soleil", level=3),
    item("crown", "head", "Crown", "Couronne", level=5),
    item("round_glasses", "face", "Round glasses", "Lunettes rondes"),
    item("star_stickers", "face", "Star stickers", "Stickers étoiles", price=20),
    item("blush_hearts", "face", "Blush hearts", "Coeurs roses", price=20),
    item("heart_glasses", "face", "Heart glasses", "Lunettes coeur", price=40),
    item("sheet_mask", "face", "Sheet mask", "Masque en tissu", level=2),
    item("ribbon", "neck", "Ribbon", "Ruban"),
    item("scarf", "neck", "Scarf", "Écharpe", price=25),
    item("bandana", "neck", "Bandana", "Bandana", price=25),
    item("pearls", "neck", "Pearl necklace", "Collier de perles", level=4),
    item("cotton_pad", "hand", "Cotton pad", "Coton"),
    item("mirror", "hand", "Tiny mirror", "Petit miroir", price=20),
    item("lipstick", "hand", "Lipstick", "Rouge à lèvres", price=30),
    item("serum", "hand", "Serum bottle", "Flacon de sérum", level=2),
]
ITEMS_BY_ID = {i["id"]: i for i in ITEMS}

EYES = [item("round", "eyes", "Round", "Ronds"), item("sparkly", "eyes", "Sparkly", "Pétillants"),
        item("sleepy", "eyes", "Sleepy", "Endormis"), item("almond", "eyes", "Almond", "Amande", price=20),
        item("button", "eyes", "Button", "Boutons", price=20), item("lash", "eyes", "Lashes", "Cils", price=30)]
MOUTHS = [item("smile", "mouth", "Smile", "Sourire"), item("tiny", "mouth", "Tiny", "Petit"),
          item("cat", "mouth", "Cat", "Chat", price=15), item("wide", "mouth", "Wide", "Grand", price=15)]
CHEEKS = [item("oval", "cheeks", "Oval", "Ovales"), item("round", "cheeks", "Round", "Ronds"),
          item("wide", "cheeks", "Wide", "Larges"), item("tiny", "cheeks", "Tiny", "Petits")]
COLORS = [item("pink", "color", "Pink", "Rose"), item("peach", "color", "Peach", "Pêche"),
          item("lilac", "color", "Lilac", "Lilas"), item("mint", "color", "Mint", "Menthe", price=25),
          item("sky", "color", "Sky", "Ciel", price=25), item("butter", "color", "Butter", "Beurre", price=25),
          item("berry", "color", "Berry", "Baie", level=3), item("pearl", "color", "Pearl", "Perle", level=4)]
GROUPS = {"eyes": EYES, "mouth": MOUTHS, "cheeks": CHEEKS, "color": COLORS}

KOKORO_VOICES = ["af_heart:50,af_bella:50", "af_heart", "af_bella", "af_nicole", "af_sky", "af_heart:60,af_sky:40",
                 "af_nicole:50,af_sky:50"]
ORPHEUS_VOICES = ["autumn", "diana", "hannah"]


def catalog() -> dict:
    return {"items": ITEMS, **GROUPS, "kokoro_voices": KOKORO_VOICES, "orpheus_voices": ORPHEUS_VOICES}


def _find(key: str) -> dict | None:
    """Group entries share ids across groups, so they're keyed "group:id"; accessories are plain ids."""
    group, _, id = key.rpartition(":")
    if group:
        return next((i for i in GROUPS.get(group, []) if i["id"] == id), None)
    return ITEMS_BY_ID.get(key)


def is_unlocked(state: dict, entry: dict, key: str) -> bool:
    if pet.level(state["xp"]) < entry["level"]:
        return False
    return entry["price"] == 0 or key in state["owned"]


def apply(state: dict, patch: dict):
    """Validates a partial appearance. ValueError = unknown value, PermissionError = still locked."""
    look = state["appearance"]
    for group in GROUPS:
        if patch.get(group) is not None:
            key = f"{group}:{patch[group]}"
            entry = _find(key)
            if not entry:
                raise ValueError(f"Unknown {group}: {patch[group]}")
            if not is_unlocked(state, entry, key):
                raise PermissionError(f"{key} is locked")
            look[group] = patch[group]
    for slot, id in (patch.get("slots") or {}).items():
        if slot not in look["slots"]:
            raise ValueError(f"Unknown slot: {slot}")
        if id is not None:
            entry = ITEMS_BY_ID.get(id)
            if not entry or entry["slot"] != slot:
                raise ValueError(f"{id} doesn't go in {slot}")
            if not is_unlocked(state, entry, id):
                raise PermissionError(f"{id} is locked")
        look["slots"][slot] = id
    if "voice" in patch:
        if patch["voice"] not in KOKORO_VOICES + ORPHEUS_VOICES + [None]:
            raise ValueError(f"Unknown voice: {patch['voice']}")
        look["voice"] = patch["voice"]
    for field, low, high in (("pitch", 1.0, 1.4), ("speed", 0.7, 1.3)):
        if patch.get(field) is not None:
            look[field] = min(high, max(low, float(patch[field])))


def buy(state: dict, key: str):
    entry = _find(key)
    if not entry or entry["price"] == 0:
        raise ValueError(f"{key} can't be bought")
    if key in state["owned"]:
        return
    if pet.level(state["xp"]) < entry["level"]:
        raise PermissionError("Level too low")
    if state["coins"] < entry["price"]:
        raise PermissionError("Not enough coins")
    state["coins"] -= entry["price"]
    state["owned"].append(key)
