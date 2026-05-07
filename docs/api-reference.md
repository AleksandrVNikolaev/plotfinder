# API Reference

Полная спецификация REST API сервиса PlotFinder. Документация описывает все 4 endpoint'а: формат запроса, структуру ответа, коды ошибок, примеры использования.

---

## Содержание

- [Базовая информация](#базовая-информация)
- [Стандарты ответов](#стандарты-ответов)
- [Endpoints](#endpoints)
  - [`GET /api/rosreestr2coord`](#get-apirosreestr2coord)
  - [`POST /api/legal/analyze-text`](#post-apilegalanalyze-text)
  - [`POST /api/legal/analyze-plot`](#post-apilegalanalyze-plot)
  - [`POST /api/legal/analyze-plot-with-doc`](#post-apilegalanalyze-plot-with-doc)
- [Коды ошибок](#коды-ошибок)
- [Тестовые кадастры](#тестовые-кадастры)
- [Лимиты и квоты](#лимиты-и-квоты)
- [Swagger UI](#swagger-ui)

---

## Базовая информация

### Base URL

```
http://79.143.24.76:8000
```

При локальной разработке:

```
http://localhost:8000
```

### Аутентификация

API в текущей версии **не требует аутентификации** — это MVP для демонстрации в рамках ВКР. В production-релизе планируется добавление JWT-токенов через Bubble Auth (Этап 2 дорожной карты).

### Content-Type

Все запросы и ответы используют JSON:

```
Content-Type: application/json
```

Исключение: `GET /api/rosreestr2coord` принимает параметры через query string.

### Кодировка

UTF-8. Все русскоязычные строки в JSON-ответах сериализуются без escape-последовательностей (`ensure_ascii=False`).

---

## Стандарты ответов

### Успешный ответ

HTTP-статус `200 OK`, тело — JSON с предметной схемой каждого endpoint'а.

### Ответ при отсутствии данных

При запросе кадастра, отсутствующего в Росреестре, возвращается **HTTP 200** с флагом `not_found: true` в теле:

```json
{
  "not_found": true,
  "summary": {
    "title": "Участок 39:05:000000:99 не найден",
    "cadnum": "39:05:000000:99",
    "address": null,
    "area_sqm": null,
    "area_source": "missing",
    "category": null,
    "ownership": null,
    "cost_rub": null,
    "date_reg": null
  },
  "summary_one_line": "Участок отсутствует в нашей базе данных. Проверьте кадастровый номер или повторите попытку позже.",
  "risk_score": "unknown",
  "risks": [],
  "recommendations": [],
  "sources": [],
  "analyzed_with_document": false,
  "document_chars": 0
}
```

> **Почему HTTP 200, а не 404:** упрощает обработку на стороне Bubble.io. Фронтенд проверяет одно поле `not_found` вместо разной обработки error-кодов.

### Ответ с ошибкой

HTTP-статус 4xx или 5xx, тело FastAPI стандарта:

```json
{
  "detail": "Описание ошибки"
}
```

### Fallback-ответ при сбое LLM

Если OpenRouter недоступен или Qwen3-32B вернул некорректный JSON, возвращается **HTTP 200** с риск-профилем, рассчитанным rule-based fallback'ом — без `summary_one_line` от модели, но со структурой полей и валидным `risk_score`.

---

## Endpoints

### `GET /api/rosreestr2coord`

Получает геометрию земельного участка по кадастровому номеру через NextGIS Toolbox API. Результат кэшируется локально в `output/geojson/`.

#### Query-параметры

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `cadastral` | string | да | Кадастровый номер в формате `XX:XX:XXXXXXX:XX` |

#### Пример запроса

```bash
curl "http://localhost:8000/api/rosreestr2coord?cadastral=39:05:030615:27"
```

#### Структура ответа

GeoJSON `FeatureCollection` с одним `Feature`:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [20.4523, 54.7104],
            [20.4527, 54.7104],
            [20.4527, 54.7107],
            [20.4523, 54.7107],
            [20.4523, 54.7104]
          ]
        ]
      },
      "properties": {
        "cadnum": "39:05:030615:27",
        "quarter": "39:05:030615",
        "address": "Калининградская обл, ...",
        "area": 1240.5,
        "category": "Земли населённых пунктов",
        "categoryFull": "Земельный участок (земли населённых пунктов)",
        "ownership": "Частная собственность",
        "cost": 1850000.00,
        "status": "Учтённый",
        "date_reg": "2014-08-22",
        "declared_area": 0,
        "cost_index": "",
        "util_by_doc": "Для индивидуального жилищного строительства",
        "type": "Земельный участок (земли населённых пунктов)",
        "label": ""
      }
    }
  ]
}
```

#### Описание полей `properties`

| Поле | Тип | Описание |
|---|---|---|
| `cadnum` | string | Кадастровый номер |
| `quarter` | string | Кадастровый квартал |
| `address` | string | Полный адрес участка |
| `area` | number | Уточнённая площадь, м² |
| `category` | string | Категория земель (краткая) |
| `categoryFull` | string | Категория земель (полная) |
| `ownership` | string | Тип собственности |
| `cost` | number | Кадастровая стоимость, ₽ |
| `status` | string | Статус записи в ЕГРН |
| `date_reg` | string | Дата регистрации (YYYY-MM-DD) |
| `declared_area` | number | Декларированная площадь, м² (если есть) |
| `util_by_doc` | string | Разрешённое использование по документу (ВРИ) |
| `type` | string | Тип объекта недвижимости |
| `label` | string | Внутренняя метка |

#### Возможные ошибки

| HTTP | Detail | Причина |
|---|---|---|
| 400 | `Некорректный кадастровый номер` | Кадастр не прошёл валидацию |
| 404 | `Архив не получен от Toolbox` | NextGIS не вернул ZIP с GeoJSON |
| 404 | `GeoJSON не найден в архиве` | ZIP пустой |
| 404 | `Нет объектов в GeoJSON` | Toolbox вернул пустой FeatureCollection |
| 404 | `Нет координат в GeoJSON` | Feature без geometry |
| 500 | `Ошибка: ...` | Непредвиденная ошибка сервера |

#### Время отклика

- Из кэша: **~50 мс**
- Из NextGIS Toolbox: **~2 секунды**

---

### `POST /api/legal/analyze-text`

Mock-анализ юридических рисков по произвольному тексту. Использует rule-based ключевые слова, не обращается к LLM. Применяется для тестирования pipeline без расхода квоты OpenRouter.

#### Тело запроса

```json
{
  "text": "string",
  "cadastral_number": "string (опц.)",
  "user_comment": "string (опц.)"
}
```

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `text` | string | да | Произвольный текст для анализа |
| `cadastral_number` | string | нет | Кадастровый номер для контекста |
| `user_comment` | string | нет | Дополнительный фокус анализа |

#### Пример запроса

```bash
curl -X POST "http://localhost:8000/api/legal/analyze-text" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Объект имеет ограничение в виде охранной зоны ЛЭП и записи об аресте",
    "cadastral_number": "39:05:030615:27",
    "user_comment": "Хочу купить под ИЖС"
  }'
```

#### Структура ответа

```json
{
  "summary": "В тексте обнаружены признаки повышенного правового риска.",
  "cadastral_number": "39:05:030615:27",
  "address": "",
  "area": "",
  "category": "",
  "allowed_use": "",
  "key_facts": [
    "Текст успешно получен сервером",
    "Mock-анализ юридического модуля выполнен"
  ],
  "risks": [
    {
      "type": "restriction",
      "level": "medium",
      "description": "В тексте найдены указания на ограничения или обременения.",
      "basis": "Обнаружены ключевые слова: огранич / обремен"
    },
    {
      "type": "dispute",
      "level": "high",
      "description": "В тексте есть признаки судебного спора, ареста или иного конфликтного статуса.",
      "basis": "Обнаружены ключевые слова: арест / спор / суд"
    }
  ],
  "missing_or_unclear": [],
  "recommendations": [
    "Проверить характер ограничений и их актуальность в действующей выписке.",
    "Проверить судебные споры, исполнительные производства и ограничения регистрационных действий."
  ],
  "overall_risk_level": "high",
  "disclaimer": "Это тестовый информационно-аналитический вывод. Не является юридическим заключением."
}
```

#### Логика rule-based анализа

| Ключевые слова в тексте | level | overall_risk_level |
|---|---|---|
| `огранич` или `обремен` | medium | `medium` |
| `арест`, `спор`, `суд` | high | `high` |
| Никакие из перечисленных | low | `low` (mock) |

#### Возможные ошибки

| HTTP | Detail | Причина |
|---|---|---|
| 400 | `text cannot be empty` | Поле `text` пустое или содержит только пробелы |
| 422 | Validation error | Невалидная JSON-структура запроса |

#### Время отклика

**~10 мс** — без внешних API.

---

### `POST /api/legal/analyze-plot`

Полный AI-анализ участка по кадастровому номеру через Qwen3-32B. Сначала получает геометрию (из кэша или Toolbox), затем передаёт нормализованные данные в LLM, получает структурированный риск-профиль.

#### Тело запроса

```json
{
  "cadastral": "string"
}
```

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `cadastral` | string | да | Кадастровый номер в формате `XX:XX:XXXXXXX:XX` |

#### Пример запроса

```bash
curl -X POST "http://localhost:8000/api/legal/analyze-plot" \
  -H "Content-Type: application/json" \
  -d '{"cadastral": "39:05:030615:27"}'
```

#### Структура ответа

```json
{
  "summary": {
    "title": "Участок 39:05:030615:27",
    "cadnum": "39:05:030615:27",
    "address": "Калининградская обл, ...",
    "area_sqm": 1240.5,
    "area_source": "area",
    "category": "Земли населённых пунктов",
    "ownership": "Частная собственность",
    "cost_rub": 1850000.00,
    "date_reg": "2014-08-22"
  },
  "summary_one_line": "Участок пригоден для ИЖС, риски средние из-за давности регистрации и отсутствия данных по ВРИ.",
  "risk_score": "medium",
  "risks": [
    {
      "severity": "medium",
      "title": "Давность регистрации",
      "reason": "Участок зарегистрирован более 10 лет назад, требуется сверка с актуальной выпиской ЕГРН.",
      "source_fields": ["properties.date_reg"]
    },
    {
      "severity": "low",
      "title": "ВРИ не проверено по выписке",
      "reason": "Анализ выполнен по кадастровым данным без приложенной выписки ЕГРН.",
      "source_fields": ["properties.util_by_doc"]
    }
  ],
  "recommendations": [
    "Закажите свежую выписку ЕГРН для проверки актуального статуса.",
    "Сверьте разрешённое использование с целью покупки."
  ],
  "sources": [
    "properties.cadnum",
    "properties.area",
    "properties.category",
    "properties.date_reg",
    "properties.util_by_doc"
  ]
}
```

#### Описание полей ответа

| Поле | Тип | Описание |
|---|---|---|
| `summary` | object | Структурированная сводка по участку |
| `summary.title` | string | Человекочитаемый заголовок |
| `summary.cadnum` | string \| null | Кадастровый номер |
| `summary.address` | string \| null | Адрес |
| `summary.area_sqm` | number \| null | Площадь, м² |
| `summary.area_source` | enum | Источник площади: `area` \| `declared_area` \| `missing` |
| `summary.category` | string \| null | Категория земель |
| `summary.ownership` | string \| null | Тип собственности |
| `summary.cost_rub` | number \| null | Кадастровая стоимость |
| `summary.date_reg` | string \| null | Дата регистрации (YYYY-MM-DD) |
| `summary_one_line` | string | Одна строка с главным выводом (≤180 символов) |
| `risk_score` | enum | Уровень риска: `low` \| `medium` \| `high` \| `unknown` |
| `risks` | array | Массив выявленных рисков (до 6 элементов) |
| `risks[].severity` | enum | `low` \| `medium` \| `high` |
| `risks[].title` | string | Название риска (≤70 символов) |
| `risks[].reason` | string | Обоснование (≤220 символов) |
| `risks[].source_fields` | array | Ссылки на поля исходных данных |
| `recommendations` | array | До 3 рекомендаций (≤160 символов каждая) |
| `sources` | array | Использованные поля исходных данных |

#### Логика risk_score (по системному промпту LLM)

| Условие | risk_score |
|---|---|
| `ownership` содержит государственная/муниципальная/федеральная | **high** |
| `category` = лесной/водный фонд/оборона/ООПТ | **high** |
| Отсутствуют `cadnum`/`category`/`address` | **high** |
| 3+ факторов medium | **high** |
| `status` = «Ранее учтённый» | medium |
| Возраст регистрации ≥ 15 лет | medium |
| `area_source` = `declared_area` | medium |
| Нет `cost_rub` | medium |
| `category` = сельхоз или промышленность | medium |
| Нет high и нет/минимум medium | **low** |

#### Возможные ошибки

| HTTP | Detail | Причина |
|---|---|---|
| 400 | `Некорректный кадастровый номер` | Кадастр не прошёл regex `^\d{2}:\d{2}:\d{1,8}:\d+$` |
| 200 | `not_found: true` | Участок отсутствует в Toolbox (см. секцию «Стандарты ответов») |
| 500 | `Ошибка: ...` | Непредвиденная ошибка |

При сбое OpenRouter или некорректном JSON от LLM возвращается **HTTP 200** с rule-based fallback-профилем.

#### Время отклика

**30–120 секунд** — основное время на инференс Qwen3-32B (max_tokens=4000, temperature=0.1).

---

### `POST /api/legal/analyze-plot-with-doc`

Расширенный AI-анализ: к данным участка из Росреестра дополнительно прикладывается распарсенный текст PDF-выписки ЕГРН. Это даёт более точный анализ — модель видит реальные данные о собственнике, обременениях и истории прав, не только из кадастровой карты.

#### Query-параметры

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `cadastral` | string | да | Кадастровый номер в формате `XX:XX:XXXXXXX:XX` |
| `document_url` | string | нет | URL PDF-файла выписки ЕГРН (поддерживает Bubble CDN) |

> **Особенность:** параметры передаются через query string, **не** через JSON body, в отличие от `/analyze-plot`.

#### Пример запроса

```bash
# Без выписки
curl -X POST "http://localhost:8000/api/legal/analyze-plot-with-doc?cadastral=39:05:030615:27"

# С выпиской по URL
curl -X POST "http://localhost:8000/api/legal/analyze-plot-with-doc?cadastral=39:05:030615:27&document_url=https://example.com/extract.pdf"
```

#### Структура ответа

Идентична `/analyze-plot`, плюс два дополнительных поля:

```json
{
  "summary": { ... },
  "summary_one_line": "...",
  "risk_score": "medium",
  "risks": [ ... ],
  "recommendations": [ ... ],
  "sources": [ ... ],

  "analyzed_with_document": true,
  "document_chars": 12450
}
```

| Поле | Тип | Описание |
|---|---|---|
| `analyzed_with_document` | boolean | Был ли в анализе использован текст PDF выписки |
| `document_chars` | integer | Количество извлечённых символов из PDF |

#### Поведение при отсутствии PDF

Если `document_url` не передан или PDF не удалось скачать/распарсить:
- `analyzed_with_document: false`
- `document_chars: 0`
- Анализ выполняется только по данным кадастра
- Предупреждения пользователю об этом нет — поведение прозрачно

#### Нормализация Bubble CDN URL

URL'ы от Bubble FileUploader приходят в разных форматах. Сервер нормализует:
- `//s3.amazonaws.com/...` → `https://s3.amazonaws.com/...`
- Относительные пути в полные
- Убирает лишние пробелы и параметры

#### Возможные ошибки

| HTTP | Detail | Причина |
|---|---|---|
| 400 | `Некорректный кадастровый номер` | Не прошёл regex |
| 200 | `not_found: true` | Участок отсутствует в Toolbox |
| 500 | `Ошибка: ...` | Непредвиденная ошибка |

При сбое скачивания или парсинга PDF — анализ продолжается без него (`analyzed_with_document: false`), не падает.

#### Время отклика

- Без PDF: **30–120 секунд** (как `/analyze-plot`)
- С PDF: **до 2 минут** (с учётом скачивания и `pdfplumber`)

---

## Коды ошибок

| HTTP | Описание | Когда возникает |
|---|---|---|
| **200** | OK | Успешный ответ. Также при `not_found` и LLM-fallback |
| **400** | Bad Request | Невалидный кадастровый номер, пустое тело запроса |
| **404** | Not Found | Внутренние ошибки получения GeoJSON (нет архива, нет координат) |
| **422** | Unprocessable Entity | Невалидная JSON-структура (FastAPI Pydantic validation) |
| **500** | Internal Server Error | Непредвиденная ошибка на сервере |

---

## Тестовые кадастры

Эти участки проверены и стабильно возвращают данные:

| Кадастровый номер | Регион | Особенность |
|---|---|---|
| `39:05:030615:27` | Калининградская обл. | Базовый тестовый, ИЖС, средний риск |
| `39:05:030616:430` | Калининградская обл. | Альтернативный для проверки кэша |
| `39:05:030615:286` | Калининградская обл. | Третий вариант для UI-демо |

Для проверки `not_found` ответа используй любой синтаксически корректный, но несуществующий: `99:99:9999999:99`.

---

## Лимиты и квоты

### NextGIS Toolbox

- ~6 000 ₽/мес за пакет вызовов `cadnums_to_geodata`
- Точное количество запросов в пакете уточняется в личном кабинете NextGIS
- При превышении — выбрасывается `ToolboxAPIError`, на которую сервер реагирует возвратом `not_found_response`

### OpenRouter (Qwen3-32B)

- ~0,04 ₽ за запрос (на ноябрь 2026)
- Лимиты определяются балансом аккаунта OpenRouter
- При исчерпании баланса — fallback на rule-based профиль

### Сервер FastAPI

- Один инстанс, без rate limiting
- Recommended нагрузка: до 5 000 запросов/мес (при текущей конфигурации Selectel 2 vCPU / 4 ГБ)
- Для масштабирования см. [`docs/architecture.md`](architecture.md#trade-offs-и-ограничения)

---

## Swagger UI

При запущенном сервере автоматически генерируемая интерактивная документация:

```
http://localhost:8000/docs
```

Или на production:

```
http://79.143.24.76:8000/docs
```

Через Swagger UI можно:
- Просматривать все endpoint'ы и их схемы
- Отправлять запросы прямо из браузера
- Видеть примеры ответов

Также доступен ReDoc:

```
http://localhost:8000/redoc
```

И сырая OpenAPI-схема в JSON:

```
http://localhost:8000/openapi.json
```

---

## Связанные документы

- [`docs/architecture.md`](architecture.md) — общая архитектура системы
- [`backend/README.md`](../backend/README.md) — установка и запуск backend
- [`backend/main.py`](../backend/main.py) — исходный код endpoint'ов
