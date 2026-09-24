from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Any

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("translator")

from .cache import TranslationCache
from .providers import build_provider
from .settings import TranslationSettings


ProgressCallback = Callable[[int, int, str], None]
AsyncProgressCallback = Callable[[int, int, str], Any]

TRANSLATABLE_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "figcaption", "div", "span", "td", "th", "dd", "dt")
BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "div", "td", "th", "dd", "dt"}
SKIP_PARENT_TAGS = {"script", "style", "svg", "math", "pre", "code"}


async def translate_html(
    html: str,
    settings: TranslationSettings,
    cache: TranslationCache | None = None,
    progress: Callable[[int, int, str, str], Any] | None = None,
    cancel_event: asyncio.Event | None = None,
    cache_only: bool = False
) -> str:
    soup = BeautifulSoup(remove_scripts(html), "xml")
    targets = collect_targets(soup)
    if not targets:
        return str(soup)

    provider = build_provider(settings)
    cache = cache or TranslationCache(None)
    
    # Map text -> list of tags that contain this exact text
    text_to_tags: dict[str, list[Tag]] = {}
    for tag in targets:
        text = inner_html(tag)
        if text not in text_to_tags:
            text_to_tags[text] = []
        text_to_tags[text].append(tag)

    total_tags = len(targets)
    completed_tags = 0

    unique_texts = list(text_to_tags.keys())
    pending_texts: list[str] = []

    # First, apply cache
    cache_applied = False
    for text in unique_texts:
        if cancel_event and cancel_event.is_set():
            return str(soup)
            
        cached = cache.get(text, settings)
        if cached:
            for tag in text_to_tags[text]:
                apply_translation(soup, tag, cached, settings)
                completed_tags += 1
                cache_applied = True
                if progress:
                    res = progress(completed_tags, total_tags, "cache", "")
                    if asyncio.iscoroutine(res):
                        await res
        else:
            pending_texts.append(text)

    if cache_applied and progress:
        res = progress(completed_tags, total_tags, "cache_update", str(soup))
        if asyncio.iscoroutine(res):
            await res

    if not pending_texts or cache_only:
        cache.save()
        return str(soup)

    chunk_size = max(1, settings.paragraphs_per_request)
    chunks = [pending_texts[i : i + chunk_size] for i in range(0, len(pending_texts), chunk_size)]
    max_workers = max(1, settings.max_concurrency)
    if settings.provider == "ollama":
        max_workers = 1

    queue: asyncio.Queue[list[str]] = asyncio.Queue()
    for chunk in chunks:
        queue.put_nowait(chunk)

    last_update_time = 0

    async def worker() -> None:
        nonlocal completed_tags, last_update_time
        while True:
            if cancel_event and cancel_event.is_set():
                break
            try:
                chunk = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                translations = await provider.translate_batch(chunk)
                updated_in_chunk = False
                for text, translated in zip(chunk, translations):
                    if cancel_event and cancel_event.is_set():
                        break
                    
                    if translated not in ("[Translation Failed]", "[Translation Missing]"):
                        cache.set(text, translated, settings)
                        for tag in text_to_tags[text]:
                            apply_translation(soup, tag, translated, settings)
                            completed_tags += 1
                            updated_in_chunk = True
                            
                if updated_in_chunk and progress:
                    now = time.time()
                    if now - last_update_time > 1.0 or completed_tags == total_tags:
                        current_html = str(soup)
                        last_update_time = now
                    else:
                        current_html = ""
                    res = progress(completed_tags, total_tags, "translated", current_html)
                    if asyncio.iscoroutine(res):
                        await res
            except Exception as e:
                import traceback
                logger.error(f"Translation batch error: {e}\n{traceback.format_exc()}")
            finally:
                cache.save()
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(max_workers)]
    await asyncio.gather(*workers)

    cache.save()
    return str(soup)


def remove_scripts(html: str) -> str:
    soup = BeautifulSoup(html, "xml")
    for script in soup.find_all("script"):
        script.decompose()
    return str(soup)


def collect_targets(soup: BeautifulSoup) -> list[Tag]:
    targets: list[Tag] = []
    target_ids = set()
    for tag in soup.find_all(TRANSLATABLE_TAGS):
        classes = set(tag.get("class", []))
        if "translated" in classes or "translation-block" in classes:
            continue
        if tag.get("data-epub-translator-original") == "1":
            continue
        if tag.find_parent(attrs={"data-epub-translator-original": "1"}):
            continue
        if tag.find_parent(class_="translation-block"):
            continue
            
        # If this tag contains other block-level translatable tags, skip it
        # so we can process the deeper block-level tags instead.
        has_block_child = False
        for child in tag.find_all(tuple(BLOCK_TAGS)):
            if child != tag:
                has_block_child = True
                break
        if has_block_child:
            continue
            
        if has_selected_parent(tag, target_ids):
            continue
        if has_translatable_text(tag) and inner_html(tag).strip():
            targets.append(tag)
            target_ids.add(id(tag))
    return targets


def has_selected_parent(tag: Tag, target_ids: set[int]) -> bool:
    return any(id(parent) in target_ids for parent in tag.parents if isinstance(parent, Tag))


def has_translatable_text(tag: Tag) -> bool:
    for text in tag.find_all(string=True):
        if not text.strip():
            continue
        if any(parent.name in SKIP_PARENT_TAGS for parent in text.parents if isinstance(parent, Tag)):
            continue
        return True
    return False


def inner_html(tag: Tag) -> str:
    return "".join(str(child) for child in tag.contents).strip()


def apply_translation(soup: BeautifulSoup, tag: Tag, translated: str, settings: TranslationSettings) -> None:
    # We ALWAYS inject bilingual HTML. The frontend uses CSS to hide original text if "Translate Only" is selected.
    # Export will filter it later.
    trans_tag = soup.new_tag(tag.name)
    trans_tag["class"] = ["translation-block", "translated"]
    trans_tag["style"] = "margin-top:4px;margin-bottom:4px;"
    # Parse translated string using 'html.parser' mode.
    # 'xml' mode expects a single root element and drops raw text or multiple roots, which causes IndexError when appending.
    trans_tag.append(BeautifulSoup(translated, "html.parser"))
    tag["data-epub-translator-original"] = "1"
    append_style(tag, "opacity:0.6;margin-top:0;margin-bottom:12px;")
    tag.insert_before(trans_tag)


def add_class(tag: Tag, class_name: str) -> None:
    classes = list(tag.get("class", []))
    if class_name not in classes:
        classes.append(class_name)
    tag["class"] = classes


def append_style(tag: Tag, style: str) -> None:
    current = str(tag.get("style", "")).strip()
    if style in current:
        return
    separator = "" if not current or current.endswith(";") else ";"
    tag["style"] = f"{current}{separator}{style}" if current else style
