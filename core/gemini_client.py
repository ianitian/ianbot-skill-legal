import json
import re
from typing import Optional, Protocol

from google import genai
from google.genai import types

from core.config import Settings, get_settings

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class GeminiExtractionError(RuntimeError):
    """Raised when Gemini extraction fails (API, empty response, or invalid JSON)."""


class GeminiExtractionClient(Protocol):
    def extract_contract_json(self, pdf_bytes: bytes, prompt: str) -> dict:
        ...


def parse_json_response(text: str) -> dict:
    """Parse model output as JSON, stripping optional markdown fences."""
    cleaned = text.strip()
    cleaned = _JSON_FENCE_RE.sub("", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiExtractionError("Gemini response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise GeminiExtractionError("Gemini response must be a JSON object")
    return data


class StudioGeminiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract_contract_json(self, pdf_bytes: bytes, prompt: str) -> dict:
        api_key = self._settings.gemini_api_key
        if not api_key or not api_key.strip():
            raise GeminiExtractionError("GEMINI_API_KEY is not set")

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=self._settings.gemini_model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                ],
            )
        except Exception as exc:  # noqa: BLE001 — surface as extraction error
            raise GeminiExtractionError("Gemini API request failed") from exc

        text = response.text
        if not text or not text.strip():
            raise GeminiExtractionError("Gemini returned an empty response")

        return parse_json_response(text)


class VertexGeminiClient:
    def extract_contract_json(self, pdf_bytes: bytes, prompt: str) -> dict:
        raise NotImplementedError(
            "Vertex Gemini backend is not implemented yet; set GEMINI_BACKEND=studio for local dev"
        )


def get_gemini_client(settings: Optional[Settings] = None) -> Optional[GeminiExtractionClient]:
    settings = settings or get_settings()
    backend = (settings.gemini_backend or "studio").strip().lower()

    if backend == "studio":
        if not settings.gemini_api_key or not settings.gemini_api_key.strip():
            return None
        return StudioGeminiClient(settings)

    if backend == "vertex":
        return VertexGeminiClient()

    raise GeminiExtractionError(f"Unknown GEMINI_BACKEND: {settings.gemini_backend}")
