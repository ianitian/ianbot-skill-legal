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


def _generate_from_pdf(client: genai.Client, model: str, pdf_bytes: bytes, prompt: str) -> dict:
    try:
        response = client.models.generate_content(
            model=model,
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


class StudioGeminiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def extract_contract_json(self, pdf_bytes: bytes, prompt: str) -> dict:
        api_key = self._settings.gemini_api_key
        if not api_key or not api_key.strip():
            raise GeminiExtractionError("GEMINI_API_KEY is not set")

        client = genai.Client(api_key=api_key)
        return _generate_from_pdf(client, self._settings.gemini_model, pdf_bytes, prompt)


class VertexGeminiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        project = settings.google_cloud_project
        location = settings.google_cloud_location
        if not project or not project.strip():
            raise GeminiExtractionError("GOOGLE_CLOUD_PROJECT is not set")
        if not location or not location.strip():
            raise GeminiExtractionError("GOOGLE_CLOUD_LOCATION is not set")

    def extract_contract_json(self, pdf_bytes: bytes, prompt: str) -> dict:
        client = genai.Client(
            vertexai=True,
            project=self._settings.google_cloud_project,
            location=self._settings.google_cloud_location,
        )
        return _generate_from_pdf(client, self._settings.gemini_model, pdf_bytes, prompt)


def get_gemini_client(settings: Optional[Settings] = None) -> Optional[GeminiExtractionClient]:
    settings = settings or get_settings()
    backend = (settings.gemini_backend or "studio").strip().lower()

    if backend == "studio":
        if not settings.gemini_api_key or not settings.gemini_api_key.strip():
            return None
        return StudioGeminiClient(settings)

    if backend == "vertex":
        if not settings.gemini_configured:
            return None
        return VertexGeminiClient(settings)

    raise GeminiExtractionError(f"Unknown GEMINI_BACKEND: {settings.gemini_backend}")


def gemini_not_configured_message(settings: Settings) -> str:
    backend = (settings.gemini_backend or "studio").strip().lower()
    if backend == "vertex":
        return (
            "Gemini enabled but not configured for vertex "
            "(set GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION; use ADC via service account)"
        )
    return "Gemini enabled but not configured (set GEMINI_API_KEY for studio backend)"
