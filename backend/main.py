"""
PlotFinder Backend — FastAPI-сервис юридической проверки земельных участков.

Принимает кадастровый номер, опционально PDF выписки ЕГРН, обращается к
NextGIS Toolbox API за геометрией участка и к OpenRouter (Qwen3-32B) за
структурированным юридическим анализом рисков.

Endpoints:
    GET  /api/rosreestr2coord            — геометрия участка по кадастру
    POST /api/legal/analyze-text         — mock-анализ по тексту
    POST /api/legal/analyze-plot         — анализ по кадастру через LLM
    POST /api/legal/analyze-plot-with-doc — анализ кадастр + PDF выписка через LLM

Переменные окружения (обязательные):
    TOOLBOX_API_KEY     — ключ NextGIS Toolbox API
    OPENROUTER_API_KEY  — ключ OpenRouter (формат sk-or-v1-...)

Переменные окружения (опциональные):
    GEOJSON_DIR         — директория для кэша GeoJSON (по умолчанию ./output/geojson)

Проект: PlotFinder MVP
Автор: Николаев Александр Владиславович
ВКР НИУ ВШЭ, магистерская программа «ЛигалТех», 2026
Лицензия: MIT (см. LICENSE в корне репозитория)
"""

from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import os
import re
import zipfile
import tempfile
from pathlib import Path

from toolbox_sdk import ToolboxClient
try:
    from toolbox_sdk.exceptions import ToolboxAPIError
except ImportError:
    class ToolboxAPIError(Exception):
        pass

app = FastAPI()

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("plotfinder")


def extract_json(raw: str) -> dict:
    """Устойчивый извлекатель JSON из ответа LLM с <think>, markdown и хвостовой прозой."""
    if not raw:
        raise ValueError("empty raw")
    # 1. Удаляем закрытые <think>...</think>
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    # 2. Незакрытый <think> — обрезаем от него до первого '{'
    if "<think>" in cleaned:
        brace = cleaned.find("{", cleaned.find("<think>"))
        if brace < 0:
            raise ValueError(f"unclosed <think>, no JSON; raw[:300]={raw[:300]!r}")
        cleaned = cleaned[brace:]
    cleaned = cleaned.strip()
    # 3. Снимаем markdown-фенсы
    cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()
    # 4. Балансировка скобок — берём первый объект целиком, игнорируя хвост
    start = cleaned.find("{")
    if start < 0:
        raise ValueError(f"no '{{' in cleaned; cleaned[:300]={cleaned[:300]!r}")
    depth, in_str, esc, end = 0, False, False, -1
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise ValueError(f"unbalanced braces; cleaned[:500]={cleaned[:500]!r}")
    return json.loads(cleaned[start:end])


TOOLBOX_API_KEY = os.getenv("TOOLBOX_API_KEY")
GEOJSON_DIR = os.getenv("GEOJSON_DIR", "./output/geojson")

if not TOOLBOX_API_KEY:
    raise RuntimeError(
        "TOOLBOX_API_KEY не задан. Скопируйте .env.example в .env и пропишите ключ NextGIS Toolbox API."
    )


def normalize_cadastral(cadastral: str) -> str:
    cadastral = cadastral.strip()
    cadastral = re.sub(r"[^0-9:]", "", cadastral)
    return cadastral


def find_cached_geojson(cadastral: str):
    def norm(s):
        return tuple(x.lstrip("0") or "0" for x in s.split(":"))
    exact = os.path.join(GEOJSON_DIR, cadastral.replace(":", "_") + ".geojson")
    if os.path.exists(exact):
        return exact
    inp = norm(cadastral)
    for f in os.listdir(GEOJSON_DIR):
        if not f.endswith(".geojson"):
            continue
        fc = f.replace(".geojson", "").replace("_", ":", 3)
        if norm(fc) == inp:
            return os.path.join(GEOJSON_DIR, f)
    return None


def fetch_via_toolbox(cadastral: str) -> dict:
    toolbox = ToolboxClient(TOOLBOX_API_KEY)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(cadastral + "\n")
        txt_path = f.name
    try:
        uploaded = toolbox.upload_file(txt_path)
        tool = toolbox.tool("cadnums_to_geodata")
        result = tool({"source_file": uploaded})
        with tempfile.TemporaryDirectory() as tmpdir:
            toolbox.download_results(result, tmpdir)
            zip_path = os.path.join(tmpdir, "cadastre_data.zip")
            if not os.path.exists(zip_path):
                raise HTTPException(status_code=404, detail="Архив не получен от Toolbox")
            with zipfile.ZipFile(zip_path) as z:
                geojson_files = [n for n in z.namelist() if n.endswith(".geojson")]
                if not geojson_files:
                    raise HTTPException(status_code=404, detail="GeoJSON не найден в архиве")
                with z.open(geojson_files[0]) as gf:
                    data = json.load(gf)
        return data
    finally:
        os.unlink(txt_path)


def build_response(cadastral: str, data: dict) -> dict:
    if not data.get("features"):
        raise HTTPException(status_code=404, detail="Нет объектов в GeoJSON")
    feature = data["features"][0]
    geometry = feature.get("geometry", {})
    props = feature.get("properties", {})
    if "coordinates" not in geometry:
        raise HTTPException(status_code=404, detail="Нет координат в GeoJSON")
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": geometry.get("type", "Polygon"),
                "coordinates": geometry["coordinates"]
            },
            "properties": {
                "cadnum": props.get("cad_num") or props.get("cn") or cadastral,
                "quarter": props.get("quarter_cad_number", ""),
                "address": props.get("readable_address", "") or props.get("address", ""),
                "area": props.get("specified_area") or props.get("area_value", 0),
                "category": props.get("land_record_category_type", ""),
                "categoryFull": props.get("land_record_type", ""),
                "ownership": props.get("ownership_type", ""),
                "cost": props.get("cost_value") or props.get("cad_cost", 0),
                "status": props.get("status", ""),
                "date_reg": props.get("land_record_reg_date", ""),
                "declared_area": props.get("declared_area", 0),
                "cost_index": props.get("cost_index", ""),
                "util_by_doc": props.get("permitted_use_established_by_document", "") or props.get("util_by_doc", ""),
                "type": props.get("land_record_type", ""),
                "label": props.get("_name", "")
            }
        }]
    }


@app.get("/api/rosreestr2coord")
async def get_plot(cadastral: str = Query(..., description="Кадастровый номер")):
    try:
        cadastral = normalize_cadastral(cadastral)
        if not cadastral:
            raise HTTPException(status_code=400, detail="Некорректный кадастровый номер")
        cached = find_cached_geojson(cadastral)
        if cached:
            with open(cached, encoding="utf-8") as f:
                data = json.load(f)
            return build_response(cadastral, data)
        data = fetch_via_toolbox(cadastral)
        os.makedirs(GEOJSON_DIR, exist_ok=True)
        cache_path = os.path.join(GEOJSON_DIR, cadastral.replace(":", "_") + ".geojson")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return build_response(cadastral, data)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


class LegalAnalyzeRequest(BaseModel):
    text: str
    cadastral_number: Optional[str] = None
    user_comment: Optional[str] = None


@app.post("/api/legal/analyze-text")
async def legal_analyze_text(data: LegalAnalyzeRequest):
    if not data.text or not data.text.strip():
        raise HTTPException(status_code=400, detail="text cannot be empty")
    text_lower = data.text.lower()
    risks = []
    recommendations = []
    missing_or_unclear = []
    overall_risk_level = "low"
    summary = "Система получила текст и выполнила тестовый юридический анализ."
    if "огранич" in text_lower or "обремен" in text_lower:
        risks.append({"type": "restriction", "level": "medium", "description": "В тексте найдены указания на ограничения или обременения.", "basis": "Обнаружены ключевые слова: огранич / обремен"})
        recommendations.append("Проверить характер ограничений и их актуальность в действующей выписке.")
        overall_risk_level = "medium"
        summary = "В тексте выявлены потенциальные ограничения или обременения, требующие дополнительной проверки."
    if "арест" in text_lower or "спор" in text_lower or "суд" in text_lower:
        risks.append({"type": "dispute", "level": "high", "description": "В тексте есть признаки судебного спора, ареста или иного конфликтного статуса.", "basis": "Обнаружены ключевые слова: арест / спор / суд"})
        recommendations.append("Проверить судебные споры, исполнительные производства и ограничения регистрационных действий.")
        overall_risk_level = "high"
        summary = "В тексте обнаружены признаки повышенного правового риска."
    if not risks:
        risks.append({"type": "test", "level": "low", "description": "Существенные негативные индикаторы в тексте не выявлены.", "basis": "Mock response"})
        recommendations.append("Подключить полноценный AI-анализ и проверку документов на следующем этапе.")
    if not data.cadastral_number:
        missing_or_unclear.append("Кадастровый номер не был передан отдельно и анализ выполнен только по тексту.")
    if not data.user_comment:
        missing_or_unclear.append("Пользователь не указал дополнительный вопрос или фокус анализа.")
    return {
        "summary": summary,
        "cadastral_number": data.cadastral_number or "",
        "address": "", "area": "", "category": "", "allowed_use": "",
        "key_facts": ["Текст успешно получен сервером", "Mock-анализ юридического модуля выполнен"],
        "risks": risks,
        "missing_or_unclear": missing_or_unclear,
        "recommendations": recommendations,
        "overall_risk_level": overall_risk_level,
        "disclaimer": "Это тестовый информационно-аналитический вывод. Не является юридическим заключением."
    }


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise RuntimeError(
        "OPENROUTER_API_KEY не задан. Скопируйте .env.example в .env и пропишите ключ OpenRouter."
    )

CAD_RE = re.compile(r"^\d{2}:\d{2}:\d{1,8}:\d+$")

import requests as req_lib
from datetime import date
from typing import Literal

class Risk(BaseModel):
    severity: Literal["low", "medium", "high"]
    title: str
    reason: str
    source_fields: list

class RiskProfile(BaseModel):
    summary: dict
    risk_score: Literal["low", "medium", "high"]
    risks: list
    recommendations: list
    sources: list

class AnalyzePlotRequest(BaseModel):
    cadastral: str

def norm_props(props: dict) -> dict:
    area = props.get("area")
    declared = props.get("declared_area")
    if area and float(area) > 0:
        area_sqm, area_source = float(area), "area"
    elif declared and float(declared) > 0:
        area_sqm, area_source = float(declared), "declared_area"
    else:
        area_sqm, area_source = None, "missing"
    return {
        "cadnum": props.get("cadnum"),
        "address": props.get("address"),
        "area_sqm": area_sqm,
        "area_source": area_source,
        "category": props.get("category"),
        "ownership": props.get("ownership"),
        "cost_rub": props.get("cost"),
        "status": props.get("status"),
        "date_reg": props.get("date_reg"),
        "quarter": props.get("quarter"),
        "type": props.get("type"),
        "util_by_doc": props.get("util_by_doc"),
        "cost_index": props.get("cost_index"),
    }

def fallback_profile(p: dict) -> dict:
    risks, recs, sources = [], [], []
    score = "low"
    own = (p.get("ownership") or "").lower()
    st = (p.get("status") or "").lower()
    cat = (p.get("category") or "").lower()
    medium_count = 0

    if any(x in own for x in ["государ", "муницип", "федераль"]):
        score = "high"
        risks.append({"severity": "high", "title": "Публичная собственность", "reason": "Форма собственности указывает на публичного правообладателя; обычная купля-продажа может быть невозможна.", "source_fields": ["properties.ownership"]})
        recs.append("Проверьте в свежей выписке ЕГРН допустимость отчуждения участка.")
        sources.append("properties.ownership")

    if not p.get("cadnum") or not p.get("category") or not p.get("address"):
        score = "high"
        risks.append({"severity": "high", "title": "Отсутствуют критические данные", "reason": "Не заполнены одно или несколько ключевых полей: кадастровый номер, категория или адрес.", "source_fields": ["properties.cadnum", "properties.category", "properties.address"]})

    if "ранее учтенный" in st:
        medium_count += 1
        risks.append({"severity": "medium", "title": "Статус: Ранее учтенный", "reason": "Сведения могут быть устаревшими. Требуется сверка актуальных данных ЕГРН.", "source_fields": ["properties.status"]})
        recs.append("Закажите свежую выписку ЕГРН и сравните статус, площадь и право.")
        sources.append("properties.status")

    if p.get("area_source") == "declared_area":
        medium_count += 1
        risks.append({"severity": "medium", "title": "Площадь декларирована", "reason": "Основная площадь взята из declared_area — фактические границы могут не совпадать с документами.", "source_fields": ["properties.area", "properties.declared_area"]})
        recs.append("Сверьте площадь по выписке ЕГРН и межевому плану.")
        sources += ["properties.area", "properties.declared_area"]

    if p.get("area_source") == "missing":
        medium_count += 1
        risks.append({"severity": "medium", "title": "Площадь не указана", "reason": "Отсутствуют данные о площади участка, что затрудняет оценку сделки.", "source_fields": ["properties.area"]})

    if any(x in cat for x in ["сельскохоз", "промышленн"]):
        medium_count += 1
        risks.append({"severity": "medium", "title": "Ограничения по категории земель", "reason": f"Категория '{p.get('category')}' накладывает специальные режимы использования.", "source_fields": ["properties.category"]})
        recs.append("Сверьте допустимое использование участка с вашими целями покупки.")
        sources.append("properties.category")

    if not p.get("cost_rub"):
        medium_count += 1
        risks.append({"severity": "medium", "title": "Кадастровая стоимость не указана", "reason": "Отсутствие кадастровой стоимости затрудняет оценку налоговой нагрузки.", "source_fields": ["properties.cost"]})

    if medium_count >= 3 and score != "high":
        score = "high"
    elif medium_count > 0 and score == "low":
        score = "medium"

    if not recs:
        recs.append("Проверьте свежую выписку ЕГРН по участку.")

    return {
        "summary": {
            "title": f"Участок {p.get('cadnum') or 'без номера'}",
            "cadnum": p.get("cadnum"),
            "address": p.get("address"),
            "area_sqm": p.get("area_sqm"),
            "area_source": p.get("area_source"),
            "category": p.get("category"),
            "ownership": p.get("ownership"),
            "cost_rub": p.get("cost_rub"),
            "date_reg": p.get("date_reg"),
        },
        "risk_score": score,
        "risks": risks[:6],
        "recommendations": recs[:3],
        "sources": sorted(set(sources))
    }


def not_found_response(cadastral: str) -> dict:
    """Структура для участков, отсутствующих в Toolbox.
    Та же форма, что у обычного ответа, плюс плоский флаг not_found=true."""
    return {
        "not_found": True,
        "summary": {
            "title": f"Участок {cadastral} не найден",
            "cadnum": cadastral,
            "address": None,
            "area_sqm": None,
            "area_source": "missing",
            "category": None,
            "ownership": None,
            "cost_rub": None,
            "date_reg": None,
        },
        "summary_one_line": "Участок отсутствует в нашей базе данных. Проверьте кадастровый номер или повторите попытку позже.",
        "risk_score": "unknown",
        "risks": [],
        "recommendations": [],
        "sources": [],
        "analyzed_with_document": False,
        "document_chars": 0,
    }


SYSTEM_PROMPT = """Ты — старший эксперт по земельному праву РФ и юридическому due diligence земельных участков.
Твоя задача: по данным одного участка сформировать КРАТКИЙ, предметный риск-профиль.
Основание анализа — ТОЛЬКО данные, явно присутствующие во входном JSON. Нельзя придумывать обременения, споры, аресты, сервитуты, ограничения если они не следуют напрямую из полей JSON.

Текущая дата: {today}

Правила оценки риска:
- HIGH если: ownership содержит государственная/муниципальная/федеральная; category = лесной/водный фонд/оборона/ООПТ; отсутствуют cadnum/category/address; 3+ факторов medium.
- MEDIUM если нет high но есть: status = Ранее учтенный; registration_age_years >= 15; area_source = declared_area; нет cost_rub; category = сельхоз или промышленность.
- LOW если нет high и нет/минимум medium.

Запрещено писать о залоге, аресте, сервитутах, судебных спорах, экологии если этого нет в данных.

Верни СТРОГО JSON без markdown и пояснений:
{{
  "summary": {{"title": "string", "cadnum": "string|null", "address": "string|null", "area_sqm": 0, "area_source": "area|declared_area|missing", "category": "string|null", "ownership": "string|null", "cost_rub": 0, "date_reg": "YYYY-MM-DD|null"}},
  "summary_one_line": "string (<=180 символов) — одно предложение с главным выводом для покупателя, объясняющее уровень риска и его причины",
  "risk_score": "low|medium|high",
  "risks": [{{"severity": "low|medium|high", "title": "string (<=70 символов)", "reason": "string (<=220 символов)", "source_fields": []}}],
  "recommendations": ["string (<=160 символов)", "string", "string"],
  "sources": []
}}"""

@app.post("/api/legal/analyze-plot")
async def analyze_plot(data: AnalyzePlotRequest):
    try:
        cadastral = normalize_cadastral(data.cadastral)
        if not cadastral or not CAD_RE.match(cadastral):
            raise HTTPException(status_code=400, detail="Некорректный кадастровый номер")

        cached = find_cached_geojson(cadastral)
        try:
            if cached:
                with open(cached, encoding="utf-8") as f:
                    geojson = json.load(f)
                plot_response = build_response(cadastral, geojson)
            else:
                geojson = fetch_via_toolbox(cadastral)
                os.makedirs(GEOJSON_DIR, exist_ok=True)
                cache_path = os.path.join(GEOJSON_DIR, cadastral.replace(":", "_") + ".geojson")
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(geojson, f, ensure_ascii=False)
                plot_response = build_response(cadastral, geojson)
        except ToolboxAPIError as e:
            logger.info("Toolbox: участок %s не найден: %s", cadastral, e)
            return not_found_response(cadastral)
        except HTTPException as e:
            if e.status_code == 404:
                logger.info("Участок %s не найден (404): %s", cadastral, e.detail)
                return not_found_response(cadastral)
            raise

        props = plot_response["features"][0]["properties"]
        parcel = norm_props(props)

        prompt = SYSTEM_PROMPT.format(today=str(date.today()))

        user_content = json.dumps(parcel, ensure_ascii=False) + (
            "\n\nОБЯЗАТЕЛЬНО верни JSON со следующими полями верхнего уровня: "
            "summary (объект с полями title, cadnum, address, area_sqm, area_source, "
            "category, ownership, cost_rub, date_reg), "
            "summary_one_line (строка <=180 символов), "
            "risk_score (одно из: low|medium|high), "
            "risks (массив объектов с полями severity, title, reason, source_fields), "
            "recommendations (массив строк), "
            "sources (массив строк). "
            "Структура ответа НЕ должна повторять структуру входных данных."
        )

        response = req_lib.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://plotfinder.ru",
                "X-OpenRouter-Title": "PlotFinder"
            },
            json={
                "model": "qwen/qwen3-32b",
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 4000,
                "provider": {"require_parameters": True},
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content}
                ]
            },
            timeout=60
        )

        logger.info("OpenRouter HTTP %s for %s", response.status_code, cadastral)
        try:
            resp_data = response.json()
        except Exception as e:
            logger.error("OpenRouter response not JSON: %s; text=%r", e, response.text[:500])
            return fallback_profile(parcel)

        if "error" in resp_data and "choices" not in resp_data:
            logger.error("OpenRouter API error: %r", resp_data.get("error"))
            return fallback_profile(parcel)

        choice = (resp_data.get("choices") or [{}])[0]
        raw = (choice.get("message") or {}).get("content")
        finish_reason = choice.get("finish_reason")
        usage = resp_data.get("usage", {})
        logger.info(
            "finish_reason=%s, raw_len=%s, usage=%s",
            finish_reason, len(raw) if raw else 0, usage
        )
        if raw:
            logger.info("raw[:600]=%r", raw[:600])
            if len(raw) > 600:
                logger.info("raw[-300:]=%r", raw[-300:])

        if raw is None:
            logger.error("raw is None; full resp_data=%r", resp_data)
            return fallback_profile(parcel)

        try:
            result = extract_json(raw)
            logger.info("LLM JSON parsed OK; keys=%s", list(result.keys()))
            return result
        except (ValueError, json.JSONDecodeError) as e:
            logger.error("extract_json failed: %s", e)
            return fallback_profile(parcel)

    except HTTPException as e:
        raise e
    except json.JSONDecodeError:
        logger.exception("Outer JSONDecodeError")
        return fallback_profile(parcel if "parcel" in locals() else {})
    except KeyError as e:
        logger.exception("Outer KeyError: %s", e)
        return fallback_profile(parcel if "parcel" in locals() else {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")


@app.post("/api/legal/analyze-plot-with-doc")
async def analyze_plot_with_doc(
    cadastral: str = Query(..., description="Кадастровый номер"),
    document_url: Optional[str] = Query(None, description="URL PDF файла (опционально)")
):
    try:
        cadastral = normalize_cadastral(cadastral)
        if not cadastral or not CAD_RE.match(cadastral):
            raise HTTPException(status_code=400, detail="Некорректный кадастровый номер")

        cached = find_cached_geojson(cadastral)
        try:
            if cached:
                with open(cached, encoding="utf-8") as f:
                    geojson = json.load(f)
                plot_response = build_response(cadastral, geojson)
            else:
                geojson = fetch_via_toolbox(cadastral)
                os.makedirs(GEOJSON_DIR, exist_ok=True)
                cache_path = os.path.join(GEOJSON_DIR, cadastral.replace(":", "_") + ".geojson")
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(geojson, f, ensure_ascii=False)
                plot_response = build_response(cadastral, geojson)
        except ToolboxAPIError as e:
            logger.info("Toolbox (with-doc): участок %s не найден: %s", cadastral, e)
            return not_found_response(cadastral)
        except HTTPException as e:
            if e.status_code == 404:
                logger.info("Участок %s не найден в with-doc (404): %s", cadastral, e.detail)
                return not_found_response(cadastral)
            raise

        props = plot_response["features"][0]["properties"]
        parcel = norm_props(props)

        # Шаг 2 - скачиваем и читаем PDF (если URL передан)
        doc_text = ""
        doc_error = None
        if document_url and document_url.strip():
            # Bubble CDN иногда возвращает protocol-relative URL: //cdn.bubble.io/...
            if document_url.startswith("//"):
                document_url = "https:" + document_url
            logger.info("Скачиваем PDF: %s", document_url[:200])
            try:
                pdf_response = req_lib.get(document_url, timeout=30)
                logger.info("PDF HTTP %s, size=%s bytes", pdf_response.status_code, len(pdf_response.content))
                if pdf_response.status_code == 200:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                        tmp_pdf.write(pdf_response.content)
                        tmp_pdf_path = tmp_pdf.name
                    try:
                        import pdfplumber
                        with pdfplumber.open(tmp_pdf_path) as pdf:
                            page_count = len(pdf.pages)
                            for page in pdf.pages:
                                doc_text += page.extract_text() or ""
                            logger.info("PDF: %s страниц, извлечено %s символов", page_count, len(doc_text))
                    finally:
                        os.unlink(tmp_pdf_path)
                else:
                    doc_error = f"Не удалось скачать PDF: HTTP {pdf_response.status_code}"
                    logger.error(doc_error)
            except Exception as e:
                doc_error = f"Ошибка при обработке PDF: {str(e)}"
                logger.exception("PDF processing failed")

        # Шаг 3 - формируем промпт
        prompt = SYSTEM_PROMPT.format(today=str(date.today()))
        user_content = json.dumps(parcel, ensure_ascii=False) + (
            "\n\nОБЯЗАТЕЛЬНО верни JSON со следующими полями верхнего уровня: "
            "summary (объект с полями title, cadnum, address, area_sqm, area_source, "
            "category, ownership, cost_rub, date_reg), "
            "summary_one_line (строка <=180 символов), "
            "risk_score (одно из: low|medium|high), "
            "risks (массив объектов с полями severity, title, reason, source_fields), "
            "recommendations (массив строк), "
            "sources (массив строк). "
            "Структура ответа НЕ должна повторять структуру входных данных."
        )

        if doc_text:
            user_content += f"""

--- ТЕКСТ ВЫПИСКИ ЕГРН ---
{doc_text[:6000]}
--- КОНЕЦ ВЫПИСКИ ---

Дополнительные инструкции при анализе выписки:
- Сопоставь данные из выписки с данными кадастра
- Если есть расхождения в площади, кадастровой стоимости, категории - укажи как отдельный риск
- Учти сведения о правообладателе, основании регистрации и обременениях из выписки
- Если обременения не зарегистрированы - укажи это как позитивный факт в summary"""
        elif doc_error:
            user_content += f"\n\nПримечание: {doc_error}. Анализ выполнен только по кадастровым данным."

        # Шаг 4 - запрос к OpenRouter
        response = req_lib.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://plotfinder.ru",
                "X-OpenRouter-Title": "PlotFinder"
            },
            json={
                "model": "qwen/qwen3-32b",
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 4000,
                "provider": {"require_parameters": True},
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content}
                ]
            },
            timeout=90
        )

        logger.info("OpenRouter HTTP %s for %s (with-doc, doc_chars=%s)", response.status_code, cadastral, len(doc_text))
        try:
            resp_data = response.json()
        except Exception as e:
            logger.error("OpenRouter response not JSON: %s; text=%r", e, response.text[:500])
            return fallback_profile(parcel)

        if "error" in resp_data and "choices" not in resp_data:
            logger.error("OpenRouter API error: %r", resp_data.get("error"))
            return fallback_profile(parcel)

        choice = (resp_data.get("choices") or [{}])[0]
        raw = (choice.get("message") or {}).get("content")
        finish_reason = choice.get("finish_reason")
        usage = resp_data.get("usage", {})
        logger.info(
            "with-doc: finish_reason=%s, raw_len=%s, usage=%s",
            finish_reason, len(raw) if raw else 0, usage
        )
        if raw:
            logger.info("with-doc raw[:600]=%r", raw[:600])
            if len(raw) > 600:
                logger.info("with-doc raw[-300:]=%r", raw[-300:])

        if raw is None:
            logger.error("with-doc raw is None; full resp_data=%r", resp_data)
            return fallback_profile(parcel)

        try:
            result = extract_json(raw)
            logger.info("with-doc LLM JSON parsed OK; keys=%s", list(result.keys()))
        except (ValueError, json.JSONDecodeError) as e:
            logger.error("with-doc extract_json failed: %s", e)
            return fallback_profile(parcel)

        result["analyzed_with_document"] = bool(doc_text)
        result["document_chars"] = len(doc_text)
        if doc_error:
            result["document_error"] = doc_error
        return result

    except HTTPException as e:
        raise e
    except json.JSONDecodeError:
        logger.exception("with-doc Outer JSONDecodeError")
        return fallback_profile(parcel if "parcel" in locals() else {})
    except KeyError as e:
        logger.exception("with-doc Outer KeyError: %s", e)
        return fallback_profile(parcel if "parcel" in locals() else {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {str(e)}")
