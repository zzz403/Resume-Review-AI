"""Provider-agnostic LLM interface.

Switch text providers with TEXT_LLM_PROVIDER or LLM_PROVIDER: "anthropic" (default),
"deepseek", "gemini", or "openai". Switch image-reading providers with
VISION_LLM_PROVIDER. Each provider reads its own API key and (optionally)
its own model override:

    TEXT_LLM_PROVIDER=anthropic
    VISION_LLM_PROVIDER=openai
    DEEPSEEK_API_KEY=sk-...
    DEEPSEEK_MODEL=deepseek-chat        # optional override

All application code calls llm.complete(...) instead of talking to a vendor
SDK directly, so the rest of the backend never has to know which model is
behind it.
"""

import base64
import json
import os

from dotenv import load_dotenv

load_dotenv()

# provider -> (env var holding the key, env var overriding the model, default model)
_PROVIDERS = {
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "deepseek-chat"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL", "gemini-2.0-flash"),
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL", "gpt-5.5"),
}

_VISION_PROVIDERS = {"anthropic", "gemini", "openai"}

_PLACEHOLDER_KEYS = {
    "",
    "dummy",
    "your_anthropic_api_key_here",
    "your_deepseek_api_key_here",
    "your_gemini_api_key_here",
    "your_openai_api_key_here",
    "your_api_key_here",
}


class LLMError(RuntimeError):
    """Raised when an LLM call cannot be completed."""


class LLMNotConfigured(LLMError):
    """Raised when the active provider has no usable API key."""


class LLMAuthError(LLMError):
    """Raised when the provider rejects the API key."""


def _valid_provider(value: str, default: str = "anthropic") -> str:
    provider = value.strip().lower()
    return provider if provider in _PROVIDERS else "anthropic"


def get_provider() -> str:
    return get_text_provider()


def get_text_provider() -> str:
    return _valid_provider(os.getenv("TEXT_LLM_PROVIDER") or os.getenv("LLM_PROVIDER", "anthropic"))


def get_vision_provider() -> str:
    configured = os.getenv("VISION_LLM_PROVIDER", "").strip().lower()
    if configured in _VISION_PROVIDERS:
        return configured
    text_provider = get_text_provider()
    return text_provider if text_provider in _VISION_PROVIDERS else "anthropic"


def available_providers() -> list[str]:
    return list(_PROVIDERS)


def available_vision_providers() -> list[str]:
    return [provider for provider in _PROVIDERS if provider in _VISION_PROVIDERS]


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
    provider = get_text_provider()
    return _complete_with_provider(provider, prompt, max_tokens=max_tokens, temperature=temperature, image_png=image_png)


def complete_vision(
    prompt: str,
    *,
    max_tokens: int,
    temperature: float = 0.0,
    image_png: bytes,
) -> str:
    provider = get_vision_provider()
    return _complete_with_provider(provider, prompt, max_tokens=max_tokens, temperature=temperature, image_png=image_png)


def complete_structured(
    prompt: str,
    *,
    schema: dict,
    schema_name: str,
    max_tokens: int,
    images: list[bytes] | None = None,
) -> dict:
    """Single-turn call that returns a dict validated against a JSON schema.

    Routes to the vision provider when images are supplied, otherwise the text
    provider. Raises LLMNotConfigured / LLMAuthError / LLMError like complete().
    """
    provider = get_vision_provider() if images else get_text_provider()
    if not is_configured(provider):
        raise LLMNotConfigured(f"{provider} API key is not configured.")

    if provider == "openai":
        return _openai_structured(prompt, schema, schema_name, max_tokens, images)
    if provider == "anthropic":
        return _anthropic_structured(prompt, schema, schema_name, max_tokens, images)
    if provider == "gemini":
        return _gemini_structured(prompt, schema, max_tokens, images)
    if provider == "deepseek":
        if images:
            raise LLMError("DeepSeek does not support image input for structured extraction.")
        return _deepseek_structured(prompt, schema, max_tokens)
    raise LLMNotConfigured(f"Unknown LLM provider: {provider}")


def _openai_structured(prompt: str, schema: dict, schema_name: str, max_tokens: int, images: list[bytes] | None) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=_api_key("openai"))
    content: list[dict] = [{"type": "input_text", "text": prompt}]
    for png in images or []:
        encoded = base64.b64encode(png).decode("ascii")
        content.append({"type": "input_image", "image_url": f"data:image/png;base64,{encoded}"})
    kwargs: dict = {
        "model": _model("openai"),
        "input": [{"role": "user", "content": content}],
        "max_output_tokens": max_tokens,
        "text": {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
    }
    # Reasoning effort is the biggest cost/latency lever for gpt-5 models. Lower
    # effort (minimal|low|medium|high) cuts reasoning tokens dramatically; "low"
    # keeps a safety margin for messy scans/handwriting. Default low.
    effort = os.getenv("OPENAI_REASONING_EFFORT", "low").strip().lower()
    if effort in {"minimal", "low", "medium", "high"}:
        kwargs["reasoning"] = {"effort": effort}
    try:
        resp = client.responses.create(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise _normalize_error(exc) from exc
    return json.loads(resp.output_text or "{}")


def _anthropic_structured(prompt: str, schema: dict, schema_name: str, max_tokens: int, images: list[bytes] | None) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=_api_key("anthropic"))
    content: list[dict] = []
    for png in images or []:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode("ascii")},
        })
    content.append({"type": "text", "text": prompt})
    try:
        message = client.messages.create(
            model=_model("anthropic"),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except Exception as exc:  # noqa: BLE001
        raise _normalize_error(exc) from exc
    text = next((block.text for block in message.content if getattr(block, "type", None) == "text"), "{}")
    return json.loads(text)


def _gemini_structured(prompt: str, schema: dict, max_tokens: int, images: list[bytes] | None) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_api_key("gemini"))
    parts: list[object] = [types.Part.from_bytes(data=png, mime_type="image/png") for png in images or []]
    parts.append(prompt)
    try:
        resp = client.models.generate_content(
            model=_model("gemini"),
            contents=parts,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                response_mime_type="application/json",
                response_json_schema=schema,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise _normalize_error(exc) from exc
    return json.loads(resp.text or "{}")


def _deepseek_structured(prompt: str, schema: dict, max_tokens: int) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=_api_key("deepseek"), base_url="https://api.deepseek.com")
    full_prompt = (
        prompt
        + "\n\nReturn ONLY a json object that conforms exactly to this JSON Schema "
          "(use null for unknown values):\n"
        + json.dumps(schema)
    )
    try:
        resp = client.chat.completions.create(
            model=_model("deepseek"),
            max_tokens=max_tokens,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": full_prompt}],
        )
    except Exception as exc:  # noqa: BLE001
        raise _normalize_error(exc) from exc
    return json.loads(resp.choices[0].message.content or "{}")


def _complete_with_provider(
    provider: str,
    prompt: str,
    *,
    max_tokens: int,
    temperature: float,
    image_png: bytes | None = None,
) -> str:
    if not is_configured(provider):
        raise LLMNotConfigured(f"{provider} API key is not configured.")

    if provider == "anthropic":
        return _anthropic_complete(prompt, max_tokens, temperature, image_png)
    if provider == "deepseek":
        return _deepseek_complete(prompt, max_tokens, temperature, image_png)
    if provider == "gemini":
        return _gemini_complete(prompt, max_tokens, temperature, image_png)
    if provider == "openai":
        return _openai_complete(prompt, max_tokens, temperature, image_png)
    raise LLMNotConfigured(f"Unknown LLM provider: {provider}")


def validate_key(api_key: str, provider: str | None = None) -> None:
    """Send a tiny request to confirm the key works. Raises on failure."""
    provider = provider or get_text_provider()
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


def _openai_complete(prompt: str, max_tokens: int, temperature: float, image_png: bytes | None) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=_api_key("openai"))
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
    if image_png is not None:
        encoded = base64.b64encode(image_png).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encoded}",
            }
        )

    try:
        resp = client.responses.create(
            model=_model("openai"),
            input=[{"role": "user", "content": content}],
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001
        raise _normalize_error(exc) from exc
    return resp.output_text or ""


def _normalize_error(exc: Exception) -> LLMError:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    message = str(exc).lower()
    if status_code in (401, 403) or "authentication" in message or "api key" in message or "unauthorized" in message:
        return LLMAuthError("The API key was rejected by the provider.")
    return LLMError(f"LLM request failed: {exc}")
