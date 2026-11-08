"""First-meeting conversation: Glowbi asks about you and fills your beauty profile.

Works with chip clicks (exact values) AND free text / voice ("uh my skin gets kinda shiny on my forehead").
"""
import re

from backend import pet


def opt(value, en, fr, kw):
    return {"value": value, "en": en, "fr": fr, "kw": kw}


NONE_KW = ["none", "nothing", "no", "nope", "rien", "aucun", "aucune", "non", "pas vraiment", "skip", "passer"]

STEPS = [
    {"id": "names", "type": "names", "emotion": "excited",
     "q": {"en": "Hiii! I'm so happy you're here! Before we start, let's get to know each other.",
           "fr": "Coucou ! Trop contente que tu sois là ! Avant de commencer, faisons connaissance."}},
    {"id": "skin_type", "type": "single", "emotion": "happy",
     "q": {"en": "Nice to meet you, {name}! How would you describe your skin?",
           "fr": "Enchantée {name} ! Comment tu décrirais ta peau ?"},
     "options": [opt("oily", "Oily", "Grasse", ["oily", "shiny", "greasy", "grasse", "gras", "brille"]),
                 opt("dry", "Dry", "Sèche", ["dry", "tight", "flaky", "sèche", "seche", "tiraille"]),
                 opt("combination", "Combination", "Mixte", ["combination", "combo", "t-zone", "t zone", "forehead", "mixte", "zone t", "le front", "mon front"]),
                 opt("normal", "Normal", "Normale", ["normal", "normale", "balanced", "équilibrée"]),
                 opt("unsure", "Not sure", "Je ne sais pas", ["not sure", "don't know", "dont know", "no idea", "unsure",
                                                                  "sais pas", "aucune idée", "help"])]},
    {"id": "skin_quiz", "type": "single", "emotion": "thinking", "only_if": lambda p: p["skin_type"] == "unsure",
     "q": {"en": "No worries, let's find out together! About an hour after washing your face with nothing on it, how does it feel?",
           "fr": "Pas de souci, on va trouver ensemble ! Une heure après avoir lavé ton visage, sans rien mettre, il est comment ?"},
     "options": [opt("oily", "Shiny all over", "Brillant partout", ["shiny all", "all over", "partout", "everywhere", "greasy"]),
                 opt("dry", "Tight or flaky", "Ça tiraille / ça pèle", ["tight", "flaky", "tiraille", "pèle", "dry", "sec"]),
                 opt("combination", "Shiny forehead & nose only", "Brillant front et nez seulement",
                     ["forehead", "nose", "t-zone", "front", "nez", "only"]),
                 opt("normal", "Comfy, nothing special", "Confortable, rien de spécial", ["comfy", "comfortable", "fine", "confortable", "normal", "rien"])]},
    {"id": "sensitive", "type": "single", "emotion": "thinking",
     "q": {"en": "Does your skin often sting, itch or turn red when you try new products?",
           "fr": "Est-ce que ta peau pique, gratte ou rougit souvent avec de nouveaux produits ?"},
     "options": [opt("yes", "Yes, often", "Oui, souvent", ["yes", "yeah", "yep", "often", "always", "oui", "souvent", "toujours"]),
                 opt("sometimes", "Sometimes", "Parfois", ["sometimes", "parfois", "kinda", "a bit", "un peu"]),
                 opt("no", "Not really", "Pas vraiment", ["no", "nope", "never", "rarely", "not really", "non", "jamais", "rarement", "pas vraiment"])]},
    {"id": "concerns", "type": "multi", "emotion": "happy",
     "q": {"en": "What would you love to improve on your skin? Pick as many as you want!",
           "fr": "Qu'est-ce que tu aimerais améliorer sur ta peau ? Choisis tout ce que tu veux !"},
     "options": [opt("acne", "Acne / breakouts", "Acné / boutons", ["acne", "acné", "breakout", "pimple", "spot", "bouton"]),
                 opt("blackheads", "Blackheads", "Points noirs", ["blackhead", "points noirs", "point noir"]),
                 opt("large pores", "Large pores", "Pores dilatés", ["pore"]),
                 opt("dark spots", "Dark spots", "Taches", ["dark spot", "pigment", "tache", "marks", "marques", "melasma"]),
                 opt("redness", "Redness", "Rougeurs", ["red", "rougeur", "rosacea", "rosacée"]),
                 opt("dryness", "Dryness", "Sécheresse", ["dryness", "dehydrat", "sécheresse", "déshydrat"]),
                 opt("dullness", "Dullness", "Teint terne", ["dull", "glow", "terne", "éclat"]),
                 opt("fine lines", "Fine lines", "Ridules", ["wrinkle", "fine line", "aging", "ageing", "ride", "ridule"]),
                 opt("dark circles", "Dark circles", "Cernes", ["dark circle", "under eye", "cerne"])]},
    {"id": "hair_type", "type": "single", "emotion": "excited",
     "q": {"en": "Ooh, now hair! What's your hair like?", "fr": "Ooh, maintenant les cheveux ! Ils sont comment ?"},
     "options": [opt("straight", "Straight", "Lisses", ["straight", "lisse", "raide"]),
                 opt("wavy", "Wavy", "Ondulés", ["wavy", "wave", "ondul"]),
                 opt("curly", "Curly", "Bouclés", ["curly", "curl", "boucl"]),
                 opt("coily", "Coily / 4C", "Crépus / frisés", ["coily", "coil", "kinky", "4c", "4a", "4b", "crépu", "frisé", "afro"]),
                 opt("skip", "Skip", "Passer", ["skip", "passer", "pass", "bald", "chauve"])]},
    {"id": "hair_concerns", "type": "multi", "emotion": "happy", "only_if": lambda p: p["hair_type"] not in (None, "skip"),
     "q": {"en": "Any hair struggles?", "fr": "Des soucis côté cheveux ?"},
     "options": [opt("frizz", "Frizz", "Frisottis", ["frizz", "frisott"]),
                 opt("dryness", "Dry / brittle", "Secs / cassants", ["dry", "brittle", "breakage", "sec", "cass"]),
                 opt("dandruff", "Dandruff", "Pellicules", ["dandruff", "flakes", "pellicule"]),
                 opt("oily roots", "Oily roots", "Racines grasses", ["oily", "greasy", "gras"]),
                 opt("hair loss", "Hair loss", "Chute de cheveux", ["loss", "falling", "thinning", "chute", "tombe"]),
                 opt("split ends", "Split ends", "Fourches", ["split", "fourche"]),
                 opt("color-treated", "Colored / bleached", "Colorés / décolorés", ["dye", "dyed", "color", "bleach", "colo", "décolor"])]},
    {"id": "avoid", "type": "text", "emotion": "concerned",
     "q": {"en": "Important one! Are you allergic to anything, or are there ingredients you want to avoid?",
           "fr": "Question importante ! Tu es allergique à quelque chose, ou il y a des ingrédients que tu veux éviter ?"},
     "chips": [{"value": "none", "en": "Nothing", "fr": "Rien"}, {"value": "fragrance", "en": "Fragrance", "fr": "Parfum"},
               {"value": "essential oils", "en": "Essential oils", "fr": "Huiles essentielles"}]},
    {"id": "routine", "type": "single", "emotion": "happy",
     "q": {"en": "How much of a routine do you want?", "fr": "Tu veux une routine de quelle taille ?"},
     "options": [opt("minimal", "Minimal (2–3 steps)", "Minimaliste (2–3 étapes)", ["minimal", "simple", "lazy", "quick", "minimal", "rapide", "flemme", "2", "3"]),
                 opt("moderate", "Moderate", "Moyenne", ["moderate", "medium", "normal", "moyen", "4", "5"]),
                 opt("nerd", "Full skincare nerd", "Passionnée de skincare", ["nerd", "full", "lots", "everything", "passion", "tout", "max"])]},
    {"id": "makeup", "type": "single", "emotion": "excited",
     "q": {"en": "Last one! How often do you wear makeup?", "fr": "Dernière question ! Tu te maquilles souvent ?"},
     "options": [opt("daily", "Every day", "Tous les jours", ["every day", "daily", "always", "tous les jours", "chaque jour", "toujours"]),
                 opt("sometimes", "Sometimes", "Parfois", ["sometimes", "weekend", "events", "parfois", "occasion"]),
                 opt("rarely", "Rarely / never", "Rarement / jamais", ["rarely", "never", "no", "rarement", "jamais", "non"])]},
]


def _applicable(i: int, p: dict) -> bool:
    cond = STEPS[i].get("only_if")
    return cond is None or cond(p)


def _next_index(i: int, p: dict) -> int:
    while i < len(STEPS) and not _applicable(i, p):
        i += 1
    return i


def _kw_match(text: str, kw: str) -> bool:
    if len(kw) <= 3:  # short words like "no", "4c" need word boundaries
        return re.search(rf"(?<![\w]){re.escape(kw)}(?![\w])", text) is not None
    return kw in text


def _match_single(text: str, options: list) -> str | None:
    best, best_len = None, 0
    for o in options:
        for kw in o["kw"]:
            if _kw_match(text, kw) and len(kw) > best_len:
                best, best_len = o["value"], len(kw)
    return best


def _match_multi(text: str, options: list) -> list[str]:
    return [o["value"] for o in options if any(_kw_match(text, kw) for kw in o["kw"])]


def _render(i: int, p: dict, lang: str, prefix: str = "") -> dict:
    s = STEPS[i]
    applicable = [j for j in range(len(STEPS)) if _applicable(j, p)]
    chips = [{"value": o["value"], "label": o[lang]} for o in s.get("options", s.get("chips", []))]
    live = pet.get()
    return {"done": False, "id": s["id"], "type": s["type"], "emotion": s["emotion"],
            "question": prefix + s["q"][lang].format(name=p.get("name") or ""), "options": chips,
            "progress": round(100 * applicable.index(i) / len(applicable)) if i in applicable else 0,
            "user_name": live["user_name"] or "", "pet_name": live["pet_name"]}


def _summary(p: dict, lang: str) -> str:
    skin = p.get("skin_type") or "?"
    if lang == "fr":
        fr = {"oily": "grasse", "dry": "sèche", "combination": "mixte", "normal": "normale"}
        txt = f"Yay, merci {p.get('name') or ''} ! Je retiens : peau {fr.get(skin, skin)}"
        if p.get("sensitive"):
            txt += " et sensible"
        if p.get("concerns"):
            txt += f", et tu veux travailler sur : {', '.join(p['concerns'])}"
        return txt + ". Maintenant, pose-moi toutes tes questions beauté !"
    txt = f"Yay, thank you {p.get('name') or ''}! Got it: {skin} skin"
    if p.get("sensitive"):
        txt += " that's on the sensitive side"
    if p.get("concerns"):
        txt += f", and you'd like help with {', '.join(p['concerns'])}"
    return txt + ". Now ask me anything about beauty!"


def current(lang: str | None = None) -> dict:
    state = pet.get()
    p = state["profile"]
    lang = lang or p.get("lang", "en")
    if p["onboarded"]:
        return {"done": True}
    i = _next_index(p["onboarding_step"], p)
    return _render(i, p, lang) if i < len(STEPS) else {"done": True}


def answer(text: str = "", values: list[str] | None = None, lang: str = "en") -> dict:
    state = pet.get()
    p = state["profile"]
    p["lang"] = lang
    i = _next_index(p["onboarding_step"], p)
    if p["onboarded"] or i >= len(STEPS):
        return {"done": True}
    s = STEPS[i]
    t = (text or "").lower().strip()
    retry = {"en": "Hmm, I didn't quite catch that. ", "fr": "Hmm, je n'ai pas bien compris. "}[lang]

    if s["type"] == "single":
        v = values[0] if values else _match_single(t, s["options"])
        if not v:
            return _render(i, p, lang, retry)
        if s["id"] == "skin_quiz":
            p["skin_type"] = v
        elif s["id"] == "sensitive":
            p["sensitive"] = v in ("yes", "sometimes")
        elif s["id"] in ("skin_type", "hair_type", "routine", "makeup"):
            p[s["id"]] = None if v == "skip" else v
            if s["id"] == "hair_type" and v == "skip":
                p["hair_type"] = "skip"
    elif s["type"] == "multi":
        chosen = values if values is not None else _match_multi(t, s["options"])
        if not chosen and t and not any(_kw_match(t, k) for k in NONE_KW):
            chosen = [t[:40]]  # keep their own words, e.g. "melasma on my cheeks"
        p[s["id"]] = [c for c in chosen if c != "none"]
    elif s["type"] == "names":  # typed only: [your name, pet name]
        user_name = (values or [""])[0].strip()
        if not user_name:
            return _render(i, p, lang, retry)
        pet.set_names(state, user_name, (values[1] if len(values) > 1 else "").strip() or "Glowbi")
    elif s["type"] == "text":
        if s["id"] == "avoid":
            t = re.sub(r"^(i'?m |i am )?(allergic to|avoid|je suis allergique (à|au|aux)|j'évite)\s*", "", t)
            raw = values or re.split(r",|;|\band\b|\bet\b|/", t)
            items = [x.strip(" .!") for x in raw if x.strip(" .!")]
            is_none = re.fullmatch(r"(none|nothing|nothing really|no|nope|non|rien|aucun\w*|pas vraiment|"
                                   r"no allergies|not allergic|rien de spécial)", " ".join(items))
            p["avoid"] = [] if not items or is_none else items

    nxt = _next_index(i + 1, p)
    p["onboarding_step"] = nxt
    if nxt >= len(STEPS):
        p["onboarded"] = True
        if p.get("skin_type") == "unsure":
            p["skin_type"] = None
        if p.get("hair_type") == "skip":
            p["hair_type"] = None
        pet.gain(state, xp=25, happy=15)
        pet.save(state)
        return {"done": True, "finished_now": True, "emotion": "love", "question": _summary(p, lang),
                "pet": pet.public(state)}
    pet.save(state)
    return _render(nxt, p, lang)


def restart() -> dict:
    state = pet.get()
    lang = state["profile"].get("lang", "en")
    state["profile"] = {**pet.DEFAULT_PROFILE, "lang": lang}
    pet.save(state)
    return current(lang)
