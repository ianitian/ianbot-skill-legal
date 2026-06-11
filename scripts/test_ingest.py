#!/usr/bin/env python3
"""Test POST /ingest for a Google Drive file URL or file ID.

Usage:
  ./scripts/test_ingest.py "https://drive.google.com/file/d/FILE_ID/view" "Contract.pdf"
  ./scripts/test_ingest.py FILE_ID "Contract.pdf"

Reads INGEST_SECRET and optional INGEST_API_URL from .env in the repo root.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"

# Common Google Drive / Docs URL shapes and bare id= query params.
_DRIVE_ID_PATTERNS = (
    re.compile(r"/file/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"/document/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"/presentation/d/([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
)
_BARE_FILE_ID = re.compile(r"^[a-zA-Z0-9_-]{10,}$")


def _load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def parse_drive_file_id(url_or_id: str) -> str:
    value = url_or_id.strip()
    if _BARE_FILE_ID.fullmatch(value):
        return value
    for pattern in _DRIVE_ID_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)
    raise ValueError(
        "Could not parse a Drive file ID. Paste a full Drive URL or a bare file ID."
    )


def _http_json(method: str, url: str, headers: dict[str, str], body: Optional[dict] = None) -> dict:
    data = None
    req_headers = dict(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=req_headers, method=method)
    try:
        with urlopen(request, timeout=300) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc
    return json.loads(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test local wonbot-api /ingest for one Drive file.")
    parser.add_argument(
        "drive_url",
        help="Google Drive file URL or bare drive_file_id",
    )
    parser.add_argument(
        "file_name",
        help='PDF file name sent to ingest (e.g. "Zenith_SOW.pdf")',
    )
    parser.add_argument(
        "--api-base",
        default=None,
        help="API base URL (default: INGEST_API_URL from .env or http://localhost:8000)",
    )
    parser.add_argument(
        "--secret",
        default=None,
        help="X-Ingest-Secret (default: INGEST_SECRET from .env)",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Call GET /health before ingest and print it",
    )
    args = parser.parse_args()

    env = _load_env(ENV_PATH)
    api_base = (args.api_base or env.get("INGEST_API_URL") or "http://localhost:8000").rstrip("/")
    secret = args.secret or env.get("INGEST_SECRET")
    if not secret:
        print("Missing INGEST_SECRET. Set it in .env or pass --secret.", file=sys.stderr)
        return 2

    try:
        drive_file_id = parse_drive_file_id(args.drive_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    headers = {"X-Ingest-Secret": secret}

    if args.health:
        health = _http_json("GET", f"{api_base}/health", headers={})
        print("Health:")
        print(json.dumps(health, indent=2))
        print()

    payload = {
        "drive_file_id": drive_file_id,
        "file_name": args.file_name,
        "mime_type": "application/pdf",
        "source": "test_ingest.py",
    }

    print(f"POST {api_base}/ingest")
    print(f"  drive_file_id: {drive_file_id}")
    print(f"  file_name:     {args.file_name}")
    print()

    result = _http_json("POST", f"{api_base}/ingest", headers=headers, body=payload)
    print(json.dumps(result, indent=2))

    if result.get("status") != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
