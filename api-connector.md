# API Connector — настройка подключений из Bubble

Описание всех настроенных в Bubble.io подключений к внешним API. Документ описывает связь фронтенда с backend FastAPI и со сторонними сервисами.

> Все API-ключи и токены замаскированы. Их реальные значения хранятся в настройках Bubble API Connector и не публикуются.

---

## Содержание

- [Что такое API Connector](#что-такое-api-connector)
- [Обзор настроенных подключений](#обзор-настроенных-подключений)
- [Подключение 1: PlotFinder Backend — Rosreestr](#подключение-1-plotfinder-backend--rosreestr)
- [Подключение 2: PlotFinder Backend — Legal Analysis](#подключение-2-plotfinder-backend--legal-analysis)
- [Подключение 3: GitHub API — Daily Backup](#подключение-3-github-api--daily-backup)
- [Recurring Event: Save Snapshot to GitHub](#recurring-event-save-snapshot-to-github)
- [Безопасность хранения ключей](#безопасность-хранения-ключей)
- [Как добавить новый endpoint](#как-добавить-новый-endpoint)
- [Связь с workflows](#связь-с-workflows)

---

## Что такое API Connector

**API Connector** — встроенный плагин Bubble для подключения к внешним REST API. Позволяет настроить запросы (методы, URL, headers, body) через UI без написания кода и использовать их в workflows как обычные действия.

Каждое подключение в API Connector состоит из:

- **Connector** (родительская группа) — общие настройки: shared headers, shared params, авторизация
- **Calls** (дочерние методы) — конкретные endpoints с отдельными параметрами

В PlotFinder настроены **3 Connector'а** с **7 Calls** в сумме.

---

## Обзор настроенных подключений

| Connector | Calls | Назначение | Тип |
|---|---|---|---|
| **PlotFinder Backend — Rosreestr** | 3 | Получение геометрии участка | Action / Data |
| **PlotFinder Backend — Legal Analysis** | 2 | AI-анализ юр. рисков | Action |
| **GitHub API — Daily Backup** | 2 | Резервирование данных в GitHub | Action |

Все Calls используют HTTP/JSON, без авторизации со стороны клиента (для backend) или с API-ключом в headers (для GitHub).

---

## Подключение 1: PlotFinder Backend — Rosreestr

Группа методов для получения геометрии земельного участка из NextGIS Toolbox через прокси FastAPI.

### Общие настройки Connector'а

| Параметр | Значение |
|---|---|
| **Authentication type** | None (backend сам не требует авторизации) |
| **Base URL** | не задан (полные URL в каждом call) |
| **Shared headers** | — |
| **Shared params** | — |

### Call 1.1: Rosreestr2coord Action

Используется как **Action** (выполнение запроса в workflow с возможностью использовать результат).

| Параметр | Значение |
|---|---|
| **Method** | GET |
| **URL** | `http://79.143.24.76:8000/api/rosreestr2coord?cadastral={cadastral}` |
| **Use as** | Action |
| **Initialize** | необходим перед использованием в workflow |

#### Параметры

| Параметр | Тип | Источник | Описание |
|---|---|---|---|
| `{cadastral}` | text | Dynamic data из workflow | Кадастровый номер участка |

#### Структура ответа (после инициализации Bubble распознал)

GeoJSON FeatureCollection — см. [`docs/api-reference.md`](../docs/api-reference.md#get-apirosreestr2coord) для детальной схемы.

### Call 1.2: Rosreestr2coord Data (json)

Тот же endpoint, но используется как **Data Source** (для отображения в repeating groups, элементах с динамическим содержимым).

| Параметр | Значение |
|---|---|
| **Method** | GET |
| **URL** | `http://79.143.24.76:8000/api/rosreestr2coord?cadastral={cadastral}` |
| **Use as** | Data |
| **Body type** | JSON |

### Call 1.3: Rosreestr2coord Action (text)

Резервный вариант — тот же endpoint, но Bubble обрабатывает ответ как text вместо JSON. Используется когда нужно получить сырой текст ответа (для отладки или передачи в другой call).

| Параметр | Значение |
|---|---|
| **Method** | GET |
| **URL** | `http://79.143.24.76:8000/api/rosreestr2coord?cadastral={cadastral}` |
| **Use as** | Action |
| **Body type** | Text |

> **Замечание:** наличие трёх calls к одному endpoint'у — не идеальная архитектура. Обычно достаточно двух (Action + Data). Текстовый вариант, скорее всего, остался от ранней отладки. Кандидат на удаление при рефакторинге.

---

## Подключение 2: PlotFinder Backend — Legal Analysis

Группа методов для запуска AI-анализа юридических рисков через backend.

### Общие настройки Connector'а

| Параметр | Значение |
|---|---|
| **Authentication type** | None |
| **Base URL** | не задан |

### Call 2.1: Legal Analyze Plot

Простой анализ только по кадастровому номеру (без PDF).

| Параметр | Значение |
|---|---|
| **Method** | POST |
| **URL** | `http://79.143.24.76:8000/api/legal/analyze-plot` |
| **Use as** | Action |
| **Content-Type** | application/json |

#### Body

```json
{
  "cadastral": "<cadastral>"
}
```

#### Параметры

| Параметр | Тип | Источник | Описание |
|---|---|---|---|
| `<cadastral>` | text | Dynamic data из workflow | Кадастровый номер |

### Call 2.2: Legal Analyze Plot With Doc

Расширенный анализ с прикреплённым PDF выписки ЕГРН. **Это основной endpoint** — используется в главном workflow «Кнопка Проанализировать нажата».

| Параметр | Значение |
|---|---|
| **Method** | POST |
| **URL** | `http://79.143.24.76:8000/api/legal/analyze-plot-with-doc` |
| **Use as** | Action |
| **Content-Type** | application/x-www-form-urlencoded или query string |

#### Параметры

| Параметр | Тип | Источник | Описание |
|---|---|---|---|
| `cadastral` | text query | Dynamic data | Кадастровый номер |
| `document_url` | text query | FileUploader's value | URL загруженного PDF (опционально) |

> **Важно:** этот endpoint принимает параметры через **query string**, а не через JSON body. Это особенность реализации backend (см. `main.py`, строки 547–551). При настройке в Bubble нужно правильно сконфигурировать query parameters, а не body params.

---

## Подключение 3: GitHub API — Daily Backup

Группа методов для автоматического резервирования данных в отдельный GitHub-репозиторий.

> ⚠ **Историческая заметка:** этот connector использовался для daily backup данных Bubble в репозиторий `AleksandrVNikolaev/bubble-project`. В прошлом в нём был зашит GitHub Personal Access Token, который **был отозван** после публикации `.bubble` файла в качестве инцидента безопасности. Если это подключение продолжает использоваться — необходимо создать новый fine-grained токен и обновить настройки.

### Общие настройки Connector'а

| Параметр | Значение |
|---|---|
| **Authentication type** | Private key in header |
| **Header name** | `Authorization` |
| **Header value** | `Bearer <GITHUB_TOKEN>` (значение замаскировано) |
| **Shared headers** | `Accept: application/vnd.github.v3+json` |

### Call 3.1: Get Repo Contents

Получает список файлов в указанном пути репозитория. Используется чтобы проверить актуальный SHA файла перед его обновлением (требование GitHub API для PUT-запросов).

| Параметр | Значение |
|---|---|
| **Method** | GET |
| **URL** | `https://api.github.com/repos/AleksandrVNikolaev/bubble-project/contents/` |
| **Use as** | Action |

### Call 3.2: Create or Update File

Создаёт или обновляет файл в репозитории. В текущей реализации — обновляет `README.md` со снимком данных Bubble.

| Параметр | Значение |
|---|---|
| **Method** | PUT |
| **URL** | `https://api.github.com/repos/AleksandrVNikolaev/bubble-project/contents/README.md` |
| **Use as** | Action |
| **Content-Type** | application/json |

#### Body

```json
{
  "message": "<message>",
  "content": "<content>",
  "sha": "<sha>"
}
```

#### Параметры

| Параметр | Тип | Источник | Описание |
|---|---|---|---|
| `<message>` | text | Workflow | Commit message (например, `Daily snapshot 2026-05-07`) |
| `<content>` | text | Workflow | Содержимое файла, закодированное в base64 |
| `<sha>` | text | Get Repo Contents | SHA текущей версии файла (нужен для PUT) |

> **Архитектурное замечание:** хранение Bubble-данных в GitHub-файле — нестандартный паттерн. Обычно для бэкапов используют S3, Dropbox или встроенные механизмы Bubble. Решение через GitHub использовалось из-за бесплатности и удобства Git-истории. Для production-эксплуатации **рекомендуется заменить** на корректное решение — Selectel S3 или встроенный Bubble Backup.

---

## Recurring Event: Save Snapshot to GitHub

В дополнение к API Connector'у, в Bubble настроено **Recurring Event** для автоматического запуска бэкапа.

| Параметр | Значение |
|---|---|
| **Event name** | Save Snapshot to GitHub |
| **Event type** | Recurring (повторяющийся) |
| **Period** | Daily (раз в день) |
| **Custom event data type** | `custom.plot` (запускается для каждого Plot) |
| **Ignore privacy rules** | Yes (системный workflow) |

### Шаги workflow

1. **Get Repo Contents** (через Call 3.1) — получить актуальный SHA файла
2. **Create or Update File** (через Call 3.2) — сохранить новое содержимое с правильным SHA

### Текущий статус

После security incident'а с утечкой GitHub-токена workflow может быть **временно неработоспособен** — нужно прописать новый токен в API Connector. Альтернативно — отключить Recurring Event и заменить решение на стандартное.

---

## Безопасность хранения ключей

### Где Bubble хранит API-ключи

API-ключи и токены в Bubble хранятся в двух местах:

1. **Plain в настройках Connector** — если поле помечено как обычный header. Эти значения попадают в **client-side код** при загрузке страницы и видны через DevTools браузера. **Использовать только для public ключей.**

2. **Server-side только** — если поле помечено флагом **«This call is private»** в Bubble. Тогда ключ хранится в backend Bubble и не передаётся клиенту.

### Что нужно проверить в текущих настройках

| Connector | Public/Private | Риск |
|---|---|---|
| PlotFinder Backend (оба) | Public (не нужен ключ) | — |
| GitHub API | **Должен быть Private** | Если Public — токен виден в DevTools любого пользователя |

### Рекомендации

1. **GitHub Connector** — обязательно пометить как Private (флаг **«This call is private»**)
2. После любой смены токена — проверить что новое значение прописано в **Private** поле
3. Никогда не вставлять API-ключи в Body или Query параметры — только в Headers с флагом Private

---

## Как добавить новый endpoint

Если в будущем нужно добавить новый endpoint к backend (например, для этапа 2 дорожной карты — endpoint OCR или генерации PDF-отчёта):

1. Bubble Editor → **Plugins** → **API Connector** → найти существующий connector «PlotFinder Backend — Legal Analysis» (или создать новый)
2. **Add another call**
3. Заполнить:
   - **Name** — человекочитаемое имя
   - **Use as** — Action или Data
   - **Method** — HTTP-метод
   - **URL** — полный URL endpoint'а
   - **Параметры** — через `<placeholder>` в URL/body/headers
4. **Initialize call** — выполнить запрос с тестовыми данными чтобы Bubble распознал структуру ответа
5. **Save** — теперь call доступен в workflow editor как действие

---

## Связь с workflows

Каждый Call из API Connector используется в одном или нескольких workflows. Подробно — в [`workflows.md`](workflows.md) *(будет добавлено)*. Краткое сопоставление:

| Workflow | Используемый Call |
|---|---|
| Кнопка «Проанализировать» нажата (на index) | Call 2.2 — Legal Analyze Plot With Doc |
| Загрузка участков на главной (HTML map) | Bubble Data API `/obj/plot` (не через Connector) |
| Поиск участка по кадастру | Call 1.1 — Rosreestr2coord Action |
| Recurring «Save Snapshot to GitHub» | Calls 3.1 + 3.2 |

> Замечание: HTML-элемент карты загружает данные напрямую через `fetch()` к **Bubble Data API**, а не через API Connector. Это делается потому что Bubble Data API публично доступен для exposed Data Types — настройка Connector'а в этом случае избыточна.

---

## Связанные документы

- [`frontend/workflows.md`](workflows.md) *(будет добавлено)* — workflows, использующие эти подключения
- [`frontend/data-model.md`](data-model.md) — Data Types которые читают/пишут эти endpoint'ы
- [`backend/main.py`](../backend/main.py) — реализация endpoint'ов на стороне backend
- [`docs/api-reference.md`](../docs/api-reference.md) — полная спецификация REST API backend
