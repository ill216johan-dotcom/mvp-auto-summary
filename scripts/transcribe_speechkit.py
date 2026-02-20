#!/usr/bin/env python3
"""
Транскрибация аудио/видео файлов через Яндекс SpeechKit.
Использует асинхронное распознавание (для файлов > 1 минуты).

Использование:
  python transcribe_speechkit.py --key AQVN... --file /path/to/file.webm
  python transcribe_speechkit.py --key AQVN... --dir /mnt/recordings/2026/02/20

Результат сохраняется в .txt рядом с исходным файлом.
"""

import argparse
import os
import sys
import time
import json
import subprocess
import tempfile
import urllib.request
import urllib.error

# ── Яндекс SpeechKit ──────────────────────────────────────────────────────────
SPEECHKIT_UPLOAD_URL = "https://storage.yandexcloud.net"
SPEECHKIT_ASR_URL = "https://transcribe.api.cloud.yandex.net/speech/stt/v2/longRunningRecognize"
SPEECHKIT_OP_URL = "https://operation.api.cloud.yandex.net/operations/{op_id}"

# Поддерживаемые форматы
AUDIO_EXTS = {'.webm', '.mp3', '.ogg', '.wav', '.mp4', '.m4a', '.flac'}
MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def convert_to_ogg(input_path: str) -> str:
    """Конвертирует файл в OGG Opus через ffmpeg. Возвращает путь к tmp файлу."""
    tmp = tempfile.mktemp(suffix='.ogg')
    cmd = [
        'ffmpeg', '-i', input_path,
        '-vn',                    # без видео
        '-acodec', 'libopus',
        '-b:a', '64k',            # 64kbps достаточно для речи
        '-ac', '1',               # моно
        '-ar', '16000',           # 16kHz — оптимально для SpeechKit
        tmp, '-y'
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr.decode(errors='replace')[-500:]}")
    log(f"Конвертировано: {os.path.basename(input_path)} → {os.path.getsize(tmp) // 1024}KB OGG")
    return tmp


def upload_to_s3(file_path: str, api_key: str, bucket: str = "speechkit-tmp") -> str:
    """
    Загружает файл в Яндекс Object Storage.
    Возвращает публичный URI.
    
    ВАЖНО: для этого нужен отдельный bucket. Если нет — используем inline base64 (только для файлов < 1MB).
    Для больших файлов — загружаем через boto3/aws-cli.
    """
    raise NotImplementedError(
        "Загрузка в S3 требует настройки Yandex Object Storage bucket.\n"
        "Используйте --local режим (Whisper на сервере) или настройте bucket."
    )


def transcribe_inline(audio_path: str, api_key: str) -> str:
    """
    Синхронная транскрипция через SpeechKit (файл < 1MB, < 30 сек).
    Отправляет файл напрямую в теле запроса.
    """
    with open(audio_path, 'rb') as f:
        audio_data = f.read()

    url = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?lang=ru-RU&format=oggopus&sampleRateHertz=16000"
    req = urllib.request.Request(
        url,
        data=audio_data,
        headers={
            'Authorization': f'Api-Key {api_key}',
            'Content-Type': 'application/octet-stream',
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    return result.get('result', '')


def transcribe_async(audio_uri: str, api_key: str) -> str:
    """
    Асинхронная транскрипция для длинных файлов через SpeechKit Long Running.
    audio_uri — публичный URL файла в Yandex Object Storage.
    """
    payload = {
        "config": {
            "specification": {
                "languageCode": "ru-RU",
                "audioEncoding": "OGG_OPUS",
                "sampleRateHertz": 16000,
                "audioChannelCount": 1,
            }
        },
        "audio": {
            "uri": audio_uri
        }
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        SPEECHKIT_ASR_URL,
        data=data,
        headers={
            'Authorization': f'Api-Key {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        op = json.loads(resp.read())

    op_id = op.get('id')
    if not op_id:
        raise RuntimeError(f"No operation ID: {op}")

    log(f"Операция запущена: {op_id}")

    # Поллинг статуса
    for attempt in range(120):  # ждём до 20 минут
        time.sleep(10)
        op_req = urllib.request.Request(
            SPEECHKIT_OP_URL.format(op_id=op_id),
            headers={'Authorization': f'Api-Key {api_key}'},
        )
        with urllib.request.urlopen(op_req, timeout=15) as resp:
            status = json.loads(resp.read())

        if status.get('done'):
            if 'error' in status:
                raise RuntimeError(f"SpeechKit error: {status['error']}")
            chunks = status.get('response', {}).get('chunks', [])
            text = ' '.join(
                alt.get('text', '')
                for chunk in chunks
                for alt in chunk.get('alternatives', [])[:1]
            )
            return text.strip()

        if attempt % 6 == 0:
            log(f"  Ждём результат... ({attempt * 10}s)")

    raise TimeoutError("SpeechKit не ответил за 20 минут")


def transcribe_file(input_path: str, api_key: str) -> str:
    """Основная функция: конвертирует и транскрибирует файл."""
    size = os.path.getsize(input_path)
    log(f"Файл: {os.path.basename(input_path)} ({size // 1024 // 1024}MB)")

    if size > MAX_SIZE_BYTES:
        log(f"ПРОПУСК: файл > 100MB")
        return None

    # Конвертируем в OGG
    tmp_ogg = None
    try:
        tmp_ogg = convert_to_ogg(input_path)
        ogg_size = os.path.getsize(tmp_ogg)

        if ogg_size < 900_000:
            # Маленький файл — синхронная транскрипция
            log("Режим: синхронный (inline)")
            text = transcribe_inline(tmp_ogg, api_key)
        else:
            # Большой файл — нужна загрузка в S3
            log(f"Размер OGG: {ogg_size // 1024}KB — нужен Object Storage")
            raise NotImplementedError(
                "Файл слишком большой для inline. Нужен Yandex Object Storage bucket.\n"
                "Создайте bucket и передайте --bucket параметр."
            )

        return text

    finally:
        if tmp_ogg and os.path.exists(tmp_ogg):
            os.unlink(tmp_ogg)


def process_file(input_path: str, api_key: str) -> bool:
    """Обрабатывает один файл, сохраняет .txt результат."""
    output_path = os.path.splitext(input_path)[0] + '_transcript.txt'

    if os.path.exists(output_path):
        log(f"УЖЕ ОБРАБОТАН: {output_path}")
        return True

    try:
        text = transcribe_file(input_path, api_key)
        if text is None:
            return False
        if not text:
            log("ПРЕДУПРЕЖДЕНИЕ: пустой текст транскрипции")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
        log(f"СОХРАНЕНО: {output_path}")
        log(f"Превью: {text[:200]}...")
        return True

    except NotImplementedError as e:
        log(f"ОШИБКА (нужна настройка): {e}")
        return False
    except Exception as e:
        log(f"ОШИБКА: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Транскрибация через Яндекс SpeechKit')
    parser.add_argument('--key', required=True, help='API ключ SpeechKit (начинается с AQVN...)')
    parser.add_argument('--file', help='Путь к одному файлу')
    parser.add_argument('--dir', help='Директория с файлами (обрабатывает все аудио/видео)')
    parser.add_argument('--test', action='store_true', help='Тест соединения с SpeechKit')
    args = parser.parse_args()

    if args.test:
        log("Тестируем SpeechKit API...")
        req = urllib.request.Request(
            "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?lang=ru-RU",
            data=b'\x00' * 100,
            headers={'Authorization': f'Api-Key {args.key}'},
            method='POST'
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as e:
            if e.code in (400, 415):
                log(f"API отвечает (ошибка {e.code} ожидаема для пустых данных) — КЛЮЧ РАБОЧИЙ")
            elif e.code == 401:
                log(f"ОШИБКА 401: неверный API ключ")
            else:
                log(f"HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
        return

    if args.file:
        process_file(args.file, args.key)

    elif args.dir:
        files = [
            os.path.join(args.dir, f)
            for f in sorted(os.listdir(args.dir))
            if os.path.splitext(f)[1].lower() in AUDIO_EXTS
        ]
        log(f"Найдено файлов: {len(files)}")
        for f in files:
            process_file(f, args.key)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
