"""Pluggable LLM brain: Ollama (local, free), OpenAI-compatible APIs, Anthropic, or offline fallback."""
import json

import httpx

from backend import config


class LLMError(Exception):
    pass


def chat(system: str, messages: list[dict], temperature: float = 0.7) -> str:
    provider = config.LLM_PROVIDER
    try:
        if provider == "ollama":
            return _ollama(system, messages, temperature)
        if provider == "openai":
            return _openai(system, messages, temperature)
        if provider == "anthropic":
            return _anthropic(system, messages, temperature)
    except (httpx.HTTPError, KeyError, IndexError) as e:
        raise LLMError(f"{provider} failed: {e}") from e
    raise LLMError("offline mode")


def chat_stream(system: str, messages: list[dict], temperature: float = 0.7):
    """Yields the reply piece by piece. Same chain as chat(), but only OpenAI-compatible APIs really stream."""
    if config.LLM_PROVIDER != "openai":
        yield chat(system, messages, temperature)
        return
    fallback = config.OPENAI_FALLBACK_MODEL
    models = [config.OPENAI_MODEL] + ([fallback] if fallback and fallback != config.OPENAI_MODEL else [])
    for i, model in enumerate(models):
        started = False
        try:
            for piece in _openai_stream(model, system, messages, temperature):
                started = True
                yield piece
            if started:
                return
            raise ValueError("empty reply")
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            if started or i == len(models) - 1:  # mid-reply failures can't switch model: the text is already out
                raise LLMError(f"openai failed: {e}") from e
            print(f"[llm] {model} failed ({e}) -> retrying once with {models[i + 1]}")


def _openai_body(model, system, messages, temperature):
    body = {"model": model, "temperature": temperature,
            "messages": [{"role": "system", "content": system}, *messages]}
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    return body


def _openai_stream(model, system, messages, temperature):
    with httpx.stream("POST", f"{config.OPENAI_BASE_URL}/chat/completions", timeout=20,
                      headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                      json={**_openai_body(model, system, messages, temperature), "stream": True}) as r:
        if r.status_code >= 400:
            r.read()
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            choices = json.loads(line[6:]).get("choices") or [{}]
            piece = choices[0].get("delta", {}).get("content")
            if piece:
                yield piece


def _ollama(system, messages, temperature):
    r = httpx.post(f"{config.OLLAMA_URL}/api/chat", timeout=120, json={
        "model": config.OLLAMA_MODEL, "stream": False, "options": {"temperature": temperature},
        "messages": [{"role": "system", "content": system}, *messages]})
    r.raise_for_status()
    return r.json()["message"]["content"]


def _openai(system, messages, temperature):
    try:
        return _openai_request(config.OPENAI_MODEL, system, messages, temperature)
    except (httpx.HTTPError, KeyError, IndexError) as e:
        fallback = config.OPENAI_FALLBACK_MODEL
        if not fallback or fallback == config.OPENAI_MODEL:
            raise
        print(f"[llm] {config.OPENAI_MODEL} failed ({e}) -> retrying once with {fallback}")
        return _openai_request(fallback, system, messages, temperature)


def _openai_request(model, system, messages, temperature):
    r = httpx.post(f"{config.OPENAI_BASE_URL}/chat/completions", timeout=20,
                   headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                   json=_openai_body(model, system, messages, temperature))
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _anthropic(system, messages, temperature):
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=60,
                   headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
                   json={"model": config.ANTHROPIC_MODEL, "max_tokens": 600, "temperature": temperature,
                         "system": system, "messages": messages})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])
