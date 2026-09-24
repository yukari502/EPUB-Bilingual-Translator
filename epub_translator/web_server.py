from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import io
import json
import logging
import os
import sys
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import uvicorn
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import mimetypes
from pydantic import BaseModel

from .cache import TranslationCache
from .config import load_config, save_config, settings_from_config
from .epub import EpubBook
from .html_translate import collect_targets, remove_scripts, translate_html


class AppState:
    def __init__(self) -> None:
        self.book: EpubBook | None = None
        self.settings = settings_from_config(load_config())
        self.cache = TranslationCache(Path(".translation_cache.json"))
        self.analysis_cache: dict[str, int] = {}
        self.analysis_cache_path = Path(".analysis_cache.json")
        if self.analysis_cache_path.exists():
            try:
                with open(self.analysis_cache_path, "r", encoding="utf-8") as f:
                    self.analysis_cache = json.load(f)
            except Exception:
                pass
                
    def save_analysis_cache(self):
        try:
            with open(self.analysis_cache_path, "w", encoding="utf-8") as f:
                json.dump(self.analysis_cache, f)
        except Exception:
            pass

state = AppState()

# Determine web directory
if getattr(sys, 'frozen', False):
    WEB_DIR = Path(sys._MEIPASS) / "web"
else:
    WEB_DIR = Path(__file__).parent / "web"

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if state.book:
        pass

app = FastAPI(title="EPUB Translator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.post("/api/upload")
async def upload_epub(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename or not file.filename.endswith(".epub"):
        return JSONResponse({"error": "Invalid file"}, status_code=400)
    
    with NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
        
    state.book = EpubBook.load(tmp_path)
    state.book.epub_path = Path(file.filename)
    
    chapters = [{"index": i, "title": ch.title} for i, ch in enumerate(state.book.chapters)]
    return JSONResponse({"chapters": chapters})


class SettingsPayload(BaseModel):
    provider: str
    target_language: str
    mode: str
    model: str
    api_url: str
    api_key: str
    concurrency: int
    paragraphs: int
    glossary: str = ""

@app.get("/api/settings")
async def get_settings() -> JSONResponse:
    s = state.settings
    return JSONResponse({
        "provider": s.provider,
        "target_language": s.target_language,
        "mode": s.mode,
        "model": s.model,
        "api_url": s.api_url,
        "api_key": s.api_key,
        "concurrency": s.max_concurrency,
        "paragraphs": s.paragraphs_per_request,
        "glossary": s.glossary,
    })

@app.post("/api/settings")
async def update_settings(payload: SettingsPayload) -> JSONResponse:
    state.settings.provider = payload.provider
    state.settings.target_language = payload.target_language
    state.settings.mode = payload.mode
    state.settings.model = payload.model
    state.settings.api_url = payload.api_url
    state.settings.api_key = payload.api_key
    state.settings.max_concurrency = payload.concurrency
    state.settings.paragraphs_per_request = payload.paragraphs
    state.settings.glossary = payload.glossary
    save_config(state.settings)
    return JSONResponse({"status": "ok"})


@app.post("/api/cache/load")
async def load_cache(file: UploadFile = File(...)) -> JSONResponse:
    with NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        state.cache.load_from(tmp_path)
        os.unlink(tmp_path)
        return JSONResponse({"status": "ok", "message": "Cache imported successfully"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/cache/clear")
async def clear_cache() -> JSONResponse:
    try:
        state.cache.clear()
        return JSONResponse({"status": "ok", "message": "Cache cleared"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
@app.get("/api/cache/export")
async def export_cache() -> FileResponse:
    path = Path(".translation_cache.json")
    if not path.exists():
        return JSONResponse({"error": "No cache file found"}, status_code=404)
    return FileResponse(path, filename="translation_cache.json", media_type="application/json")

@app.get("/api/chapter/{index}")
async def get_chapter(index: int) -> JSONResponse:
    if not state.book or index < 0 or index >= len(state.book.chapters):
        return JSONResponse({"error": "Not found"}, status_code=404)
    chapter = state.book.chapters[index]
    html = state.book.read_text(chapter.path)
    return JSONResponse({"html": html, "path": chapter.path})

@app.get("/api/epub/{path:path}")
async def get_epub_resource(path: str):
    if not state.book:
        return JSONResponse({"error": "No book loaded"}, status_code=404)
    try:
        normalized = state.book._normalize(path)
        data = state.book.files[normalized]
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return Response(content=data, media_type=mime)
    except KeyError:
        return JSONResponse({"error": "Not found"}, status_code=404)


@app.get("/api/export")
async def export_epub() -> FileResponse:
    if not state.book:
        return JSONResponse({"error": "No book loaded"}, status_code=400)
        
    original_name = state.book.epub_path.stem
    target_lang = state.settings.target_language.replace(" ", "")
    mode_str = "Bilingual" if state.settings.mode == "bilingual" else "TranslateOnly"
    out_name = f"{original_name}_{target_lang}_{mode_str}.epub"
    out_path = Path(out_name).resolve()
    
    # If mode is translate-only, we strip out the original text before saving!
    if state.settings.mode != "bilingual":
        for index, chapter in enumerate(state.book.chapters):
            html = state.book.read_text(chapter.path)
            soup = BeautifulSoup(html, "xml")
            for tag in soup.find_all(attrs={"data-epub-translator-original": "1"}):
                tag.decompose()
            state.book.write_text(chapter.path, str(soup))
            
    state.book.export(str(out_path))
    return FileResponse(path=out_path, filename=out_name, media_type="application/epub+zip")


@app.websocket("/ws/translate")
async def websocket_translate(websocket: WebSocket, mode: str = "all", chapter_idx: int = -1):
    await websocket.accept()
    if not state.book:
        await websocket.send_json({"type": "error", "message": "No book loaded"})
        await websocket.close()
        return

    cancel_event = asyncio.Event()
    
    async def listen_for_cancel():
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("action") == "stop":
                    cancel_event.set()
                    break
        except WebSocketDisconnect:
            cancel_event.set()

    listener_task = asyncio.create_task(listen_for_cancel())

    try:
        await websocket.send_json({"type": "init"})
        
        # Calculate global text targets for accurate progress
        total_targets = 0
        chapter_targets = {}
        
        loop = asyncio.get_running_loop()
        
        # Setup logger
        log_queue: asyncio.Queue[str] = asyncio.Queue()
        
        class WebSocketLogHandler(logging.Handler):
            def emit(self, record):
                try:
                    msg = self.format(record)
                    log_queue.put_nowait(msg)
                except Exception:
                    pass

        log_handler = WebSocketLogHandler()
        log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S'))
        
        logger = logging.getLogger("translator")
        logger.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        
        async def log_sender():
            try:
                while True:
                    msg = await log_queue.get()
                    await websocket.send_json({"type": "log", "message": msg})
            except Exception:
                pass
                
        log_task = asyncio.create_task(log_sender())
        
        def analyze_chapter(index: int, chapter_path: str) -> tuple[int, int]:
            if mode == "chapter" and index != chapter_idx:
                return index, 0
                
            html_text = state.book.read_text(chapter_path)
            html_hash = hashlib.md5(html_text.encode("utf-8")).hexdigest()
            if html_hash in state.analysis_cache:
                return index, state.analysis_cache[html_hash]
                
            soup_obj = BeautifulSoup(remove_scripts(html_text), "xml")
            targs = collect_targets(soup_obj)
            count = len(targs)
            state.analysis_cache[html_hash] = count
            return index, count

        with concurrent.futures.ThreadPoolExecutor() as pool:
            tasks = [
                loop.run_in_executor(pool, analyze_chapter, index, chapter.path)
                for index, chapter in enumerate(state.book.chapters)
            ]
            results = await asyncio.gather(*tasks)

        for index, count in results:
            chapter_targets[index] = count
            total_targets += count
            
        state.save_analysis_cache()
            
        global_completed = 0
        
        for index, chapter in enumerate(state.book.chapters):
            if cancel_event.is_set():
                break
                
            if mode == "chapter" and index != chapter_idx:
                continue
            
            html = state.book.read_text(chapter.path)
            if chapter_targets[index] == 0:
                await websocket.send_json({
                    "type": "chapter_done", 
                    "chapter_index": index, 
                    "html": html,
                    "path": chapter.path
                })
                continue
                
            chapter_completed = 0
            
            async def progress_cb(done: int, total: int, source: str, current_html: str = ""):
                nonlocal chapter_completed, global_completed
                increment = done - chapter_completed
                chapter_completed = done
                global_completed += increment
                await websocket.send_json({
                    "type": "progress",
                    "done": global_completed,
                    "total": total_targets,
                    "chapter_index": index,
                    "live_html": current_html,
                    "path": chapter.path
                })

            translated_html = await translate_html(
                html=html,
                settings=state.settings,
                cache=state.cache,
                progress=progress_cb,
                cancel_event=cancel_event,
                cache_only=(mode == "cache_only")
            )
            state.book.write_text(chapter.path, translated_html)
            
            if not cancel_event.is_set():
                await websocket.send_json({
                    "type": "chapter_done",
                    "chapter_index": index,
                    "html": translated_html,
                    "path": chapter.path
                })
                
        if cancel_event.is_set():
            await websocket.send_json({"type": "stopped"})
        else:
            await websocket.send_json({"type": "done"})
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        if 'logger' in locals() and 'log_handler' in locals():
            logger.removeHandler(log_handler)
        if 'log_task' in locals():
            log_task.cancel()
        listener_task.cancel()
        if not websocket.client_state.name == "DISCONNECTED":
            try:
                await websocket.close()
            except Exception:
                pass


def main():
    print("Starting EPUB Translator Web UI...")
    url = "http://127.0.0.1:8000"
    
    async def open_browser():
        await asyncio.sleep(1)
        webbrowser.open(url)
        
    loop = asyncio.new_event_loop()
    loop.create_task(open_browser())
    config = uvicorn.Config(app=app, host="127.0.0.1", port=8000, loop=loop)
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())

if __name__ == "__main__":
    main()
