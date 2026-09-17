from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ProviderName = Literal["openai", "gemini", "custom", "deepseek", "ollama"]
TranslationMode = Literal["bilingual", "translate-only"]


@dataclass(slots=True)
class TranslationSettings:
    mode: TranslationMode = "bilingual"
    provider: ProviderName = "openai"
    api_key: str = ""
    api_url: str = ""
    model: str = ""
    target_language: str = "Traditional Chinese"
    max_concurrency: int = 4
    paragraphs_per_request: int = 4
    glossary: str = ""
    cache_path: Path | None = Path(".translation_cache.json")
    retries: int = 3
    timeout: float = 90.0
