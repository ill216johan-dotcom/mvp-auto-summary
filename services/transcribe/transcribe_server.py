#!/usr/bin/env python3
# pyright: reportMissingModuleSource=false
"""
Transcription Server — универсальный адаптер STT.
Переключение провайдера через ENV: STT_PROVIDER=speechkit|whisper|assemblyai

API:
  POST /          — запустить транскрипцию { filepath, filename }
  POST /check     — проверить результат { filename }
  GET  /health    — статус сервиса
"""

import json, os, queue, shutil, subprocess, tempfile, time, urllib.request, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Конфигурация ─────────────────────────────────────────────────────────────────────────────

PORT = int(os.getenv('TRANSCRIBE_PORT', '9001'))

# Активный провайдер: speechkit | whisper | assemblyai
STT_PROVIDER = os.getenv('STT_PROVIDER', 'speechkit').lower().strip()

# SpeechKit (Yandex)
YANDEX_API_KEY = os.getenv('YANDEX_API_KEY', '')

# Whisper self-hosted (faster-whisper HTTP API, напр. http://whisper:9000)
WHISPER_URL = os.getenv('WHISPER_URL', 'http://whisper:9000')

# AssemblyAI
ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY', '')
ASSEMBLYAI_UPLOAD_URL = 'https://api.assemblyai.com/v2/upload'
ASSEMBLYAI_TRANSCRIPT_URL = 'https://api.assemblyai.com/v2/transcript'


def build_db_dsn():
    dsn = os.getenv('DB_DSN', '')
    if dsn:
        return dsn
    host = os.getenv('POSTGRES_HOST', 'postgres')
    port = os.getenv('POSTGRES_PORT', '5432')
    dbname = os.getenv('POSTGRES_DB', 'n8n')
    user = os.getenv('POSTGRES_USER', 'n8n')
    password = os.getenv('POSTGRES_PASSWORD', '')
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


DB_DSN = build_db_dsn()

WORKER_COUNT = int(os.getenv('TRANSCRIBE_WORKERS', '2'))
QUEUE_SIZE = int(os.getenv('TRANSCRIBE_QUEUE_SIZE', '50'))
WHISPER_TIMEOUT_MIN = int(os.getenv('WHISPER_TIMEOUT_MIN', '600'))
WHISPER_TIMEOUT_MAX = int(os.getenv('WHISPER_TIMEOUT_MAX', '86400'))
WHISPER_TIMEOUT_MULTIPLIER = float(os.getenv('WHISPER_TIMEOUT_MULTIPLIER', '4'))

JOB_QUEUE: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=QUEUE_SIZE)
JOB_LOCK = threading.Lock()
QUEUED_JOBS: set[str] = set()
RUNNING_JOBS: set[str] = set()


# ── Утилиты ─────────────────────────────────────────────────────────────────────────────────

def log(msg):
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] [{STT_PROVIDER.upper()}] {msg}'
    print(line, flush=True)
    try:
        with open('/tmp/ts.log', 'a') as f:
            f.write(line + '\n')
    except Exception:
        pass


def resolve_filepath(filepath):
    if not filepath:
        return filepath
    if os.path.exists(filepath):
        return filepath
    if filepath.startswith('/recordings/'):
        alt = filepath.replace('/recordings/', '/mnt/recordings/', 1)
        if os.path.exists(alt):
            return alt
    return filepath


def db_update(filename, status, transcript=None, error_message=None):
    try:
        import psycopg2
        conn = psycopg2.connect(DB_DSN)
        cur = conn.cursor()
        if transcript is not None:
            cur.execute(
                'UPDATE processed_files SET status=%s, transcript_text=%s WHERE filename=%s',
                (status, transcript, filename)
            )
        elif error_message is not None:
            cur.execute(
                'UPDATE processed_files SET status=%s, error_message=%s, retry_count=retry_count+1 WHERE filename=%s',
                (status, error_message, filename)
            )
        else:
            cur.execute(
                'UPDATE processed_files SET status=%s WHERE filename=%s',
                (status, filename)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        log(f'DB ERR: {e}')


def convert_to_ogg_chunks(filepath, tmpdir, chunk_sec=25):
    """Converts audio to OGG Opus and splits into chunks."""
    ogg = tmpdir + '/a.ogg'
    subprocess.run(['ffmpeg', '-i', filepath, '-vn', '-acodec', 'libopus', '-b:a', '16k', '-ac', '1', '-ar', '16000', ogg, '-y'], capture_output=True, timeout=300)
    subprocess.run(
        ['ffmpeg', '-i', ogg, '-f', 'segment',
         '-segment_time', str(chunk_sec), '-c', 'copy',
         tmpdir + '/c_%03d.ogg', '-y'],
        capture_output=True, timeout=60
    )
    return sorted([tmpdir + '/' + f for f in os.listdir(tmpdir) if f.startswith('c_')])


def get_media_duration_seconds(filepath: str) -> float | None:
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except Exception:
        return None


def compute_whisper_timeout(filepath: str) -> int:
    duration = get_media_duration_seconds(filepath)
    if duration is None:
        return WHISPER_TIMEOUT_MAX
    timeout = int(duration * WHISPER_TIMEOUT_MULTIPLIER)
    return max(WHISPER_TIMEOUT_MIN, min(timeout, WHISPER_TIMEOUT_MAX))


# ── Провайдер: SpeechKit (Yandex) ─────────────────────────────────────────────────────────

def transcribe_speechkit(filepath, filename):
    """
    Тарификация: каждые 15 сек аудио (округление вверх), 0.60₽/мин.
    Кодек и количество слов не влияют на цену — только длительность.
    Нарезаем на 25-секундные чанки для sync API.
    """
    if not YANDEX_API_KEY:
        raise RuntimeError('YANDEX_API_KEY is not set')

    td = tempfile.mkdtemp()
    try:
        chunks = convert_to_ogg_chunks(filepath, td)
        texts = []
        for c in chunks:
            with open(c,'rb') as f: audio = f.read()
            req = urllib.request.Request(
                'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize'
                '?lang=ru-RU&format=oggopus&sampleRateHertz=16000',
                data=audio,
                headers={'Authorization': 'Api-Key ' + YANDEX_API_KEY},
                method='POST'
            )
            try:
                r = urllib.request.urlopen(req, timeout=30)
                texts.append(json.loads(r.read()).get('result', ''))
            except Exception as e:
                log(f'SpeechKit chunk err: {e}')
            time.sleep(0.3)
        return ' '.join(t for t in texts if t)
    finally:
        shutil.rmtree(td, ignore_errors=True)


# ── Провайдер: Whisper (faster-whisper HTTP) ─────────────────────────────────────────────────

def transcribe_whisper(filepath, filename):
    """
    Отправляет файл на faster-whisper HTTP сервис (WHISPER_URL).
    Совместим с: faster-whisper-server, whisper.cpp server, openai-whisper-api-server.
    """
    ext = filepath.rsplit('.', 1)[-1].lower()
    tmp_audio = None
    timeout_seconds = compute_whisper_timeout(filepath)
    
    try:
        # Если файл видео (mp4, webm) - извлекаем аудио
        video_extensions = ('mp4', 'webm', 'avi', 'mov', 'mkv')
        if ext in video_extensions:
            log(f'Extracting audio from video: {filename}')
            tmp_audio = tempfile.mktemp(suffix='.wav')
            subprocess.run([
                'ffmpeg', '-i', filepath,
                '-vn', '-acodec', 'pcm_s16le',
                '-ar', '16000', '-ac', '1',
                tmp_audio, '-y'
            ], capture_output=True, timeout=300, check=True)
            filepath = tmp_audio
            ext = 'wav'
            log(f'Audio extracted successfully: {tmp_audio}')
        
        with open(filepath, 'rb') as f:
            audio_data = f.read()

        boundary = '----TranscribeBoundary'
        mime = {
            'ogg': 'audio/ogg', 'webm': 'audio/webm', 'mp3': 'audio/mpeg',
            'wav': 'audio/wav', 'm4a': 'audio/mp4'
        }.get(ext, 'application/octet-stream')

        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f'Content-Type: {mime}\r\n\r\n'
        ).encode() + audio_data + f'\r\n--{boundary}\r\n'.encode() + (
            f'Content-Disposition: form-data; name="language"\r\n\r\nru\r\n'
            f'--{boundary}--\r\n'
        ).encode()

        req = urllib.request.Request(
            WHISPER_URL + '/v1/audio/transcriptions',
            data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
            method='POST'
        )
        r = urllib.request.urlopen(req, timeout=timeout_seconds)
        result = json.loads(r.read())
        return result.get('text', '')
    finally:
        # Cleanup temporary audio file
        if tmp_audio and os.path.exists(tmp_audio):
            try:
                os.remove(tmp_audio)
                log(f'Temporary file removed: {tmp_audio}')
            except Exception as e:
                log(f'Failed to remove temp file: {e}')


# ── Провайдер: AssemblyAI ────────────────────────────────────────────────────────────────────────────────

def transcribe_assemblyai(filepath, filename):
    """
    AssemblyAI: ~$0.0025/мин (~0.23₽), поддержка русского.
    Загружает файл → создаёт задачу → polling результата.
    """
    if not ASSEMBLYAI_API_KEY:
        raise RuntimeError('ASSEMBLYAI_API_KEY is not set')

    headers = {'authorization': ASSEMBLYAI_API_KEY}

    # 1. Upload file
    with open(filepath, 'rb') as f:
        req = urllib.request.Request(
            ASSEMBLYAI_UPLOAD_URL,
            data=f.read(),
            headers={**headers, 'content-type': 'application/octet-stream'},
            method='POST'
        )
        r = urllib.request.urlopen(req, timeout=120)
        upload_url = json.loads(r.read())['upload_url']

    # 2. Submit transcription
    payload = json.dumps({
        'audio_url': upload_url,
        'language_code': 'ru',
        'punctuate': True,
        'format_text': True
    }).encode()
    req = urllib.request.Request(
        ASSEMBLYAI_TRANSCRIPT_URL,
        data=payload,
        headers={**headers, 'content-type': 'application/json'},
        method='POST'
    )
    r = urllib.request.urlopen(req, timeout=30)
    transcript_id = json.loads(r.read())['id']

    # 3. Poll until completed
    poll_url = f'{ASSEMBLYAI_TRANSCRIPT_URL}/{transcript_id}'
    for attempt in range(60):  # max 10 минут
        time.sleep(10)
        req = urllib.request.Request(poll_url, headers=headers)
        r = urllib.request.urlopen(req, timeout=15)
        data = json.loads(r.read())
        status = data.get('status')
        if status == 'completed':
            return data.get('text', '')
        if status == 'error':
            raise RuntimeError(f'AssemblyAI error: {data.get("error")}')

    raise RuntimeError('AssemblyAI timeout after 10 minutes')


# ── Диспетчер провайдеров ──────────────────────────────────────────────────────────────────────────────

PROVIDERS = {
    'speechkit': transcribe_speechkit,
    'whisper': transcribe_whisper,
    'assemblyai': transcribe_assemblyai,
}


def _worker_loop(worker_id: int) -> None:
    while True:
        filepath, filename = JOB_QUEUE.get()
        with JOB_LOCK:
            QUEUED_JOBS.discard(filename)
            RUNNING_JOBS.add(filename)

        log(f'START: {filename} (provider={STT_PROVIDER})')
        db_update(filename, 'transcribing')

        try:
            provider_fn = PROVIDERS.get(STT_PROVIDER)
            if not provider_fn:
                allowed = ', '.join(PROVIDERS.keys())
                raise RuntimeError(
                    f'Unknown STT_PROVIDER={STT_PROVIDER!r}. Allowed: {allowed}'
                )
            result = provider_fn(filepath, filename)
            if result:
                db_update(filename, 'completed', result)
                log(f'DONE: {filename} -> {len(result)} chars')
            else:
                db_update(filename, 'error', error_message='empty transcript')
                log(f'ERR: {filename}: empty transcript')
        except Exception as e:
            log(f'ERR: {filename}: {e}')
            db_update(filename, 'error', error_message=str(e))
        finally:
            with JOB_LOCK:
                RUNNING_JOBS.discard(filename)
            JOB_QUEUE.task_done()


def enqueue_job(filepath: str, filename: str) -> tuple[bool, str]:
    with JOB_LOCK:
        if filename in RUNNING_JOBS or filename in QUEUED_JOBS:
            return False, 'already_queued'
        if JOB_QUEUE.full():
            return False, 'queue_full'
        QUEUED_JOBS.add(filename)

    db_update(filename, 'queued')
    JOB_QUEUE.put((filepath, filename))
    return True, 'queued'


# ── HTTP Handler ─────────────────────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # отключаем стандартный nginx-style лог

    def do_GET(self):
        if self.path in ('/health', '/healthz'):
            issues = []
            if STT_PROVIDER == 'speechkit' and not YANDEX_API_KEY:
                issues.append('YANDEX_API_KEY not set')
            if STT_PROVIDER == 'assemblyai' and not ASSEMBLYAI_API_KEY:
                issues.append('ASSEMBLYAI_API_KEY not set')
            if issues:
                self._send(500, {'status': 'error', 'provider': STT_PROVIDER, 'issues': issues})
            else:
                self._send(200, {'status': 'ok', 'provider': STT_PROVIDER})
            return
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length) if length > 0 else b''
            body = json.loads(raw.decode('utf-8')) if raw else {}

            # /check — вернуть транскрипт из БД
            if self.path == '/check':
                filename = body.get('filename', '')
                import psycopg2
                conn = psycopg2.connect(DB_DSN)
                cur = conn.cursor()
                cur.execute('SELECT transcript_text, status FROM processed_files WHERE filename=%s', (filename,))
                row = cur.fetchone()
                conn.close()
                if row and row[0]:
                    self._send(200, {'transcript': row[0], 'status': row[1]})
                else:
                    self._send(200, {'transcript': None, 'status': row[1] if row else 'not_found'})
                return

            # / — запустить транскрипцию
            filepath = resolve_filepath(body.get('filepath', ''))
            filename = body.get('filename') or filepath.split('/')[-1]
            log(f'REQUEST: {filename}')

            if not filepath or not os.path.exists(filepath):
                self._send(400, {'error': 'file not found', 'path': filepath})
                return

            ok, state = enqueue_job(filepath, filename)
            if not ok and state == 'queue_full':
                self._send(503, {'status': 'error', 'error': 'queue_full', 'filename': filename})
                return
            if not ok and state == 'already_queued':
                self._send(200, {'status': 'processing', 'filename': filename, 'provider': STT_PROVIDER})
                return

            self._send(202, {'status': 'queued', 'filename': filename, 'provider': STT_PROVIDER})
            
        except Exception as e:
            log(f'HANDLER ERR: {e}')
            self._send(500, {'error': str(e)})

    def _send(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))


# ── Entrypoint ─────────────────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    log(f'TRANSCRIBE SERVER START — provider={STT_PROVIDER}, port={PORT}')
    for i in range(WORKER_COUNT):
        t = threading.Thread(target=_worker_loop, args=(i,), daemon=True)
        t.start()
        log(f'WORKER STARTED: {i+1}/{WORKER_COUNT}')
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
