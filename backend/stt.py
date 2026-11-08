"""Server-side speech-to-text with Whisper: Groq's hosted API, or faster-whisper (local, free). Works in every browser.

The browser's built-in Web Speech API is used first (instant live words, Chrome/Edge). This is the fallback
for Firefox/Safari/Brave, or when you set STT_MODE=server to always use Whisper.
"""
import os
import tempfile

import httpx

from backend import config

_model = None
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # tiny | base | small | medium (bigger = better, slower)
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_STT_MODEL = "whisper-large-v3-turbo"
VOCAB_HINT = "Skincare, makeup, hair: niacinamide, retinol, SPF, sérum, peau grasse, cheveux bouclés."
# groq | local. Defaults to groq when the LLM already points at Groq
STT_PROVIDER = os.getenv("STT_PROVIDER", "").lower() or ("groq" if "api.groq.com" in config.OPENAI_BASE_URL else "local")


def _use_groq() -> bool:
    return STT_PROVIDER == "groq" and bool(config.OPENAI_API_KEY)


def available() -> bool:
    if _use_groq():
        return True
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="int8")
    return _model


def _groq_transcribe(audio: bytes, lang: str | None, suffix: str) -> str:
    data = {"model": GROQ_STT_MODEL, "prompt": VOCAB_HINT, **({"language": lang} if lang else {})}
    r = httpx.post(GROQ_STT_URL, timeout=60, headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                   data=data, files={"file": (f"audio{suffix}", audio)})
    r.raise_for_status()
    return r.json()["text"].strip()


def transcribe(audio: bytes, lang: str | None = None, suffix: str = ".webm") -> str:
    if _use_groq():
        return _groq_transcribe(audio, lang, suffix)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio)
        path = f.name
    try:
        segments, _ = _get_model().transcribe(
            path, language=lang, vad_filter=True, beam_size=1,
            initial_prompt=VOCAB_HINT)
        return " ".join(s.text.strip() for s in segments).strip()
    finally:
        os.unlink(path)
