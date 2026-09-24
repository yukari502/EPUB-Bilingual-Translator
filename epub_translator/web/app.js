const elements = {
  dropZone: document.getElementById('drop-zone'),
  fileInput: document.getElementById('file-input'),
  uploadArea: document.getElementById('upload-area'),
  workspace: document.getElementById('workspace'),
  chapterList: document.getElementById('chapter-list'),
  previewContent: document.getElementById('preview-content'),
  btnTranslateAll: document.getElementById('btn-translate-all'),
  btnTranslateChapter: document.getElementById('btn-translate-chapter'),
  btnToggleLogs: document.getElementById('btn-toggle-logs'),
  logConsole: document.getElementById('log-console'),
  logOutput: document.getElementById('log-output'),
  btnStop: document.getElementById('btn-stop'),
  btnExport: document.getElementById('btn-export'),
  btnSaveSettings: document.getElementById('btn-save-settings'),
  progressText: document.getElementById('progress-text'),
  progressPercentage: document.getElementById('progress-percentage'),
  progressBarFill: document.getElementById('progress-bar-fill'),
  progressStats: document.getElementById('progress-stats'),
};

let ws = null;
let currentChapters = [];
let activeChapterIndex = -1;
let translationActive = false;

// Initialize
async function init() {
  await loadSettings();
  setupEventListeners();
}

// Drag and Drop
function setupEventListeners() {
  elements.dropZone.addEventListener('click', () => elements.fileInput.click());
  
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    elements.dropZone.addEventListener(eventName, preventDefaults, false);
  });
  
  ['dragenter', 'dragover'].forEach(eventName => {
    elements.dropZone.addEventListener(eventName, () => elements.dropZone.classList.add('dragover'), false);
  });
  
  ['dragleave', 'drop'].forEach(eventName => {
    elements.dropZone.addEventListener(eventName, () => elements.dropZone.classList.remove('dragover'), false);
  });
  
  elements.dropZone.addEventListener('drop', handleDrop, false);
  elements.fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) uploadFile(e.target.files[0]);
  });

  elements.btnTranslateAll.addEventListener('click', () => startTranslation('all'));
  elements.btnTranslateChapter.addEventListener('click', () => {
    if (activeChapterIndex >= 0) {
      startTranslation('chapter', activeChapterIndex);
    } else {
      alert("Please select a chapter first.");
    }
  });
  elements.btnToggleLogs.addEventListener('click', () => {
    elements.logConsole.classList.toggle('hidden');
  });
  elements.btnStop.addEventListener('click', stopTranslation);
  elements.btnExport.addEventListener('click', exportEpub);
  elements.btnSaveSettings.addEventListener('click', saveSettings);
}

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

function handleDrop(e) {
  const dt = e.dataTransfer;
  const files = dt.files;
  if (files.length) uploadFile(files[0]);
}

async function uploadFile(file) {
  if (!file.name.endsWith('.epub')) {
    alert('Please upload an EPUB file.');
    return;
  }
  
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    elements.dropZone.querySelector('p').innerText = 'Uploading and parsing...';
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    if (!res.ok) throw new Error(await res.text());
    
    const data = await res.json();
    currentChapters = data.chapters;
    
    elements.uploadArea.style.display = 'none';
    elements.workspace.classList.add('active');
    elements.btnExport.classList.remove('hidden');
    
    renderChapterList();
    if (currentChapters.length > 0) {
      loadChapter(0);
    }
  } catch (err) {
    alert('Upload failed: ' + err.message);
    elements.dropZone.querySelector('p').innerText = 'Drag and drop EPUB file here';
  }
}

function renderChapterList() {
  elements.chapterList.innerHTML = '';
  currentChapters.forEach((ch, idx) => {
    const div = document.createElement('div');
    div.className = 'chapter-item' + (idx === activeChapterIndex ? ' active' : '');
    const statusText = ch.statusText || 'Pending';
    const statusClass = ch.statusClass || 'chapter-status';
    div.innerHTML = `<span>${ch.index}. ${ch.title}</span> <span class="${statusClass}" id="status-${idx}">${statusText}</span>`;
    div.onclick = () => loadChapter(idx);
    elements.chapterList.appendChild(div);
  });
}

function updateChapterStatus(idx, text, className) {
  if (idx >= 0 && idx < currentChapters.length) {
    currentChapters[idx].statusText = text;
    currentChapters[idx].statusClass = className;
  }
  const statusEl = document.getElementById(`status-${idx}`);
  if (statusEl) {
    statusEl.innerText = text;
    statusEl.className = className;
  }
}

async function loadChapter(index) {
  if (index < 0 || index >= currentChapters.length) return;
  activeChapterIndex = index;
  renderChapterList(); // Update active class
  
  try {
    const res = await fetch(`/api/chapter/${index}?t=${Date.now()}`);
    const data = await res.json();
    renderPreview(data.html, data.path);
  } catch (err) {
    elements.previewContent.innerHTML = `<div style="color:red">Failed to load chapter: ${err.message}</div>`;
  }
}

// Render preview inside an isolated iframe
function renderPreview(html, chapterPath = '') {
  // Strip XML declaration to avoid text/html parsing issues
  html = html.replace(/<\?xml[\s\S]*?\?>/gi, '');
  
  // FIX: XHTML self-closing <script /> tags cause HTML5 parsers to swallow the ENTIRE rest of the document!
  // We must remove all scripts (both normal and self-closing) via regex BEFORE parsing.
  html = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
  html = html.replace(/<script\b[^>]*\/>/gi, '');
  
  // Remove external stylesheets to prevent 404s
  html = html.replace(/<link\b[^>]*rel=["']stylesheet["'][^>]*\/?>/gi, '');

  // Parse HTML just to extract the body content
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  
  let bodyContent = '';
  if (doc.body) {
    bodyContent = doc.body.innerHTML;
  } else {
    const bodyMatch = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
    bodyContent = bodyMatch ? bodyMatch[1] : html;
  }

  // Use the chapter path to construct a base URL so images and assets load properly!
  const baseHref = chapterPath ? `/api/epub/${chapterPath}` : '';

  const currentMode = document.getElementById('mode')?.value || 'bilingual';
  const displayOriginal = currentMode === 'bilingual' ? 'block' : 'none';

  // Build a completely clean, isolated HTML skeleton
  const finalHtml = `
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8">
        ${baseHref ? `<base href="${baseHref}">` : ''}
        <style>
          html, body { 
            background-color: #111111 !important; 
            color: #ededed !important; 
            font-family: 'Inter', system-ui, sans-serif; 
            padding: 1rem 2rem; 
            margin: 0;
            line-height: 1.7;
            font-size: 1.1rem;
            overflow-x: hidden;
            overflow-wrap: break-word;
          }
          .original-text, [data-epub-translator-original="1"] { 
            color: #888888 !important; 
            font-size: 0.95em; 
            display: block;
            margin-bottom: 0.5rem;
          }
          .translation-block { 
            color: #ededed !important; 
            font-weight: 500; 
            margin-top: 0.2rem;
            margin-bottom: 1.5rem;
            display: block;
          }
          img { 
            max-width: 100%; 
            height: auto; 
            display: block; 
            margin: 1rem auto; 
            border-radius: 8px;
          }
        </style>
        <style id="dynamic-mode-style">
          [data-epub-translator-original="1"] { display: ${displayOriginal} !important; }
        </style>
      </head>
      <body>
        ${bodyContent}
      </body>
    </html>
  `;

  elements.previewContent.innerHTML = '';
  const iframe = document.createElement('iframe');
  iframe.style.width = '100%';
  iframe.style.height = '100%';
  iframe.style.minHeight = '600px';
  iframe.style.border = 'none';
  iframe.style.background = 'transparent';
  elements.previewContent.appendChild(iframe);
  
  const idoc = iframe.contentWindow.document;
  idoc.open();
  idoc.write(finalHtml);
  idoc.close();
}

async function loadSettings() {
  const res = await fetch('/api/settings');
  const s = await res.json();
  ['provider', 'target_language', 'mode', 'model', 'api_url', 'api_key', 'concurrency', 'paragraphs', 'glossary'].forEach(k => {
    if (document.getElementById(k)) document.getElementById(k).value = s[k] || '';
  });
}

// Setup Cache Event Listeners
document.getElementById('clearCacheBtn')?.addEventListener('click', async () => {
  if (confirm('Are you sure you want to clear the translation cache? This cannot be undone.')) {
    const res = await fetch('/api/cache/clear', { method: 'POST' });
    const data = await res.json();
    alert(data.message || data.error);
  }
});

document.getElementById('importCacheBtn')?.addEventListener('click', () => {
  document.getElementById('cacheFileInput')?.click();
});

document.getElementById('exportCacheBtn')?.addEventListener('click', () => {
  window.location.href = '/api/cache/export';
});

document.getElementById('cacheFileInput')?.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/cache/load', { method: 'POST', body: formData });
    if (res.ok) {
      alert('Cache imported! Applying to current book...');
      startTranslation('cache_only');
    } else {
      const err = await res.json();
      alert('Import failed: ' + err.error);
    }
  } catch (err) {
    alert('Error: ' + err.message);
  }
});

async function saveSettings() {
  const payload = {};
  ['provider', 'target_language', 'mode', 'model', 'api_url', 'api_key', 'concurrency', 'paragraphs', 'glossary'].forEach(k => {
    if (document.getElementById(k)) payload[k] = document.getElementById(k).value;
  });
  
  await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  elements.btnSaveSettings.innerText = 'Saved!';
  setTimeout(() => elements.btnSaveSettings.innerText = 'Save Settings', 2000);
}

// Dynamic mode toggling without re-translating
document.getElementById('mode')?.addEventListener('change', (e) => {
  const isBilingual = e.target.value === 'bilingual';
  const iframe = elements.previewContent.querySelector('iframe');
  if (iframe && iframe.contentWindow) {
    const styleEl = iframe.contentWindow.document.getElementById('dynamic-mode-style');
    if (styleEl) {
      styleEl.textContent = `[data-epub-translator-original="1"] { display: ${isBilingual ? 'block' : 'none'} !important; }`;
    }
  }
});

// Translation WebSocket
function startTranslation(mode = 'all', chapterIdx = -1) {
  if (translationActive) return;
  translationActive = true;
  
  elements.btnTranslateAll.classList.add('hidden');
  elements.btnTranslateChapter.classList.add('hidden');
  elements.btnStop.classList.remove('hidden');
  elements.btnExport.classList.add('hidden');
  
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${wsProto}//${window.location.host}/ws/translate?mode=${mode}&chapter_idx=${chapterIdx}`);
  
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleWsMessage(msg, mode);
  };
  
  ws.onclose = () => {
    translationActive = false;
    elements.btnTranslateAll.classList.remove('hidden');
    elements.btnTranslateChapter.classList.remove('hidden');
    elements.btnStop.classList.add('hidden');
    elements.btnExport.classList.remove('hidden');
  };
}

function stopTranslation() {
  if (ws) {
    ws.send(JSON.stringify({ action: 'stop' }));
    elements.btnStop.innerText = 'Stopping...';
    elements.btnStop.disabled = true;
    elements.btnStop.style.opacity = '0.7';
  }
}

async function exportEpub() {
  window.location.href = '/api/export';
}

let startTime = 0;
let progressHistory = [];

function handleWsMessage(msg, mode) {
  if (msg.type === 'init') {
    elements.progressBarFill.style.width = '0%';
    elements.progressPercentage.innerText = '0%';
    elements.progressText.innerText = 'Analyzing full book...';
    startTime = Date.now();
    progressHistory = [];
  } else if (msg.type === 'progress') {
    const { done, total, chapter_index } = msg;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    
    elements.progressBarFill.style.width = `${pct}%`;
    elements.progressPercentage.innerText = `${pct}%`;
    elements.progressText.innerText = `Translating...`;
    
    // Estimate remaining time using a sliding window (e.g., last 15 seconds)
    const now = Date.now();
    progressHistory.push({ time: now, done: done });
    progressHistory = progressHistory.filter(p => now - p.time <= 15000);
    
    let rate = 0;
    if (progressHistory.length > 1) {
      const oldest = progressHistory[0];
      const elapsed = (now - oldest.time) / 1000;
      if (elapsed > 0) {
        rate = (done - oldest.done) / elapsed;
      }
    }
    
    if (rate > 0) {
      const remaining = (total - done) / rate;
      elements.progressStats.innerText = `Speed: ${rate.toFixed(1)} blocks/s | ETA: ${Math.round(remaining)}s`;
    } else if (done > 0) {
      const elapsedGlobal = (now - startTime) / 1000;
      rate = elapsedGlobal > 0 ? done / elapsedGlobal : 0;
      if (rate > 0) {
        const remaining = (total - done) / rate;
        elements.progressStats.innerText = `Speed: ${rate.toFixed(1)} blocks/s | ETA: ${Math.round(remaining)}s`;
      }
    }
    
    if (chapter_index !== undefined) {
      updateChapterStatus(chapter_index, 'Translating', 'chapter-status');
      
      // Live preview update
      if (msg.live_html && chapter_index === activeChapterIndex) {
        const iframe = elements.previewContent.querySelector('iframe');
        if (iframe && iframe.contentWindow) {
          const idoc = iframe.contentWindow.document;
          const scrollY = idoc.documentElement.scrollTop || idoc.body.scrollTop;
          
          let liveBody = msg.live_html;
          // Strip XML just like renderPreview
          liveBody = liveBody.replace(/<\?xml[\s\S]*?\?>/gi, '');
          liveBody = liveBody.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
          liveBody = liveBody.replace(/<script\b[^>]*\/>/gi, '');
          liveBody = liveBody.replace(/<link\b[^>]*rel=["']stylesheet["'][^>]*\/?>/gi, '');
          
          const match = liveBody.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
          if (match) liveBody = match[1];
          
          idoc.body.innerHTML = liveBody;
          idoc.documentElement.scrollTop = scrollY;
          idoc.body.scrollTop = scrollY;
        }
      }
    }
  } else if (msg.type === 'chapter_done') {
    const { chapter_index, html, path } = msg;
    updateChapterStatus(chapter_index, 'Done', 'chapter-status done');
    
    if (chapter_index === activeChapterIndex) {
      renderPreview(html, path);
    }
  } else if (msg.type === 'done' || msg.type === 'stopped') {
    if (mode === 'cache_only') {
      elements.progressText.innerText = 'Cache Applied';
    } else {
      elements.progressText.innerText = msg.type === 'done' ? 'Translation Complete!' : 'Stopped';
    }
    translationActive = false;
    elements.btnTranslateAll.classList.remove('hidden');
    elements.btnTranslateChapter.classList.remove('hidden');
    elements.btnStop.classList.add('hidden');
    elements.btnStop.innerText = 'Stop Translation';
    elements.btnStop.disabled = false;
    elements.btnStop.style.opacity = '1';
    elements.btnExport.classList.remove('hidden');
  } else if (msg.type === 'error') {
    alert('Translation error: ' + msg.message);
    ws.close();
  } else if (msg.type === 'log') {
    const logLine = document.createElement('div');
    logLine.style.marginBottom = '2px';
    logLine.innerText = msg.message;
    elements.logOutput.appendChild(logLine);
    elements.logConsole.scrollTop = elements.logConsole.scrollHeight;
  }
}

init();
