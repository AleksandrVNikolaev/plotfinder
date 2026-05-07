# Развёртывание PlotFinder

Инструкция по развёртыванию backend-сервиса на сервере Selectel или совместимом облачном провайдере с Ubuntu 22.04 LTS.

---

## Содержание

- [Боевое окружение PlotFinder MVP](#боевое-окружение-plotfinder-mvp)
- [Подготовка сервера](#подготовка-сервера)
- [Развёртывание приложения](#развёртывание-приложения)
- [Настройка systemd](#настройка-systemd)
- [Сетевая безопасность](#сетевая-безопасность)
- [Мониторинг и логи](#мониторинг-и-логи)
- [Резервное копирование](#резервное-копирование)
- [Перевыпуск API-ключей](#перевыпуск-api-ключей)
- [Чек-лист после развёртывания](#чек-лист-после-развёртывания)
- [Рекомендуемые улучшения для production](#рекомендуемые-улучшения-для-production)
- [Восстановление после сбоев](#восстановление-после-сбоев)

---

## Боевое окружение PlotFinder MVP

| Параметр | Значение |
|---|---|
| **Провайдер** | Selectel |
| **Регион** | ru-2a (Москва) |
| **Конфигурация** | 2 vCPU / 4 ГБ RAM / 5 ГБ SSD |
| **ОС** | Ubuntu 22.04 LTS |
| **Стоимость** | ~3 590 ₽/мес |
| **IP-адрес** | 79.143.24.76 |
| **Порт сервиса** | 8000 |
| **Python** | 3.11 |
| **Расположение проекта** | `/root/rosreestr_api/` |

### Почему такая конфигурация

- **Selectel ru-2a** — российский провайдер (соответствие 152-ФЗ о персональных данных), стабильная доступность из РФ
- **2 vCPU / 4 ГБ RAM** — достаточно для до 5 000 запросов/мес. Узким местом является не сервер, а время отклика OpenRouter (30–120 сек/запрос)
- **Ubuntu 22.04 LTS** — стандарт для Python-сервисов, поддержка до 2027 года
- **5 ГБ SSD** — хватает с большим запасом. Реально занято: ОС ~3 ГБ, проект+venv ~250 МБ, кэш GeoJSON растёт на ~5 КБ за участок

### Альтернативные провайдеры

PlotFinder можно развернуть и на других провайдерах, но для production-эксплуатации на территории РФ предпочтительны:

- **Selectel** — текущий выбор
- **Yandex Cloud** — альтернатива с лучшей интеграцией с GIS-сервисами
- **VK Cloud** — альтернатива по схожей цене

**AWS / GCP / Azure исключены** — санкционные риски, требования к локализации ПДн.

---

## Подготовка сервера

### Создание сервера в Selectel

1. Войти в [my.selectel.ru](https://my.selectel.ru/)
2. Облачные серверы → Добавить сервер
3. Выбрать:
   - Регион: **ru-2a**
   - Образ: **Ubuntu 22.04 LTS**
   - Конфигурация: **Линейка Standard, 2 vCPU / 4 ГБ / 5 ГБ SSD**
   - Сеть: **Публичный IPv4** (обязательно)
4. Создать SSH-ключ или загрузить существующий
5. Запустить сервер

### Первое подключение

```bash
ssh root@<your-server-ip>
```

### Обновление системы

```bash
apt update
apt upgrade -y
```

### Системные зависимости

```bash
apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    git \
    curl \
    nano \
    htop \
    ufw
```

Проверка версии Python:

```bash
python3 --version
# Должно быть Python 3.10 или новее
```

### Установка временной зоны

```bash
timedatectl set-timezone Europe/Moscow
```

---

## Развёртывание приложения

### Клонирование репозитория

```bash
cd /root
git clone https://github.com/AleksandrVNikolaev/plotfinder.git
cd plotfinder
```

> Если планируешь хранить проект под другим путём — измени соответственно. На текущем боевом сервере используется исторический путь `/root/rosreestr_api/`.

### Виртуальное окружение

```bash
cd /root/plotfinder/backend
python3 -m venv venv
source venv/bin/activate
```

После активации в начале строки терминала появится `(venv)`.

### Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Установка занимает 1–3 минуты, скачивает около 80 МБ пакетов (FastAPI, uvicorn с extras, pdfplumber, pdfminer.six, и т.д.).

### Проверка установки

```bash
pip freeze | grep -iE "fastapi|uvicorn|pydantic|requests|toolbox|pdfplumber"
```

Ожидаемый вывод:

```
fastapi==0.116.1
pdfplumber==0.11.9
pydantic==2.11.7
requests==2.32.5
toolbox-sdk==0.1.0b4
uvicorn==0.35.0
```

### Конфигурация переменных окружения

```bash
cp .env.example .env
nano .env
```

Прописать в `.env`:

```env
TOOLBOX_API_KEY=<реальный-ключ-NextGIS>
OPENROUTER_API_KEY=sk-or-v1-<реальный-ключ-OpenRouter>
GEOJSON_DIR=/root/plotfinder/backend/output/geojson
```

Сохранить (`Ctrl+O`, `Enter`, `Ctrl+X`).

> ⚠ Файл `.env` НЕ коммитится в git — он заблокирован в `.gitignore`. Прописывать ключи можно только на сервере.

### Тестовый запуск

```bash
# Активировать venv если ещё не активирован
source /root/plotfinder/backend/venv/bin/activate

# Запустить
cd /root/plotfinder/backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

Откроется сервер. Проверить из второго SSH-окна:

```bash
curl "http://localhost:8000/api/rosreestr2coord?cadastral=39:05:030615:27"
```

Должен вернуться GeoJSON. Если всё работает — остановить сервер `Ctrl+C` и переходить к настройке systemd.

---

## Настройка systemd

Для автозапуска при перезагрузке сервера и автоматического перезапуска при падении используется systemd unit.

### Создание unit-файла

```bash
nano /etc/systemd/system/plotfinder.service
```

Содержимое:

```ini
[Unit]
Description=PlotFinder FastAPI Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/plotfinder/backend
Environment="PATH=/root/plotfinder/backend/venv/bin"
EnvironmentFile=/root/plotfinder/backend/.env
ExecStart=/root/plotfinder/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=plotfinder

[Install]
WantedBy=multi-user.target
```

Сохранить и закрыть.

### Активация сервиса

```bash
# Перечитать конфигурацию systemd
systemctl daemon-reload

# Включить автозапуск при загрузке системы
systemctl enable plotfinder

# Запустить прямо сейчас
systemctl start plotfinder

# Проверить статус
systemctl status plotfinder
```

В выводе `systemctl status` должно быть:

```
● plotfinder.service - PlotFinder FastAPI Backend
     Loaded: loaded (/etc/systemd/system/plotfinder.service; enabled; ...)
     Active: active (running) since ...
```

### Управление сервисом

```bash
# Перезапустить (после обновления кода)
systemctl restart plotfinder

# Остановить
systemctl stop plotfinder

# Проверить, запущен ли
systemctl is-active plotfinder

# Отключить автозапуск
systemctl disable plotfinder
```

### Параметры unit-файла

| Параметр | Значение | Назначение |
|---|---|---|
| `Type=simple` | — | systemd считает процесс запущенным сразу после старта |
| `Restart=always` | — | Перезапуск при любом завершении (краш, exit) |
| `RestartSec=5` | 5 сек | Пауза перед рестартом, чтобы не зацикливаться при ошибке конфигурации |
| `EnvironmentFile` | `.env` | Загрузка переменных окружения из файла |
| `WantedBy=multi-user.target` | — | Автозапуск на стандартном уровне работы системы |

---

## Сетевая безопасность

### Настройка UFW (firewall)

```bash
# Разрешить SSH (важно сделать ДО включения!)
ufw allow 22/tcp

# Разрешить порт сервиса
ufw allow 8000/tcp

# Включить firewall
ufw enable

# Проверить статус
ufw status verbose
```

Ожидаемый вывод:

```
Status: active
To                         Action      From
--                         ------      ----
22/tcp                     ALLOW       Anywhere
8000/tcp                   ALLOW       Anywhere
22/tcp (v6)                ALLOW       Anywhere (v6)
8000/tcp (v6)              ALLOW       Anywhere (v6)
```

### Защита SSH

После настройки рекомендуется:

1. Отключить вход по паролю (только SSH-ключи):

```bash
nano /etc/ssh/sshd_config
```

Установить:
```
PasswordAuthentication no
PubkeyAuthentication yes
```

```bash
systemctl restart sshd
```

2. Сменить порт SSH с 22 на нестандартный (опционально, но снижает шум от bot-сканеров):

```
Port 2222
```

И обновить UFW:
```bash
ufw allow 2222/tcp
ufw delete allow 22/tcp
```

---

## Мониторинг и логи

### Просмотр логов через journald

```bash
# Live-просмотр (как tail -f)
journalctl -u plotfinder -f

# Логи за сегодня
journalctl -u plotfinder --since today

# Логи за последние 100 строк
journalctl -u plotfinder -n 100

# Логи между датами
journalctl -u plotfinder --since "2026-05-01" --until "2026-05-07"

# Только ошибки
journalctl -u plotfinder -p err
```

### Что должно быть видно в логах при нормальной работе

```
[INFO] plotfinder: Toolbox: участок 39:05:030615:27 найден
[INFO] plotfinder: OpenRouter HTTP 200 for 39:05:030615:27
[INFO] plotfinder: finish_reason=stop, raw_len=1247, usage={'prompt_tokens': ...}
[INFO] plotfinder: LLM JSON parsed OK; keys=['summary', 'risks', ...]
```

### Признаки проблем в логах

| Сообщение | Что происходит | Что делать |
|---|---|---|
| `OpenRouter API error` | OpenRouter вернул ошибку | Проверить баланс OpenRouter, перевыпустить ключ |
| `extract_json failed` | LLM вернул некорректный JSON | Проверить запрос в логе; пользователь получит fallback |
| `Toolbox: участок ... не найден` | NextGIS не нашёл участок | Норма для несуществующих кадастров |
| `OPENROUTER_API_KEY не задан` | Сервис упал при старте | Проверить `.env`, перезапустить service |

### Проверка здоровья сервиса

```bash
# Простая проверка доступности
curl -I http://localhost:8000/docs
# Ожидается: HTTP/1.1 200 OK

# Полная проверка работоспособности
curl "http://localhost:8000/api/rosreestr2coord?cadastral=39:05:030615:27"
# Ожидается: GeoJSON с FeatureCollection
```

### Использование ресурсов

```bash
# Текущие процессы PlotFinder
ps auxf | grep -E "python|uvicorn" | grep -v grep

# Использование RAM/CPU процессом
top -p $(pgrep -f "uvicorn main:app")

# Размер кэша GeoJSON
du -sh /root/plotfinder/backend/output/geojson/

# Свободное место на диске
df -h /
```

---

## Резервное копирование

### Что нужно бэкапить

| Файл/директория | Критичность | Регулярность |
|---|---|---|
| `/root/plotfinder/backend/.env` | **Критично** | После каждого изменения ключей |
| `/root/plotfinder/backend/output/geojson/` | Низкая | Не нужен — пересоздаётся из Toolbox |
| Системный snapshot Selectel | Средняя | Раз в неделю автоматически |
| Git-репозиторий на GitHub | Высокая | После каждого commit |

### Бэкап `.env`

```bash
cp /root/plotfinder/backend/.env /root/.env.backup.$(date +%Y%m%d)
```

Хранить в безопасном месте **не на сервере** (зашифрованный файл, password manager, и т.п.).

### Снапшоты Selectel

В панели Selectel → Облачные серверы → твой сервер → Снапшоты → Создать снапшот.

Рекомендуется делать перед:
- Обновлением Ubuntu
- Перезапуском Python после `pip install`
- Любыми экспериментами с конфигурацией systemd/firewall

Хранится в облаке Selectel, тариф ~50 ₽/мес за GB.

---

## Перевыпуск API-ключей

В случае компрометации (попадание в репозиторий, в чат, в скриншот) ключи нужно перевыпустить **немедленно**.

### Перевыпуск OpenRouter

1. Зайти на [openrouter.ai/keys](https://openrouter.ai/keys)
2. Найти текущий ключ → нажать иконку отзыва (🗑) → подтвердить
3. **Create New** → задать имя (например `plotfinder-prod-2026-05`)
4. Скопировать новый ключ (формат `sk-or-v1-...`) — **показывается только один раз**
5. На сервере:

```bash
nano /root/plotfinder/backend/.env
# Заменить значение OPENROUTER_API_KEY
```

6. Перезапустить сервис:

```bash
systemctl restart plotfinder
systemctl status plotfinder
```

### Перевыпуск NextGIS Toolbox

1. Зайти на [my.nextgis.com](https://my.nextgis.com/)
2. Раздел Tokens → найти текущий → отозвать
3. Создать новый
4. Аналогично обновить `.env` и перезапустить сервис

### Проверка после перевыпуска

```bash
# Проверить, что сервис запустился
systemctl status plotfinder

# Проверить, что API работает
curl "http://localhost:8000/api/rosreestr2coord?cadastral=39:05:030615:27"

# Посмотреть логи на ошибки
journalctl -u plotfinder --since "5 minutes ago"
```

Если `journalctl` показывает `OPENROUTER_API_KEY не задан` или `Authorization error` — проверить правильность копирования ключа в `.env` (нет лишних пробелов, кавычек, переносов).

---

## Чек-лист после развёртывания

После завершения развёртывания пройти по списку:

- [ ] Сервер доступен по SSH с твоего компьютера
- [ ] `python3 --version` показывает 3.10+
- [ ] `systemctl status plotfinder` — Active: active (running)
- [ ] `curl "http://localhost:8000/docs"` возвращает HTML страницу Swagger
- [ ] `curl "http://localhost:8000/api/rosreestr2coord?cadastral=39:05:030615:27"` возвращает GeoJSON
- [ ] `journalctl -u plotfinder` не содержит ошибок ERROR/CRITICAL
- [ ] `ufw status` показывает разрешённые 22/tcp и 8000/tcp
- [ ] Внешний URL работает: `curl "http://<ip-сервера>:8000/docs"` с твоего компьютера
- [ ] `systemctl is-enabled plotfinder` возвращает `enabled` (автозапуск настроен)
- [ ] Резервная копия `.env` сохранена в безопасном месте
- [ ] Снапшот сервера в Selectel создан (на случай отката)

После прохождения чек-листа обновить статус в `/docs/architecture.md` или README репозитория, если есть.

---

## Рекомендуемые улучшения для production

Текущая конфигурация — MVP-уровень, достаточный для защиты ВКР и пилотного использования. Для коммерческой эксплуатации рекомендуется реализовать следующие улучшения. Они входят в этап 2 дорожной карты PlotFinder.

### 1. Запуск под отдельным пользователем (не root)

**Зачем:** уменьшает поверхность атаки. Если кто-то найдёт уязвимость в Python-коде, он не сможет получить root прямо.

```bash
# Создать пользователя
useradd -m -s /bin/bash plotfinder
usermod -aG sudo plotfinder  # опционально, для административных задач

# Перенести проект
mv /root/plotfinder /home/plotfinder/
chown -R plotfinder:plotfinder /home/plotfinder/plotfinder

# В systemd unit заменить:
# User=root → User=plotfinder
# WorkingDirectory=/root/... → /home/plotfinder/...
# и пути к venv и .env
```

### 2. Reverse proxy через nginx

**Зачем:** скрывает Uvicorn от внешнего мира, добавляет логирование запросов, кэш статики, rate limiting.

```bash
apt install nginx
nano /etc/nginx/sites-available/plotfinder
```

Минимальный конфиг:

```nginx
server {
    listen 80;
    server_name plotfinder.ru www.plotfinder.ru;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout под долгие запросы к LLM
        proxy_read_timeout 180s;
        proxy_connect_timeout 75s;
    }
}
```

Активация:

```bash
ln -s /etc/nginx/sites-available/plotfinder /etc/nginx/sites-enabled/
nginx -t  # проверка конфигурации
systemctl restart nginx
ufw allow 80/tcp
ufw delete allow 8000/tcp  # порт сервиса больше не нужен извне
```

### 3. HTTPS через Let's Encrypt

**Зачем:** обязательно для production: защищает от MITM, требуется браузерами, важен для SEO.

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d plotfinder.ru -d www.plotfinder.ru
# Автоматически добавит HTTPS-блок в nginx-конфиг и настроит автообновление
```

После этого сервис будет доступен по `https://plotfinder.ru/` с авто-редиректом с HTTP.

### 4. Доменное имя

Купить домен (например, `plotfinder.ru` за ~700 ₽/год через REG.RU) и настроить A-запись на IP сервера. Затем `certbot` выпустит SSL-сертификат.

### 5. Внешний мониторинг

Настроить health-check через бесплатные сервисы:
- **UptimeRobot** — пингует endpoint раз в 5 минут, шлёт email/Telegram при падении
- **Better Uptime** — аналогично, плюс status-page для внешних пользователей

Health-check URL: `https://plotfinder.ru/docs` (Swagger UI всегда возвращает 200 если сервис жив).

### 6. Rate limiting

Через nginx-уровень:

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/m;

location /api/ {
    limit_req zone=api burst=20 nodelay;
    proxy_pass http://127.0.0.1:8000;
    # ... остальные параметры
}
```

Это защитит от случайного/намеренного злоупотребления API.

### 7. Логирование в файлы

В дополнение к journald:

```bash
# Создать директорию
mkdir -p /var/log/plotfinder

# Добавить в systemd unit:
StandardOutput=append:/var/log/plotfinder/access.log
StandardError=append:/var/log/plotfinder/error.log
```

Настроить ротацию через `logrotate`:

```bash
nano /etc/logrotate.d/plotfinder
```

```
/var/log/plotfinder/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    sharedscripts
    postrotate
        systemctl reload plotfinder > /dev/null 2>&1 || true
    endscript
}
```

---

## Восстановление после сбоев

### Сервис не запускается

```bash
# Посмотреть последние логи
journalctl -u plotfinder -n 50 --no-pager

# Проверить .env
cat /root/plotfinder/backend/.env

# Проверить, что порт не занят
ss -tlnp | grep 8000

# Запустить вручную, чтобы увидеть точную ошибку
cd /root/plotfinder/backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

Типичные причины:
- Не задан `OPENROUTER_API_KEY` или `TOOLBOX_API_KEY` в `.env`
- Конфликт с другим процессом на порту 8000
- Удалён или переименован venv

### Сервис запущен, но возвращает 500

```bash
# Посмотреть логи
journalctl -u plotfinder -f

# Воспроизвести запрос
curl -v "http://localhost:8000/api/rosreestr2coord?cadastral=39:05:030615:27"
```

Возможные причины:
- Закончился баланс OpenRouter — пополнить или подождать обновления квоты
- Истёк/отозван ключ NextGIS Toolbox — перевыпустить
- Сетевые проблемы между сервером и openrouter.ai/toolbox.nextgis.com

### Сервер недоступен по SSH

В крайнем случае:

1. Зайти в панель Selectel
2. Открыть консоль через web-интерфейс (KVM-доступ)
3. Войти под root
4. Проверить состояние SSH:

```bash
systemctl status sshd
ufw status
```

5. Если что-то сломано в UFW — временно отключить:

```bash
ufw disable
```

Или восстановить из снапшота через панель Selectel.

---

## Связанные документы

- [`backend/README.md`](../backend/README.md) — установка backend локально для разработки
- [`docs/architecture.md`](architecture.md) — общая архитектура системы
- [`docs/api-reference.md`](api-reference.md) — спецификация REST API
