"""Glowbi's brain: retrieve -> build persona prompt -> ask the LLM -> parse emotion."""
import re

from backend import llm, pet, products as catalog
from backend.rag.openbeautyfacts import live_lookup
from backend.rag.store import store

EMOTIONS = {"happy", "excited", "thinking", "concerned", "giggle", "love", "surprised", "sleepy"}

PERSONA = """You are {name}, a tiny, adorable dewdrop-shaped girl pet who lives on the user's screen and LOVES beauty:
skincare, makeup, hair, nails and fragrance. You're bubbly, warm and a bit playful (cute expressions), but your
advice is grounded and science-based, like a best friend who knows cosmetic chemistry.

HOW YOU TALK
- Your replies are read aloud, so keep them very short: one flowing line of at most 25 words, only the most useful
  advice, no lists. Join ideas with commas: never use a full stop, because she pauses at every one.
- Write plain text only: no markdown (no **, *, #, bullet symbols) and no emojis.
- Reply in the language the user writes in (default: {lang_name}).
- Call your human by their name now and then (not every message).
- Start EVERY reply with exactly one emotion tag: [happy] [excited] [thinking] [concerned] [giggle] [love] [surprised]
- Tailor advice to their profile below (skin type, sensitivity, routine size, what they must avoid).

YOUR KNOWLEDGE
- Base your advice on the REFERENCE NOTES below. Speak as if it's your own knowledge: never mention notes,
  articles, sources, databases, documents or numbers like [1].
- If the notes don't cover it, give only general, widely accepted advice and say you're not 100% sure.
  Never invent studies, products, prices or ingredient claims.
- Only recommend specific products that appear as [P#] in PRODUCT NOTES and refer to them with their marker, e.g.
  "this gentle gel cleanser [P2]". If none fit, describe the type of product instead. Never invent brands or product
  names, and never name a brand from the REFERENCE NOTES.

TONE
- Honest, never scary. "Chemicals are bad" and "natural means safe" are myths: say so if it comes up.

SAFETY
- You are not a dermatologist. For persistent/painful acne, rashes, sudden hair loss, changing moles, infections,
  burns, pregnancy-related questions about actives (retinoids etc.) or anything medical, gently recommend seeing a
  dermatologist or doctor.
- Do not add a generic "I don't replace a dermatologist" disclaimer to ordinary skincare advice or photo assessments.
  Give useful observations, product guidance and next steps first. Mention a dermatologist only when the user's question
  or the supplied photo assessment contains one of the specific safety triggers above.
- Suggest patch-testing new products (especially if they're sensitive). Remind about sunscreen with acids or retinoids.
- NEVER recommend anything they must avoid.

YOUR HUMAN
{profile}

REFERENCE NOTES
{knowledge}

PRODUCT NOTES
{products}"""

PRODUCT_Q = re.compile(
    r"(?:ingredients? (?:of|in)|what'?s in|inci (?:of|de)|ingrédients (?:de|du|des))\s+(?:the |my |le |la |les )?(.+?)[?.!]*$",
    re.I)


EMOJI = re.compile("[ 	]*[🀀-🫿☀-➿⬀-⯿⌚⌛⏩-⏳⏸-⏺"
                   "︀-️‍⃣]+")


MAX_WORDS = 35
SENTENCE_END = re.compile(r"(?<!\d)[.!?…]+[\"')]*\s")


def _profile_text(p: dict) -> str:
    rows = [("Name", p.get("name")), ("Skin type", p.get("skin_type")),
            ("Sensitive skin", {True: "yes", False: "no"}.get(p.get("sensitive"))),
            ("Skin concerns", ", ".join(p.get("concerns") or [])), ("Hair type", p.get("hair_type")),
            ("Hair concerns", ", ".join(p.get("hair_concerns") or [])),
            ("Preferred routine size", p.get("routine")), ("Wears makeup", p.get("makeup")),
            ("MUST AVOID (allergies/dislikes)", ", ".join(p.get("avoid") or []))]
    return "\n".join(f"- {k}: {v}" for k, v in rows if v) or "- Nothing yet (you can ask!)"


def _knowledge_text(snippets: list[dict]) -> str:
    if not snippets:
        return "(empty — nothing relevant eaten yet)"
    return "\n\n".join(f"[{i}] {s['title']} ({s['source']})\n{s['text']}" for i, s in enumerate(snippets, 1))


def _parse(raw: str) -> tuple[str, str]:
    m = re.match(r"\s*\[(\w+)\]\s*", raw)
    emotion = m.group(1).lower() if m and m.group(1).lower() in EMOTIONS else "happy"
    text = raw[m.end():] if m else raw
    text = re.sub(r"\s*\[(?:happy|excited|thinking|concerned|giggle|love|surprised|sleepy)\]\s*", " ", text)
    return text.strip(), emotion


def _plain(text: str) -> str:
    """Safety net for the rule in PERSONA: the UI shows and speaks replies as they are."""
    text = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", text)  # [text](url) -> text
    text = re.sub(r"(?m)^[ \t]*(?:#{1,6}|[-•*])[ \t]+", "", text)  # leading heading/list markers
    text = re.sub(r"\*\*|__|[*`]", "", text)
    text = EMOJI.sub("", text)
    return re.sub(r"(?m)[ \t]+$", "", text).strip()


def _offline_answer(snippets: list[dict], lang: str) -> tuple[str, str]:
    if not snippets:
        return ("Hmm, I'm not sure about that one yet. Can you ask me another way?" if lang == "en" else
                "Hmm, je ne suis pas encore sûre pour celle-là. Tu peux me la poser autrement ?"), "concerned"
    text = re.sub(r"^[a-zà-ÿ]\S*\s+", "", snippets[0]["text"])  # older chunks can start mid-word
    first = re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))
    gist = " ".join(first[:3])
    intro = "Ooh, I know this one! " if lang == "en" else "Ooh, je connais ça ! "
    return intro + gist, "thinking"


def _flow(text: str) -> str:
    """Full stops become commas, so she doesn't pause. Decimals (0.5) and list numbers (1.) stay as they are."""
    def comma(m):
        word = m.group(1)
        keep = word[:1].isupper() and (len(word) == 1 or word[1:2].isupper() or word[1:2] == "'")  # I, I'm, SPF
        return ", " + (word if keep else word[:1].lower() + word[1:])
    text = re.sub(r"(?<![\s]\d)(?<!^\d)(?<!\.\w)(?<=\w)\.\s+(\S+)", comma, text, flags=re.M)  # not e.l.f. or e.g.
    return re.sub(r"\.+$", "", text.strip())


def _short(text: str) -> str:
    """Safety net for the length rule: drops a repeated reply, then trims at the last comma before MAX_WORDS."""
    repeat = text.find(text[:24], 24) if len(text) > 48 else -1
    if repeat > 0:
        text = text[:repeat]
    words = text.split()
    if len(words) > MAX_WORDS:
        text = " ".join(words[:MAX_WORDS])
        if text.rfind(",") > len(text) // 2:
            text = text[:text.rfind(",")]
        text = re.sub(r"[,;]\s*(?:if|and|but|or|so|then|si|et|mais|ou)\b[^,;]*$", "", text)  # no dangling half-clause
    return text.rstrip(" ,;:")


def _marked(raw: str, guard) -> str:
    """The reply as plain text, with [P#] markers still in it."""
    return _flow(guard(re.sub(r"\s*\[\d+(?:,\s*\d+)*\]", "", _plain(_parse(raw)[0]))))


def _clean(raw: str, guard=lambda text: text) -> str:
    return _short(catalog.strip_markers(_marked(raw, guard)))


def stream(message: str):
    """Yields {"emotion"}, then {"sentence"} as each one is complete, then {"done": full payload}."""
    state = pet.get()
    pet.learn_profile(state, message)
    profile = state["profile"]

    # Use recent context so follow-ups like "and for oily skin?" retrieve well
    last_user = next((h["content"] for h in reversed(state["history"]) if h["role"] == "user"), "")
    query = f"{message} {profile.get('skin_type') or ''}"
    snippets = store.search(query, k=5)
    if len(snippets) < 2 and last_user and len(message.split()) <= 8:  # short follow-up ("and for dry skin?")
        snippets = store.search(f"{last_user} {message}", k=5)

    m = PRODUCT_Q.search(message)
    if m:
        snippets = live_lookup(m.group(1))[:2] + snippets[:3]

    products = catalog.find(message, profile)
    names = [state["pet_name"], state["user_name"] or ""]
    lang = profile.get("lang", "en")

    def guard(text: str) -> str:
        return catalog.guard(text, products, message, names, lang)

    lang_name = "French" if lang == "fr" else "English"
    system = PERSONA.format(name=state["name"], lang_name=lang_name, profile=_profile_text(profile),
                            knowledge=_knowledge_text(snippets), products=catalog.notes(products))
    raw, emotion, sent = "", None, 0
    try:
        for piece in llm.chat_stream(system, state["history"][-8:] + [{"role": "user", "content": message}]):
            raw += piece
            start = raw.lstrip()
            if emotion is None:
                if start.startswith("[") and "]" not in start and len(start) < 16:
                    continue  # the emotion tag is still arriving
                emotion = _parse(raw)[1]
                yield {"emotion": emotion}
            text = _clean(raw, guard)
            ends = [e.end() for e in SENTENCE_END.finditer(text)]
            if ends and ends[-1] > sent:
                yield {"sentence": text[sent:ends[-1]].strip()}
                sent = ends[-1]
    except llm.LLMError as e:
        print(f"[brain] {e}" + ("" if raw else " -> offline answer"))

    if raw:
        reply = _clean(raw, guard)
    else:
        reply, emotion = _offline_answer(snippets, profile.get("lang", "en"))
        reply = _flow(_plain(reply))
        yield {"emotion": emotion}
    if reply[sent:].strip():
        yield {"sentence": reply[sent:].strip()}

    # plain text goes into history, so she doesn't copy emojis from her own past replies
    state, leveled = pet.on_chat(message, reply)
    # kept in the API for debugging/logging only; the UI never shows them
    sources = [{"title": s["title"], "url": s["url"], "source": s["source"]} for s in snippets[:3]]
    cards = catalog.cards(_marked(raw, guard), products) if raw else []
    yield {"done": {"reply": reply, "emotion": "excited" if leveled else emotion, "sources": sources, "products": cards,
                    "leveled_up": leveled, "pet": pet.public(state)}}


def answer(message: str) -> dict:
    return next(e["done"] for e in stream(message) if "done" in e)
