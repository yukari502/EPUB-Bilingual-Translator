from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

import httpx

from .settings import TranslationSettings


import json

LANGUAGE_CODES = {
    "Chinese": "zh-CN",
    "Simplified Chinese": "zh-CN",
    "Traditional Chinese": "zh-TW",
    "English": "en",
    "Japanese": "ja",
    "Korean": "ko",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Russian": "ru",
    "Italian": "it",
    "Portuguese": "pt",
    "Vietnamese": "vi",
}


def system_prompt(target_language: str, glossary: str = "", context: list[str] = None) -> str:
    prompt = f"""You are a professional {target_language} native translator.

Translation rules:
1. Output ONLY the translated content. MUST strictly use the exact {target_language} script and dialect.
2. Keep exactly the same number of paragraphs as the input.
3. Preserve the original HTML structure exactly: do not add, remove, rename, reorder, or simplify tags and attributes.
4. Translate only human-readable text nodes. Keep code, URLs, placeholders, entities, punctuation-only text, and proper nouns unchanged when appropriate.
5. Keep inline formatting tags around the corresponding translated words.
6. The user will provide a JSON array of strings. You MUST return a JSON array of translated strings of the exact same length. Return ONLY valid JSON."""
    if glossary.strip():
        prompt += f"\n\nGlossary and custom instructions:\n{glossary.strip()}"
    if context and any(context):
        prompt += f"\n\nContext from previous paragraphs (for reference ONLY, do NOT translate these):\n{json.dumps(context, ensure_ascii=False)}"
    return prompt


class TranslationProvider(ABC):
    def __init__(self, settings: TranslationSettings):
        self.settings = settings

    @abstractmethod
    async def translate_batch(self, texts: list[str], previous_texts: list[str] = None) -> list[str]:
        raise NotImplementedError

    async def _execute_with_retries(self, req_func, texts: list[str], extract_func) -> list[str]:
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self.settings.timeout) as client:
            for attempt in range(1, self.settings.retries + 1):
                try:
                    response = await req_func(client)
                    if response.is_success:
                        data = response.json()
                        content = extract_func(data)
                        return parse_json_parts(content, texts)
                    
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            await asyncio.sleep(int(retry_after))
                            continue
                    last_error = RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
                except Exception as exc:
                    last_error = exc
                if attempt < self.settings.retries:
                    await asyncio.sleep(2 ** (attempt - 1))
        
        print(f"Batch translation failed after {self.settings.retries} attempts: {last_error}")
        return ["[Translation Failed]"] * len(texts)


class OpenAICompatibleProvider(TranslationProvider):
    DEFAULT_URLS = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "deepseek": "https://api.deepseek.com/chat/completions",
        "ollama": "http://localhost:11434/v1/chat/completions",
        "custom": "",
    }
    DEFAULT_MODELS = {
        "openai": "gpt-4.1-mini",
        "deepseek": "deepseek-chat",
        "ollama": "llama3",
        "custom": "gpt-4.1-mini",
    }

    async def translate_batch(self, texts: list[str], previous_texts: list[str] = None) -> list[str]:
        url = self._chat_completions_url()
        model = self.settings.model or self.DEFAULT_MODELS.get(self.settings.provider, self.DEFAULT_MODELS["openai"])
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
            
        async def req_func(client):
            return await client.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"} if self.settings.provider in ("openai", "deepseek") else None,
                    "messages": [
                        {"role": "system", "content": system_prompt(self.settings.target_language, self.settings.glossary, previous_texts)},
                        {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
                    ],
                },
            )
            
        def extract_func(data):
            return data["choices"][0]["message"]["content"].strip()
            
        return await self._execute_with_retries(req_func, texts, extract_func)

    def _chat_completions_url(self) -> str:
        url = (self.settings.api_url or self.DEFAULT_URLS.get(self.settings.provider, "")).strip()
        if not url:
            if self.settings.provider == "custom":
                raise ValueError("Custom provider requires an API URL.")
            url = self.DEFAULT_URLS["openai"]
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid API URL: {url}")
        url_stripped = url.rstrip("/")
        if url_stripped.endswith("/chat/completions"):
            return url
        if self.settings.provider == "deepseek":
            return url_stripped + "/chat/completions"
        if url_stripped.endswith("/v1"):
            return url_stripped + "/chat/completions"
        return url_stripped + "/v1/chat/completions"


class GeminiProvider(TranslationProvider):
    async def translate_batch(self, texts: list[str], previous_texts: list[str] = None) -> list[str]:
        model = self.settings.model or "gemini-1.5-pro"
        url = self.settings.api_url or (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        )
        params = {}
        if self.settings.api_key and "key=" not in url:
            params["key"] = self.settings.api_key
            
        async def req_func(client):
            return await client.post(
                url,
                params=params,
                headers={"Content-Type": "application/json"},
                json={
                    "system_instruction": {
                        "parts": [{"text": system_prompt(self.settings.target_language, self.settings.glossary, previous_texts)}]
                    },
                    "contents": [{"parts": [{"text": json.dumps(texts, ensure_ascii=False)}]}],
                    "generationConfig": {"temperature": 0},
                },
            )
            
        def extract_func(data):
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            
        return await self._execute_with_retries(req_func, texts, extract_func)


def parse_json_parts(content: str, texts: list[str]) -> list[str]:
    expected = len(texts)
    try:
        # Some models wrap JSON in markdown blocks
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        parts = json.loads(content.strip())
        if not isinstance(parts, list):
            parts = [str(parts)]
    except json.JSONDecodeError:
        parts = [content.strip()]
        
    parts = [str(p).strip() for p in parts]
    if len(parts) != expected:
        raise ValueError(f"Translation returned {len(parts)} items, expected {expected}")
    return parts


def build_provider(settings: TranslationSettings) -> TranslationProvider:
    if settings.provider == "gemini":
        return GeminiProvider(settings)
    return OpenAICompatibleProvider(settings)
