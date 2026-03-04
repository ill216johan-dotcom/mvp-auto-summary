# Jitsi + Jibri: автозапись созвонов → NFS → система

> Для кого: человек без технического опыта (продакт/менеджер)
> Цель: созвон в Jitsi автоматически записывается и попадает в систему транскрипции
> Кто делает: этот файл — для руководителя или сисадмина, у которого есть Jitsi

---

## Что такое Jibri и зачем он нужен

**Jitsi** — это сервис для созвонов (как Zoom, но свой).
**Jibri** — это отдельная программа, которая сидит рядом с Jitsi и пишет видео/аудио митингов в файл.

Без Jibri: созвон прошёл → запись нигде нет.
С Jibri: созвон прошёл → файл `.webm` сохранился на сервер → наша система подхватила → транскрипт → дайджест.

---

## Требования

Jibri требует **отдельного сервера** (не тот же, что n8n):

| Параметр | Минимум | Рекомендация |
|----------|---------|--------------|
| CPU | 4 vCPU | 8 vCPU |
| RAM | 8 GB | 16 GB |
| Диск | 50 GB | 200 GB (записи занимают место) |
| ОС | Ubuntu 20.04/22.04 | Ubuntu 22.04 LTS |

> Записи копятся быстро: 1 час созвона ≈ 500 MB–1 GB. Планируй место заранее.

---

## Часть 1: Установка Jibri

### Шаг 1.1 — Установить зависимости

Подключись к серверу (ssh) и выполни:

```bash
apt update && apt upgrade -y

# Java (нужна Jibri)
apt install -y openjdk-11-jdk

# Chrome (Jibri открывает браузер и пишет его экран)
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
  > /etc/apt/sources.list.d/google-chrome.list
apt update
apt install -y google-chrome-stable

# Утилиты
apt install -y ffmpeg curl unzip

# Проверить
google-chrome --version   # должно быть: Google Chrome 120.x.x.x
java -version             # должно быть: openjdk version "11..."
ffmpeg -version           # должно быть: ffmpeg version 4.x
```

### Шаг 1.2 — Установить Jibri

```bash
# Добавить репозиторий Jitsi
curl https://download.jitsi.org/jitsi-key.gpg.key | gpg --dearmor > /usr/share/keyrings/jitsi-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/jitsi-keyring.gpg] https://download.jitsi.org stable/" \
  > /etc/apt/sources.list.d/jitsi-stable.list
apt update

# Установить Jibri
apt install -y jibri

# Проверить что установился
systemctl status jibri
```

### Шаг 1.3 — Настроить звуковые устройства (ALSA loopback)

Jibri пишет звук через виртуальный микрофон. Нужно создать его:

```bash
# Загрузить модуль виртуального звука
modprobe snd-aloop

# Чтобы модуль загружался при перезагрузке:
echo "snd-aloop" >> /etc/modules

# Проверить:
lsmod | grep snd_aloop
# Должна появиться строка: snd_aloop  ...
```

---

## Часть 2: Настройка Jibri

### Шаг 2.1 — Основной конфиг

Открой файл конфига:

```bash
nano /etc/jitsi/jibri/jibri.conf
```

Замени содержимое на:

```
jibri {
  id = ""
  single-use-mode = false

  api {
    http {
      port = 2222
      health-port = 2223
    }
  }

  recording {
    recordings-directory = /tmp/recordings
    # Сюда Jibri сохраняет записи ДО финализации
    finalize-script = /opt/jibri/finalize.sh
  }

  streaming {
    rtmp-allow-list = [".*"]
  }

  chrome {
    flags = [
      "--use-fake-ui-for-media-stream",
      "--start-maximized",
      "--kiosk",
      "--enabled",
      "--disable-infobars",
      "--autoplay-policy=no-user-gesture-required"
    ]
  }

  stats {
    enable-stats-d = false
  }

  webhook {
    subscribers = []
  }

  jwt-info {
    signing-key-path = ""
  }
}
```

> Ключевые строки:
> - `recordings-directory` — временная папка (не финальная, это буфер)
> - `finalize-script` — скрипт, который запускается ПОСЛЕ окончания записи и перекладывает файл куда нужно

### Шаг 2.2 — Создать скрипт финализации

Это самый важный файл — он переименовывает запись и кладёт её в нужную папку:

```bash
mkdir -p /opt/jibri
nano /opt/jibri/finalize.sh
```

Вставь содержимое:

```bash
#!/bin/bash
# /opt/jibri/finalize.sh
#
# Jibri вызывает этот скрипт после окончания записи.
# Аргументы:
#   $1 = полный путь к файлу записи (например: /tmp/recordings/recording.webm)
#   $2 = название комнаты (например: LEAD-12345-conf)
#
# Что делает:
#   1. Проверяет что комната начинается с LEAD-
#   2. Извлекает ID клиента
#   3. Переименовывает файл по схеме: {ID}_{дата}_{время}.webm
#   4. Кладёт в /recordings/{год}/{месяц}/{день}/

RECORDING_FILE="$1"
ROOM_NAME="$2"
DATE_PATH=$(date +%Y/%m/%d)
DATE_FILE=$(date +%Y-%m-%d_%H-%M)

LOG="/var/log/jibri-finalize.log"
echo "[$(date)] Финализация: файл=$RECORDING_FILE комната=$ROOM_NAME" >> "$LOG"

# Проверить что комната LEAD-*
LEAD_ID=$(echo "$ROOM_NAME" | grep -oP '(?<=LEAD-)\d+(?=-)')

if [ -z "$LEAD_ID" ]; then
  echo "[$(date)] Не LEAD-комната, пропускаем: $ROOM_NAME" >> "$LOG"
  exit 0
fi

# Создать папку назначения
DEST_DIR="/recordings/$DATE_PATH"
mkdir -p "$DEST_DIR"

# Новое имя файла
EXTENSION="${RECORDING_FILE##*.}"
NEW_NAME="${LEAD_ID}_${DATE_FILE}.${EXTENSION}"
DEST_PATH="$DEST_DIR/$NEW_NAME"

# Переместить файл
mv "$RECORDING_FILE" "$DEST_PATH"

if [ $? -eq 0 ]; then
  echo "[$(date)] Успешно: $DEST_PATH" >> "$LOG"
else
  echo "[$(date)] ОШИБКА при перемещении файла" >> "$LOG"
  exit 1
fi
```

Сделай скрипт исполняемым:

```bash
chmod +x /opt/jibri/finalize.sh
```

Проверь что работает:

```bash
# Тест: создай пустой файл и запусти скрипт вручную
mkdir -p /tmp/recordings
touch /tmp/recordings/test.webm
bash /opt/jibri/finalize.sh /tmp/recordings/test.webm LEAD-99999-conf

# Должен появиться файл:
ls /recordings/$(date +%Y/%m/%d)/
# Пример: 99999_2026-03-02_15-30.webm
```

---

## Часть 3: NFS — расшаривание папки с записями

NFS — это сетевая папка. Jibri пишет на один сервер, а n8n читает с другого. NFS — мост между ними.

### Шаг 3.1 — На сервере с Jibri (NFS-сервер)

```bash
# Установить NFS-сервер
apt install -y nfs-kernel-server

# Создать папку с записями
mkdir -p /recordings
chmod 755 /recordings

# Разрешить доступ серверу n8n
# ЗАМЕНИ 84.252.100.93 на реальный IP сервера n8n
echo "/recordings  84.252.100.93(rw,sync,no_subtree_check,no_root_squash)" >> /etc/exports

# Применить
exportfs -a
systemctl restart nfs-kernel-server

# Проверить:
exportfs -v
# Должно показать: /recordings  84.252.100.93(...)
```

### Шаг 3.2 — На сервере n8n (NFS-клиент)

```bash
# Уже установлено (nfs-common), но на всякий случай:
apt install -y nfs-common

# Создать точку монтирования (уже есть)
mkdir -p /mnt/recordings

# Смонтировать (ЗАМЕНИ IP на реальный IP сервера Jibri)
mount -t nfs JIBRI_SERVER_IP:/recordings /mnt/recordings

# Проверить:
ls /mnt/recordings/
# Если видишь папки — всё ок

# Автомонтирование при перезагрузке:
echo "JIBRI_SERVER_IP:/recordings /mnt/recordings nfs defaults,_netdev 0 0" >> /etc/fstab
```

---

## Часть 4: Подключить Jibri к Jitsi

Это настраивается в конфиге Jitsi (Prosody). Нужно создать два аккаунта: для control и для recorder.

### Шаг 4.1 — Создать аккаунты

На сервере с Jitsi:

```bash
# Замени meet.example.com на твой домен Jitsi
JITSI_DOMAIN="meet.example.com"

# Аккаунт для управления Jibri
prosodyctl register jibri auth.$JITSI_DOMAIN JibriAuthPassword123

# Аккаунт для записи в комнату
prosodyctl register recorder recorder.$JITSI_DOMAIN JibriRecorderPassword123
```

### Шаг 4.2 — Добавить Jibri в конфиг Jitsi

Открой `/etc/prosody/conf.avail/$JITSI_DOMAIN.cfg.lua` и найди секцию `VirtualHost "recorder.$JITSI_DOMAIN"`. Убедись что она есть и выглядит так:

```lua
VirtualHost "recorder.meet.example.com"
  modules_enabled = {
    "ping";
  }
  authentication = "anonymous"
```

### Шаг 4.3 — Конфиг Jibri для подключения к Jitsi

Снова открой `/etc/jitsi/jibri/jibri.conf` и добавь секцию xmpp:

```
jibri {
  # ... (то что было выше) ...

  xmpp {
    environments = [
      {
        name = "prod environment"
        xmpp-server-hosts = ["meet.example.com"]  # IP или домен Jitsi
        xmpp-domain = "meet.example.com"

        control-login {
          domain = "auth.meet.example.com"
          username = "jibri"
          password = "JibriAuthPassword123"
        }

        control-muc {
          domain = "internal.auth.meet.example.com"
          room-name = "JibriBrewery"
          nickname = "jibri"
        }

        call-login {
          domain = "recorder.meet.example.com"
          username = "recorder"
          password = "JibriRecorderPassword123"
        }

        strip-from-room-domain = "conference."
        usage-timeout = 0
        trust-all-xmpp-certs = true
      }
    ]
  }
}
```

### Шаг 4.4 — Перезапустить всё

```bash
# На сервере Jibri:
systemctl restart jibri
systemctl status jibri   # должно быть: active (running)

# На сервере Jitsi:
systemctl restart jicofo
systemctl restart jitsi-videobridge2
```

---

## Часть 5: Настройка Jitsi — автозапись комнат LEAD-*

По умолчанию запись начинается вручную (кнопка в интерфейсе). Чтобы LEAD-комнаты записывались автоматически — нужно добавить хук в конфиг Jitsi.

### Вариант А: через config.js Jitsi (рекомендуется)

Открой `/etc/jitsi/meet/meet.example.com-config.js` и найди/добавь:

```javascript
var config = {
  // ... существующий конфиг ...

  // Автозапись для комнат с префиксом LEAD-
  recordingService: {
    enabled: true,
    hideStorageWarning: true,
  },

  // Кнопка записи видна всем
  toolbarButtons: [
    'microphone', 'camera', 'chat', 'desktop', 'fullscreen',
    'hangup', 'participants-pane', 'recording', 'settings',
    'tileview', 'toggle-camera', 'videoquality',
  ],
};
```

### Вариант Б: автозапись через токены (сложнее, но надёжнее)

Jitsi поддерживает JWT-токены с параметром `"recording": true`. При создании комнаты с таким токеном запись стартует автоматически. Это требует настройки JWT в Prosody — спроси сисадмина.

---

## Часть 6: Проверка что всё работает

### Чеклист:

```bash
# 1. Jibri запущен?
systemctl is-active jibri        # → active

# 2. NFS примонтирован на n8n?
mountpoint /mnt/recordings        # → /mnt/recordings is a mountpoint

# 3. Finalize-скрипт работает?
bash /opt/jibri/finalize.sh /tmp/test.webm LEAD-99999-conf
ls /recordings/$(date +%Y/%m/%d)/  # → 99999_*.webm

# 4. n8n видит файл?
docker exec mvp-auto-summary-n8n-1 find /recordings -type f -name "*.webm" | head -5

# 5. Логи финализации:
tail -f /var/log/jibri-finalize.log
```

### Полный тест end-to-end:

1. Открой Jitsi
2. Создай комнату с именем `LEAD-99999-conf`
3. Нажми кнопку записи (или войди в комнату, если автозапись настроена)
4. Поговори 1-2 минуты
5. Выйди из комнаты (запись остановится)
6. Подожди 3-5 минут
7. Проверь:

```bash
# На сервере n8n:
ls /mnt/recordings/$(date +%Y/%m/%d)/
# Должен быть файл: 99999_2026-MM-DD_HH-MM.webm

# Через 10 минут — запись в БД:
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT filename, status FROM processed_files ORDER BY id DESC LIMIT 3;"
# status должен быть: completed
```

---

## Типичные проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| Jibri не запускается | Нет Chrome или нет snd-aloop | `lsmod \| grep snd_aloop`, `google-chrome --version` |
| Файл не появляется в /recordings | Скрипт finalize.sh не запустился | `tail /var/log/jibri-finalize.log` |
| NFS не монтируется | Firewall или IP не тот | Проверь `ufw status`, разреши порт 2049 |
| n8n не видит файлы | /mnt/recordings не примонтирован | `mountpoint /mnt/recordings` |
| Комната не записывается | Jibri не подключён к Jitsi | `systemctl status jibri`, смотри логи |
| В имени файла нет ID | Комната названа не по правилу | Название должно быть ровно `LEAD-{цифры}-conf` |

---

## Правило именования комнат

Это самое важное правило для менеджеров:

```
Правильно:   LEAD-4405-conf
Правильно:   LEAD-987-conf
Неправильно: lead-4405-conf     (маленькие буквы)
Неправильно: LEAD-4405          (нет -conf)
Неправильно: 4405-conf          (нет LEAD-)
Неправильно: LEAD-ФФ-4405-conf  (буквы в ID)
```

ID — это числовой ID клиента из вашей CRM/таблицы. Тот же ID что используется в системе (LEAD-4405, LEAD-987 и т.д.).

---

## Что происходит после настройки (автоматически)

```
Менеджер создаёт комнату LEAD-4405-conf
         ↓
Jibri начинает запись
         ↓
Созвон закончился → Jibri останавливает запись
         ↓
finalize.sh переименовывает файл → 4405_2026-03-02_14-30.webm
         ↓
Файл копируется на NFS → /recordings/2026/03/02/
         ↓
n8n (WF01) через 0-5 минут замечает файл
         ↓
Whisper транскрибирует (~3-10 минут для часового созвона)
         ↓
Транскрипт сохраняется в PostgreSQL
         ↓
В 22:00 — WF03 делает саммари → Dify Knowledge Base
В 23:00 — WF02 отправляет дайджест в Telegram
```

---

## Параллельные записи (несколько Jibri)

Если у вас несколько менеджеров и созвоны идут одновременно, один Jibri не справится.
Нужно поднять несколько инстансов.

### Шаг 1 — Убрать фиксированный JIBRI_INSTANCE_ID

В файле `/opt/jitsi-meet/.env` выставить пустое значение (чтобы Jibri использовал уникальный hostname контейнера):

```bash
JIBRI_INSTANCE_ID=
```

### Шаг 2 — Запустить 2+ инстанса

```bash
cd /opt/jitsi-meet
docker compose -f docker-compose.yml -f jibri.yml -f jibri-override.yml up -d --scale jibri=2
```

### Шаг 3 — Проверить что оба Jibri готовы

```bash
docker compose ps | grep jibri

docker exec jitsi-meet-jibri-1 curl -s http://localhost:2222/jibri/api/v1.0/health
docker exec jitsi-meet-jibri-2 curl -s http://localhost:2222/jibri/api/v1.0/health
# Ожидается: busyStatus=IDLE, healthStatus=HEALTHY
```

> Важно: каждый новый Jibri потребляет CPU/RAM. Планируйте ресурсы заранее.

---

## Текущий статус на сервере 84.252.100.93 (02.03.2026)

**Jitsi + Jibri установлены и работают через Docker (docker-jitsi-meet):**

```bash
# Текущий запуск:
cd /opt/jitsi-meet
docker compose -f docker-compose.yml -f jibri.yml -f jibri-override.yml up -d

# Статус:
docker compose ps
# jitsi-meet-jibri-1    → Up (IDLE/HEALTHY)
# jitsi-meet-jicofo-1   → Up
# jitsi-meet-jvb-1      → Up
# jitsi-meet-prosody-1  → Up
# jitsi-meet-web-1      → Up (внутренний порт 8443)

# Проверить что Jibri готов к записи:
docker exec jitsi-meet-jibri-1 curl -s http://localhost:2222/jibri/api/v1.0/health
# → {"status":{"busyStatus":"IDLE","health":{"healthStatus":"HEALTHY","details":{}}}}
```

**Протестированная цепочка:**
- Файл `99999_тест-jibri_2026-03-02.webm` положен в `/mnt/recordings/`
- WF01 подхватил через ~5 минут → статус `transcribing` → `completed`
- End-to-end пайплайн работает

### HTTPS через nginx reverse proxy (добавлено 02.03.2026)

**Важно**: WebRTC не работает по HTTP! Браузеры блокируют доступ к камере/микрофону на незащищённых соединениях.

**Архитектура:**
```
Internet → host nginx (:443) → internal services
            ↓
    ff-meet.duckdns.org → 127.0.0.1:8443 (Jitsi)
    dify-ff.duckdns.org → 127.0.0.1:9002 (Dify)
```

**SSL сертификаты** (Let's Encrypt через acme.sh):
```bash
# Установка acme.sh
apt install -y cron socat
curl -sL https://get.acme.sh | sh -s email=your@email.com
~/.acme.sh/acme.sh --set-default-ca --server letsencrypt

# Получить сертификат
~/.acme.sh/acme.sh --issue -d ff-meet.duckdns.org --standalone

# Установить для nginx
~/.acme.sh/acme.sh --install-cert -d ff-meet.duckdns.org --ecc \
  --key-file /etc/nginx/ssl/ff-meet.key \
  --fullchain-file /etc/nginx/ssl/ff-meet.crt
```

**Nginx конфигурация** (`/etc/nginx/sites-available/ff-meet.conf`):
```nginx
server {
    listen 443 ssl http2;
    server_name ff-meet.duckdns.org;
    
    ssl_certificate /etc/nginx/ssl/ff-meet.crt;
    ssl_certificate_key /etc/nginx/ssl/ff-meet.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

**Продление сертификатов** (автоматически через cron):
```bash
~/.acme.sh/acme.sh --renew -d ff-meet.duckdns.org --ecc --reloadcmd "systemctl reload nginx"
```

### Рабочие ссылки

| Сервис | URL | Для кого |
|--------|-----|----------|
| Jitsi Meet | `https://ff-meet.duckdns.org/LEAD-{ID}-conf` | Клиенты |
| Dify | `https://dify-ff.duckdns.org` | Работники |

### Миграция на постоянный домен

DuckDNS — временное решение для тестов. Для продакшена:

1. **Купить домен** (например `meet.ff-platform.ru` — ~200-300₽/год на reg.ru)
2. **Создать DNS A-запись**: `meet.ff-platform.ru → 84.252.100.93`
3. **Получить SSL сертификат**:
   ```bash
   ~/.acme.sh/acme.sh --issue -d meet.ff-platform.ru --standalone
   ~/.acme.sh/acme.sh --install-cert -d meet.ff-platform.ru \
     --key-file /etc/nginx/ssl/meet.ff-platform.key \
     --fullchain-file /etc/nginx/ssl/meet.ff-platform.crt
   ```
4. **Обновить nginx конфиг** (заменить `ff-meet.duckdns.org` на новый домен)
5. **Обновить Jitsi PUBLIC_URL**:
   ```bash
   sed -i 's|PUBLIC_URL=.*|PUBLIC_URL=https://meet.ff-platform.ru|' /opt/jitsi-meet/.env
   cd /opt/jitsi-meet && docker compose up -d --force-recreate web
   ```
6. **Перезапустить nginx**: `systemctl reload nginx`

### Если есть существующий Jitsi-сервер

Если у организации уже есть Jitsi (например `global-meet.ff-platform.ru`):

**Вариант А: Перенести только Jibri на существующий сервер**
- Плюсы: Меньше нагрузки на текущий сервер
- Минусы: Нужно настраивать NFS для `/recordings`
- Порядок: Установить Jibri на существующий сервер → настроить finalize.sh → смонтировать NFS

**Вариант Б: Использовать существующий домен для текущего сервера**
- Плюсы: Быстро, не нужно настраивать NFS
- Минусы: Текущий сервер может не хватать ресурсов для продакшена
- Порядок: См. инструкцию выше (миграция на постоянный домен)

**Вариант В: Текущий сервер как staging, продакшен на существующем**
- Плюсы: Безопасное тестирование
- Минусы: Два сервера, два домена
- Порядок: Оставить текущий как есть, интегрировать Jibri с продакшен-сервером позже

---

*Создано: 02.03.2026*
*Обновлено: 02.03.2026 — Добавлен HTTPS через nginx reverse proxy, DuckDNS домены, инструкция миграции*
*Актуально для: Ubuntu 22.04, docker-jitsi-meet (unstable), Jibri (unstable), nginx 1.18, acme.sh*
