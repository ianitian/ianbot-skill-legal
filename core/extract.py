import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

from core.config import get_settings
from core.gemini_client import GeminiExtractionError, gemini_not_configured_message, get_gemini_client

PROMPT_PATH = Path(__file__).parent / "prompts" / "extract_contract.txt"


class ContractFields(BaseModel):
    counterparty: Optional[str] = None
    signed_date: Optional[str] = None
    total_value: Optional[float] = None
    currency: str = "USD"
    summary_text: Optional[str] = None
    watch_outs: List[str] = Field(default_factory=list)


def load_extraction_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def extract_contract_stub(file_name: str) -> ContractFields:
    """Placeholder when GEMINI_ENABLED=false."""
    stem = Path(file_name).stem.replace("_", " ")
    return ContractFields(
        counterparty=stem[:80] if stem else None,
        summary_text=f"Stub extraction for {file_name}. Set GEMINI_ENABLED=true when ready.",
        watch_outs=["Stub: review payment terms and termination when real extraction is enabled."],
    )


def extract_contract(pdf_bytes: bytes, file_name: str, *, gemini_enabled: bool) -> ContractFields:
    if not gemini_enabled:
        return extract_contract_stub(file_name)

    if not pdf_bytes:
        raise GeminiExtractionError("PDF bytes required for Gemini extraction")

    settings = get_settings()
    client = get_gemini_client(settings)
    if client is None:
        raise GeminiExtractionError(gemini_not_configured_message(settings))

    prompt = load_extraction_prompt()
    try:
        data = client.extract_contract_json(pdf_bytes, prompt)
        return ContractFields.model_validate(data)
    except ValidationError as exc:
        raise GeminiExtractionError("Gemini JSON does not match contract schema") from exc


def fields_to_extraction_json(fields: ContractFields) -> dict:
    return json.loads(fields.model_dump_json())
