"""The pet's skincare routine mini-game: step order, tips from the knowledge base, daily rewards and streaks."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from backend import config, llm, pet
from backend.brain import _plain
from backend.rag.store import store

PRODUCTS = {
    "cleanser": {"en": "Cleanser", "fr": "Nettoyant"},
    "toner": {"en": "Toner", "fr": "Lotion"},
    "serum": {"en": "Serum", "fr": "Sérum"},
    "eye_cream": {"en": "Eye cream", "fr": "Crème yeux"},
    "moisturizer": {"en": "Moisturizer", "fr": "Crème hydratante"},
    "sunscreen": {"en": "Sunscreen", "fr": "Crème solaire"},
    "retinol": {"en": "Retinol", "fr": "Rétinol"},
    "oil_cleanser": {"en": "Oil cleanser", "fr": "Huile démaquillante"},
}
ORDER = {"morning": ["cleanser", "toner", "serum", "eye_cream", "moisturizer", "sunscreen"],
         "night": ["oil_cleanser", "cleanser", "toner", "retinol", "eye_cream", "moisturizer"]}

# Used when the LLM can't write one from the knowledge base
TIPS = {
    "cleanser": {"en": "Cleansing first gives everything after it a clean start.",
                 "fr": "Nettoyer d'abord, c'est offrir une peau propre à tout le reste."},
    "toner": {"en": "Toner goes on clean skin, before thicker products.", "fr": "La lotion se met sur peau propre, avant les textures riches."},
    "serum": {"en": "Thin serums go before creams so they can reach your skin.",
              "fr": "Les sérums légers passent avant les crèmes pour atteindre la peau."},
    "eye_cream": {"en": "Pat eye cream gently: the skin there is delicate.", "fr": "Tapote la crème yeux en douceur : la peau y est fragile."},
    "moisturizer": {"en": "Moisturizer seals in the layers underneath.", "fr": "La crème hydratante scelle les couches du dessous."},
    "sunscreen": {"en": "Sunscreen is the last morning step, so nothing dilutes your protection.",
                  "fr": "La crème solaire est la dernière étape du matin, pour ne pas diluer ta protection."},
    "retinol": {"en": "Retinol belongs at night: sunlight breaks it down, and it can make skin more sensitive.",
                "fr": "Le rétinol se met le soir : le soleil le dégrade, et il peut sensibiliser la peau."},
    "oil_cleanser": {"en": "Oil dissolves sunscreen and makeup, so it comes first at night.",
                     "fr": "L'huile dissout la crème solaire et le maquillage : elle passe en premier le soir."},
}
QUERIES = {
    "cleanser": ("why cleanse skin first in routine",), "toner": ("what does toner do after cleansing",),
    "serum": ("apply serum before moisturizer thin to thick",), "eye_cream": ("how to apply eye cream",),
    "moisturizer": ("why moisturizer locks in hydration after serum",), "sunscreen": ("sunscreen last step of morning routine",),
    "retinol": ("why use retinol at night not morning",), "oil_cleanser": ("oil cleanser removes sunscreen makeup double cleanse",),
}
WRONG = {
    "morning": {"retinol": {"en": "Hehe, not retinol in the morning! It's a night step, since sunlight breaks it down.",
                            "fr": "Hihi, pas de rétinol le matin ! C'est pour le soir, le soleil le dégrade."},
                "oil_cleanser": {"en": "No need for oil cleanser now: it's for removing sunscreen and makeup at night.",
                                 "fr": "Pas besoin d'huile maintenant : elle sert à enlever solaire et maquillage le soir."}},
    "night": {"sunscreen": {"en": "Hehe, sunscreen at night? There's no sun to block, so let's skip it!",
                            "fr": "Hihi, de la crème solaire le soir ? Pas de soleil à bloquer, on la saute !"},
              "serum": {"en": "Let's keep tonight simple: retinol is our treatment step.",
                        "fr": "Restons simples ce soir : le rétinol est notre soin."}},
}
WRONG_ORDER = {"en": "Hehe, not yet! {next} comes first.", "fr": "Hihi, pas encore ! {next} d'abord."}

BASE_COINS, COINS_PER_STREAK_DAY, MAX_STREAK_BONUS, XP_REWARD = 10, 2, 10, 10
TIPS_PATH = config.DATA_DIR / "routine_tips.json"
_tip_lock = threading.Lock()


def _load_tips() -> dict:
    return json.loads(TIPS_PATH.read_text(encoding="utf-8")) if TIPS_PATH.exists() else {}


def _kb_tip(step: str, mode: str) -> str | None:
    """One English line written from what the knowledge base says about this step. None if the LLM isn't available."""
    query = QUERIES[step][0]
    notes = "\n\n".join(h["text"] for h in store.search(query, k=4, category="skincare"))
    try:
        tip = llm.chat("You write one-line skincare tips for a cute pet game. Plain text only, no emojis, one sentence, "
                       "at most 16 words, friendly and practical. Never name a brand or a specific product. Keep the KEY IDEA "
                       "accurate and talk only about this one "
                       "product. Add a detail from the NOTES only if it fits the idea.\n\nKEY IDEA\n" + TIPS[step]["en"] +
                       "\n\nNOTES\n" + notes,
                       [{"role": "user", "content": f"Write the tip for this step of a {mode} routine: {PRODUCTS[step]['en']}."}],
                       temperature=0.3)
    except llm.LLMError as e:
        print(f"[routine] {e} -> built-in tip")
        return None
    tip = _plain(tip).strip()
    return tip if 20 <= len(tip) <= 160 else None


def _tips(mode: str) -> dict:
    """English tips, written once per step from the knowledge base, then kept in data/routine_tips.json."""
    with _tip_lock:
        tips = _load_tips()
        missing = [id for id in ORDER[mode] if f"{mode}:{id}" not in tips]
        if missing:
            with ThreadPoolExecutor(max_workers=3) as pool:
                for id, tip in zip(missing, pool.map(lambda i: _kb_tip(i, mode), missing)):
                    if tip:
                        tips[f"{mode}:{id}"] = tip
            TIPS_PATH.write_text(json.dumps(tips, indent=2, ensure_ascii=False), encoding="utf-8")
    return tips


def plan(mode: str, lang: str) -> dict:
    if mode not in ORDER:
        raise ValueError(f"Unknown routine: {mode}")
    lang = lang if lang in ("en", "fr") else "en"
    tips = _tips(mode) if lang == "en" else {}  # French uses the hand-written tips: LLM French drifted and got facts wrong
    steps = [{"id": id, "tip": tips.get(f"{mode}:{id}") or TIPS[id][lang]} for id in ORDER[mode]]
    return {"mode": mode, "steps": steps,
            "products": [{"id": id, "label": p[lang]} for id, p in PRODUCTS.items()],
            "wrong": {id: t[lang] for id, t in WRONG[mode].items()}, "wrong_order": WRONG_ORDER[lang]}


def complete(state: dict, mode: str) -> dict:
    """Rewards the first completion of each routine per day. Morning and night have separate streaks."""
    if mode not in ORDER:
        raise ValueError(f"Unknown routine: {mode}")
    today = time.strftime("%Y-%m-%d")
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    streak = state["streaks"][mode]
    if streak["last"] == today:
        return {"coins": 0, "xp": 0, "streak": streak["count"], "already_done": True, "leveled_up": False}
    streak["count"] = streak["count"] + 1 if streak["last"] == yesterday else 1
    streak["last"] = today
    coins = BASE_COINS + min(MAX_STREAK_BONUS, (streak["count"] - 1) * COINS_PER_STREAK_DAY)
    state["coins"] += coins
    leveled = pet.gain(state, xp=XP_REWARD, happy=5)
    return {"coins": coins, "xp": XP_REWARD, "streak": streak["count"], "already_done": False, "leveled_up": leveled}
