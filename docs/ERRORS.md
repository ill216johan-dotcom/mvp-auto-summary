# Known Errors & Troubleshooting

> База знаний ошибок: symptom → root cause → fix

---

## Setup Errors

### E001: n8n не запускается — `N8N_ENCRYPTION_KEY required`

**Symptom**: Container exits with `Error: n8n requires an encryption key`  
**Root Cause**: Missing `N8N_ENCRYPTION_KEY` in `.env`  
**Fix**:
```bash
# Generate random key and add to .env
echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 16)" >> .env
docker compose up -d
```

---

### E002: PostgreSQL connection refused

**Symptom**: n8n logs `Error: connect ECONNREFUSED postgres:5432`  
**Root Cause**: PostgreSQL не успел запуститься до n8n  
**Fix**: docker-compose уже содержит `depends_on` + `healthcheck`. Если всё равно падает:
```bash
docker compose down && docker compose up -d
```

---

### E003: open-notebook не подключается к SurrealDB

**Symptom**: open-notebook UI показывает ошибку подключения к базе  
**Root Cause**: SurrealDB ещё стартует или неверные credentials  
**Fix**:
```bash
# Проверить что SurrealDB запущен
curl http://localhost:8000/health

# Проверить credentials в .env
# SURREAL_USER и SURREAL_PASSWORD должны совпадать
```

---

## Pipeline Errors

### E010: Whisper — `audio_file is required`

**Symptom**: Whisper возвращает 422 или `{"detail":"audio_file is required"}`  
**Root Cause**: n8n HTTP Request не отправляет бинарный файл (нет Read Binary File или неверный inputDataFieldName)  
**Fix**:
1. Добавить ноду **Read Binary File** перед Whisper
2. В HTTP Request выставить `multipart-form-data`
3. Параметр `formBinaryData` → name: `audio_file`, inputDataFieldName: `data`

---

### E011: Whisper — контейнер падает (OOM)

**Symptom**: `whisper` контейнер перезапускается, в логах `Killed` или OOM  
**Root Cause**: Модель слишком тяжёлая для RAM VPS  
**Fix**:
1. Поменять `WHISPER_MODEL` на `small` или `medium`
2. Увеличить RAM VPS до 8–16 GB

---

### E012: Whisper — timeout при длинных файлах

**Symptom**: HTTP Request к Whisper падает по таймауту  
**Root Cause**: Длинный файл + слабый CPU или короткий timeout в ноде  
**Fix**:
1. Увеличить timeout в HTTP Request (например, 600000)
2. Использовать более лёгкую модель (`small`/`medium`)
3. При необходимости — разбить файл на части

---

### E013: open-notebook API возвращает 401

**Symptom**: `POST /sources` возвращает 401 Unauthorized  
**Root Cause**: Неверный Bearer token  
**Fix**: По умолчанию open-notebook использует `Authorization: Bearer password`. Проверить настройки аутентификации в open-notebook.

---

### E014: GLM-4 API timeout

**Symptom**: HTTP Request к GLM-4 падает по таймауту  
**Root Cause**: Длинный транскрипт (>50K tokens) или проблемы с API z.ai  
**Fix**:
1. Увеличить timeout в n8n HTTP Request node до 120 секунд
2. Если транскрипт >100K tokens — разбить на части
3. Попробовать fallback на GLM-4.7-Flash (бесплатный)

---

### E015: Telegram — "chat not found"

**Symptom**: Telegram sendMessage возвращает `{"ok": false, "description": "Bad Request: chat not found"}`  
**Root Cause**: Бот не добавлен в чат или неверный chat_id  
**Fix**:
1. Добавить бота в нужный чат
2. Получить правильный chat_id:
```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates"
# Найти chat.id в ответе
```

---

### E016: NFS mount dropped — recordings not detected

**Symptom**: Новые файлы в /mnt/recordings не обнаруживаются  
**Root Cause**: NFS mount отвалился  
**Fix**:
```bash
# Проверить mount
mountpoint /mnt/recordings

# Перемонтировать
mount -a

# Проверить автомонтирование в /etc/fstab
```

---

### E017: Duplicate processing — file transcribed twice

**Symptom**: Один и тот же файл транскрибируется повторно  
**Root Cause**: Запись в processed_files не была создана (или PostgreSQL был недоступен)  
**Fix**: Workflow должен СНАЧАЛА записать файл в PostgreSQL (status='transcribing'), ЗАТЕМ начинать обработку. Проверить порядок нод в Workflow 1.

---

*Document created: 2026-02-18 | Auto-updated by Living Documentation Protocol*
