import json
from unittest.mock import MagicMock, patch

import pytest

from core.config import get_settings
from core.extract import ContractFields, extract_contract, extract_contract_stub
from core.gemini_client import GeminiExtractionError, VertexGeminiClient, get_gemini_client, parse_json_response


def test_parse_json_response_plain():
    data = parse_json_response('{"counterparty": "ACME", "currency": "USD"}')
    assert data["counterparty"] == "ACME"


def test_parse_json_response_fenced():
    text = '```json\n{"counterparty": "ACME", "currency": "USD"}\n```'
    data = parse_json_response(text)
    assert data["counterparty"] == "ACME"


def test_parse_json_response_invalid():
    with pytest.raises(GeminiExtractionError, match="valid JSON"):
        parse_json_response("not json")


def test_extract_contract_stub():
    fields = extract_contract_stub("ACME_Corp_MSA.pdf")
    assert fields.counterparty == "ACME Corp MSA"
    assert "Stub extraction" in (fields.summary_text or "")


def test_extract_contract_gemini_disabled():
    fields = extract_contract(b"%PDF", "ACME.pdf", gemini_enabled=False)
    assert "Stub extraction" in (fields.summary_text or "")


def test_extract_contract_requires_pdf_bytes():
    with pytest.raises(GeminiExtractionError, match="PDF bytes required"):
        extract_contract(b"", "ACME.pdf", gemini_enabled=True)


def test_extract_contract_with_mocked_client():
    sample = {
        "counterparty": "ACME Corp",
        "signed_date": "2026-01-15",
        "total_value": 100000.0,
        "currency": "USD",
        "summary_text": "Master services agreement.",
        "watch_outs": ["Net 30 payment terms"],
    }
    mock_client = MagicMock()
    mock_client.extract_contract_json.return_value = sample

    with patch("core.extract.get_gemini_client", return_value=mock_client):
        fields = extract_contract(b"%PDF-1.4\n", "ACME.pdf", gemini_enabled=True)

    assert fields.counterparty == "ACME Corp"
    assert fields.summary_text == "Master services agreement."
    assert fields.watch_outs == ["Net 30 payment terms"]
    mock_client.extract_contract_json.assert_called_once()


def test_extract_contract_invalid_schema_from_gemini():
    mock_client = MagicMock()
    mock_client.extract_contract_json.return_value = {"watch_outs": "not-a-list"}

    with patch("core.extract.get_gemini_client", return_value=mock_client):
        with pytest.raises(GeminiExtractionError, match="schema"):
            extract_contract(b"%PDF-1.4\n", "ACME.pdf", gemini_enabled=True)


def test_gemini_configured_vertex_requires_project_and_location(monkeypatch):
    monkeypatch.setenv("GEMINI_BACKEND", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "")
    get_settings.cache_clear()
    assert get_settings().gemini_configured is False

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    get_settings.cache_clear()
    assert get_settings().gemini_configured is True
    get_settings.cache_clear()


def test_get_gemini_client_vertex_returns_client_when_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_BACKEND", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    get_settings.cache_clear()

    client = get_gemini_client()
    assert isinstance(client, VertexGeminiClient)
    get_settings.cache_clear()


def test_vertex_client_calls_genai_with_vertexai(monkeypatch):
    monkeypatch.setenv("GEMINI_BACKEND", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    get_settings.cache_clear()
    settings = get_settings()

    with patch("core.gemini_client.genai.Client") as mock_ctor:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"counterparty": "ACME", "currency": "USD"}'
        mock_instance.models.generate_content.return_value = mock_response
        mock_ctor.return_value = mock_instance

        client = VertexGeminiClient(settings)
        data = client.extract_contract_json(b"%PDF", "prompt")

        mock_ctor.assert_called_once_with(
            vertexai=True,
            project="my-project",
            location="us-central1",
        )
        assert data["counterparty"] == "ACME"

    get_settings.cache_clear()


def test_fields_to_extraction_json_roundtrip():
    from core.extract import fields_to_extraction_json

    fields = ContractFields(counterparty="X", currency="EUR")
    data = fields_to_extraction_json(fields)
    assert json.loads(json.dumps(data))["counterparty"] == "X"
