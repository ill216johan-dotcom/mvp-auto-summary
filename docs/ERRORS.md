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

### ~~E010: Whisper — `audio_file is required`~~ (УСТАРЕЛО — Whisper не используется)

> ℹ️ Этот раздел относился к self-hosted Whisper STT. Проект использует **Яндекс SpeechKit**.

---

### ~~E011: Whisper — контейнер падает (OOM)~~ (УСТАРЕЛО — Whisper не используется)

> ℹ️ Этот раздел относился к self-hosted Whisper STT. Проект использует **Яндекс SpeechKit**.

---

### ~~E012: Whisper — timeout при длинных файлах~~ (УСТАРЕЛО — Whisper не используется)

> ℹ️ Этот раздел относился к self-hosted Whisper STT. Проект использует **Яндекс SpeechKit**.

---

### E010-NEW: SpeechKit — `401 Unauthorized` при запросе транскрипции

**Symptom**: POST к `transcribe.api.cloud.yandex.net` возвращает 401  
**Root Cause**: Неверный или просроченный YANDEX_API_KEY  
**Fix**:
1. Проверить ключ в Яндекс Облаке → IAM → Service Accounts
2. Создать новый API-ключ если старый просрочен
3. Обновить переменную окружения в docker-compose.yml

---

### E011-NEW: SpeechKit — операция зависла в статусе `RUNNING`

**Symptom**: Polling getOperation возвращает `done: false` бесконечно, транскрипция не завершается  
**Root Cause**: Яндекс SpeechKit перегружен или файл слишком большой  
**Диагностика**:
```bash
# Проверить статус вручную
curl -H "Authorization: Api-Key ВАШ_КЛЮЧ" \
  "https://operation.api.cloud.yandex.net/operations/OPERATION_ID"
```
**Fix**:
1. Подождать 10-15 минут — SpeechKit может медленно обрабатывать
2. Если операция висит >30 мин — удалить запись из processed_files и повторить
3. Для очень длинных файлов (>2 часа) — разбить на части

---

### E012-NEW: SpeechKit — `413 Request Entity Too Large` при загрузке в S3

**Symptom**: Загрузка файла в Яндекс Object Storage завершается с ошибкой 413  
**Root Cause**: Файл превышает лимиты однократной загрузки (5 GB для single-part)  
**Fix**: Использовать multipart upload для файлов >5 GB (редкий случай)

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

---

## Deployment Errors (обнаружены 2026-02-18 при первом запуске)

### E020: SurrealDB — `unexpected argument '--auth' found`

**Symptom**: SurrealDB перезапускается в цикле, в логах `error: unexpected argument '--auth' found`  
**Root Cause**: В SurrealDB v2.x флаг `--auth` убрали — аутентификация включена по умолчанию  
**Fix**: Убрать `--auth` из команды запуска в docker-compose.yml:
```yaml
# НЕПРАВИЛЬНО (v1.x синтаксис):
command: start --auth --user root --pass pass file:/data/srdb.db

# ПРАВИЛЬНО (v2.x синтаксис):
command: start --user root --pass pass surrealkv:/data/srdb.db
```
Также: `file:` заменён на `surrealkv:` в v2.x.

---

### E021: SurrealDB — `Permission denied (os error 13)` на volume

**Symptom**: SurrealDB стартует но сразу падает с `IO error: Permission denied`  
**Root Cause**: Docker volume создаётся с правами root, а процесс SurrealDB не имеет прав на запись  
**Fix**: Добавить `user: root` в секцию surrealdb в docker-compose.yml, либо вручную выставить права на volume:
```bash
docker compose stop surrealdb
docker volume rm mvp-auto-summary_surrealdb_data
docker volume create mvp-auto-summary_surrealdb_data
docker run --rm -v mvp-auto-summary_surrealdb_data:/data alpine chmod 777 /data
docker compose up -d surrealdb
```

---

### E022: n8n — "secure cookie" ошибка в браузере

**Symptom**: При открытии `http://IP:5678` браузер показывает:  
`Your n8n server is configured to use a secure cookie, however you are either visiting this via an insecure URL, or using Safari.`  
**Root Cause**: n8n по умолчанию требует HTTPS для cookies. При доступе по HTTP без домена — блокирует.  
**Fix**: Добавить переменную окружения в docker-compose.yml (в секцию environment n8n):
```yaml
- N8N_SECURE_COOKIE=false
```
Затем пересоздать контейнер:
```bash
docker compose up -d --force-recreate n8n
```
**Важно**: Добавлять именно в docker-compose.yml, а не только в .env — иначе может не применяться.

---

### E023: n8n API — `'X-N8N-API-KEY' header required` (401)

**Symptom**: Запросы к `/api/v1/*` возвращают 401 с сообщением `'X-N8N-API-KEY' header required`  
**Root Cause**: n8n Public API требует API Key, не Basic Auth. Ключ нужно создать через UI.  
**Fix**: 
1. Войти в n8n UI (`http://IP:5678`)
2. Меню → Settings → n8n API → **Create API Key**
3. Использовать в запросах: `-H "X-N8N-API-KEY: <ключ>"`

**Важно**: Попытка создать ключ напрямую через PostgreSQL INSERT не работает — n8n, по всей видимости, дополнительно обрабатывает ключ при создании через UI.

---

### E024: docker-compose.yml — предупреждение `version is obsolete`

**Symptom**: `WARN[0000] the attribute 'version' is obsolete, it will be ignored`  
**Root Cause**: В новых версиях Docker Compose поле `version:` убрали  
**Fix**: Удалить строку `version: '3.8'` из начала docker-compose.yml:
```bash
sed -i '/^version:/d' docker-compose.yml
```

---

### E025: n8n первый запуск — показывает форму регистрации вместо логина

**Symptom**: При первом открытии n8n просит ввести email, имя и пароль  
**Root Cause**: Это нормальное поведение — n8n создаёт первого пользователя  
**Fix**: Придумать и ввести любые данные:
- Email: `admin@mvp.local` (или любой)
- Имя: любое
- Пароль: тот же что в `.env` (`N8N_PASSWORD`)

После этого использовать эти же данные для входа.

---

---

### E026: n8n API — `POST method not allowed` для `/execute`

**Symptom**: `POST /api/v1/workflows/{id}/execute` возвращает `{"message":"POST method not allowed"}`  
**Root Cause**: В данной версии n8n этот endpoint не поддерживается через Public API  
**Fix**: Запускать workflow вручную через UI (кнопка ▶ Execute workflow) или ждать триггера по расписанию. Workflow 01 запускается автоматически каждые 5 минут.

---

### E027: n8n API — credential создание требует `ssl` как строку

**Symptom**: POST `/api/v1/credentials` возвращает длинную ошибку про `sshAuthenticateWith`, `sshHost` и т.д.  
**Root Cause**: n8n API ожидает `ssl` как строку (`"disable"`, `"allow"`, `"require"`), а не boolean `false`  
**Fix**:
```json
{"name":"PostgreSQL","type":"postgres","data":{"host":"postgres","port":5432,"database":"n8n","user":"n8n","password":"...","ssl":"disable","sshTunnel":false}}
```

---

### E028: n8n API — импорт workflow с лишними полями

**Symptom**: POST `/api/v1/workflows` возвращает `"request/body must NOT have additional properties"`  
**Root Cause**: n8n API принимает только `name`, `nodes`, `connections`, `settings` — остальные поля (tags, staticData, triggerCount и др.) отклоняются  
**Fix**: Перед импортом очистить JSON:
```bash
python3 -c "
import sys, json
wf = json.load(sys.stdin)
clean = {'name': wf.get('name'), 'nodes': wf.get('nodes'), 'connections': wf.get('connections'), 'settings': wf.get('settings', {})}
print(json.dumps(clean))
" < workflow.json > workflow_clean.json
```

---

### E029: 02-daily-digest.json — невалидный JSON escape

**Symptom**: `json.decoder.JSONDecodeError: Invalid \escape: line 67`  
**Root Cause**: В jsonBody строке были `\'` (экранированные одиночные кавычки) — невалидный escape в JSON  
**Fix**: Убрать `\'` → заменить на обычный текст без кавычек. В файле исправлено: `\'Нет\'` → `Нет`

---

### E030: Telegram бот не получает сообщения из группы

**Symptom**: `getUpdates` возвращает `{"ok":true,"result":[]}` после добавления бота в группу  
**Root Cause**: Бот создан с `can_read_all_group_messages: false` — по умолчанию боты не читают все сообщения группы, только те где их упомянули или команды (`/cmd`)  
**Гипотезы и решения**:
1. **Упомянуть бота**: написать `@ffp_report_bot тест` в группе — бот увидит сообщение с упоминанием
2. **Включить Group Privacy mode OFF**: через @BotFather → выбрать бота → Bot Settings → Group Privacy → Turn off. После этого бот будет видеть все сообщения группы
3. **Использовать getUpdates после отправки**: getUpdates работает только если сообщение пришло ПОСЛЕ последнего вызова getUpdates (или добавить `offset=0`)
4. **Проверить что бот добавлен именно в нужную группу**: команда `getMe` показала имя `@ffp_report_bot` — убедиться что добавлен именно этот бот

**Правильный порядок действий**:
```
1. @BotFather → /mybots → @ffp_report_bot → Bot Settings → Group Privacy → Disable
2. Удалить бота из группы и добавить снова
3. Написать в группе любое сообщение
4. curl "https://api.telegram.org/bot{TOKEN}/getUpdates"
```

---

### E031: n8n workflow execution — status `canceled`, lastNode `None`

**Symptom**: Execution завершается со статусом `canceled`, `lastNode: None`, `error: {}`  
**Root Cause**: Workflow запущен вручную через UI кнопку Stop или execution был отменён до начала работы. Также может означать что `/recordings` папка пуста или файлы не найдены командой `find`  
**Диагностика**:
```bash
# Проверить что n8n видит файлы
docker exec mvp-auto-summary-n8n-1 find /recordings -type f -name "*.wav" -o -name "*.mp3" -o -name "*.webm"
```
**Fix**: Убедиться что файл существует внутри контейнера, затем запустить workflow заново (не нажимать Stop).

---

---

### E032: n8n IF нода — `Unknown filter parameter operator "boolean:notTrue"`

**Symptom**: Workflow останавливается на IF ноде сразу, в логах `Unknown filter parameter operator "boolean:notTrue"`  
**Root Cause**: n8n 2.8.x не поддерживает оператор `notTrue` в IF нодах  
**Fix**: Заменить оператор на `equal` и поменять местами TRUE/FALSE ветки в connections:
```json
// БЫЛО (не работает в 2.8.x):
"operator": { "type": "boolean", "operation": "notTrue" }
// СТАЛО:
"operator": { "type": "boolean", "operation": "equal" }
```
В connections поменять `[[{node: "Next"}], []]` на `[[], [{node: "Next"}]]`

---

### E033: n8n workflow — `status: success, lastNode: None` (файл уже обработан)

**Symptom**: Workflow выполняется успешно но ничего не делает — `lastNode: None`  
**Root Cause**: Файл уже есть в таблице `processed_files` — нода "Is New File?" пропускает его  
**Диагностика**:
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT filename, status FROM processed_files;"
```
**Fix**: Создать новый тестовый файл с другим именем или очистить таблицу:
```bash
# Новый файл:
cp /mnt/recordings/2026/02/18/99999_2026-02-18_14-30.wav \
   /mnt/recordings/2026/02/18/12345_2026-02-18_15-00.wav
# Или очистить processed_files:
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "DELETE FROM processed_files;"
```

---

### E034: n8n — `EXECUTIONS_TIMEOUT overflow` (TimeoutOverflowWarning)

**Symptom**: В логах n8n: `TimeoutOverflowWarning: 3600000000 does not fit into a 32-bit signed integer. Timeout duration was set to 1.` Workflows завершаются мгновенно.  
**Root Cause**: `EXECUTIONS_TIMEOUT` задан в миллисекундах (3600000), но n8n 2.x ожидает значение в **секундах**  
**Fix**: Исправить в docker-compose.yml:
```yaml
# БЫЛО (миллисекунды — слишком большое число):
- EXECUTIONS_TIMEOUT=3600000
- EXECUTIONS_TIMEOUT_MAX=7200000
# СТАЛО (секунды):
- EXECUTIONS_TIMEOUT=1800
- EXECUTIONS_TIMEOUT_MAX=3600
```
Затем: `docker compose up -d --force-recreate n8n`

---

---

### E035: open-notebook — `TimeoutError: timed out during opening handshake` (неверные имена env-переменных)

**НАСТОЯЩАЯ ПРИЧИНА** (найдена 2026-02-18): open-notebook ожидает `SURREAL_URL` и `SURREAL_PASSWORD`, а в docker-compose.yml были прописаны `SURREAL_ADDRESS` и `SURREAL_PASS` — из-за этого приложение не получало адрес БД и падало.

**Дополнительно**: образ `surrealdb:latest` может быть v3, который несовместим с open-notebook. Нужно пиновать `v2`.

**Симптом**: В логах open-notebook:

**Symptom**: В логах open-notebook:
```
TimeoutError: timed out during opening handshake
WARN exited: worker (exit status 1; not expected)
INFO spawned: 'worker' with pid XXXXX
```
Контейнер циклично перезапускает воркеры. В n8n нода "Get Notebooks" / "Save Transcript to Notebook" возвращает ошибку. В processed_files запись имеет `status='error'`.

**Root Cause**: Неверные имена переменных окружения в docker-compose.yml:

| Неправильно (не работает) | Правильно |
|---------------------------|-----------|
| `SURREAL_ADDRESS=ws://...` | `SURREAL_URL=ws://surrealdb:8000/rpc` |
| `SURREAL_PASS=...` | `SURREAL_PASSWORD=...` |

open-notebook читает только `SURREAL_URL` и `SURREAL_PASSWORD`. При неверных именах переменная не передаётся в приложение, WebSocket открывается с пустым/дефолтным URL и немедленно падает.

**Дополнительная причина 1**: `surrealdb:latest` может подтянуть v3, несовместимую с open-notebook (которая рассчитана на v2).

**Дополнительная причина 2**: volume `surrealdb_data` создан образом с uid `65532`, а контейнер запущен с `user: root` — конфликт прав приводит к `read only transaction` при попытке писать в БД. Решается пересозданием volume с правильными правами (или удалением старого volume и пересозданием).

**Диагностика**:
```bash
# Проверить что именно получает open-notebook
docker exec mvp-auto-summary-open-notebook-1 env | grep -i surreal
# Если видишь SURREAL_ADDRESS вместо SURREAL_URL — это и есть причина

# Проверить что SurrealDB работает в read-write режиме
python3 -c "
import urllib.request, base64
creds = base64.b64encode(b'root:ПАРОЛЬ').decode()
req = urllib.request.Request('http://localhost:8000/sql',
  data=b'INFO FOR DB;',
  headers={'Authorization': 'Basic '+creds, 'surreal-ns':'open_notebook',
           'surreal-db':'open_notebook', 'Content-Type':'application/json'})
print(urllib.request.urlopen(req, timeout=5).read().decode())
"
# Если видишь "read only transaction" — SurrealDB запущен неправильно
```

**Fix**: Исправить docker-compose.yml:
```yaml
# НЕПРАВИЛЬНО:
environment:
  - SURREAL_ADDRESS=ws://surrealdb:8000/rpc   # ← неверное имя!
  - SURREAL_PASS=${SURREAL_PASSWORD}            # ← неверное имя!

# ПРАВИЛЬНО:
environment:
  - SURREAL_URL=ws://surrealdb:8000/rpc        # ← правильное имя
  - SURREAL_PASSWORD=${SURREAL_PASSWORD}        # ← правильное имя
```

Также пиновать версии:
```yaml
surrealdb:
  image: surrealdb/surrealdb:v2        # не latest!

open-notebook:
  image: lfnovo/open_notebook:v1-latest  # не latest!
```

После исправления:
```bash
docker compose up -d --force-recreate surrealdb open-notebook
sleep 40
docker compose logs open-notebook --tail=8
# Должно быть: "success: worker entered RUNNING state" — стабильно, без "exited"
```

---

### ~~E036: Тестовый WAV из случайного шума — Whisper возвращает пустой текст~~ (УСТАРЕЛО — Whisper не используется)

> ℹ️ Этот раздел относился к self-hosted Whisper STT. Проект использует **Яндекс SpeechKit**.
>
> Актуальная ситуация для SpeechKit: если передать файл без речи, SpeechKit вернёт пустой массив chunks. Нода Extract Transcript получит пустую строку → нода "Has Transcript?" направит в "Mark Error". Это ожидаемое поведение, не баг.
>
> Для реального теста используйте реальные WebM-файлы созвонов из `/mnt/recordings/`.

---

### E037: processed_files — файл застрял в статусе `error` или `transcribing`

**Symptom**: Повторный запуск workflow пропускает файл — он уже есть в processed_files. Файл не обрабатывается заново.

**Root Cause**: Нода "Is New File?" проверяет наличие записи в processed_files. Если запись есть (в любом статусе) — файл считается обработанным.

**Диагностика**:
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT filename, status, summary_sent, created_at FROM processed_files ORDER BY created_at DESC LIMIT 10;"
```

**Fix (сброс конкретного файла)**:
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "DELETE FROM processed_files WHERE filename = '77777_2026-02-18_17-30.wav';"
```

**Fix (полная очистка для тестирования)**:
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "DELETE FROM processed_files;"
```
После этого запустить Workflow 01 вручную через n8n UI.

---

### E038: n8n — `/recordings` внутри контейнера read-only

**Symptom**: При попытке создать файл внутри контейнера n8n: `EROFS: read-only file system, open '/recordings/...'`

**Root Cause**: В docker-compose.yml папка `/recordings` монтируется с флагом `:ro` (read-only):
```yaml
- /mnt/recordings:/recordings:ro
```
Это сделано намеренно — n8n только читает файлы, не модифицирует.

**Fix**: Создавать тестовые файлы НА СЕРВЕРЕ (не внутри контейнера):
```bash
# ПРАВИЛЬНО — на хосте:
mkdir -p /mnt/recordings/2026/02/18
dd if=/dev/urandom bs=96000 count=1 > /mnt/recordings/2026/02/18/77777_2026-02-18_17-30.wav

# НЕПРАВИЛЬНО — внутри контейнера:
docker exec mvp-auto-summary-n8n-1 node -e "fs.writeFileSync('/recordings/...')" # → EROFS
```

---

### E039: python3 не найден в контейнере n8n

**Symptom**: `sh: python3: not found` при попытке запустить Python внутри n8n контейнера.

**Root Cause**: Образ `n8nio/n8n:latest` основан на Node.js Alpine — Python не установлен.

**Fix**: Использовать Node.js (он есть в контейнере):
```bash
docker exec mvp-auto-summary-n8n-1 node -e "console.log('works')"
```
Для создания файлов — использовать хост или bash-команды.

---

### E040: curl не найден в контейнере open-notebook

**Symptom**: `OCI runtime exec failed: exec failed: unable to start container process: exec: "curl": executable file not found in $PATH`

**Root Cause**: Контейнер `lfnovo/open_notebook` не включает curl.

**Fix**: Использовать wget:
```bash
docker exec mvp-auto-summary-open-notebook-1 wget -qO- http://surrealdb:8000/health
```

---

### E041: GLM-4 API — `Insufficient balance` (код 1113)

**Symptom**: HTTP Request к `api.z.ai` или `open.bigmodel.cn` возвращает:
```json
{"error":{"code":"1113","message":"Insufficient balance or no resource package. Please recharge."}}
```

**Root Cause**: На API-аккаунте ZhipuAI закончились кредиты. **Важно**: GLM-4.7 в веб-интерфейсе (chat.z.ai) — это отдельный продукт, он не связан с API-балансом. Можно пользоваться веб-версией при нулевом API-балансе.

**Диагностика** (проверить конкретный ключ):
```bash
curl -s -X POST https://open.bigmodel.cn/api/paas/v4/chat/completions \
  -H "Authorization: Bearer ВАШ_КЛЮЧ" \
  -H "Content-Type: application/json" \
  -d '{"model":"glm-4.7-flash","messages":[{"role":"user","content":"Hi"}],"max_tokens":5}'
```
- `{"choices":[...]}` → ключ работает ✅
- `{"error":{"code":"1113",...}}` → нет баланса ❌
- `{"error":{"code":"1211",...}}` → модель не существует (попробовать другое имя)

**Рабочие имена моделей** на `open.bigmodel.cn`:
- `glm-4.7-flash` ✅ — бесплатная квота
- `glm-4.7-flashx` — платная
- `glm-4.7` — платная, высокое качество

**Fix**:
1. Найти рабочий ключ: перебрать все ключи curl-командой выше
2. В n8n обновить ноду GLM-4 Summarize:
   - URL: `https://open.bigmodel.cn/api/paas/v4/chat/completions`
   - Authorization: `Bearer РАБОЧИЙ_КЛЮЧ`
   - model в jsonBody: `glm-4.7-flash`

---

### E042: n8n — `access to env vars denied` в ноде Telegram

**Symptom**: Workflow 02 падает на ноде "Send Telegram":
```
Problem in node 'Send Telegram'
access to env vars denied
```

**Root Cause**: n8n 2.x с External Runners блокирует `$env` в expressions. Переменные `$env.TELEGRAM_BOT_TOKEN` и `$env.TELEGRAM_CHAT_ID` недоступны при ручном или автоматическом запуске.

**Затронутые ноды**: любая нода с `$env.*` в expressions:
- URL: `={{ 'https://api.telegram.org/bot' + $env.TELEGRAM_BOT_TOKEN + '/sendMessage' }}`
- jsonBody: `={{ JSON.stringify({ chat_id: $env.TELEGRAM_CHAT_ID, ... }) }}`

**Fix**: Заменить `$env.*` на хардкодированные значения:
- URL: тип "Fixed" → `https://api.telegram.org/botТОКЕН/sendMessage`
- `chat_id` в jsonBody: заменить `$env.TELEGRAM_CHAT_ID` на числовое значение

**Получить значения** (если не знаешь):
```bash
# На сервере (через PuTTY):
grep -i telegram /root/mvp-auto-summary/.env
```

**Долгосрочное решение**: Использовать n8n Credentials (тип "Generic Credential") для хранения токенов вместо env vars.

---

### E043: GLM-4.7-Flash возвращает пустой `content` (thinking-модель)

**Symptom**: Workflow 02 выполняется успешно, GLM-4 возвращает ответ, но в Telegram приходит:
```
Ежедневный дайджест за 19.02.2026
Встреч: 3
Клиенты: LEAD-101, LEAD-102, LEAD-103

Сводка не получена.
```

При этом в execution видно, что `message.content` пустой, а `message.reasoning_content` содержит длинный текст ("Analyze the Request...", "Draft 1...", "Draft 2..." и т.д.).

**Root Cause**: Модель `glm-4.7-flash` — это **thinking-модель** (модель с цепочкой рассуждений). По умолчанию она:
1. Пишет ход рассуждений в поле `reasoning_content`
2. Пишет финальный ответ в поле `content`
3. Иногда `content` остаётся пустым — весь ответ в `reasoning_content`

Нода Build Digest читала только `content` → пусто → "Сводка не получена".

**Доказательство** (официальная документация ZhipuAI):
- Документация Thinking Mode: https://docs.z.ai/guides/capabilities/thinking-mode
- GLM-4.5 и выше (включая GLM-4.7-Flash) по умолчанию включают thinking mode
- Поле `reasoning_content` появляется только у thinking-моделей

**Fix (рекомендуется)**: Отключить thinking mode в запросе:
```json
{
  "model": "glm-4.7-flash",
  "messages": [...],
  "temperature": 0.2,
  "max_tokens": 1400,
  "stream": false,
  "thinking": { "type": "disabled" }
}
```

В n8n нода GLM-4 Summarize → jsonBody (Expression):
```javascript
={{ JSON.stringify({ 
  model: 'glm-4.7-flash', 
  messages: [...], 
  temperature: 0.2, 
  max_tokens: 1400, 
  stream: false, 
  thinking: { type: "disabled" } 
}) }}
```

**Fallback (дополнительная защита)**: Обновить ноду Build Digest:
```javascript
const msg = $json.choices && $json.choices[0] && $json.choices[0].message ? $json.choices[0].message : {};
const rawContent = (msg.content || '').trim();
const rawReasoning = (msg.reasoning_content || '').trim();
const summaryText = rawContent || rawReasoning || 'Сводка не получена.';
```

**Проверка после фикса**:
```bash
curl -s -X POST https://open.bigmodel.cn/api/paas/v4/chat/completions \
  -H "Authorization: Bearer ВАШ_КЛЮЧ" \
  -H "Content-Type: application/json" \
  -d '{"model":"glm-4.7-flash","messages":[{"role":"user","content":"Привет"}],"max_tokens":50,"thinking":{"type":"disabled"}}'
```
Ожидается: `content` заполнен, `reasoning_content` пустой или отсутствует.

---

### E044: Workflow 02 останавливается на Load Today's Transcripts

**Symptom**: Workflow 02 выполняется, но последняя зелёная нода — "Load Today's Transcripts". Дальше workflow не идёт.

**Root Cause**: SQL запрос возвращает 0 строк. Возможные причины:

1. **`summary_sent = true`** — записи уже обработаны предыдущим запуском
2. **`transcript_text IS NULL`** — нет текста транскрипта
3. **Дата не совпадает** — view `v_today_completed` фильтрует по текущей дате

**Диагностика**:
```bash
# Проверить данные в view
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT * FROM v_today_completed LIMIT 5;"

# Проверить фильтр summary_sent
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT id, summary_sent, transcript_text IS NOT NULL as has_text FROM processed_files WHERE status='completed' ORDER BY id DESC LIMIT 10;"
```

**Fix**:
```bash
# Сбросить summary_sent для повторной обработки
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "UPDATE processed_files SET summary_sent = false WHERE id IN (18, 19, 20);"
```

**Fix (создать тестовые данные)**:
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "INSERT INTO processed_files (filename, filepath, lead_id, status, summary_sent, transcript_text, created_at) VALUES ('TEST101_2026-02-19.wav', '/recordings/TEST101.wav', 101, 'completed', false, 'Текст транскрипта...', NOW());"
```

**Важно**: Поле `filepath` обязательное (NOT NULL constraint).

---

### E045: INSERT в processed_files — null value in column "filepath"

**Symptom**:
```
ERROR: null value in column "filepath" of relation "processed_files" violates not-null constraint
```

**Root Cause**: Таблица `processed_files` имеет обязательное поле `filepath`. При INSERT без указания filepath — ошибка.

**Fix**: Всегда указывать filepath:
```bash
# НЕПРАВИЛЬНО:
INSERT INTO processed_files (filename, lead_id, status, ...) VALUES (...);

# ПРАВИЛЬНО:
INSERT INTO processed_files (filename, filepath, lead_id, status, ...) VALUES ('test.wav', '/recordings/test.wav', ...);
```

---

---

### E046: Save Success? всегда FALSE — неправильная проверка undefined

**Symptom**: Workflow 01 останавливается на ноде "Mark Notebook Error" даже когда open-notebook успешно сохранил транскрипт.

**Root Cause**: Нода `Save Success?` проверяет `$json.error == ""`. Но при успешном ответе open-notebook поле `error` отсутствует — `$json.error` возвращает `undefined`. В JavaScript `undefined == ""` — это `false`, поэтому workflow идёт в FALSE ветку.

**Диагностика**:
```bash
# Проверить что open-notebook возвращает успешный ответ
docker logs mvp-auto-summary-open-notebook-1 --tail=50
```

**Fix**: Изменить условие в ноде `Save Success?`:
```javascript
// БЫЛО (неправильно):
leftValue: "={{ $json.error }}"
operator: "equals"
rightValue: ""

// СТАЛО (правильно):
leftValue: "={{ $json.id || $json.source_id || $json.command_id }}"
operator: "notEmpty"
```

Проверяем наличие `id` в ответе — признак успешного создания source.

---

### E047: 404 Not Found при сохранении в open-notebook

**Symptom**: Нода "Save Transcript to Notebook" возвращает 404:
```
"message": "404 - \"{\"detail\":\"Not Found\"}\""
```

**Root Cause**: Неправильный URL endpoint'а. Было несколько вариантов:
- `/api/sources/{notebookId}/entries` — НЕ СУЩЕСТВУЕТ
- `/api/sources//entries` — НЕ СУЩЕСТВУЕТ (пустой notebookId)
- `/api/sources/json` — ПРАВИЛЬНЫЙ

**Правильный URL**:
```
http://open-notebook:5055/api/sources/json
```

**Важно:** Порт 5055 — это внутренний порт API контейнера. Порт 8888 — это Web UI.

**Fix**: В ноде "Save Transcript to Notebook":
1. URL: `http://open-notebook:5055/api/sources/json` (Fixed, не Expression!)
2. Body: Expression с `JSON.stringify({...})`

---

### E048: "JSON parameter needs to be valid JSON"

**Symptom**: Нода возвращает ошибку:
```
"error": "JSON parameter needs to be valid JSON"
```

**Root Cause**: В n8n поле JSON Body заполнено как plain JSON, но содержит выражения `{{ ... }}`. n8n не может их распарсить.

**Fix**: Переключить JSON Body в режим **Expression** и использовать `JSON.stringify()`:
```javascript
{{ JSON.stringify({ 
  notebooks: [$json.notebookId], 
  type: "text", 
  content: $('Extract Transcript').first().json.transcript 
}) }}
```

---

### E049: Workflow не обновляется после копирования файла

**Symptom**: Копируешь `.json` файл через WinSCP, но workflow в n8n не меняется.

**Root Cause**: n8n хранит workflows в PostgreSQL, НЕ в файлах! Копирование файла на диск ничего не даёт.

**Fix**: Обновлять workflow через n8n UI:
1. Открыть workflow
2. **⋮** → Import from File
3. Или редактировать ноды вручную
4. **Save!**

**См. также:** `docs/N8N_WORKFLOW_UPDATE.md`

---

### E050: "Wrong type: ... is an object but was expecting a string"

**Symptom**: IF нода падает с ошибкой типа:
```
Wrong type: 'AxiosError: 404...' is an object but was expecting a string
```

**Root Cause**: При ошибке HTTP запроса n8n возвращает объект ошибки в поле `error`. IF нода пытается сравнить его как строку.

**Fix**: Проверять наличие `id` через `.length`:
```javascript
// НЕПРАВИЛЬНО:
leftValue: "={{ $json.id }}"
operator: "notEmpty"  // ошибка если $json.error — объект!

// ПРАВИЛЬНО:
leftValue: "={{ ($json.id || '').length }}"
operator: "gt"
rightValue: 0
```

---

---

### E051: SpeechKit — chunks пустые, транскрипт пустой

**Symptom**: Workflow 01 завершается с `status='error'`, в логах видно что SpeechKit вернул `done: true` но текст пустой.

**Root Cause**: Файл содержит только тишину, фоновый шум или нераспознанную речь.

**Диагностика**:
```bash
# Проверить что файл содержит речь (должна быть ненулевая длина)
docker exec mvp-auto-summary-n8n-1 ls -la /recordings/2026/02/20/
```

**Fix**: Использовать реальные записи созвонов. Workflow корректно обрабатывает этот случай — помечает файл как error и не добавляет в дайджест.

---

### E052: Дублирующиеся ноутбуки в open-notebook для одного LEAD_ID

**Symptom**: В open-notebook UI видно несколько ноутбуков с одинаковым именем `LEAD-XXXXXX`.

**Root Cause**: Нода "Find Client Notebook" использовала `$input.first()` вместо `$input.all()`. При каждом запуске создавала новый ноутбук вместо поиска существующего.

**Fix** (уже исправлено в WF01):
```javascript
// БЫЛО (неправильно):
const notebooks = $input.first().json;

// СТАЛО (правильно):
const allNotebooks = $input.all();
const notebooks = allNotebooks.map(item => item.json);
```

**Если дубликаты уже созданы**: удалить лишние ноутбуки вручную через open-notebook UI (`http://84.252.100.93:8888`).

---

### E053: open-notebook UI — красная плашка "Ключ шифрования не настроен"

**Symptom**: При открытии `http://84.252.100.93:8888` в верхней части UI красная плашка с предупреждением о ключе шифрования.

**Root Cause**: Переменная `OPEN_NOTEBOOK_ENCRYPTION_KEY` не задана в docker-compose.yml.

**Fix** (уже применено):
```yaml
# В docker-compose.yml, секция open-notebook environment:
- OPEN_NOTEBOOK_ENCRYPTION_KEY=a4f9fe1e61e6464b2f020d235f1d78548912503d767ccb2e797c744661852796
```
После добавления: `docker compose up -d --force-recreate open-notebook`

---

*Document created: 2026-02-18 | Updated: 2026-02-22 — E010-E012 помечены как устаревшие (Whisper→SpeechKit), E036 помечен устаревшим, добавлены E051-E053 (SpeechKit, дубликаты ноутбуков, encryption key)*
