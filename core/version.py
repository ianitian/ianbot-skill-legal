from pathlib import Path


def get_app_version() -> str:
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    return version_file.read_text(encoding="utf-8").strip()
