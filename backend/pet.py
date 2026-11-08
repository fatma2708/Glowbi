"""Glowbi's little life: happiness, XP/levels, moods, and what she knows about you."""
import json
import re
import time

from backend import config

HAPPINESS_DECAY_PER_HOUR = 1.0
UNLOCKS = {3: "sparkles"}  # the bow and crown moved to the wardrobe

DEFAULT_PROFILE = {
    "name": None, "skin_type": None, "sensitive": None, "concerns": [], "hair_type": None,
    "hair_concerns": [], "avoid": [], "routine": None, "makeup": None, "lang": "en",
    "onboarding_step": 0, "onboarded": False,
}
DEFAULT_APPEARANCE = {"color": "pink", "eyes": "round", "mouth": "smile", "cheeks": "oval",
                      "slots": {"head": None, "face": None, "neck": None, "hand": None},
                      "voice": None, "pitch": None, "speed": None}  # None = the .env voice
DEFAULT_SETTINGS = {"music_on": True, "music_volume": 0.3, "music_track": "generated", "sfx_volume": 0.7}
DEFAULT_STREAKS = {"morning": {"count": 0, "last": None}, "night": {"count": 0, "last": None}}
TICKLE_REWARDS_PER_MINUTE = 3
DEFAULT = {"name": "Glowbi", "pet_name": "Glowbi", "user_name": None, "xp": 0, "happiness": 70.0, "updated": time.time(),
           "chats": 0, "profile": DEFAULT_PROFILE, "history": [], "appearance": DEFAULT_APPEARANCE, "settings": DEFAULT_SETTINGS,
           "coins": 0, "owned": [], "streaks": DEFAULT_STREAKS, "tickles": []}

SKIN = {"oily": ["oily skin", "peau grasse", "skin is oily"], "dry": ["dry skin", "peau sèche", "skin is dry"],
        "combination": ["combination skin", "peau mixte", "skin is combination"],
        "normal": ["normal skin", "peau normale"]}
HAIR = {"straight": ["straight hair", "cheveux lisses"], "wavy": ["wavy hair", "cheveux ondulés"],
        "curly": ["curly hair", "cheveux bouclés"], "coily": ["coily hair", "4c hair", "cheveux crépus", "cheveux frisés"]}
CONCERNS = ["acne", "blackheads", "dark spots", "hyperpigmentation", "wrinkles", "fine lines", "redness",
            "dehydration", "dullness", "large pores", "dark circles", "boutons", "taches", "rides", "rougeurs"]
HAIR_CONCERNS = ["frizz", "dandruff", "hair loss", "split ends", "pellicules", "chute de cheveux", "fourches"]


def _load() -> dict:
    if config.PET_STATE_PATH.exists():
        state = json.loads(config.PET_STATE_PATH.read_text(encoding="utf-8"))
        defaults = json.loads(json.dumps(DEFAULT))
        look = state.get("appearance", {})
        merged = {**defaults, **state, "profile": {**DEFAULT_PROFILE, **state.get("profile", {})},
                  "appearance": {**defaults["appearance"], **look, "slots": {**defaults["appearance"]["slots"], **look.get("slots", {})}},
                  "settings": {**defaults["settings"], **state.get("settings", {})},
                  "streaks": {**defaults["streaks"], **state.get("streaks", {})}}
        # User names are intentionally session-local and are never restored from disk.
        merged["pet_name"] = state.get("pet_name") or state.get("name") or "Glowbi"
        merged["name"] = merged["pet_name"]
        merged["user_name"] = None
        merged["profile"]["name"] = None
        return merged
    return json.loads(json.dumps(DEFAULT))


def save(state: dict):
    config.PET_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def get() -> dict:
    state = _load()
    hours = (time.time() - state["updated"]) / 3600
    state["happiness"] = max(0.0, state["happiness"] - hours * HAPPINESS_DECAY_PER_HOUR)
    state["updated"] = time.time()
    save(state)
    return state


def level(xp: int) -> int:
    return xp // 100 + 1


def public(state: dict) -> dict:
    lvl = level(state["xp"])
    h = state["happiness"]
    mood = "sad" if h < 25 else "joyful" if h > 80 else "content"
    profile = {k: v for k, v in state["profile"].items() if k != "onboarding_step"}
    return {"name": state["pet_name"], "pet_name": state["pet_name"], "user_name": state["user_name"], "level": lvl,
            "xp_in_level": state["xp"] % 100, "happiness": round(h), "mood": mood,
            "accessories": [v for k, v in UNLOCKS.items() if lvl >= k], "profile": profile,
            "appearance": state["appearance"], "settings": state["settings"], "coins": state["coins"],
            "owned": state["owned"], "streaks": state["streaks"]}


def gain(state, xp=0, happy=0.0) -> bool:
    before = level(state["xp"])
    state["xp"] += xp
    state["happiness"] = min(100.0, state["happiness"] + happy)
    return level(state["xp"]) > before


def on_chat(user_msg: str, reply: str) -> tuple[dict, bool]:
    state = get()
    learn_profile(state, user_msg)
    state["chats"] += 1
    state["history"] = (state["history"] + [{"role": "user", "content": user_msg},
                                            {"role": "assistant", "content": reply}])[-12:]
    leveled = gain(state, xp=4, happy=3)
    save(state)
    return state, leveled


def on_poke() -> dict:
    state = get()
    gain(state, xp=1, happy=2)
    save(state)
    return state


def update_profile(**fields) -> dict:
    state = get()
    for k, v in fields.items():
        if k in state["profile"] and v is not None:
            state["profile"][k] = v
    save(state)
    return state


def set_names(state: dict, user_name: str | None = None, pet_name: str | None = None):
    if pet_name:
        state["pet_name"] = state["name"] = pet_name.strip()[:24]
    state["user_name"] = None
    state["profile"]["name"] = None


def remember(state: dict, field: str, value: str):
    """Saves something seen in a photo, after you've said yes."""
    current = state["profile"].get(field)
    if isinstance(current, list):
        _add(current, value)
    else:
        state["profile"][field] = value


def on_tickle() -> tuple[dict, bool]:
    """Small reward, capped per minute so it can't be farmed."""
    state = get()
    now = time.time()
    state["tickles"] = [t for t in state["tickles"] if now - t < 60]
    rewarded = len(state["tickles"]) < TICKLE_REWARDS_PER_MINUTE
    if rewarded:
        state["tickles"].append(now)
        gain(state, xp=1, happy=2)
    save(state)
    return state, rewarded


def _add(lst: list, item: str, cap: int = 10):
    if item and item not in lst:
        lst.append(item)
        del lst[:-cap]


def learn_profile(state: dict, msg: str):
    """Keeps learning during normal chat: skin/hair type, concerns, things to avoid."""
    m = msg.lower()
    p = state["profile"]
    for value, cues in SKIN.items():
        if any(c in m for c in cues):
            p["skin_type"] = value
    if any(c in m for c in ["sensitive skin", "peau sensible", "peau réactive"]):
        p["sensitive"] = True
    for value, cues in HAIR.items():
        if any(c in m for c in cues):
            p["hair_type"] = value
    for c in CONCERNS:
        if re.search(rf"\b{re.escape(c)}\b", m):
            _add(p["concerns"], c)
    for c in HAIR_CONCERNS:
        if re.search(rf"\b{re.escape(c)}\b", m):
            _add(p["hair_concerns"], c)
    for match in re.findall(r"(?:allergic to|irritated by|can't use|cannot use|allergique (?:à|au|aux))\s+([\w\s-]{3,30})", m):
        _add(p["avoid"], match.strip().split(" and ")[0])
