# EPUB Translator

A lightweight, modern Python tool to translate EPUB files using LLMs (OpenAI, Gemini, DeepSeek, etc.) directly in your browser.

## Features
- **Extremely fast and lightweight**: Uses a modern FastAPI + AsyncIO backend, avoiding slow Tkinter GUIs.
- **Deduplication Engine**: Caches paragraphs and removes duplicates before sending to LLMs, reducing token costs and translation time by up to 50%.
- **Live Translation Preview**: A WYSIWYG (What You See Is What You Get) reader directly in the browser. See translations appear block-by-block.
- **Dynamic Bilingual Mode**: Switch between Bilingual and Translation Only modes instantly, without re-translating.
- **One-Click Startup**: Auto-creates virtual environments and installs dependencies automatically.

## Quick Start (Windows)
### Option A: Standalone Executable (Recommended for beginners)
1. Double click `EPUB-Translator.exe`.
2. A black console window will appear and the Web UI will automatically open in your default browser.
3. **To close the application:** Simply close the black console window.

### Option B: From Source / Batch script
1. Double click `start.bat`.
2. It will automatically download dependencies (if needed) and open the translation web UI in your browser.

## CLI Mode (For Servers & Local Models)
If you are deploying on a headless server or prefer pure terminal operations (e.g., translating using a locally deployed model like Ollama or vLLM), you can use the built-in Command Line Interface (CLI).

1. **Install dependencies:**
   ```bash
   pip install -e .
   ```

2. **Run the translation command:**
   Example for translating using a local **Ollama** model:
   ```bash
   epub-translator input.epub output.epub \
       --provider ollama \
       --model llama3 \
       --api-url http://localhost:11434/v1/chat/completions \
       --target "Simplified Chinese" \
       --mode bilingual
   ```

   Example for batch translating multiple books (or a directory of EPUBs):
   ```bash
   epub-translator ./my_books/ ./translated_books/ \
       --provider openai \
       --target "Simplified Chinese"
   ```

**Common CLI Arguments:**
- `input`: Source EPUB file path(s) or a directory containing EPUB files (required).
- `output`: Output EPUB file path or output directory (required).
- `--provider`: Options include `openai`, `gemini`, `deepseek`, `ollama`, `custom`.
- `--model`: Model name (e.g., `llama3`, `gpt-4o-mini`).
- `--api-url`: Your local or custom API URL.
- `--api-key`: API key if required by your provider.
- `--target`: Target language (default: `Traditional Chinese`).
- `--mode`: `bilingual` or `translate-only` (default: `bilingual`).
- `--concurrency`: Number of concurrent API requests (default: `4`).
- `--paragraphs`: Number of paragraphs per request (default: `4`).
- `--cache`: Custom path for the cache file (default: `.translation_cache.json`).

## Supported Providers
- **OpenAI Compatible** (ChatGPT, Claude, etc)
- **Gemini** (Google API)
- **DeepSeek**
- **Ollama** (Local models)
- **Custom API**

## Cache Management & Auto-Resume
- Translations are cached locally to `.translation_cache.json` (or a custom path via `--cache`) so you never pay twice for the same sentence.
- **Graceful Auto-Resume:** The cache is saved dynamically as translation progresses. If the process is interrupted (e.g. server crash, `Ctrl+C`), simply rerun the exact same command. The tool will instantly resume translation from where it left off!
- You can Export/Import caches to share translation progress across devices.

## Environment Variables (.env)
You can set defaults by creating a `.env` file in the directory to avoid exposing API keys in your terminal history:
```env
EPUB_PROVIDER=ollama
EPUB_MODEL=qwen2.5:7b
EPUB_API_URL=http://localhost:11434/v1/chat/completions
EPUB_API_KEY=your_key_here
EPUB_CACHE_PATH=/path/to/custom_cache.json
EPUB_TARGET=Simplified Chinese
EPUB_CONCURRENCY=1
```

## FAQ

### Does it support MOBI, AZW, or AZW3 formats?
This tool is specifically designed to be lightweight and focuses exclusively on the standard **EPUB** format. Kindle proprietary formats (MOBI/AZW3) are complex binary files that require heavy dependencies to repackage properly.

**Recommended Workflow for Kindle Users:**
1. Use [Calibre](https://calibre-ebook.com/) to convert your `.mobi` or `.azw3` files to `.epub`.
2. Translate the generated `.epub` file using this tool.
3. Use Amazon's **Send to Kindle** service to send the translated `.epub` to your device (Amazon now officially recommends EPUB and has deprecated MOBI).
4. *(Optional)* If you must transfer via USB, use Calibre to convert the translated EPUB back to AZW3.
