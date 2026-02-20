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

### E036: Тестовый WAV из случайного шума — Whisper возвращает пустой текст или музыку

**Symptom**: Workflow 01 выполняется успешно (Mark Completed), но в open-notebook транскрипт пустой или содержит `[СПОКОЙНАЯ МУЗЫКА]` / `[Тихая музыка]`.

**Root Cause**: Тестовый файл создан из `/dev/urandom` или синусоиды — это не речь. Whisper правильно распознаёт что речи нет.

**Fix**: Для полноценного теста pipeline нужен файл с реальной речью:
```bash
# На сервере — скачать тестовый файл с речью на русском
mkdir -p /mnt/recordings/2026/02/18
cd /tmp
wget -q "https://www2.cs.uic.edu/~i101/SoundFiles/gettysburg10.wav" -O test_speech.wav 2>/dev/null || \
  dd if=/dev/urandom bs=96000 count=1 > /mnt/recordings/2026/02/18/88888_2026-02-18_10-00.wav
```
Или использовать реальную запись созвона.

**Важно**: Даже с пустым транскриптом pipeline работает корректно — нода "Has Transcript?" проверяет наличие текста и направляет в "Mark Error" при пустом результате. Это ожидаемое поведение, не баг.

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

### E046: Файл с нестандартным именем пропускается workflow

**Symptom**: Загрузил файл в `/mnt/recordings/`, но workflow 01 его не обрабатывает.

**Root Cause**: Имя файла не начинается с цифр — система не может определить LEAD_ID.

**Fix**: Переименовать файл — добавить ID клиента в начало:
```
# НЕПРАВИЛЬНО (нет цифр в начале):
разговор_с_клиентом.mp3
митинг_101.wav

# ПРАВИЛЬНО (любые цифры в начале, дальше — что угодно):
101_разговор_с_клиентом.mp3
101_митинг.wav
101_2026-02-20_10-30.mp3   ← строгий формат (опционально)
```

Workflow 01 обновлён (2026-02-20): поддерживает форматы `101_`, `101-`, `101.` в начале имени.

---

---

## Ошибки Telegram (авторизация и выгрузка чатов)

> **Контекст:** Для выгрузки истории чатов используется библиотека Telethon.
> Она работает от имени ЛИЧНОГО аккаунта (не бота) — только так можно читать старую историю переписки.
> Нужен ОДИН рабочий Telegram-аккаунт у которого есть доступ ко всем нужным чатам.
> Приложение (api_id/api_hash) создаётся один раз на my.telegram.org/apps.

---

### E047: SMS-код при авторизации Telethon не приходит

**Symptom**: Запустил скрипт, ввёл номер телефона — код в Telegram не пришёл ни с +7, ни с 8, ни через VPN.

**Root Cause**: Telegram блокирует запросы с незнакомых IP (серверы, VPN, новые устройства). Код уходит в "незавершённые попытки" вместо доставки.

**Fix**: Использовать вход через QR-код:
```
python list_telegram_chats.py → выбрать 1 (QR)
Telegram на телефоне: Настройки → Устройства → Подключить устройство → навести камеру
```
QR-вход не зависит от IP и не требует SMS.

---

### E048: QR отсканирован ("успешно" в Telegram), но скрипт не реагирует и пишет "Не удалось войти"

**Symptom**: Telegram на телефоне пишет "успешно", но PowerShell продолжает ждать и в итоге завершается с ошибкой.

**Root Cause**: Старая версия скрипта (до 2026-02-20) проверяла авторизацию через `get_me()` в цикле — это не работает с QR. Нужен `qr_login.wait()`.

**Fix**: Обновить скрипт до актуальной версии. Текущая версия `list_telegram_chats.py` содержит `await qr_login.wait(timeout=120)` и работает корректно.

---

### E049: После QR в PowerShell запрашивает пароль, в Telegram приходит "Незавершённая попытка входа"

**Symptom**: QR отсканирован, Telegram говорит "успешно", но скрипт просит ввести пароль. В Telegram приходит уведомление про незавершённую попытку с устройства "mvpsummary, Vienna, Austria".

**Root Cause**: На аккаунте включена двухэтапная проверка (облачный пароль). Это ОТДЕЛЬНЫЙ пароль — не код из SMS. Уведомление про "незавершённую попытку" приходит именно в этот момент — это нормально, это не взлом.

**Fix**: Ввести облачный пароль в PowerShell когда скрипт его запросит.

**Где посмотреть/сбросить пароль**: Telegram → Настройки → Конфиденциальность → Двухэтапная проверка.

**Если пароль забыт**: там же → "Забыл пароль" → сброс через привязанный email.

---

### E050: Нужно собирать чаты у 5+ менеджеров — нужно ли 5 приложений?

**Вопрос**: У нас несколько менеджеров, у каждого свои чаты с клиентами. Нужно ли каждому создавать своё приложение на my.telegram.org?

**Ответ: НЕТ. Достаточно одного аккаунта и одного приложения.**

**Правильная схема:**
```
Один рабочий Telegram-аккаунт (общий, не личный)
    ├── Добавлен во все групповые чаты с клиентами
    ├── Авторизован в скрипте ОДИН РАЗ
    └── Файл mvp_session.session лежит на сервере и работает вечно
```

**Что нужно сделать:**
1. Завести один общий рабочий Telegram-аккаунт (или использовать аккаунт руководителя)
2. Добавить этот аккаунт во все группы с клиентами (менеджеры должны добавить его)
3. Создать приложение на my.telegram.org/apps под этим аккаунтом
4. Авторизоваться один раз на компьютере → скопировать `mvp_session.session` на сервер

**Личный аккаунт НЕ рекомендуется** — риск случайной блокировки и личная переписка попадёт в систему.

---

### E051: Пошаговая инструкция — получить api_id и api_hash

1. Открыть **https://my.telegram.org/apps** в браузере
2. Ввести номер телефона аккаунта в формате `+79161234567` → нажать Next
3. В Telegram придёт код подтверждения (в само приложение, не SMS) → ввести на сайте
4. Заполнить форму:

| Поле | Что вписать |
|------|-------------|
| App title | `MVP Auto-Summary` |
| Short name | `mvpsummary` |
| URL | оставить пустым |
| Platform | Desktop |
| Description | оставить пустым |

5. Нажать "Create application"
6. Скопировать **App api_id** (число, например `32782815`) и **App api_hash** (строка 32 символа)

**Хранить в `.env` файле, не публиковать в git.**

**Текущие credentials проекта** (рабочий аккаунт, авторизован 2026-02-20):
```
TELEGRAM_API_ID=32782815
TELEGRAM_API_HASH=a4c241e64433835b4a335b62520ab005
```
Файл сессии: `/root/mvp-auto-summary/scripts/mvp_session.session`

---

### E052: Что такое файл mvp_session.session и зачем его копировать на сервер

**Что это**: После первой авторизации Telethon сохраняет сессию в файл `.session` — как куки в браузере. Позволяет не вводить пароль при каждом запуске скрипта.

**Где создаётся**: В папке где запускался скрипт.
- На Windows: `C:\Users\dev\mvp-autosummary\scripts\mvp_session.session`
- На сервере: `/root/mvp-auto-summary/scripts/mvp_session.session`

**Что делать:**
1. Запустить `list_telegram_chats.py` на своём компьютере → пройти авторизацию
2. Через WinSCP скопировать файл на сервер:
   - Откуда: `C:\Users\dev\mvp-autosummary\scripts\mvp_session.session`
   - Куда: `/root/mvp-auto-summary/scripts/mvp_session.session`
3. Все последующие запуски скриптов на сервере работают автоматически

**Если файл устарел или слетел**: просто авторизоваться заново на компьютере и скопировать новый файл.

---

### E053: Таблица lead_chat_mapping — как связать договор с чатом

**Что это**: Таблица в PostgreSQL где хранится соответствие "номер договора ↔ Telegram чат". Заполняется вручную один раз, потом используется для автоматической ежедневной выгрузки всех чатов.

**Структура:**
```sql
lead_id       — номер договора (например '101')
lead_name     — название клиента ('ООО Ромашка')
chat_id       — числовой ID чата в Telegram (например -1009876543210)
chat_username — @username группы если есть
chat_title    — название чата как в Telegram
chat_type     — 'group', 'supergroup', 'private'
```

**Как получить chat_id**: запустить `python list_telegram_chats.py` — выведет список всех чатов с их ID.

**Как добавить запись** (в PuTTY на сервере):
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "
INSERT INTO lead_chat_mapping (lead_id, lead_name, chat_id, chat_title, chat_type)
VALUES ('101', 'ООО Ромашка', -1009876543210, 'ООО Ромашка поставки', 'supergroup');
"
```

**Как посмотреть что уже есть:**
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT * FROM lead_chat_mapping;"
```

**Когда таблица заполнена** — можно запустить выгрузку сразу всех чатов одной командой:
```bash
python export_all_chats.py  # (скрипт будет создан после тестирования)
```

---

### E054: export_telegram_chat.py — "Cannot find any entity corresponding to"

**Symptom**:
```
ОШИБКА: Cannot find any entity corresponding to "-4796144277"
```

**Root Cause**: Telethon не может найти чат по числовому ID через `get_entity()` напрямую — это работает только если сущность уже есть в локальном кэше сессии.

**Fix**: Скрипт обновлён (2026-02-20) — теперь при неудаче `get_entity()` автоматически ищет чат через перебор `iter_dialogs()`. Это всегда работает для чатов в которых состоит аккаунт.

Если всё равно не находит — значит аккаунт не состоит в этом чате. Проверить через `list_telegram_chats.py`.

---

### E055: Workflow 01 — нода переименована при импорте (Mark as Transcribing1)

**Symptom**: При запуске workflow ошибка `Invalid expression` в ноде `Mark as Transcribing1`.

**Root Cause**: При импорте нового workflow в n8n существовал старый workflow с такой же нодой. n8n переименовал ноду добавив цифру (`1`), из-за чего сломались references в expressions других нод.

**Fix**: Удалить старый workflow перед импортом нового:
1. n8n UI → Workflows → найти старый Workflow 01 → три точки → Delete
2. Затем импортировать новый JSON заново

---

### E056: Workflow 01 — файлы зависают в статусе `transcribing` из-за медленного Whisper

**Symptom**: Файлы попадают в `transcribing`, Whisper CPU 40-50% (он работает), но n8n execution таймаутится раньше чем Whisper заканчивает.

**Root Cause**: Файлы Jitsi/Jibri большие (47–978MB). Whisper модель `medium` на CPU работает в ~1.5x реального времени:
- `4590-фф.webm` (47MB, 22 мин) → ~33 минуты транскрипции
- `2239-фф.webm` (414MB, 41 мин) → ~62 минуты — превышает таймаут n8n (30 мин)

**Ключевое открытие**: webm → ogg конвертация через ffmpeg уменьшает файл в 10x (47MB → 4.9MB), но не ускоряет транскрипцию — размер файла ≠ время обработки. Время зависит от длительности аудио, не размера.

**Fix применён (2026-02-20)**:
1. **ffmpeg в n8n контейнере**: статический бинарь (musl-compatible) установлен через volume mount:
   - Host: `/usr/local/bin/ffmpeg` (johnvansickle.com static build v7.0.2)
   - docker-compose.yml: `- /usr/local/bin/ffmpeg:/usr/bin/ffmpeg:ro`
2. **Workflow 01 обновлён**: ffmpeg конвертирует webm→ogg перед отправкой в Whisper
3. **Фильтр по размеру**: файлы > 100MB пропускаются (status не меняется, будут обработаны вручную)
4. **Старые дублирующие workflows** деактивированы — остался только `01 New Recording v3 FINAL` (id: ZCtnggR6qrPy7bS6)

**Верификация ffmpeg в контейнере**:
```bash
docker exec mvp-auto-summary-n8n-1 ffmpeg -version
# Ожидается: "ffmpeg version 7.0.2-static"
```

**Сброс зависших файлов**:
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "DELETE FROM processed_files WHERE status = 'transcribing';"
```

---

### E057: ffmpeg в n8n контейнере — несовместимость glibc/musl

**Symptom**: `/usr/bin/ffmpeg: Error loading shared library libavdevice.so.58` внутри n8n контейнера.

**Root Cause**: n8n Docker образ использует Alpine Linux (musl libc). Системный ffmpeg Ubuntu (glibc) несовместим с musl. Volume mount `/usr/bin/ffmpeg` + `/lib/x86_64-linux-gnu` не работает — libresolv и другие системные библиотеки конфликтуют.

**Попытки которые НЕ работают**:
- `apk add ffmpeg` — apk не доступен в Docker Hardened Images
- Mount `/usr/bin/ffmpeg` + `/usr/lib/x86_64-linux-gnu` — неверная директория (нужна `/lib/`)
- Mount `/usr/bin/ffmpeg` + `/lib/x86_64-linux-gnu` — libresolv конфликтует с musl

**Fix (рабочий)**:
```bash
# На хосте (Ubuntu) — скачать статический musl-совместимый ffmpeg:
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -O /tmp/ffmpeg-static.tar.xz
tar xf /tmp/ffmpeg-static.tar.xz -C /tmp/
cp /tmp/ffmpeg-7.0.2-amd64-static/ffmpeg /usr/local/bin/ffmpeg
chmod +x /usr/local/bin/ffmpeg
/usr/local/bin/ffmpeg -version  # Должно работать

# docker-compose.yml — пробросить статический бинарь:
volumes:
  - /usr/local/bin/ffmpeg:/usr/bin/ffmpeg:ro  # статический (musl-совместимый)
  # НЕ добавлять /lib/x86_64-linux-gnu — статический ffmpeg не нуждается в хостовых libs
```

---

### E058: Whisper модель — `latest-cpu` тег не существует в Docker Hub

**Symptom**: `docker compose up` падает с `Error: failed to resolve reference: docker.io/onerahmet/openai-whisper-asr-webservice:latest-cpu: not found`

**Root Cause**: Тег `latest-cpu` был удалён с Docker Hub. На сервере был установлен образ `v1.4.0`.

**Fix**: В docker-compose.yml пиновать конкретную версию:
```yaml
whisper:
  image: onerahmet/openai-whisper-asr-webservice:v1.4.0  # не latest-cpu!
```

**Проверить доступные теги**:
```bash
docker images | grep whisper
# Использовать тот что уже есть локально
```

---

### E059: Whisper модель не меняется через docker-compose (перебивается .env)

**Symptom**: Меняешь `ASR_MODEL=small` в docker-compose.yml, пересоздаёшь контейнер — но Whisper всё равно загружает `medium`.

**Root Cause**: В файле `.env` на сервере прописан `WHISPER_MODEL=medium`. Переменная из `.env` перебивает default-значение в docker-compose.yml:
```yaml
- ASR_MODEL=${WHISPER_MODEL:-small}   # ← берёт значение из .env, а не default "small"
```

**Fix**: Изменить значение непосредственно в `.env`:
```bash
sed -i 's/WHISPER_MODEL=medium/WHISPER_MODEL=small/' /root/mvp-auto-summary/.env
docker compose stop whisper && docker compose rm -f whisper && docker compose up -d whisper
```

**Проверить модель в контейнере**:
```bash
docker exec mvp-auto-summary-whisper-1 env | grep ASR
# Должно быть: ASR_MODEL=small
```

**Примечание**: Модель `medium` + `faster_whisper v1.0.1` на CPU:
- Скорость: ~1.5x реального времени (45 секунд на 30 секунд аудио)
- Качество русского: отличное
- Для файлов > 30 минут — превышает n8n таймаут 30 минут

---

### E060: n8n — несколько активных Workflow 01 конкурируют

**Symptom**: Файлы иногда обрабатываются дважды или получают `Unknown error`. В n8n видно 2-3 активных workflow с похожими именами.

**Root Cause**: При тестировании были созданы несколько версий Workflow 01, все с активными Schedule Trigger. Они запускались одновременно и конкурировали за одни и те же файлы.

**Диагностика**:
```python
# Получить список всех активных workflows через API:
import json, urllib.request
api_key = 'ВАШ_КЛЮЧ'
req = urllib.request.Request('http://84.252.100.93:5678/api/v1/workflows?active=true',
    headers={'X-N8N-API-KEY': api_key})
wf = json.loads(urllib.request.urlopen(req).read())
for w in wf['data']: print(w['id'], w['name'])
```

**Fix**: Деактивировать все кроме актуального (ZCtnggR6qrPy7bS6 — `01 New Recording v3 FINAL`):
```python
# Деактивировать через API:
req = urllib.request.Request(
    f'http://84.252.100.93:5678/api/v1/workflows/{wf_id}/deactivate',
    data=b'{}', headers={'X-N8N-API-KEY': api_key, 'Content-Type': 'application/json'},
    method='POST')
urllib.request.urlopen(req)
```

**Актуальный рабочий workflow**: `ZCtnggR6qrPy7bS6` (`01 New Recording v3 FINAL`, 22 ноды)

---

## Яндекс SpeechKit — полная документация (2026-02-20)

> **Контекст**: После часов отладки Whisper workflow (E056-E060) было решено переключиться на Яндекс SpeechKit.
> Этот раздел документирует ВСЕ проблемы, с которыми мы столкнулись, и их решения.
> Это критически важно чтобы не повторять те же ошибки.

---

### E070: Яндекс SpeechKit — получение API ключа

**Где получать**: https://console.yandex.cloud

**Пошаговая инструкция**:
1. Зайти на console.yandex.cloud (войди через Яндекс аккаунт)
2. Слева вверху — выбрать или создать "Каталог" (folder), обычно уже есть `default`
3. В каталоге → слева меню → "Сервисные аккаунты"
4. Создать сервисный аккаунт:
   - Имя: `speechkit-bot`
   - Роль: `ai.speechkit-stt.user` (только распознавание речи)
   - Создать
5. Открыть созданный аккаунт → вкладка "API-ключи"
6. Создать API-ключ:
   - Описание: `mvp-autosummary`
   - Область действия: "Без ограничений" или "speechkit" если есть
   - Создать
7. **СРАЗУ скопировать ключ** — он показывается один раз!
   - Формат: `AQVN_xxxxxxxxxxxxxxxxxxxxxxxx`

**Текущий рабочий ключ** (хранится в скрипте):
```
AQVN_your_yandex_api_key_here
```

---

### E071: SpeechKit синхронный API — лимит 30 секунд

**Symptom**: Файл 2+ минуты — SpeechKit возвращает:
```json
{"error_code":"BAD_REQUEST","error_message":"audio duration should be less than 30s"}
```

**Root Cause**: SpeechKit имеет ДВА API:
- **Синхронный** (`/speech/v1/stt:recognize`) — до 30 секунд, ответ сразу
- **Асинхронный** (`/speech/stt/v2/longRunningRecognize`) — до 3 часов, нужен S3 bucket

**Fix для файлов < 30 сек**: Использовать синхронный API напрямую:
```python
import urllib.request, json
with open('audio.ogg', 'rb') as f:
    audio = f.read()
req = urllib.request.Request(
    'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize?lang=ru-RU&format=oggopus&sampleRateHertz=16000',
    data=audio,
    headers={'Authorization': 'Api-Key AQVN...'},
    method='POST'
)
resp = urllib.request.urlopen(req, timeout=30)
result = json.loads(resp.read())
print(result.get('result', ''))
```

**Fix для файлов > 30 сек**: Нарезать файл на чанки по 25 сек:
```python
# 1. Конвертировать в OGG 16kHz моно
ffmpeg -i input.webm -vn -acodec libopus -b:a 16k -ac 1 -ar 16000 audio.ogg -y

# 2. Нарезать на 25-секундные чанки
ffmpeg -i audio.ogg -f segment -segment_time 25 -c copy chunk_%03d.ogg -y

# 3. Отправить каждый чанк в SpeechKit, склеить результаты
texts = []
for chunk in sorted(glob('chunk_*.ogg')):
    with open(chunk, 'rb') as f:
        resp = urllib.request.urlopen(req_with_audio, timeout=30)
        texts.append(json.loads(resp.read()).get('result', ''))
    time.sleep(0.3)  # не DDOS'ить API

full_text = ' '.join(texts)
```

---

### E072: n8n HTTP Request нода — expressions НЕ работают в jsonBody

**Symptom**: n8n отправляет:
```json
{"filepath": "={{ $json.filepath }}"}
```
вместо подставленного значения.

**Root Cause**: В n8n HTTP Request ноде поле `jsonBody` с типом "Expression" **не раскрывает expressions** — отправляет как есть. Это особенность реализации n8n.

**НЕПРАВИЛЬНО** (expression не раскрывается):
```json
{
  "specifyBody": "json",
  "jsonBody": "={ \"filepath\": \"{{ $json.filepath }}\" }"
}
```

**ПРАВИЛЬНО — использовать Code ноду с helpers.httpRequest**:
```javascript
const filepath = $input.first().json.filepath;
const body = JSON.stringify({ filepath: filepath });
const response = await this.helpers.httpRequest({
  method: 'POST',
  url: 'http://172.17.0.1:9001/',
  body: body,
  headers: { 'Content-Type': 'application/json' },
  timeout: 180000
});
return [{ json: response }];
```

**Альтернатива — Expression в URL/query, но не в body**:
- URL с expression: `http://server/?file={{ $json.filepath }}` — работает ✅
- Body с expression: `{"file":"{{ $json.filepath }}"}` — НЕ работает ❌

---

### E073: n8n Code нода — модуль `http` запрещён

**Symptom**:
```
Error: Module 'http' is disallowed [line 3]
```

**Root Cause**: n8n Code нода работает в sandbox и запрещает Node.js модули (`http`, `https`, `fs`, `child_process` и др.) из соображений безопасности.

**НЕПРАВИЛЬНО**:
```javascript
const http = require('http');  // ← запрещено!
```

**ПРАВИЛЬНО — использовать this.helpers.httpRequest**:
```javascript
const response = await this.helpers.httpRequest({
  method: 'POST',
  url: 'http://example.com/api',
  json: { key: 'value' },
  timeout: 60000
});
return [{ json: response }];
```

**Доступные helpers в n8n Code ноде**:
- `this.helpers.httpRequest(options)` — HTTP запросы
- `this.helpers.binaryToString(buffer)` — конвертация бинарных данных
- `$input`, `$json`, `$('NodeName')` — доступ к данным других нод

---

### E074: n8n expression `.item` vs `.first()` — Multiple matches error

**Symptom**:
```
ExpressionError: Multiple matching items for item [0]
The code here won't work because it uses .item and n8n can't figure out the matching item.
```

**Root Cause**: `.item` работает когда на входе ОДИН элемент. Если на входе несколько элементов (массив) — n8n не знает какой выбрать.

**НЕПРАВИЛЬНО** (ошибка при множестве элементов):
```javascript
$('Parse Filenames & LEAD_ID').item.json.filepath
$json.someField  // иногда тоже падает
```

**ПРАВИЛЬНО**:
```javascript
$('Parse Filenames & LEAD_ID').first().json.filepath  // первый элемент
$('Parse Filenames & LEAD_ID').last().json.filepath   // последний
$('Parse Filenames & LEAD_ID').all()[0].json.filepath // по индексу
$input.first().json.filepath                          // из входа текущей ноды
```

**Затронутые ноды**:
- IF ноды с conditions
- Postgres ноды с SQL expressions
- HTTP Request ноды с URL/body expressions
- Любая нода с expression полем

---

### E075: HTTP сервер — JSON parse error "Expecting property name enclosed in double quotes"

**Symptom**:
```python
json.decoder.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
RAW: b'{filepath:/recordings/...}'  # ← кавычки пропущены!
```

**Root Cause**: Python `json.loads()` требует правильный JSON с двойными кавычками. Отправитель (n8n helpers.httpRequest с параметром `json`) отправляет без кавычек.

**НЕПРАВИЛЬНО** (отправка через `json:` параметр):
```javascript
await this.helpers.httpRequest({
  url: 'http://server/',
  json: { filepath: '/path' }  // ← n8n отправляет как {filepath:/path}
});
```

**ПРАВИЛЬНО** (отправка через `body:` с JSON.stringify):
```javascript
await this.helpers.httpRequest({
  url: 'http://server/',
  body: JSON.stringify({ filepath: '/path' }),  // ← правильный JSON
  headers: { 'Content-Type': 'application/json' }
});
```

**На сервере — всегда ловить JSON ошибки**:
```python
try:
    body = json.loads(raw.decode('utf-8'))
except json.JSONDecodeError as e:
    self._send(400, {'error': f'invalid json: {e}', 'raw': raw.decode()[:100]})
    return
```

---

### E076: n8n → HTTP Request timeout (socket hang up / BrokenPipeError)

**Symptom**: 
- n8n: `Error: socket hang up`
- Server: `BrokenPipeError: [Errno 32] Broken pipe`

**Root Cause**: n8n закрывает соединение по timeout раньше чем сервер успевает ответить. Типичный сценарий:
- Файл 71MB (31 минута аудио)
- SpeechKit обрабатывает 5-7 минут
- n8n timeout = 180 секунд (3 минуты)
- n8n закрывает соединение → сервер получает BrokenPipeError при попытке записать ответ

**НЕПРАВИЛЬНО** (синхронная обработка):
```
n8n → POST /transcribe → ждёт ответа → timeout → BrokenPipe
                    ↑
            сервер работает 5 минут
```

**ПРАВИЛЬНО — асинхронная архитектура**:
```
n8n → POST /transcribe → немедленно получает {"status":"processing"}
         ↓
    сервер работает в фоне (threading)
         ↓
    сервер пишет результат в БД (processed_files.transcript)
         ↓
n8n → ждёт 60 сек → читает результат из БД
```

**Реализация асинхронного сервера**:
```python
import threading

def transcribe_async(filepath, filename):
    """Работает в отдельном потоке"""
    try:
        # ... ffmpeg + SpeechKit ...
        conn = psycopg2.connect(DB)
        cur = conn.cursor()
        cur.execute('UPDATE processed_files SET status=%s, transcript=%s WHERE filename=%s',
                    ('completed', result_text, filename))
        conn.commit()
    except Exception as e:
        # Записать ошибку в БД
        cur.execute('UPDATE processed_files SET status=%s WHERE filename=%s',
                    ('error', filename))

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # ... parse request ...
        
        # Запустить в фоне
        t = threading.Thread(target=transcribe_async, args=(filepath, filename))
        t.daemon = True
        t.start()
        
        # Ответить немедленно
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status":"processing"}')
```

**n8n workflow для асинхронной обработки**:
```
Mark as Transcribing → SpeechKit (async, returns immediately) 
                     → Wait 60 сек → Check DB (SELECT transcript) 
                     → If not null → Parse & Continue
                     → If null → Wait more or Mark Error
```

---

### E077: Пути к файлам — n8n контейнер vs хост

**Symptom**: 
```json
{"error": "file not found", "path": "/recordings/2026/02/20/file.webm"}
```

**Root Cause**: n8n видит файлы по пути `/recordings/...` (внутри контейнера). Сервер транскрипции работает на хосте и видит файлы по пути `/mnt/recordings/...`.

**docker-compose.yml volume mount**:
```yaml
n8n:
  volumes:
    - /mnt/recordings:/recordings:ro  # хост:контейнер
```

**Fix — сервер конвертирует пути**:
```python
filepath = body.get('filepath', '').replace('/recordings/', '/mnt/recordings/')
```

**Альтернатива — запускать сервер внутри контейнера** (сложнее, не рекомендуется).

---

### E078: SpeechKit — лимиты и квоты

**Бесплатная квота** (на момент 2026-02):
- До 10 000 запросов в месяц
- До 1 часа аудио в месяц
- Файлы до 30 сек — синхронный API
- Файлы до 3 часов — асинхронный API (нужен S3)

**Платные тарифы**: см. https://cloud.yandex.ru/docs/speechkit/stt/pricing

**Рекомендации**:
- Кешировать результаты (не транскрибировать один файл дважды)
- Сжимать аудио перед отправкой (16kHz моно opus достаточно для речи)
- Нарезать на чанки по 25 сек для синхронного API
- Использовать асинхронный API для файлов > 5 минут

---

### E079: PostgreSQL — добавить поле transcript в processed_files

**Symptom**:
```
column "transcript" of relation "processed_files" does not exist
```

**Fix**:
```sql
ALTER TABLE processed_files ADD COLUMN IF NOT EXISTS transcript TEXT;
```

**Использование**:
```sql
-- Записать результат
UPDATE processed_files SET status='completed', transcript='Текст транскрипции...' WHERE filename='file.webm';

-- Прочитать результат
SELECT transcript, status FROM processed_files WHERE filename='file.webm';
```

---

### E080: n8n HTTP Request нода — GET вместо POST (версия v1 vs v4)

**Symptom**: 
```
501 - Unsupported method ('GET')
```

**Root Cause**: HTTP Request нода v1 (устаревшая) игнорирует параметр `method` или требует другой формат.

**Fix — обновить ноду до v4+**:
```json
{
  "type": "n8n-nodes-base.httpRequest",
  "typeVersion": 4.2,
  "parameters": {
    "method": "POST",
    "url": "http://example.com/",
    "sendBody": true,
    "contentType": "json",
    "specifyBody": "json",
    "jsonBody": "..."
  }
}
```

**Или использовать Code ноду** — она всегда работает предсказуемо.

---

### E081: Python HTTP сервер — не запускается после записи через SSH

**Symptom**: `python3 server.py &` не создаёт процесс.

**Root Cause**: При запуске через SSH с перенаправлением вывода процесс может завершиться при закрытии сессии.

**Fix — использовать nohup**:
```bash
nohup python3 /path/to/server.py > /tmp/server.log 2>&1 &
sleep 2
pgrep -a python3  # проверить что запустился
```

**Или записать скрипт на диск и запустить**:
```python
import paramiko
ssh = paramiko.SSHClient()
ssh.connect(host, username=user, password=pwd)

# Записать файл
sftp = ssh.open_sftp()
with sftp.open('/root/server.py', 'w') as f:
    f.write(server_code)
sftp.close()

# Запустить с nohup
stdin, stdout, stderr = ssh.exec_command(
    'nohup python3 /root/server.py > /tmp/server.log 2>&1 & sleep 2; pgrep -a python3'
)
print(stdout.read().decode())
```

---

### E082: SpeechKit vs Whisper — когда что использовать

| Критерий | Whisper (локально) | SpeechKit (облако) |
|----------|-------------------|-------------------|
| Стоимость | Бесплатно | Квота + платно сверх |
| Скорость | ~1.5x realtime (CPU) | ~0.3x realtime |
| Качество RU | Хорошее (medium+) | Отличное |
| Файлы > 30 мин | OK | Нужен S3 или чанки |
| Офлайн | Да | Нет |
| Сложность setup | Docker контейнер | API ключ |

**Рекомендация**:
- **Для production**: SpeechKit (быстрее, качественнее)
- **Для offline/privacy**: Whisper
- **Гибрид**: Whisper как fallback когда SpeechKit недоступен

---

### Итоговая архитектура SpeechKit (рабочая)

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   n8n       │───▶│  HTTP Server     │───▶│  SpeechKit API  │
│  Workflow   │    │  (Python, host)  │    │  (Яндекс Cloud) │
└─────────────┘    └──────────────────┘    └─────────────────┘
       │                   │
       │                   ▼
       │          ┌──────────────────┐
       │          │  PostgreSQL      │
       └─────────▶│  processed_files │
                  │  (transcript)    │
                  └──────────────────┘
```

**Компоненты**:
1. **transcribe_server.py** — HTTP сервер на порту 9001
   - Принимает POST с `{filepath: "..."}`
   - Конвертирует путь `/recordings/` → `/mnt/recordings/`
   - Запускает транскрипцию в отдельном потоке
   - Возвращает `{status: "processing"}` немедленно
   - Результат пишет в БД

2. **n8n Workflow 01**:
   - Mark as Transcribing → INSERT в БД
   - SpeechKit Transcribe (Code нода) → POST к серверу
   - Wait 60 сек
   - Check DB → SELECT transcript
   - If not null → Continue
   - If null → Mark Error

3. **PostgreSQL**:
   - `processed_files.transcript` — TEXT поле для результата
   - `processed_files.status` — 'transcribing' | 'completed' | 'error'

---

### E083: PostgreSQL с хоста — "could not translate host name postgres"

**Symptom**:
```
ASYNC ERR: could not translate host name "postgres" to address: No address associated with hostname
```

**Root Cause**: Сервер транскрипции работает на хосте, а `postgres` — это Docker hostname. С хоста нужно использовать `localhost`.

**НЕПРАВИЛЬНО** (для сервера на хосте):
```python
DB = 'host=postgres dbname=n8n user=n8n password=...'
```

**ПРАВИЛЬНО**:
```python
DB = 'host=localhost port=5432 dbname=n8n user=n8n password=...'
```

**Примечание**: Порт 5432 должен быть проброшен наружу в docker-compose.yml:
```yaml
postgres:
  ports:
    - "5432:5432"
```

---

### E084: Успешная транскрипция — верификация

**Дата**: 2026-02-20

**Тестовый файл**: `1000023_ракурс техно по расх. озон.webm` (71MB, ~31 минута аудио)

**Результат**:
```
ASYNC DONE: 1000023_...webm -> 26358 chars, 75 chunks
status: completed
```

**Проверка в БД**:
```sql
SELECT filename, status, LENGTH(transcript) FROM processed_files WHERE transcript IS NOT NULL;
-- Результат: 1000023_... | completed | 26358
```

**Workflow chain (финальная)**:
```
List Recording Files → Parse Filenames → Has Files? → Check If Already Processed
→ Is New File? → Mark as Transcribing → SpeechKit Transcribe (async)
→ Wait 90s → Check Transcript → Has Transcript? → Get Notebooks → ... → Mark Completed
```

---

### E085: open-notebook порт 8888 vs 5055

**Symptom**:
```
Error: connect ECONNREFUSED 172.18.0.6:8888
```

**Root Cause**: open-notebook API слушает на порту **5055** (uvicorn), а не 8888. Порт 8888 — это внешний порт docker-proxy для UI.

**Fix — обновить переменные окружения**:
```bash
# В docker-compose.yml:
- OPEN_NOTEBOOK_URL=http://open-notebook:5055

# Также проверить .env:
OPEN_NOTEBOOK_URL=http://open-notebook:5055
```

**После изменения — пересоздать контейнер**:
```bash
docker compose up -d --force-recreate n8n
```

**Проверка**:
```bash
docker exec mvp-auto-summary-n8n-1 env | grep OPEN_NOTEBOOK_URL
# Должно быть: OPEN_NOTEBOOK_URL=http://open-notebook:5055
```

---

### E086: Retry loop для Check Transcript — ожидание завершения

**Symptom**: `_notReady: true` — 90 секунд не хватило для длинного файла.

**Root Cause**: Файл 31 минута обрабатывается 5-7 минут. Фиксированный Wait недостаточен.

**НЕПРАВИЛЬНО** (фиксированный Wait):
```
Wait 90s → Check DB → if not ready → Mark Error
```

**ПРАВИЛЬНО — retry loop в Code ноде**:
```javascript
const filename = $('Parse Filenames & LEAD_ID').first().json.filename;
const maxAttempts = 20;
const waitSeconds = 60;

for (let i = 0; i < maxAttempts; i++) {
  const result = await this.helpers.httpRequest({
    method: 'POST',
    url: 'http://172.17.0.1:9001/check',
    body: JSON.stringify({ filename: filename }),
    headers: { 'Content-Type': 'application/json' },
    timeout: 10000
  });
  
  if (result && result.transcript) {
    return [{ json: { text: result.transcript, attempts: i + 1 } }];
  }
  
  if (i < maxAttempts - 1) {
    await new Promise(r => setTimeout(r, waitSeconds * 1000));
  }
}

return [{ json: { text: '', _notReady: true, attempts: maxAttempts } }];
```

**Параметры**:
- `maxAttempts = 20` — максимум 20 попыток
- `waitSeconds = 60` — ждать 60 сек между попытками
- **Максимальное ожидание**: 20 минут (достаточно для файлов до 60 минут)

**Workflow chain (финальная)**:
```
Mark as Transcribing → SpeechKit Transcribe (async, returns immediately)
                    → Check Transcript (retry loop, up to 20 min)
                    → Has Transcript? → Get Notebooks → ... → Mark Completed
```

---

### E087: open-notebook API endpoints — /api/sources, не /notebooks

**Symptom**:
```
404 - {"detail":"Not Found"}
GET /notebooks?archived=false → 404 Not Found
```

**Root Cause**: open-notebook использует `/api/sources` для работы с notebooks, не `/notebooks`.

**НЕПРАВИЛЬНО**:
```
GET http://open-notebook:5055/notebooks
```

**ПРАВИЛЬНО**:
```
GET http://open-notebook:5055/api/sources
POST http://open-notebook:5055/api/sources (create)
POST http://open-notebook:5055/api/sources/{id}/entries (add entry)
```

**Затронутые ноды**:
- `Get Notebooks` → URL должен быть `/api/sources`
- `Create Notebook` → URL должен быть `/api/sources`
- `Save Transcript to Notebook` → URL должен быть `/api/sources/{sourceId}/entries`

---

### E088: Code нода читает из удалённой ноды — "Referenced node doesn't exist"

**Symptom**:
```
Cannot assign to read only property 'name' of object 'Error: Referenced node doesn't exist'
$('Extract Transcript').first().json.notebookName
```

**Root Cause**: Code нода пытается прочитать данные из ноды, которая была удалена или переименована.

**НЕПРАВИЛЬНО**:
```javascript
// Extract Transcript была удалена!
const notebookName = $('Extract Transcript').first().json.notebookName;
```

**ПРАВИЛЬНО — читать из существующей ноды**:
```javascript
const leadId = $('Parse Filenames & LEAD_ID').first().json.leadId;
const notebookName = 'LEAD-' + leadId;
```

**Как диагностировать**:
1. Проверить список всех нод в workflow
2. Найти какая нода читается в Code ноде
3. Убедиться что эта нода существует

---

### E089: Workflow останавливается — нет связи после Create Notebook

**Symptom**: Workflow выполнился до `Create Notebook`, дальше не идёт, ошибок нет.

**Root Cause**: `Create Notebook` не соединена со следующей нодой (`Get Notebook ID`).

**Диагностика**:
```json
"Create Notebook": {"main": [[]]}  // Пустой массив = нет связи!
```

**Fix — добавить connection**:
```json
"Create Notebook": {"main": [[{"node": "Get Notebook ID", "type": "main", "index": 0}]]}
```

---

### E090: n8n Code нода — setTimeout/loop ломает task runner

**Symptom**:
```
Error: Node execution failed
TaskBrokerWsServer.removeConnection
```

**Root Cause**: n8n Code нода с JavaScript `setTimeout` в цикле (retry loop) перегружает task runner и он падает.

**НЕПРАВИЛЬНО** (JavaScript loop с setTimeout):
```javascript
for (let i = 0; i < 20; i++) {
  // ... check ...
  await new Promise(r => setTimeout(r, 60000));  // ← ломает task runner!
}
```

**ПРАВИЛЬНО — использовать Wait ноду + IF loop**:
```
SpeechKit → Wait 3min → Check Transcript → Has Transcript?
                                                ↓ False
                                          ┌─────┘
                                          │
                                          └─→ Wait 1min → Check Transcript → (повтор)
```

Или проще — **фиксированный Wait достаточной длины**:
- Файл 30 мин → Wait 5 минут
- Файл 60 мин → Wait 10 минут

---

## ИТОГ: SpeechKit транскрипция РАБОТАЕТ (2026-02-20)

### Быстрый старт (если всё сломалось)

**1. Проверить сервер транскрипции**:
```bash
ssh root@84.252.100.93
pgrep -a python3 | grep transcribe  # должен быть процесс
tail /tmp/ts.log                     # логи
```

**2. Если сервер не работает**:
```bash
cd /root/mvp-auto-summary/scripts
nohup python3 transcribe_server.py >> /tmp/ts.log 2>&1 &
sleep 2
pgrep -a python3 | grep transcribe
```

**3. Очистить processed_files для повторной обработки**:
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "DELETE FROM processed_files WHERE filename ~ '(webm|wav)';"
```

**4. Запустить workflow вручную** в n8n UI (кнопка Test workflow)

---

### Архитектура (схема)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         n8n Workflow 01                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Every 5 min → List Recording Files → Parse Filenames               │
│       ↓                                                             │
│  Has Files? → Check If Already Processed → Is New File?             │
│       ↓                                                             │
│  Mark as Transcribing (INSERT status='transcribing')                │
│       ↓                                                             │
│  SpeechKit Transcribe (Code нода, POST to localhost:9001)           │
│       ↓                                                             │
│  Wait 3min → Check Transcript (Code нода, POST to /check)           │
│       ↓                                                             │
│  Has Transcript? → True → Get Notebooks → Find Client Notebook      │
│       ↓                       ↓                                     │
│       False        Create Notebook → Get Notebook ID                │
│       ↓                       ↓                                     │
│  Mark Error         Save Transcript to Notebook → Mark Completed    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    transcribe_server.py (host:9001)                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  POST /           → {"filepath": "/recordings/..."}                 │
│                    ↓                                                │
│                    Запуск транскрипции в threading.Thread           │
│                    Немедленный ответ: {"status":"processing"}       │
│                                                                     │
│  POST /check      → {"filename": "..."}                             │
│                    ↓                                                │
│                    SELECT transcript FROM processed_files           │
│                    Ответ: {"transcript": "..." или null}            │
│                                                                     │
│  Асинхронная транскрипция:                                          │
│    1. ffmpeg -i input.webm → audio.ogg (16kHz mono opus)            │
│    2. ffmpeg -i audio.ogg → chunk_%03d.ogg (25 сек каждый)          │
│    3. Для каждого чанка: POST to SpeechKit API                      │
│    4. Склеить тексты → UPDATE processed_files SET transcript=...    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         PostgreSQL                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  processed_files:                                                   │
│    - filename (PRIMARY KEY)                                         │
│    - filepath                                                       │
│    - lead_id                                                        │
│    - status ('transcribing' | 'completed' | 'error')                │
│    - transcript (TEXT) — результат транскрипции                     │
│    - created_at, updated_at                                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Переменные окружения (критично!)

**В docker-compose.yml**:
```yaml
n8n:
  environment:
    - OPEN_NOTEBOOK_URL=http://open-notebook:5055  # НЕ 8888!
    - OPEN_NOTEBOOK_TOKEN=password
```

**В .env**:
```bash
OPEN_NOTEBOOK_URL=http://open-notebook:5055
OPEN_NOTEBOOK_TOKEN=password
```

**После изменения**:
```bash
cd /root/mvp-auto-summary
docker compose up -d --force-recreate n8n
```

---

### Open-notebook API (финально)

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/health` | GET | Health check |
| `/api/sources` | GET | Список notebooks |
| `/api/sources` | POST | Создать notebook: `{"name":"LEAD-123","description":"..."}` |
| `/api/sources/{id}` | GET | Получить notebook |
| `/api/sources/{id}/entries` | POST | Добавить запись: `{"content":"Текст...","title":"Транскрипция"}` |

**Примеры**:
```bash
# Создать notebook
curl -X POST http://localhost:5055/api/sources \
  -H "Authorization: Bearer password" \
  -H "Content-Type: application/json" \
  -d '{"name":"LEAD-1000023","description":"Клиент 1000023"}'

# Добавить транскрипцию
curl -X POST http://localhost:5055/api/sources/{SOURCE_ID}/entries \
  -H "Authorization: Bearer password" \
  -H "Content-Type: application/json" \
  -d '{"content":"Транскрибированный текст...","title":"Созвон 2026-02-20"}'
```

---

### SpeechKit API ключ

**Где получить**: https://console.yandex.cloud → Сервисные аккаунты → API-ключ

**Текущий рабочий ключ** (в transcribe_server.py):
```
AQVN_your_yandex_api_key_here
```

**Квота**: ~10 000 запросов/месяц бесплатно

---

### Производительность

| Файл | Размер | Длительность | Чанков | Символов | Время обработки |
|------|--------|--------------|--------|----------|-----------------|
| 1000023_...webm | 71MB | 31 мин | 75 | 26000+ | ~5-7 минут |

**Формула**: ~1 чанк = 25 сек аудио, ~350 символов текста

---

### Типичные проблемы и решения

| Проблема | Решение |
|----------|---------|
| `_notReady: true` | Увеличить Wait (3 → 5 → 10 мин) |
| `Task runner failed` | Убрать JavaScript loop, использовать Wait ноду |
| `404 Not Found` | Проверить endpoint (`/api/sources` не `/notebooks`) |
| `ECONNREFUSED :8888` | Порт 5055, не 8888. Проверить OPEN_NOTEBOOK_URL |
| `connect ECONNREFUSED postgres` | Сервер на хосте, использовать `localhost:5432` |
| `JSONDecodeError` | Использовать `JSON.stringify()` в body, не `json:` параметр |

---

### Файлы на сервере

```
/root/mvp-auto-summary/
├── docker-compose.yml
├── .env
└── scripts/
    └── transcribe_server.py   ← HTTP сервер транскрипции

/tmp/ts.log                    ← Логи сервера

/mnt/recordings/               ← Записи созвонов (NFS mount)
```

---

### Workflow 01 — финальная цепочка нод

```
1.  Every 5 min (schedule)
2.  List Recording Files (executeCommand: find /recordings ...)
3.  Parse Filenames & LEAD_ID (code)
4.  Has Files? (if)
5.  Check If Already Processed (postgres: SELECT COUNT)
6.  Is New File? (if)
7.  Mark as Transcribing (postgres: INSERT status='transcribing')
8.  SpeechKit Transcribe (code: POST to localhost:9001)
9.  Wait 3min (wait)
10. Check Transcript (code: POST to localhost:9001/check)
11. Has Transcript? (if)
12. Get Notebooks (httpRequest: GET /api/sources)
13. Find Client Notebook (code)
14. Notebook Exists? (if)
15. Create Notebook (httpRequest: POST /api/sources)
16. Get Notebook ID (code)
17. Save Transcript to Notebook (httpRequest: POST /api/sources/{id}/entries)
18. Save Success? (if)
19. Mark Completed (postgres: UPDATE status='completed')
20. Mark Notebook Error (postgres)
21. Mark Error (postgres)
```

---

*Document created: 2026-02-18 | Updated: 2026-02-20 17:30 MSK — E090, полный quick start*
