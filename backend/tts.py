"""Glowbi's voice: text -> WAV. Kokoro (local, free, CPU) by default, Groq Orpheus optional (English only).

The browser's speechSynthesis stays as the last fallback, on the front-end. Audio is cached in data/tts_cache/.
"""
import hashlib
import io
import os
import re
import struct
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np

from backend import config
from backend.brain import _plain

ENGINE = os.getenv("TTS_ENGINE", "kokoro").lower()  # kokoro | groq | browser
VOICE_EN = os.getenv("TTS_VOICE_EN", "af_heart")  # one voice, or a blend like af_heart:60,af_sky:40
VOICE_FR = os.getenv("TTS_VOICE_FR", "ff_siwis")  # Kokoro's only French voice
GROQ_VOICE = os.getenv("TTS_GROQ_VOICE", "hannah")  # English with TTS_ENGINE=groq; TTS_VOICE_EN stays the Kokoro fallback
SPEED = float(os.getenv("TTS_SPEED", "1.05"))
PITCH = float(os.getenv("TTS_PITCH", "1.12"))  # browser playbackRate: the cute lift, also speeds her up a little
KOKORO_MODEL = os.getenv("TTS_KOKORO_MODEL", "kokoro-v1.0.onnx")  # or kokoro-v1.0.int8.onnx (~190 MB less RAM)

MODEL_DIR = config.DATA_DIR / "tts_models"
CACHE_DIR = config.DATA_DIR / "tts_cache"
CACHE_MAX_FILES = 200
RELEASE_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
VOICES_FILE = "voices-v1.0.bin"
KOKORO_LANGS = {"en": "en-us", "fr": "fr-fr"}

KOKORO_THREADS = max(1, min(4, (os.cpu_count() or 2) // 2))  # physical cores: measured faster than all logical ones
TAIL_SILENCE = 0.05  # seconds kept after the last sound, so sentences flow into each other

GROQ_TTS_URL = "https://api.groq.com/openai/v1/audio/speech"
GROQ_TTS_MODEL = "canopylabs/orpheus-v1-english"
GROQ_VOICES = {"autumn", "diana", "hannah", "austin", "daniel", "troy"}
GROQ_MAX_CHARS = 200  # Orpheus limit per request, including the [cheerful] direction
GROQ_DIRECTION = "[cheerful] "

_groq_paused_until = 0.0  # after a 429 we go straight to Kokoro: this key allows 100 requests a day
_kokoro = None
_load_lock = threading.Lock()
_synth_lock = threading.Lock()  # one synthesis at a time: it already uses every CPU core


DIRECTION = re.compile(r"\[[\w ]+\]\s*|<\w+>\s*")


class TTSError(Exception):
    pass


def _download(name: str):
    path = MODEL_DIR / name
    if path.exists():
        return path
    MODEL_DIR.mkdir(exist_ok=True)
    print(f"[tts] downloading {name}…")
    part = path.with_suffix(".part")
    with httpx.stream("GET", f"{RELEASE_URL}/{name}", follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with open(part, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    part.replace(path)
    return path


def _get_kokoro():
    global _kokoro
    with _load_lock:
        if _kokoro is None:
            try:
                import onnxruntime as rt
                from kokoro_onnx import Kokoro
            except ImportError as e:
                raise TTSError("Kokoro not installed: pip install kokoro-onnx") from e
            options = rt.SessionOptions()
            options.intra_op_num_threads = KOKORO_THREADS
            options.inter_op_num_threads = 1
            session = rt.InferenceSession(str(_download(KOKORO_MODEL)), options, providers=["CPUExecutionProvider"])
            _kokoro = Kokoro.from_session(session, str(_download(VOICES_FILE)))
            print(f"[tts] Kokoro ready ({KOKORO_MODEL})")
    return _kokoro


def _style(kokoro, voice: str):
    """'af_heart' stays a name; 'af_heart:60,af_sky:40' becomes a weighted mix of the voice styles."""
    known = set(kokoro.get_voices())
    parts = [p.strip().partition(":") for p in voice.split(",")]
    names = [p[0] for p in parts]
    if unknown := [n for n in names if n not in known]:
        raise ValueError(f"Unknown voice: {', '.join(unknown)}")
    if len(parts) == 1:
        return names[0]
    try:
        weights = np.array([float(p[2] or 1) for p in parts], dtype=np.float32)
    except ValueError as e:
        raise ValueError(f"Bad blend: {voice}") from e
    if weights.min() < 0 or weights.sum() <= 0:
        raise ValueError(f"Bad blend: {voice}")
    weights /= weights.sum()
    return sum(w * kokoro.get_voice_style(n) for w, n in zip(weights, names))


def _to_wav(audio, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def _trim_tail(audio, sample_rate: int):
    loud = np.flatnonzero(np.abs(audio) > 0.01)
    return audio[:loud[-1] + int(TAIL_SILENCE * sample_rate)] if loud.size else audio


def _kokoro_wav(text: str, voice: str, lang: str, speed: float = SPEED) -> bytes:
    text = DIRECTION.sub("", text)  # Kokoro would read "[cheerful]" aloud
    kokoro = _get_kokoro()
    style = _style(kokoro, voice)
    with _synth_lock:
        audio, sample_rate = kokoro.create(text, voice=style, speed=speed, lang=KOKORO_LANGS[lang])
    return _to_wav(_trim_tail(audio, sample_rate), sample_rate)


def _groq_chunks(text: str) -> list[str]:
    """Split on sentences, then on spaces, so each request fits Orpheus's character limit."""
    limit = GROQ_MAX_CHARS - len(GROQ_DIRECTION)
    chunks, current = [], ""
    for piece in re.split(r"(?<=[.!?])\s+|(?<=,)\s+", text):
        while len(piece) > limit:
            cut = piece.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            chunks.append(piece[:cut])
            piece = piece[cut:].strip()
        if len(current) + len(piece) + 1 > limit:
            chunks.append(current)
            current = piece
        else:
            current = f"{current} {piece}".strip()
    return [c for c in chunks + [current] if c]


def _groq_chunk(chunk: str, voice: str) -> tuple[bytes, int]:
    global _groq_paused_until
    text = chunk if chunk.startswith(("[", "<")) else GROQ_DIRECTION + chunk
    r = httpx.post(GROQ_TTS_URL, timeout=20, headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                   json={"model": GROQ_TTS_MODEL, "input": text, "voice": voice, "response_format": "wav"})
    if r.status_code == 429:
        _groq_paused_until = time.time() + float(r.headers.get("retry-after") or 60)
        threading.Thread(target=_get_kokoro, daemon=True).start()  # the fallback should be ready by the next clip
    if r.status_code >= 400:
        raise TTSError(f"Groq TTS failed ({r.status_code}): {r.text[:200]}")
    left = r.headers.get("x-ratelimit-remaining-requests")
    if left and int(left) <= 10:
        print(f"[tts] Orpheus: {left} requests left today")
    start = r.content.index(b"data") + 8  # the header is written for streaming, with a fake length
    return r.content[start:], struct.unpack("<I", r.content[24:28])[0]


def _groq_wav(text: str, voice: str) -> bytes:
    if not config.OPENAI_API_KEY:
        raise TTSError("Groq TTS needs OPENAI_API_KEY")
    if time.time() < _groq_paused_until:
        raise TTSError("Groq TTS rate limited")
    chunks = _groq_chunks(text)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda c: _groq_chunk(c, voice), chunks))
    audio = np.frombuffer(b"".join(pcm for pcm, _ in results), dtype="<i2").astype(np.float32) / 32768
    return _to_wav(_trim_tail(audio, results[0][1]), results[0][1])


def _cache_put(path, audio: bytes):
    CACHE_DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_bytes(audio)
    tmp.replace(path)
    files = sorted(CACHE_DIR.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[CACHE_MAX_FILES:]:
        old.unlink(missing_ok=True)


def active_engine() -> str:
    return "kokoro" if ENGINE == "groq" and time.time() < _groq_paused_until else ENGINE


def synthesize(text: str, lang: str = "en", voice: str | None = None, engine: str | None = None,
               speed: float | None = None) -> tuple[bytes, bool, str]:
    """Returns (wav bytes, came from cache, engine). ValueError = bad input, TTSError = the engines failed."""
    text = _plain(text)
    if not text:
        raise ValueError("Nothing to say")
    lang = lang if lang in KOKORO_LANGS else "en"
    engine = (engine or ENGINE).lower()
    if engine == "browser":
        raise TTSError("TTS_ENGINE=browser: the browser speaks")
    if engine not in ("kokoro", "groq"):
        raise ValueError(f"Unknown engine: {engine}")
    if lang == "fr":  # Orpheus is English only
        engine = "kokoro"
    if engine == "groq":
        voice = voice or GROQ_VOICE
        if voice not in GROQ_VOICES:
            raise ValueError(f"Unknown Groq voice: {voice}")
    else:
        voice = voice or (VOICE_FR if lang == "fr" else VOICE_EN)

    speed = speed or SPEED
    key = hashlib.sha256(f"{engine}|{lang}|{voice}|{speed}|{KOKORO_MODEL}|{TAIL_SILENCE}|{text}".encode()).hexdigest()[:32]
    path = CACHE_DIR / f"{key}.wav"
    if path.exists():
        path.touch()  # keeps often-used lines from being evicted
        return path.read_bytes(), True, engine

    try:
        audio = _groq_wav(text, voice) if engine == "groq" else _kokoro_wav(text, voice, lang, speed)
    except TTSError as e:
        if engine != "groq":
            raise
        print(f"[tts] {e} -> Kokoro")
        return synthesize(text, lang, None, "kokoro", speed)
    except ValueError:
        raise
    except httpx.HTTPError as e:
        if engine != "groq":
            raise TTSError(f"{engine} failed: {e}") from e
        print(f"[tts] Groq TTS failed: {e} -> Kokoro")
        return synthesize(text, lang, None, "kokoro", speed)
    except Exception as e:  # network, model or espeak failure: the front-end falls back to the browser voice
        raise TTSError(f"{engine} failed: {e}") from e
    _cache_put(path, audio)
    return audio, False, engine


SFX_DIR = config.DATA_DIR / "sfx"
SFX_LINES = {"hihi": "Hihi!", "hehe": "Hehe!", "hehehe": "Hehehehe!", "breathless": "Hehe... haha... hehehe...",
             "yay": "Yay!", "ooh": "Ooh?", "yawn": "Aaah... mmm.", "mmh": "Mmm..."}


def _sfx_voice(voice: str | None) -> str:
    """Sound effects always use Kokoro, so they never spend the Orpheus quota."""
    return VOICE_EN if not voice or voice in GROQ_VOICES else voice


def _sfx_path(kind: str, voice: str | None):
    key = hashlib.sha256(f"{_sfx_voice(voice)}|{SPEED}".encode()).hexdigest()[:12]
    return SFX_DIR / f"{key}_{kind}.wav"


def sfx(kind: str, voice: str | None = None) -> bytes:
    if kind not in SFX_LINES:
        raise ValueError(f"Unknown sound: {kind}")
    path = _sfx_path(kind, voice)
    if not path.exists():
        SFX_DIR.mkdir(exist_ok=True)
        path.write_bytes(_kokoro_wav(SFX_LINES[kind], _sfx_voice(voice), "en"))
    return path.read_bytes()


def prepare_sfx(voice: str | None = None):
    """Generates her sounds in the background, and drops the ones made with a previous voice."""
    global _kokoro
    wanted = {_sfx_path(k, voice).name for k in SFX_LINES}
    try:
        for kind in SFX_LINES:
            sfx(kind, voice)
    except Exception as e:
        print(f"[tts] sound effects failed: {e}")
        return
    for old in SFX_DIR.glob("*.wav"):
        if old.name not in wanted:
            old.unlink(missing_ok=True)
    if ENGINE != "kokoro" and active_engine() == ENGINE:
        with _load_lock:
            _kokoro = None  # ~500 MB back: Orpheus is the main voice


def warm():
    """Load Kokoro and run it once: the first synthesis is ~8 s slower than the next ones."""
    if ENGINE != "kokoro":
        return
    try:
        _get_kokoro().create("Hi.", voice=VOICE_EN.split(":")[0].split(",")[0], speed=SPEED, lang="en-us")
    except Exception as e:
        print(f"[tts] warm-up failed: {e}")
