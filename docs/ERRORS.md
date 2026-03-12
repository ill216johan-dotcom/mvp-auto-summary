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

### E056: Workflow 01 — файлы зависают в статусе `transcribing`, Whisper CPU ~0%

**Symptom**: После запуска workflow все файлы попадают в статус `transcribing` в PostgreSQL, но Whisper не загружен (CPU < 1%). Последняя зелёная нода — `Has Transcript?` → False branch.

**Root Cause**: Whisper получает файл, но возвращает пустой ответ (`Unexpected end of JSON input`). Нода `Has Transcript?` уходит в False ветку → `Mark Error`. Но `Mark Error` не всегда успевает обновить статус — файл остаётся в `transcribing`.

**Возможные причины пустого ответа Whisper**:
1. Файл повреждён или нулевой длины
2. Кириллица в имени файла вызывает проблему при передаче через curl внутри n8n
3. Файл слишком короткий (< 1 секунды)

**Диагностика** — проверить файл напрямую:
```bash
curl -sS -X POST 'http://localhost:9000/asr?task=transcribe&language=ru&output=json' \
  -F "audio_file=@/mnt/recordings/2026/02/20/2048-ФФ.webm" | head -c 500
```

**Fix (сброс зависших файлов)**:
```bash
# Удалить зависшие записи чтобы workflow обработал заново
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "
DELETE FROM processed_files WHERE status = 'transcribing';
"
```

**Статус**: выясняется 2026-02-20. Продолжить диагностику завтра.

---

## Bitrix Integration Errors

### E070: Bitrix datasets stored in wrong table (CRITICAL — FIXED)

**Symptom**:
- Датасеты создавались для каждого клиента
- Они сохранялись в `lead_chat_mapping.dify_dataset_id`
- Но должны были в `bitrix_leads.dify_dataset_id`
- Результат: система не могла находить нужные датасеты

**Root Cause**: Функция `db.get_dataset_map()` возвращала маппинг из таблицы `lead_chat_mapping` (для Telegram чатов), но Bitrix клиенты использовали ту же функцию.

**Fix**: Разделить функции:
- `db.get_dataset_map()` → для Telegram чатов (старое, backward compatibility)
- `db.get_bitrix_dataset_map()` → для Bitrix лидов/контактов (новое)
- `db.save_bitrix_dataset_mapping()` → сохранять в `bitrix_leads`

**Migration**: `scripts/migrate_fix_bitrix_mapping.sql`
- Перенес 4,154 датасетов из `lead_chat_mapping` → `bitrix_leads`
- Удалил 3,366 некорректных записей
- Применён: 2026-03-12

**Verification**: Фаза 3 тест показала что датасеты создаются в правильной таблице.

**Статус**: ✅ ИСПРАВЛЕНО (Phase 1, commit f458bc1)

---

### E071: Bitrix calls — phone_number is NULL (CRITICAL — FIXED)

**Symptom**:
- Звонки синхронизировались из Битрикса (66 штук для ФФ-4405)
- Но все `phone_number` были NULL в таблице `bitrix_calls`
- Невозможно определить какой номер звонил
- Отсутствует важная бизнес-информация

**Root Cause**:

1. **Ожидалось enrichment из voximplant**:
   - Код вызывал `voximplant.statistic.get` для получения `CALL_ID` и `PHONE_NUMBER`
   - Но для старых звонков (до июня 2025) `SETTINGS.CALL_ID` пустой
   - Связь между activity и voximplant терялась → enrichment не работал

2. **Телефон был доступен в activity**:
   - API `crm.activity.list` возвращает `COMMUNICATIONS` массив
   - `COMMUNICATIONS[0].VALUE` содержал номер телефона
   - Но код не извлекал его — ожидал voximplant

**Исследование** (ФФ-4405, 66 звонков):

```bash
# Прямой запрос к Bitrix API:
curl -X POST "https://bitrix24.ff-platform.ru/rest/1/.../crm.activity.list" \
  -d '{"filter":{"OWNER_TYPE_ID":3,"OWNER_ID":5723,"TYPE_ID":2}}'

# Ответ:
{
  "ID": "150513",
  "TYPE_ID": "2",
  "SETTINGS": [],           # ПУСТОЙ! CALL_ID здесь нет
  "COMMUNICATIONS": [
    {
      "TYPE": "PHONE",
      "VALUE": "+79135379385"   # ТЕЛЕФОН ЗДЕСЬ!
    }
  ]
}
```

**Fix** (реализовано в коммитах `2a90924`, `f4858dc`):

```python
# Извлекать телефон из COMMUNICATIONS (PRIMARY SOURCE)
communications = activity.get("COMMUNICATIONS") or []
phone_number = ""
if communications and len(communications) > 0:
    comm = communications[0]
    if comm.get("TYPE") == "PHONE":
        phone_number = comm.get("VALUE") or ""

# Fallback: enrichment из voximplant (SECONDARY SOURCE)
# Работает только для новых звонков (после июня 2025)
```

**SQL Changes**:
```sql
-- Добавлено в INSERT statement
INSERT INTO bitrix_calls (... phone_number ...)
VALUES (... , %s , ...)

-- Добавлен enrichment при confict (для обновления существующих)
ON CONFLICT (bitrix_activity_id) DO UPDATE SET
    phone_number = EXCLUDED.phone_number
```

**Результат после исправления** (ФФ-4405):
```
phone_number  | COUNT
--------------+-------
NULL          |     0  ✅
+79099358635   |    25  ✅
+79135379385   |    41  ✅
```

**Workaround для существующих данных**:
```python
# Если ON CONFLICT не сработал - прямой UPDATE
for activity in activities:
    phone = extract_phone_from_communications(activity)
    cur.execute(
        "UPDATE bitrix_calls SET phone_number = %s WHERE bitrix_activity_id = %s",
        (phone, activity["ID"])
    )
```

**Дата обнаружения**: 2026-03-13 00:20
**Дата исправления**: 2026-03-13 00:27
**Статус**: ✅ ИСПРАВЛЕНО (commits 2a90924, f4858dc)
**Test клиент**: ФФ-4405 (Алексей, 66 звонков, 2 номера телефона)

**Документация**: `docs/BITRIX_CALLS_RESEARCH.md` — полное исследование проблемы

---

*Document created: 2026-02-18 | Updated: 2026-03-13 — added E070 (Bitrix dataset mapping bug), E071 (Bitrix calls phone_number NULL)*

---

### E072: MegaPBX Recordings — Connection Timeout (CRITICAL — BLOCKING)

**Symptom**:
- ❌ Невозможно скачать записи звонков для транскрибации
- ❌ 30 звонков enriched с `record_url` из `voximplant.statistic.get`
- ❌ `transcribe_pending_calls()` заканчивается с ошибкой timeout
- ❌ Все попытки скачивания: `ConnectTimeoutError` к `vats528994.megapbx.ru`
- ❌ 0 транскрибированных звонков в БД

**Current State**:
```sql
SELECT transcript_status, COUNT(*) 
FROM bitrix_calls
GROUP BY transcript_status;

-- no_record: 174,303 (нет URL)
-- pending:       30 (есть URL, не скачаны)
-- failed:        10 (timeout при скачивании)
-- completed:      0  (НЕТ ТРАНСКРИПЦИЙ!)
```

**Root Cause**:
```
URL: https://vats528994.megapbx.ru/api/v2/call-records/record/2025-01-23/...
IP:  193.201.230.178
Ping: 100% packet loss
HTTPS: timeout (60s)
```

**Исследование**:

1. **Проверка прямого доступа:**
```bash
# С сервера
ping vats528994.megapbx.ru
# PING 193.201.230.178: 100% packet loss

curl -I "https://vats528994.megapbx.ru/api/v2/..."
# curl: (28) Connection timeout after 10001 ms
```

2. **Проверка источника URL:**
- URL берётся из Bitrix24 → `voximplant.statistic.get`
- Поле: `CALL_RECORD_URL` или `SRC_URL`
- Пример:
  ```
  https://vats528994.megapbx.ru/api/v2/call-records/record/
  2025-01-23/9f7f1e92-98c9-4fbd-9758-b29095ce58a0/
  evgeniy_rodzevich_out_79099358635_2025_01_23-15_45_04.mp3
  ```

3. **Структура доступа:**
```
Bitrix24 → VoxImplant.statistic.get → record_url (MegaPBX)
                                                    ↓
                                          (нужен доступ/токен)
                                                    ↓
                                             Скачать файл
                                                    ↓
                                                Whisper
```

**Возможные причины**:

1. **Firewall/Network:**
   - IP `193.201.230.178` недоступен с сервера
   - Возможно нужен VPN до офисной сети
   - Или белый IP в firewall Мегафона

2. **Авторизация:**
   - Может требоваться API токен в headers
   - Bitrix24 может иметь специальный доступ, который не передаётся

3. **Временная недоступность:**
   - Мегафон мог изменить политику доступа
   - URL устарел (но тесты показывают что свежие 2025-2026)

**Временное решение** (нет):

ПРЯМЫХ АЛЬТЕРНАТИВ НЕТ — нужны записи для транскрибации.

**План решения**:

**Phase 1: Исследование (на завтра)**
- [ ] Проверить доступ к megapbx.ru из офисной сети
- [ ] Открыть URL в браузере с офисного IP
- [ ] Найти документацию MegaPBX API
- [ ] Проверить нужен ли API токен

**Phase 2: Настройка доступа**

*Option A: VPN/Proxy*
```bash
# Если доступен только из офисной сети
# Добавить VPN туннель или пробросить порт
```

*Option B: API токен*
```bash
# Получить токен в личном кабинете MegaPBX
# Добавить в запросы:
headers = {'Authorization': f'Bearer {MEGAPBX_API_KEY}'}
```

*Option C: VoxImplant API*
```python
# Может можно скачать через VoxImplant API напрямую
# Изучить: https://voximplant.com/docs/references/httpapi/
```

**Phase 3: Тестирование**
```python
# После настройки доступа
stats = transcribe_pending_calls(db, transcribe_url, limit=5)
# Ожидается: transcribed=5, failed=0
```

**Files affected**:
- `app/tasks/bitrix_summary.py:transcribe_pending_calls()` — скачивание записей
- `docs/MEGAPBX_RESEARCH.md` — план исследования

**Expected result**:
```
-- completed:  100+  (транскрибировано)
-- pending:      0
-- failed:       0
```

**Статус**: ❌ BLOCKING — нужна помощь пользователя с доступом к MegaPBX

**Связанные ошибки**:
- E071 (phone_number NULL) — FIXED, enrichment работает
- E073 (будет добавлена) — нет transcript_text в саммари

---
