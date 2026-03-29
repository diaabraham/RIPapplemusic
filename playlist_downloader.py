#!/usr/bin/env python3
"""
playlist_downloader.py — Universal iTunes/Apple Music Playlist Downloader
Downloads every song in an exported .txt playlist from Apple Music / iTunes as MP3.

GUI mode:  python3 playlist_downloader.py
CLI mode:  python3 playlist_downloader.py yourplaylist.txt [--jobs 5] [--output ~/Music/Downloads]

Requires: yt-dlp, ffmpeg
  brew install yt-dlp ffmpeg
"""

import sys, os, re, json, threading, subprocess, shutil, time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import webbrowser

# ─── Playlist Parser ──────────────────────────────────────────────────────────

def parse_playlist(data: bytes) -> list[dict]:
    """Parse an iTunes/Apple Music exported .txt playlist (UTF-16 or UTF-8)."""
    for enc in ('utf-16', 'utf-8', 'utf-16-le', 'utf-16-be'):
        try:
            text = data.decode(enc, errors='strict')
            break
        except Exception:
            continue
    else:
        text = data.decode('utf-8', errors='replace')

    lines = re.split(r'\r\n|\r|\n', text)
    if not lines:
        return []

    # Parse header
    header = lines[0].split('\t')
    try:
        name_idx   = header.index('Name')
        artist_idx = header.index('Artist')
    except ValueError:
        return []

    songs = []
    seen  = set()
    for line in lines[1:]:
        parts = line.split('\t')
        if len(parts) <= max(name_idx, artist_idx):
            continue
        name   = parts[name_idx].strip()
        artist = parts[artist_idx].strip()
        if name and artist:
            key = (name.lower(), artist.lower())
            if key not in seen:
                seen.add(key)
                songs.append({'title': name, 'artist': artist})
    return songs

# ─── Downloader ───────────────────────────────────────────────────────────────

def check_deps():
    missing = [t for t in ('yt-dlp', 'ffmpeg') if not shutil.which(t)]
    return missing

def download_song(title, artist, output_dir, success_log, failed_log, log_cb=print):
    safe_name = f"{artist} - {title}"
    # Skip if already downloaded
    if success_log.exists():
        if safe_name in success_log.read_text(encoding='utf-8'):
            log_cb(f"⏭  Skip: {safe_name}")
            return 'skip'

    log_cb(f"↓  {safe_name}")
    result = subprocess.run(
        [
            'yt-dlp',
            '--format', 'bestaudio[ext=m4a]/bestaudio',
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', '0',
            '--embed-thumbnail',
            '--add-metadata',
            '--output', str(output_dir / '%(uploader)s - %(title)s.%(ext)s'),
            '--no-playlist',
            '--quiet',
            '--no-warnings',
            '--ignore-errors',
            '--', f'ytsearch1:{artist} {title}'
        ],
        capture_output=True
    )
    if result.returncode == 0:
        with open(success_log, 'a', encoding='utf-8') as f:
            f.write(safe_name + '\n')
        log_cb(f"✓  Done: {safe_name}")
        return 'ok'
    else:
        with open(failed_log, 'a', encoding='utf-8') as f:
            f.write(safe_name + '\n')
        log_cb(f"✗  Fail: {safe_name}")
        return 'fail'

def run_downloads(songs, output_dir: Path, jobs: int = 5, log_cb=print, done_cb=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    success_log = output_dir / 'downloaded.txt'
    failed_log  = output_dir / 'failed.txt'
    failed_log.write_text('', encoding='utf-8')

    from concurrent.futures import ThreadPoolExecutor, as_completed
    counts = {'ok': 0, 'skip': 0, 'fail': 0}

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {
            ex.submit(download_song, s['title'], s['artist'],
                      output_dir, success_log, failed_log, log_cb): s
            for s in songs
        }
        for fut in as_completed(futs):
            r = fut.result()
            counts[r] += 1

    log_cb(f"\n{'─'*40}")
    log_cb(f"Done!  ✓ {counts['ok']}  ⏭ {counts['skip']}  ✗ {counts['fail']}")
    log_cb(f"Output: {output_dir}")
    if counts['fail']:
        log_cb(f"Failed list: {failed_log}")
    if done_cb:
        done_cb(counts)

# ─── HTML GUI ─────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Playlist Downloader</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:       #0a0a0a;
    --surface:  #111111;
    --border:   #222222;
    --accent:   #c8f542;
    --red:      #ff4444;
    --muted:    #555;
    --text:     #ebebeb;
    --subtext:  #888;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Syne', sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 48px 24px;
  }

  .wordmark {
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--subtext);
    margin-bottom: 40px;
    align-self: flex-start;
  }

  h1 {
    font-size: clamp(36px, 6vw, 72px);
    font-weight: 800;
    line-height: 1;
    margin-bottom: 8px;
    letter-spacing: -0.02em;
  }

  h1 span { color: var(--accent); }

  .sub {
    color: var(--subtext);
    font-size: 14px;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 48px;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 32px;
    width: 100%;
    max-width: 760px;
    margin-bottom: 16px;
  }

  /* Drop zone */
  #dropzone {
    border: 2px dashed var(--border);
    border-radius: 4px;
    padding: 48px;
    text-align: center;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    position: relative;
  }
  #dropzone.drag { border-color: var(--accent); background: rgba(200,245,66,0.04); }
  #dropzone input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  #dropzone .icon { font-size: 40px; margin-bottom: 12px; }
  #dropzone .label {
    font-size: 16px; font-weight: 700; margin-bottom: 6px;
  }
  #dropzone .hint {
    font-size: 12px; color: var(--subtext);
    font-family: 'JetBrains Mono', monospace;
  }

  /* Settings row */
  .settings {
    display: flex;
    gap: 16px;
    align-items: flex-end;
    flex-wrap: wrap;
  }
  .field { display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 160px; }
  .field label {
    font-size: 10px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--subtext);
    font-family: 'JetBrains Mono', monospace;
  }
  .field input {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 3px;
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    padding: 10px 12px;
    outline: none;
    transition: border-color 0.15s;
  }
  .field input:focus { border-color: var(--accent); }

  /* Song list */
  #song-list {
    max-height: 340px;
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }
  .song-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 9px 0;
    border-bottom: 1px solid var(--border);
    gap: 12px;
    font-size: 13px;
  }
  .song-row:last-child { border-bottom: none; }
  .song-title { font-weight: 700; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .song-artist { color: var(--subtext); font-family: 'JetBrains Mono', monospace; font-size: 11px; white-space: nowrap; }
  .song-status { font-size: 14px; width: 20px; text-align: center; flex-shrink: 0; }

  .list-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
  .list-header h2 { font-size: 18px; font-weight: 800; }
  .badge {
    background: var(--accent);
    color: #000;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 2px;
  }

  /* Buttons */
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 24px;
    border: none;
    border-radius: 3px;
    font-family: 'Syne', sans-serif;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    transition: opacity 0.15s, transform 0.1s;
    letter-spacing: 0.02em;
  }
  .btn:active { transform: scale(0.98); }
  .btn:disabled { opacity: 0.35; cursor: not-allowed; }
  .btn-primary { background: var(--accent); color: #000; width: 100%; justify-content: center; font-size: 15px; padding: 16px; }
  .btn-primary:hover:not(:disabled) { opacity: 0.88; }
  .btn-secondary { background: var(--border); color: var(--text); }

  /* Log */
  #log {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 3px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    padding: 16px;
    height: 260px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-all;
    color: #aaa;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }
  .log-ok   { color: var(--accent); }
  .log-fail { color: var(--red); }
  .log-skip { color: var(--muted); }
  .log-info { color: var(--text); }

  /* Progress bar */
  .progress-wrap {
    background: var(--border);
    border-radius: 2px;
    height: 4px;
    overflow: hidden;
    margin-bottom: 16px;
  }
  .progress-bar {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.3s;
    width: 0%;
  }

  /* Stats */
  .stats {
    display: flex;
    gap: 24px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    margin-bottom: 12px;
    color: var(--subtext);
  }
  .stat-ok   { color: var(--accent); }
  .stat-fail { color: var(--red); }

  /* Dep warning */
  #dep-warning {
    background: rgba(255,68,68,0.08);
    border: 1px solid rgba(255,68,68,0.3);
    border-radius: 3px;
    padding: 12px 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--red);
    margin-bottom: 16px;
    display: none;
  }

  .section-title {
    font-size: 10px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--subtext);
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 12px;
  }

  .hidden { display: none !important; }

  .done-banner {
    background: rgba(200,245,66,0.08);
    border: 1px solid rgba(200,245,66,0.25);
    border-radius: 3px;
    padding: 16px;
    text-align: center;
    font-weight: 700;
    font-size: 18px;
    color: var(--accent);
    margin-bottom: 16px;
    display: none;
  }
</style>
</head>
<body>

<div class="wordmark">// playlist-downloader</div>

<h1>Drop a playlist.<br><span>Get MP3s.</span></h1>
<p class="sub">Apple Music / iTunes export → YouTube → your disk</p>

<div id="dep-warning"></div>

<!-- Upload -->
<div class="card" id="upload-card">
  <div id="dropzone">
    <input type="file" accept=".txt" id="file-input">
    <div class="icon">📂</div>
    <div class="label">Drop your iTunes playlist .txt here</div>
    <div class="hint">File → Library → Export Playlist → .txt in iTunes/Music</div>
  </div>
</div>

<!-- Settings -->
<div class="card hidden" id="settings-card">
  <p class="section-title">Settings</p>
  <div class="settings">
    <div class="field">
      <label>Output folder</label>
      <input type="text" id="output-dir" placeholder="~/Music/Downloads">
    </div>
    <div class="field" style="max-width:120px">
      <label>Parallel jobs</label>
      <input type="number" id="jobs" value="5" min="1" max="20">
    </div>
  </div>
</div>

<!-- Song list -->
<div class="card hidden" id="list-card">
  <div class="list-header">
    <h2>Songs</h2>
    <span class="badge" id="count-badge">0</span>
  </div>
  <div id="song-list"></div>
</div>

<!-- Download button -->
<div style="width:100%;max-width:760px;margin-bottom:16px" class="hidden" id="btn-wrap">
  <button class="btn btn-primary" id="download-btn">↓ Download All as MP3</button>
</div>

<!-- Log / Progress -->
<div class="card hidden" id="progress-card">
  <div class="done-banner" id="done-banner">🎉 All done!</div>
  <div class="stats">
    <span>Total: <b id="s-total">0</b></span>
    <span class="stat-ok">Done: <b id="s-ok">0</b></span>
    <span class="stat-fail">Failed: <b id="s-fail">0</b></span>
    <span>Skipped: <b id="s-skip">0</b></span>
  </div>
  <div class="progress-wrap"><div class="progress-bar" id="pbar"></div></div>
  <p class="section-title">Log</p>
  <div id="log"></div>
</div>

<script>
let songs = [];
let running = false;
let counts = {ok:0, fail:0, skip:0};
let total = 0;

// ── Dep check on load ──
fetch('/api/check').then(r=>r.json()).then(d=>{
  if(d.missing && d.missing.length){
    const w = document.getElementById('dep-warning');
    w.style.display = 'block';
    w.innerHTML = `⚠ Missing dependencies: <b>${d.missing.join(', ')}</b><br>Run: <code>brew install ${d.missing.join(' ')}</code>`;
  }
});

// ── Drop zone ──
const dz = document.getElementById('dropzone');
const fi = document.getElementById('file-input');

dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('drag'); handleFile(e.dataTransfer.files[0]); });
fi.addEventListener('change', () => handleFile(fi.files[0]));

function handleFile(file) {
  if(!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const bytes = new Uint8Array(e.target.result);
    fetch('/api/parse', {
      method: 'POST',
      headers: {'Content-Type':'application/octet-stream'},
      body: bytes
    })
    .then(r => r.json())
    .then(d => {
      if(d.error){ alert('Parse error: ' + d.error); return; }
      songs = d.songs;
      // Default output dir from filename
      const stem = file.name.replace(/\.txt$/i,'').replace(/[^a-zA-Z0-9_\- ]/g,'').trim() || 'Playlist';
      document.getElementById('output-dir').value = `~/Music/${stem}_Downloads`;
      renderSongList();
      show('settings-card');
      show('list-card');
      show('btn-wrap');
    });
  };
  reader.readAsArrayBuffer(file);
}

function renderSongList() {
  const list = document.getElementById('song-list');
  document.getElementById('count-badge').textContent = songs.length;
  list.innerHTML = songs.map((s,i) =>
    `<div class="song-row" id="row-${i}">
      <span class="song-title">${esc(s.title)}</span>
      <span class="song-artist">${esc(s.artist)}</span>
      <span class="song-status" id="status-${i}"> </span>
    </div>`
  ).join('');
}

// ── Download ──
document.getElementById('download-btn').addEventListener('click', () => {
  if(running) return;
  running = true;
  counts = {ok:0, fail:0, skip:0};
  total = songs.length;
  document.getElementById('s-total').textContent = total;
  updateStats();
  show('progress-card');
  document.getElementById('download-btn').disabled = true;
  document.getElementById('done-banner').style.display = 'none';

  const outputDir = document.getElementById('output-dir').value.trim();
  const jobs = parseInt(document.getElementById('jobs').value) || 5;

  fetch('/api/start', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({songs, output_dir: outputDir, jobs})
  });

  pollLog();
});

function pollLog() {
  const logEl = document.getElementById('log');
  let offset = 0;
  const interval = setInterval(() => {
    fetch(`/api/log?offset=${offset}`)
    .then(r => r.json())
    .then(d => {
      if(d.lines && d.lines.length){
        d.lines.forEach(line => {
          offset++;
          const span = document.createElement('span');
          if(line.startsWith('✓')){ span.className='log-ok'; counts.ok++; updateStatusIcon(line,'✓'); }
          else if(line.startsWith('✗')){ span.className='log-fail'; counts.fail++; updateStatusIcon(line,'✗'); }
          else if(line.startsWith('⏭')){ span.className='log-skip'; counts.skip++; updateStatusIcon(line,'⏭'); }
          else if(line.startsWith('─') || line.startsWith('Done')){ span.className='log-info'; }
          span.textContent = line + '\n';
          logEl.appendChild(span);
          logEl.scrollTop = logEl.scrollHeight;
        });
        updateStats();
        updateProgress();
      }
      if(d.done){
        clearInterval(interval);
        running = false;
        document.getElementById('done-banner').style.display = 'block';
        document.getElementById('download-btn').disabled = false;
        document.getElementById('pbar').style.width = '100%';
      }
    });
  }, 800);
}

function updateStatusIcon(line, icon) {
  const match = line.match(/: (.+)$/);
  if(!match) return;
  const name = match[1];
  songs.forEach((s,i) => {
    if(`${s.artist} - ${s.title}` === name){
      const el = document.getElementById(`status-${i}`);
      if(el) el.textContent = icon;
    }
  });
}

function updateStats() {
  document.getElementById('s-ok').textContent   = counts.ok;
  document.getElementById('s-fail').textContent = counts.fail;
  document.getElementById('s-skip').textContent = counts.skip;
}

function updateProgress() {
  const done = counts.ok + counts.fail + counts.skip;
  document.getElementById('pbar').style.width = (done/total*100) + '%';
}

function show(id){ document.getElementById(id).classList.remove('hidden'); }
function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
</script>
</body>
</html>"""

# ─── HTTP Server ──────────────────────────────────────────────────────────────

_log_lines  = []
_job_done   = False
_job_lock   = threading.Lock()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # silence request logs

    def do_GET(self):
        path = urlparse(self.path).path
        qs   = parse_qs(urlparse(self.path).query)

        if path == '/':
            self._send(200, 'text/html', HTML.encode())

        elif path == '/api/check':
            missing = check_deps()
            self._json({'missing': missing})

        elif path == '/api/log':
            offset = int(qs.get('offset', ['0'])[0])
            with _job_lock:
                new_lines = _log_lines[offset:]
                done = _job_done
            self._json({'lines': new_lines, 'done': done})

        else:
            self._send(404, 'text/plain', b'Not found')

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)

        if path == '/api/parse':
            try:
                songs = parse_playlist(body)
                self._json({'songs': songs})
            except Exception as e:
                self._json({'error': str(e)})

        elif path == '/api/start':
            global _log_lines, _job_done
            data = json.loads(body)
            with _job_lock:
                _log_lines = []
                _job_done  = False

            songs      = data['songs']
            output_dir = Path(data['output_dir'].replace('~', str(Path.home())))
            jobs       = int(data.get('jobs', 5))

            def log_cb(msg):
                with _job_lock:
                    _log_lines.append(msg)

            def done_cb(counts):
                global _job_done
                with _job_lock:
                    _job_done = True

            threading.Thread(
                target=run_downloads,
                args=(songs, output_dir, jobs, log_cb, done_cb),
                daemon=True
            ).start()

            self._json({'ok': True})
        else:
            self._send(404, 'text/plain', b'Not found')

    def _send(self, code, ct, body):
        self.send_response(code)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self._send(200, 'application/json', body)

# ─── CLI mode ─────────────────────────────────────────────────────────────────

def cli_mode(txt_path: str, jobs: int, output_dir: str | None):
    path = Path(txt_path)
    if not path.exists():
        print(f"Error: file not found: {txt_path}")
        sys.exit(1)

    missing = check_deps()
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print(f"Run: brew install {' '.join(missing)}")
        sys.exit(1)

    songs = parse_playlist(path.read_bytes())
    if not songs:
        print("No songs found. Is this a valid iTunes/Apple Music .txt export?")
        sys.exit(1)

    stem = path.stem.replace(' ', '_')
    out  = Path(output_dir.replace('~', str(Path.home()))) if output_dir \
           else Path.home() / 'Music' / f'{stem}_Downloads'

    print(f"\nPlaylist : {path.name}")
    print(f"Songs    : {len(songs)}")
    print(f"Output   : {out}")
    print(f"Jobs     : {jobs}")
    print('─' * 40)

    run_downloads(songs, out, jobs=jobs)

# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    # CLI mode if a .txt is passed
    if args and not args[0].startswith('--'):
        txt   = args[0]
        jobs  = 5
        outd  = None
        for i, a in enumerate(args[1:], 1):
            if a == '--jobs'   and i+1 < len(args): jobs = int(args[i+1])
            if a == '--output' and i+1 < len(args): outd = args[i+1]
        cli_mode(txt, jobs, outd)
        return

    # GUI mode
    missing = check_deps()
    if missing:
        print(f"⚠  Missing: {', '.join(missing)}")
        print(f"   Run: brew install {' '.join(missing)}\n")

    port = 7842
    server = HTTPServer(('127.0.0.1', port), Handler)
    url = f'http://localhost:{port}'
    print(f"┌─────────────────────────────────┐")
    print(f"│  Playlist Downloader            │")
    print(f"│  {url}        │")
    print(f"│  Ctrl+C to quit                 │")
    print(f"└─────────────────────────────────┘")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")

if __name__ == '__main__':
    main()
