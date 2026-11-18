"""The AI provider call.

Owner: Zahid. Module 3.

This is the **only** place in the project that talks to an AI provider. Every
other module goes through ``app/services/ai_service.py``, so swapping the
provider later means changing this file and nothing else.

Rules this file obeys:

* The API key is read from ``settings.AI_API_KEY`` (an environment variable).
  It is never written into the source, never logged and never returned to the
  client (R17).
* The model name is read from ``settings.AI_MODEL``.
* The model is asked for JSON only, and the response is requested in JSON
  mode, so the answer is meant to be parseable (R6).
* Every failure is turned into :class:`AIProviderError`, which carries a
  **safe** message. The raw provider text stays in the exception's
  ``detail`` attribute for the server-side log and never reaches the client
  (R18).

The SDK is imported lazily inside :func:`call_model`, so the rest of the
backend keeps working when the package is not installed and the test suite
never needs an API key.
"""

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# The fixed JSON shape the model must answer with (R6). It is repeated here
# as plain text because it is part of the instruction, not a schema.
JSON_SHAPE_INSTRUCTION = """
Return ONLY a single JSON object, with no markdown fence and no prose, using
exactly this shape:

{
  "customer_name": "<name of the customer, or null when the sentence names none>",
  "items": [
    {"product_name": "<product name>", "quantity": <number>, "unit_price": <number>}
  ],
  "payment_type": "cash" or "credit",
  "paid_amount": <number or null>,
  "total_amount": <number>
}

Rules for the JSON:
- "items" must contain at least one item.
- "quantity" and "unit_price" are plain numbers, never strings.
- "total_amount" is the sum of quantity * unit_price over all items.
- "payment_type" is "cash" when the customer paid in full on the counter and
  "credit" when the sale goes on account.
- Use the product and customer names exactly as they are written in the
  sentence, in the original Bangla script.
- Do not add any key that is not in this shape.
""".strip()

# The instruction that asks the model to answer with JSON only.
SYSTEM_INSTRUCTION = (
    "You are a shop assistant for a Bangladeshi grocery shop. "
    "You read one Bangla sentence describing a sale and extract the sale "
    "details from it. Never invent items that are not in the sentence. "
    "Never add explanations, greetings or commentary. "
    + JSON_SHAPE_INSTRUCTION
)

# How long the provider may take before the request is abandoned.
REQUEST_TIMEOUT_SECONDS = 30


class AIProviderError(Exception):
    """The provider could not give a usable answer.

    ``message`` is safe to show to a user. ``detail`` holds the raw provider
    text for the server-side log only.
    """

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


def is_configured() -> bool:
    """Return True when an API key is present in the environment.

    The key itself is never returned by this module.
    """
    return bool(settings.AI_API_KEY and settings.AI_API_KEY.strip())


def _strip_code_fence(text: str) -> str:
    """Remove a ```json ... ``` fence if the model wrapped its answer in one."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    # Drop the opening fence line and the closing fence line.
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_json_response(raw: str) -> dict[str, Any]:
    """Parse the provider's answer into a JSON object.

    Raises :class:`AIProviderError` when the answer is not a JSON object.
    """
    if raw is None or not raw.strip():
        raise AIProviderError(
            "The AI service returned an empty answer.",
            detail="empty response",
        )

    candidate = _strip_code_fence(raw)
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AIProviderError(
            "The AI service returned a response that could not be read as JSON.",
            detail=f"json decode error: {exc}",
        ) from exc

    if not isinstance(parsed, dict):
        raise AIProviderError(
            "The AI service returned a response that was not a JSON object.",
            detail=f"unexpected json root type: {type(parsed).__name__}",
        )
    return parsed


def call_model(text: str) -> str:
    """Send one Bangla sentence to the provider and return its raw answer.

    The key is taken from the environment at call time, so a key that is set
    after import is still picked up.
    """
    if not is_configured():
        raise AIProviderError(
            "The AI service is not configured on this server.",
            detail="AI_API_KEY is not set",
        )

    try:
        import google.generativeai as genai
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise AIProviderError(
            "The AI service is not available on this server.",
            detail=f"google-generativeai is not installed: {exc}",
        ) from exc

    try:
        genai.configure(api_key=settings.AI_API_KEY)
        model = genai.GenerativeModel(
            model_name=settings.AI_MODEL,
            system_instruction=SYSTEM_INSTRUCTION,
        )
        response = model.generate_content(
            text,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0,
            },
            request_options={"timeout": REQUEST_TIMEOUT_SECONDS},
        )
        raw = response.text
    except Exception as exc:  # noqa: BLE001 - any provider failure is one case
        # The raw text of the exception may carry the key or a URL, so it is
        # logged and never returned to the client.
        logger.exception("AI provider call failed")
        raise AIProviderError(
            "The AI service could not be reached. Please use the manual entry form.",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    if raw is None or not str(raw).strip():
        raise AIProviderError(
            "The AI service returned an empty answer.",
            detail="empty response text",
        )
    return str(raw)
