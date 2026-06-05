"""Provider-agnostic LLM interface.

Switch providers with the LLM_PROVIDER env var: "anthropic" (default),
"deepseek", or "gemini". Each provider reads its own API key and (optionally)
its own model override:

    LLM_PROVIDER=deepseek
    DEEPSEEK_API_KEY=sk-...
    DEEPSEEK_MODEL=deepseek-chat        # optional override

All application code calls llm.complete(...) instead of talking to a vendor
SDK directly, so the rest of the backend never has to know which model is
behind it.
"""

import base64
import os

from dotenv import load_dotenv

load_dotenv()

# provider -> (env var holding the key, env var overriding the model, default model)
_PROVIDERS = {
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "deepseek-chat"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL", "gemini-2.0-flash"),
}

_PLACEHOLDER_KEYS = {
    "",
    "dummy",
    "your_anthropic_api_key_here",
    "your_deepseek_api_key_here",
    "your_gemini_api_key_here",
    "your_api_key_here",
}


class LLMError(RuntimeError):
    """Raised when an LLM call cannot be completed."""


class LLMNotConfigured(LLMError):
    """Raised when the active provider has no usable API key."""


class LLMAuthError(LLMError):
    """Raised when the provider rejects the API key."""


def get_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    return provider if provider in _PROVIDERS else "anthropic"


def available_providers() -> list[str]:
    return list(_PROVIDERS)


def provider_key_env(provider: str) -> str:
    """Name of the env var that holds the API key for the given provider."""
    return _PROVIDERS[provider][0]


def _api_key(provider: str | None = None) -> str:
    provider = provider or get_provider()
    return os.getenv(_PROVIDERS[provider][0], "").strip()


def _model(provider: str | None = None) -> str:
    provider = provider or get_provider()
    _, model_env, default_model = _PROVIDERS[provider]
    return os.getenv(model_env, "").strip() or default_model


def is_configured(provider: str | None = None) -> bool:
    """True when the active (or given) provider has a real-looking API key."""
    key = _api_key(provider)
    return bool(key) and key.lower() not in _PLACEHOLDER_KEYS


def complete(
    prompt: str,
    *,
    max_tokens: int,
    temperature: float = 0.0,
    image_png: bytes | None = None,
) -> str:
    """Run a single-turn completion against the active provider.

    Returns the model's text output. Raises LLMNotConfigured when no key is set,
    LLMAuthError when the key is rejected, or LLMError for any other failure.
    """
    provider = get_provider()
    if not is_configured(provider):
        raise LLMNotConfigured(f"{provider} API key is not configured.")

    if provider == "anthropic":
        return _anthropic_complete(prompt, max_tokens, temperature, image_png)
    if provider == "deepseek":
        return _deepseek_complete(prompt, max_tokens, temperature, image_png)
    if provider == "gemini":
        return _gemini_complete(prompt, max_tokens, temperature, image_png)
    raise LLMNotConfigured(f"Unknown LLM provider: {provider}")


def validate_key(api_key: str, provider: str | None = None) -> None:
    """Send a tiny request to confirm the key works. Raises on failure."""
    provider = provider or get_provider()
    prev = os.environ.get(_PROVIDERS[provider][0])
    os.environ[_PROVIDERS[provider][0]] = api_key.strip()
    prev_provider = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = provider
    try:
        complete("Reply OK.", max_tokens=5, temperature=0)
    finally:
        if prev is None:
            os.environ.pop(_PROVIDERS[provider][0], None)
        else:
            os.environ[_PROVIDERS[provider][0]] = prev
        if prev_provider is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = prev_provider


# ── Providers ──────────────────────────────────────────────────────────────


def _anthropic_complete(prompt: str, max_tokens: int, temperature: float, image_png: bytes | None) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=_api_key("anthropic"))
    if image_png is not None:
        content: object = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(image_png).decode("ascii"),
                },
            },
            {"type": "text", "text": prompt},
        ]
    else:
        content = prompt

    try:
        message = client.messages.create(
            model=_model("anthropic"),
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as exc:  # noqa: BLE001 - normalize vendor errors
        raise _normalize_error(exc) from exc
    return message.content[0].text


def _deepseek_complete(prompt: str, max_tokens: int, temperature: float, image_png: bytes | None) -> str:
    if image_png is not None:
        raise LLMError("DeepSeek chat model does not support image input.")

    from openai import OpenAI

    client = OpenAI(api_key=_api_key("deepseek"), base_url="https://api.deepseek.com")
    try:
        resp = client.chat.completions.create(
            model=_model("deepseek"),
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        raise _normalize_error(exc) from exc
    return resp.choices[0].message.content or ""


def _gemini_complete(prompt: str, max_tokens: int, temperature: float, image_png: bytes | None) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_api_key("gemini"))
    if image_png is not None:
        contents: object = [
            types.Part.from_bytes(data=image_png, mime_type="image/png"),
            prompt,
        ]
    else:
        contents = prompt

    try:
        resp = client.models.generate_content(
            model=_model("gemini"),
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise _normalize_error(exc) from exc
    return resp.text or ""


def _normalize_error(exc: Exception) -> LLMError:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    message = str(exc).lower()
    if status_code in (401, 403) or "authentication" in message or "api key" in message or "unauthorized" in message:
        return LLMAuthError("The API key was rejected by the provider.")
    return LLMError(f"LLM request failed: {exc}")
