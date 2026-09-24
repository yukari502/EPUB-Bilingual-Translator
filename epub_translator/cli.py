from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

load_dotenv()

from .cache import TranslationCache
from .epub import EpubBook
from .html_translate import translate_html
from .settings import TranslationSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate EPUB books.")
    parser.add_argument("input", type=Path, nargs="+", help="Input .epub file(s) or directory containing .epub files")
    parser.add_argument("output", type=Path, help="Output .epub file or output directory")
    parser.add_argument("--provider", default=os.getenv("EPUB_PROVIDER", "openai"), choices=["openai", "gemini", "custom", "deepseek", "ollama"])
    parser.add_argument("--target", default=os.getenv("EPUB_TARGET", "Traditional Chinese"), help="Target language name")
    parser.add_argument("--mode", default=os.getenv("EPUB_MODE", "bilingual"), choices=["translate-only", "bilingual"])
    parser.add_argument("--api-key", default=os.getenv("EPUB_API_KEY", ""))
    parser.add_argument("--api-url", default=os.getenv("EPUB_API_URL", ""))
    parser.add_argument("--model", default=os.getenv("EPUB_MODEL", ""))
    parser.add_argument("--glossary", default="")
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("EPUB_CONCURRENCY", "4")))
    parser.add_argument("--paragraphs", type=int, default=int(os.getenv("EPUB_PARAGRAPHS", "4")))
    parser.add_argument("--cache", type=Path, default=Path(os.getenv("EPUB_CACHE_PATH", ".translation_cache.json")))
    parser.add_argument("--chapter", type=int, action="append", help="Translate only selected chapter number. Repeatable.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = TranslationSettings(
        mode=args.mode,
        provider=args.provider,
        api_key=args.api_key,
        api_url=args.api_url,
        model=args.model,
        target_language=args.target,
        max_concurrency=args.concurrency,
        paragraphs_per_request=args.paragraphs,
        glossary=args.glossary,
        cache_path=args.cache,
    )
    input_paths = []
    for path in args.input:
        if path.is_dir():
            input_paths.extend(list(path.glob("**/*.epub")))
        else:
            input_paths.append(path)

    if not input_paths:
        print("No input EPUB files found.")
        return 1

    for book_idx, input_path in enumerate(input_paths, start=1):
        if len(input_paths) > 1:
            print(f"\n[{book_idx}/{len(input_paths)}] Processing Book: {input_path.name}")
            if args.output.suffix == ".epub":
                # If output was specified as a file but we have multiple inputs, treat output as a dir
                output_dir = args.output.parent / args.output.stem
            else:
                output_dir = args.output
            
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{input_path.stem}_{args.target.replace(' ', '')}_{args.mode}.epub"
        else:
            output_path = args.output
            if output_path.is_dir() or not output_path.name.endswith(".epub"):
                output_path.mkdir(parents=True, exist_ok=True)
                output_path = output_path / f"{input_path.stem}_{args.target.replace(' ', '')}_{args.mode}.epub"

        try:
            book = EpubBook.load(input_path)
            cache = TranslationCache(settings.cache_path)
            selected = set(args.chapter or [])
            chapters = [chapter for chapter in book.chapters if not selected or chapter.index in selected]

            for position, chapter in enumerate(chapters, start=1):
                print(f"  [{position}/{len(chapters)}] Translating {chapter.title}")

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeRemainingColumn(),
                ) as progress:
                    task = progress.add_task("[cyan]Translating...", total=100)
                    
                    def on_progress(done: int, total: int, source: str, html: str) -> None:
                        progress.update(task, total=total, completed=done)

                    translated = asyncio.run(
                        translate_html(book.read_text(chapter.path), settings, cache=cache, progress=on_progress)
                    )
                    
                book.write_text(chapter.path, translated)

            book.export(output_path)
            print(f"Saved: {output_path}")
        except Exception as e:
            print(f"Error processing {input_path}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
