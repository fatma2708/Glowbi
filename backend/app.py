"""Glowbi API + serves the pet UI.  Run:  uvicorn backend.app:app --reload

The RAG knowledge base is fed by a background job (and/or `python -m scripts.feed`).
Nothing about feeding is exposed in the UI.
"""
import json
import os
import threading
import time

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import brain, config, ingredients, onboarding, pet, routine, stt, tts, vision, wardrobe
from backend.rag.scraper import feed_glowbi, ingest_seed
from backend.rag.store import store

AUTO_FEED = os.getenv("AUTO_FEED", "true").lower() == "true"
FEED_INTERVAL_HOURS = float(os.getenv("FEED_INTERVAL_HOURS", "12"))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
STT_MODE = os.getenv("STT_MODE", "auto")  # auto = browser first, Whisper fallback | server = always Whisper

app = FastAPI(title="Glowbi")
_feeding = {"running": False, "last": None}


@app.get("/health")
def health():
    return {"status": "ok"}


def _run_feed():
    if _feeding["running"]:
        return
    _feeding["running"] = True
    try:
        _feeding["last"] = {**feed_glowbi(), "at": time.time()}
        print(f"[feeder] done: {_feeding['last']}")
    except Exception as e:  # a blog being down must never crash the app
        _feeding["last"] = {"error": str(e), "at": time.time()}
        print(f"[feeder] failed: {e}")
    finally:
        _feeding["running"] = False


def _feeder_loop():
    time.sleep(20)  # let the server boot first
    while True:
        _run_feed()
        time.sleep(FEED_INTERVAL_HOURS * 3600)


def _warm_up():
    store.search("warm up", k=1)  # loads the embedding model + search index, else the first chat takes ~25 s
    tts.warm()
    tts.prepare_sfx(pet.get()["appearance"]["voice"])


@app.on_event("startup")
def _startup():
    if store.stats()["documents"] == 0:
        print(f"[startup] seeded {ingest_seed()} starter notes")
    if AUTO_FEED:
        threading.Thread(target=_feeder_loop, daemon=True).start()
        print(f"[startup] background feeder ON (every {FEED_INTERVAL_HOURS}h)")
    threading.Thread(target=_warm_up, daemon=True).start()


# ---------------- models ----------------
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class AnswerIn(BaseModel):
    text: str = ""
    values: list[str] | None = None
    lang: str = "en"


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    lang: str = "en"
    voice: str | None = None   # the pet's chosen voice; empty = the .env voice
    engine: str | None = None
    speed: float | None = Field(default=None, ge=0.5, le=1.5)


class NamesIn(BaseModel):
    user_name: str | None = Field(default=None, max_length=24)
    pet_name: str | None = Field(default=None, max_length=24)


class CheckIn(BaseModel):
    text: str = Field(min_length=2, max_length=6000)
    lang: str = "en"


class RememberIn(BaseModel):
    field: str
    value: str


class UnlockIn(BaseModel):
    id: str


class RoutineDoneIn(BaseModel):
    mode: str


class SettingsIn(BaseModel):
    music_on: bool | None = None
    music_volume: float | None = Field(default=None, ge=0, le=1)
    music_track: str | None = None
    sfx_volume: float | None = Field(default=None, ge=0, le=1)


class ProfileIn(BaseModel):
    skin_type: str | None = None
    hair_type: str | None = None
    concerns: list[str] | None = None
    avoid: list[str] | None = None
    lang: str | None = None


# ---------------- pet & chat ----------------
@app.get("/api/config")
def ui_config():
    return {"stt_mode": STT_MODE, "server_stt": stt.available(), "tts_engine": tts.active_engine(), "tts_rate": tts.PITCH}


@app.get("/api/pet")
def get_pet():
    return pet.public(pet.get())


@app.post("/api/chat")
def chat(body: ChatIn):
    return brain.answer(body.message.strip())


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn):
    events = (json.dumps(e, ensure_ascii=False) + "\n" for e in brain.stream(body.message.strip()))
    return StreamingResponse(events, media_type="application/x-ndjson")


@app.post("/api/pet/poke")
def poke():
    return pet.public(pet.on_poke())


@app.post("/api/profile")
def set_profile(body: ProfileIn):
    return pet.public(pet.update_profile(**body.model_dump()))


# ---------------- onboarding ----------------
@app.get("/api/onboarding")
def onboarding_state(lang: str = "en"):
    return onboarding.current(lang)


@app.post("/api/onboarding/answer")
def onboarding_answer(body: AnswerIn):
    return onboarding.answer(body.text, body.values, body.lang if body.lang in ("en", "fr") else "en")


@app.post("/api/onboarding/restart")
def onboarding_restart():
    return onboarding.restart()


# ---------------- speech to text ----------------
@app.post("/api/stt")
async def speech_to_text(audio: UploadFile = File(...), lang: str = Form("en")):
    if not stt.available():
        raise HTTPException(501, "Server STT not installed: pip install faster-whisper")
    data = await audio.read()
    if len(data) > 15_000_000:
        raise HTTPException(413, "Recording too long")
    suffix = ".ogg" if "ogg" in (audio.content_type or "") else ".mp4" if "mp4" in (audio.content_type or "") else ".webm"
    try:
        text = stt.transcribe(data, lang if lang in ("en", "fr") else None, suffix)
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")
    return {"text": text}


# ---------------- text to speech ----------------
@app.post("/api/tts")
def text_to_speech(body: TtsIn):
    try:
        audio, cached, engine = tts.synthesize(body.text, body.lang, body.voice, body.engine, body.speed)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except tts.TTSError as e:
        raise HTTPException(503, str(e))
    return Response(audio, media_type="audio/wav", headers={"X-TTS-Cache": "hit" if cached else "miss", "X-TTS-Engine": engine})


@app.get("/api/sfx/{kind}")
def sound_effect(kind: str):
    try:
        return Response(tts.sfx(kind, pet.get()["appearance"]["voice"]), media_type="audio/wav")
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(503, f"Sound failed: {e}")


# ---------------- wardrobe, names, sound settings ----------------
@app.get("/api/wardrobe")
def wardrobe_catalog():
    return wardrobe.catalog()


@app.patch("/api/pet/appearance")
def update_appearance(patch: dict):
    state = pet.get()
    voice = state["appearance"]["voice"]
    try:
        wardrobe.apply(state, patch)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    pet.save(state)
    if state["appearance"]["voice"] != voice:  # her giggles should match her new voice
        threading.Thread(target=tts.prepare_sfx, args=(state["appearance"]["voice"],), daemon=True).start()
    return pet.public(state)


@app.post("/api/pet/unlock")
def unlock_item(body: UnlockIn):
    state = pet.get()
    try:
        wardrobe.buy(state, body.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    pet.save(state)
    return pet.public(state)


@app.post("/api/pet/names")
def rename(body: NamesIn):
    state = pet.get()
    pet.set_names(state, body.user_name, body.pet_name)
    pet.save(state)
    return pet.public(state)


@app.post("/api/pet/settings")
def update_settings(body: SettingsIn):
    state = pet.get()
    state["settings"].update({k: v for k, v in body.model_dump().items() if v is not None})
    pet.save(state)
    return pet.public(state)


@app.post("/api/pet/tickle")
def tickle():
    state, rewarded = pet.on_tickle()
    return {"rewarded": rewarded, "pet": pet.public(state)}


@app.get("/api/music")
def music_files():
    folder = config.FRONTEND_DIR / "music"
    return sorted(f.name for f in folder.glob("*") if f.suffix.lower() in (".mp3", ".ogg")) if folder.exists() else []


# ---------------- photos and ingredient checker ----------------
@app.post("/api/vision")
def read_photo(image: UploadFile = File(...), question: str = Form(""), lang: str = Form("en")):
    """Photos stay in memory: nothing here writes them to disk."""
    data = image.file.read()
    if len(data) > 8_000_000:
        raise HTTPException(413, "Photo too large")
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(415, "Not an image")
    return vision.analyze(data, question[:300], lang)


@app.post("/api/ingredients/check")
def check_ingredients(body: CheckIn):
    """A pasted INCI list, a barcode, or a product name."""
    text = body.text.strip()
    if text.count(",") >= 2:
        return vision.checked(text, body.lang)
    hit = ingredients.lookup(text)
    if not hit:
        return vision._simple("product_front", vision.LINES["not_found"]["fr" if body.lang == "fr" else "en"].format(name=text), "thinking")
    return vision.checked(hit["ingredients"], body.lang, f"{hit['brand']} {hit['name']}".strip())


@app.post("/api/pet/remember")
def remember_photo_finding(body: RememberIn):
    if body.value not in vision.ALLOWED.get(body.field, ()):
        raise HTTPException(400, "Unknown value")
    state = pet.get()
    pet.remember(state, body.field, body.value)
    pet.save(state)
    return pet.public(state)


# ---------------- routine quest ----------------
@app.get("/api/routine")
def routine_plan(mode: str = "morning", lang: str = "en"):
    try:
        return routine.plan(mode, lang)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/routine/complete")
def routine_complete(body: RoutineDoneIn):
    state = pet.get()
    try:
        reward = routine.complete(state, body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    pet.save(state)
    return {**reward, "pet": pet.public(state)}


# ---------------- admin (not used by the UI) ----------------
def _check_admin(token: str | None):
    if ADMIN_TOKEN and token != ADMIN_TOKEN:
        raise HTTPException(403, "Bad admin token")


@app.post("/admin/feed")
def admin_feed(x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    if _feeding["running"]:
        raise HTTPException(409, "Already feeding")
    threading.Thread(target=_run_feed, daemon=True).start()
    return {"status": "started"}


@app.get("/admin/stats")
def admin_stats(x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    return {"knowledge": store.stats(), "feeder": _feeding, "auto_feed": AUTO_FEED,
            "interval_hours": FEED_INTERVAL_HOURS, "llm": config.LLM_PROVIDER}


@app.get("/admin/search")
def admin_search(q: str, k: int = 5, category: str | None = None, x_admin_token: str | None = Header(default=None)):
    _check_admin(x_admin_token)
    return store.search(q, k, category)


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")
