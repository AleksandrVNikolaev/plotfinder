# PlotFinder Backend

FastAPI-сервис юридической проверки земельных участков. Принимает кадастровый номер, опционально PDF выписки ЕГРН, обращается к NextGIS Toolbox API за геометрией и к OpenRouter (Qwen3-32B) за структурированным анализом юридических рисков.

---

## Стек

- **Python** 3.10+ (на production-сервере 3.11)
- **FastAPI** 0.116.1 — веб-фреймворк
- **Uvicorn** 0.35.0 — ASGI-сервер
- **Pydantic** 2.11.7 — валидация моделей
- **toolbox-sdk** 0.1.0b4 — клиент NextGIS Toolbox
- **pdfplumber** 0.11.9 — парсер PDF выписок ЕГРН
- **requests** 2.32.5 — HTTP-клиент для OpenRouter

Полный список с зафиксированными версиями — в `requirements.txt`.

---

## Требования

- **Python 3.10 или новее** (проверить: `python3 --version`)
- **API-ключ NextGIS Toolbox** — получить на [toolbox.nextgis.com](https://toolbox.nextgis.com/)
- **API-ключ OpenRouter** — получить на [openrouter.ai/keys](https://openrouter.ai/keys)
- ~50 МБ свободного места под виртуальное окружение и кэш GeoJSON

---

## Установка локально

### 1. Клонировать репозиторий

```bash
git clone https://github.com/AleksandrVNikolaev/plotfinder.git
cd plotfinder/backend
```

### 2. Создать виртуальное окружение

```bash
python3 -m venv venv
```

### 3. Активировать окружение

**Linux / macOS:**
```bash
source venv/bin/activate
```

**Windows (cmd):**
```cmd
venv\Scripts\activate.bat
```

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

### 4. Установить зависимости

```bash
pip install -r requirements.txt
```

### 5. Настроить переменные окружения

```bash
cp .env.example .env
```

Открыть `.env` в редакторе и заполнить:

```env
TOOLBOX_API_KEY=ваш-реальный-ключ-от-NextGIS
OPENROUTER_API_KEY=sk-or-v1-ваш-реальный-ключ-OpenRouter
```

> ⚠ Файл `.env` заблокирован в `.gitignore` и **никогда не коммитится** в репозиторий.

### 6. Запустить сервер

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Сервер будет доступен на `http://localhost:8000`.

Автоматически генерируемая документация Swagger UI: `http://localhost:8000/docs`

---

## Endpoints

Сервис предоставляет 4 endpoint'а: один для получения геометрии участка и три для юридического анализа разной глубины.

### `GET /api/rosreestr2coord`

Получает геометрию земельного участка из Росреестра (через NextGIS Toolbox) по кадастровому номеру. Результат кэшируется локально.

**Query-параметры:**
- `cadastral` (string, обязательный) — кадастровый номер в формате `XX:XX:XXXXXXX:XX`

**Пример запроса:**

```bash
curl "http://localhost:8000/api/rosreestr2coord?cadastral=39:05:030615:27"
```

**Структура ответа:** GeoJSON `FeatureCollection` с одним `Feature`, содержащим геометрию участка и properties с площадью, категорией, ВРИ, адресом и т.д.

---

### `POST /api/legal/analyze-text`

Mock-анализ юридических рисков по произвольному тексту. Использует rule-based ключевые слова, не обращается к LLM. Применяется для тестирования pipeline без расхода квоты OpenRouter.

**Тело запроса (JSON):**

```json
{
  "text": "Произвольный текст с упоминанием ограничений или обременений",
  "cadastral_number": "39:05:030615:27",
  "user_comment": "Опциональный фокус анализа"
}
```

**Пример запроса:**

```bash
curl -X POST "http://localhost:8000/api/legal/analyze-text" \
  -H "Content-Type: application/json" \
  -d '{"text": "Объект имеет ограничение в виде охранной зоны ЛЭП", "cadastral_number": "39:05:030615:27"}'
```

---

### `POST /api/legal/analyze-plot`

Полный AI-анализ участка по кадастровому номеру через Qwen3-32B. Возвращает структурированный риск-профиль: оценку риска 0–100, summary одной строкой, список рисков по категориям, рекомендации к сделке.

**Тело запроса (JSON):**

```json
{
  "cadastral": "39:05:030615:27"
}
```

**Пример запроса:**

```bash
curl -X POST "http://localhost:8000/api/legal/analyze-plot" \
  -H "Content-Type: application/json" \
  -d '{"cadastral": "39:05:030615:27"}'
```

**Время отклика:** 30–120 секунд (зависит от загруженности OpenRouter и модели Qwen3-32B).

---

### `POST /api/legal/analyze-plot-with-doc`

Расширенный AI-анализ: помимо геометрии участка из Росреестра, дополнительно парсится приложенная PDF-выписка ЕГРН и передаётся в LLM как контекст. Это даёт более точный анализ — модель видит реальные данные о собственнике, обременениях и истории прав.

**Query-параметры:**
- `cadastral` (string, обязательный) — кадастровый номер
- `document_url` (string, опциональный) — URL PDF-файла выписки ЕГРН

**Пример запроса:**

```bash
curl -X POST "http://localhost:8000/api/legal/analyze-plot-with-doc?cadastral=39:05:030615:27&document_url=https://example.com/extract.pdf"
```

**Время отклика:** до 2 минут (с учётом скачивания и парсинга PDF).

---

## Тестовые кадастры

Эти кадастровые номера проверены на боевом сервере и стабильно возвращают данные:

- `39:05:030615:27`
- `39:05:030616:430`
- `39:05:030615:286`

Все три участка расположены в Калининградской области. Для тестирования различных риск-профилей рекомендуется использовать `39:05:030615:27` — на нём активирована проверка с показом среднего уровня риска.

---

## Production deployment

### Боевое окружение PlotFinder MVP

- **Провайдер:** Selectel, регион ru-2a
- **Конфигурация:** 2 vCPU / 4 ГБ RAM / 5 ГБ SSD
- **ОС:** Ubuntu 22.04 LTS
- **Python:** 3.11
- **Стоимость:** ~3 790 ₽/мес

### Развёртывание на сервере Ubuntu 22.04

```bash
# Установить системные зависимости
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# Клонировать проект
git clone https://github.com/AleksandrVNikolaev/plotfinder.git /root/plotfinder
cd /root/plotfinder/backend

# Создать venv и установить зависимости
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Настроить переменные окружения
cp .env.example .env
nano .env  # прописать реальные ключи

# Тестовый запуск (Ctrl+C для остановки)
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Автозапуск через systemd

Для production-эксплуатации сервис запускается под systemd. Пример unit-файла `/etc/systemd/system/plotfinder.service`:

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

[Install]
WantedBy=multi-user.target
```

Активация:

```bash
sudo systemctl daemon-reload
sudo systemctl enable plotfinder
sudo systemctl start plotfinder
sudo systemctl status plotfinder    # проверить что запустился
```

Логи:

```bash
journalctl -u plotfinder -f          # follow live
journalctl -u plotfinder --since today
```

---

## Структура файлов

```
backend/
├── main.py              ← основной модуль FastAPI со всеми endpoints
├── requirements.txt     ← Python-зависимости с зафиксированными версиями
├── .env.example         ← шаблон переменных окружения
├── .env                 ← реальные ключи (не в git!)
└── README.md            ← этот файл
```

При первом запуске автоматически создаётся директория `output/geojson/` для кэша геометрий участков.

---

## Логи и устойчивость

### Логирование

Используется стандартный модуль `logging` с уровнем `INFO`. Все ключевые операции (запрос к Toolbox, обращение к LLM, ошибки парсинга) пишутся в stdout, который перехватывается systemd journald на сервере.

### Механизмы устойчивости

В коде реализованы 5 механизмов отказоустойчивости:

1. **`extract_json()`** — устойчивый парсер ответа LLM, корректно обрабатывает `<think>`-теги, markdown-фенсы, хвостовую прозу
2. **`fallback_profile`** — дефолтный риск-профиль если LLM вернул некорректный JSON или упал
3. **Нормализация Bubble CDN URL** — автодополнение протокола для URL приходящих от no-code фронтенда
4. **`not_found` ответ** — структурированный 404-эквивалент с HTTP 200 для удобства фронтенда
5. **Кэш GeoJSON** — локальное хранение геометрий участков, повторные запросы не идут в Toolbox

---

## Перевыпуск API-ключей

Если ключи случайно попали в публичный репозиторий или в чат с LLM — их нужно перевыпустить:

**OpenRouter:**
1. Зайти на [openrouter.ai/keys](https://openrouter.ai/keys)
2. Найти текущий ключ → **Revoke**
3. **Create New** → скопировать новый
4. Обновить `OPENROUTER_API_KEY` в `.env` на сервере
5. Перезапустить сервис: `sudo systemctl restart plotfinder`

**NextGIS Toolbox:**
1. Зайти в личный кабинет на [toolbox.nextgis.com](https://toolbox.nextgis.com/)
2. Раздел API tokens → отозвать текущий ключ
3. Создать новый
4. Обновить `TOOLBOX_API_KEY` в `.env` на сервере
5. Перезапустить сервис

---

## Контекст проекта

Этот backend разработан в рамках выпускной квалификационной работы:

- **Тема:** Создание веб-сервиса размещения и поиска объявлений о купле-продаже земельных участков с интеграцией данных Росреестра и функционалом анализа юридических рисков совершения сделок
- **Автор:** Николаев Александр Владиславович
- **ВУЗ:** НИУ ВШЭ
- **Программа:** Магистерская программа «ЛигалТех»
- **Год:** 2026

Полная документация проекта — в корневом `README.md` репозитория.
