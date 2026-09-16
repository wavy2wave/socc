#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СУТОЧНЫЙ ЦИКЛ (ymarket_day_v1) — утренняя смена органа: все роли докладывают управляющему.

Что просил оператор дословно: «утром я захожу в рабочий чат и вижу каждый день 100% отчёт от
управляющего; ему приходят отчёты от других; он общается со мной как с другом, но все данные даёт;
свои KPI и стремление стать больше и лучше».

Это и есть цикл дня:
  0. ПЛАНЁРКА (опционально, шаг 0 «УТРО ПРЕЖДЕ РАБОТ», planner_fn) — собрать ПЛАН ДНЯ из сторов
     (0₽, read); OFF по умолчанию, включается вызывающим (автопилот/_plannerka или --plannerka).
  1. БРИГАДИР проводит смену — ДИСПЕТЧЕР (горящие заказы) → СКЛАДОВЩИК (остатки) → ТОВАРОВЕД
     (что берём) → ЦЕНОВИК (маржа) → КОНТРОЛЁР (индекс качества). Порядок не случайный: сначала
     горящее, потом важное, потом выгодное.
  2. УПРАВЛЯЮЩИЙ делает свой тик — карточки, заполненность, память.
  3. СТРАТЕГ смотрит, где лежат недобранные деньги, и считает потолок каждого хода.
  4. ТРЕНД-СКАУТ ищет окна спроса (или честно говорит, что источник не подключён).
  5. Всё сводится в ОДИН дневной отчёт: KPI, дельта ко вчера, что горит, куда растём.
  6. День дописывается в журнал — завтра из него берётся дельта (рост виден только в сравнении).

ЗАКОН B2 (наследуем у БРИГАДИРА): упавшая роль НЕ роняет день. Её провал честно попадает в отчёт,
остальные работают. Отчёт, который скрывает провал, хуже отсутствующего отчёта.

ЗАКОН ЧЕСТНОСТИ: цикл ничего не отправляет наружу и не двигает денег (dry по умолчанию). Реальные
READ/WRITE — только при not dry AND commit, как во всём органе.

Журнал дня: MEMORY_WAVE/reports/mint/arbiter/ymarket_day_journal.jsonl (env YM_DAY_JOURNAL).
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ymarket_state_v1 as state                    # noqa: E402
import ymarket_self_v1 as self_mod                  # noqa: E402
import ymarket_econ_v1 as econ                      # noqa: E402
import ymarket_role_strategist_v1 as strategist     # noqa: E402
import ymarket_role_trendscout_v1 as trendscout     # noqa: E402
import ymarket_role_head_v1 as head                 # noqa: E402  (ГОЛОВА: синтез в шорт-лист)

ROOT = HERE.parent.parent.parent
REPORTS = ROOT / "MEMORY_WAVE/reports/mint/arbiter"
DAY_SCHEMA = "ymarket.day.v1"


def journal_path():
    """Журнал дней (для дельты «вчера→сегодня»). env YM_DAY_JOURNAL перекрывает (тесты)."""
    p = os.environ.get("YM_DAY_JOURNAL")
    return Path(p) if p else (REPORTS / "ymarket_day_journal.jsonl")


# Ключи кабинета/органа, наличие которых цикл докладывает в env_loaded (только ИМЕНА, не значения).
_KNOWN_ENV = ("YANDEX_MARKET_API_KEY", "YANDEX_BUSINESS_ID", "YANDEX_CAMPAIGN_ID",
              "OZON_CLIENT_ID", "OZON_API_KEY")


def load_env_file(path=None):
    """Подтянуть ключи органа из .env — БЕЗ перезаписи уже заданных переменных.

    Зачем: суточный цикл задуман для расписания (cron/launchd), где нет интерактивной оболочки и
    некому сделать `set -a; . ./.env`. Без ключей ДИСПЕТЧЕР и КОНТРОЛЁР слепнут, и отчёт честно, но
    бесполезно пишет «индекс НЕ ПРОЧИТАН».

    ДВА ИСТОЧНИКА (в порядке приоритета уже-заданного):
      (A) общий загрузчик MINT (socc_mint_env_v1) — знает про mint/.env, SOCC/.env, wavecore-bot/.env.
          Руки Яндекса читают ЖИВОЙ кабинет именно через него; цикл обязан видеть тот же кабинет,
          иначе руки знают токен, а управляющий слеп — худший вид рассинхрона.
      (B) локальный arbiter/.env — исторический путь, оставлен для совместимости.

    ЗАКОН: уже заданное окружение НИКОГДА не перетирается (иначе тесты/песочница потеряют изоляцию),
    любая беда — молча пропускаем (fail-soft): загрузчик секретов не имеет права уронить цикл.
    Возвращает список ИМЁН подхваченных переменных (без значений — секреты не логируем).
    """
    picked = []
    # (A) канонический загрузчик — фиксируем, какие известные ключи он ВПЕРВЫЕ сделал видимыми.
    before = {k for k in _KNOWN_ENV if os.environ.get(k)}
    _menv = None
    try:
        import socc_mint_env_v1 as _menv          # noqa: F811
    except Exception:
        try:
            import sys
            mint = str(Path(__file__).resolve().parent.parent)   # SOCC/scripts/mint
            if mint not in sys.path:
                sys.path.insert(0, mint)
            import socc_mint_env_v1 as _menv      # noqa: F811
        except Exception:
            _menv = None
    if _menv is not None:
        try:
            _menv.ensure_env()
        except Exception:
            pass
    picked.extend(sorted(k for k in _KNOWN_ENV if os.environ.get(k) and k not in before))

    # (B) локальный arbiter/.env — уже заданное (в т.ч. подтянутое из mint/.env) не перетираем.
    p = Path(path) if path else (HERE / ".env")
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and not os.environ.get(k):
                os.environ[k] = v
                picked.append(k)
    except Exception:
        pass
    return picked


def _resolve_ids(business_id, campaign_id):
    """Достать id кабинета/магазина: аргумент → окружение. Ничего не выдумываем — None остаётся None."""
    if not business_id:
        business_id = os.environ.get("YANDEX_BUSINESS_ID") or None
    if not campaign_id:
        campaign_id = os.environ.get("YANDEX_CAMPAIGN_ID") or None
    return business_id, campaign_id


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe(name, fn, *a, **kw):
    """B2: роль упала → фиксируем провал, день не роняем."""
    try:
        return {"ok": True, "result": fn(*a, **kw)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "step": name}


def _read_journal(limit=30):
    p = journal_path()
    if not p.exists():
        return []
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
    return rows[-limit:]


def _append_journal(day):
    """Дописать день в журнал (append-only). Fail-soft: не смогли — день всё равно вернём.

    После успешной записи журнала мягко (0₽, лениво, сбой не роняет день) дублируем роли дня
    в ТАБЕЛЬ виртуального офиса (ymarket_office_v1.record_day): это даёт каждой роли ДОКАЗУЕМЫЙ
    след смены на диске — «работал на совесть» по фактам, а не на слово."""
    try:
        p = journal_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        slim = {"ts": day["ts"], "date": day["date"], "kpis": day["kpis"],
                "burning": day["burning"]["count"], "top_move": day["growth"].get("top_move")}
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")
        try:
            import ymarket_office_v1 as _office      # лениво: офис не нужен для хода дня
            _office.record_day(day)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _delta(today, yesterday):
    """Дельта по числовым KPI. Нет вчера или нет числа → None (не выдумываем «0 изменений»)."""
    if not yesterday:
        return {}
    out = {}
    for k, v in (today or {}).items():
        pv = (yesterday or {}).get(k)
        if isinstance(v, (int, float)) and isinstance(pv, (int, float)):
            out[k] = round(v - pv, 2)
    return out


def _first_offer_error(o):
    """Первое человекочитаемое сообщение об ошибке оффера (или None). 200 OK ≠ успех — читаем errors."""
    errs = (o or {}).get("errors")
    if isinstance(errs, list) and errs:
        e0 = errs[0]
        if isinstance(e0, dict):
            return e0.get("message") or e0.get("comment") or e0.get("code")
        return str(e0)
    return None


def _read_cabinet(business_id, campaign_id, hands=None):
    """ЖИВОЕ ЧТЕНИЕ витрины кабинета (0₽, RUBICON цел — только READ). Правда, а не память.

    «SOCC регулирует правду»: отчёт обязан отражать РЕАЛЬНЫЙ кабинет, а не то, что запомнила
    само-модель. Читает все магазины (campaigns), витрину каждого (campaign_offers) и заполненность
    каталога (offer-cards). Ничего не пишет и денег не двигает. Каждый под-запрос fail-soft: один
    упавший магазин не рушит снимок — его беда честно ложится в shops[].error.

    Снимок:
      {shops:[{id,placement,name,offers_total,offers_live,offers_disabled,
               disabled_offers:[{offerId,status,reason}], error?}],
       shops_total, offers_live, disabled, catalog:{cards, avg_content_rating}}
    «live» = статус PUBLISHED; «disabled» = есть статус, но не PUBLISHED (напр. DISABLED_BY_PARTNER).
    Статус None (не размещён/не ответил) не считаем ни живым, ни отключённым — не выдумываем.
    """
    if hands is None:
        import ymarket_hands_v1 as hands
    shops = []
    offers_live_total = 0
    disabled_total = 0
    for c in (hands.campaigns() or []):
        cid = c.get("id")
        shop = {"id": cid, "placement": c.get("placementType") or c.get("type"),
                "name": c.get("domain"), "offers_total": None,
                "offers_live": 0, "offers_disabled": 0, "disabled_offers": []}
        try:
            offers = hands.campaign_offers(cid, limit=100)
            if isinstance(offers, list):
                shop["offers_total"] = len(offers)
                for o in offers:
                    stt = o.get("status")
                    if stt == "PUBLISHED":
                        shop["offers_live"] += 1
                        offers_live_total += 1
                    elif stt:                              # есть статус, но не PUBLISHED → отключён
                        shop["offers_disabled"] += 1
                        disabled_total += 1
                        shop["disabled_offers"].append(
                            {"offerId": o.get("offerId"), "status": stt,
                             "reason": _first_offer_error(o)})
                    # stt None → ни живой, ни отключённый (честно не считаем)
        except Exception as e:
            shop["error"] = f"{type(e).__name__}: {e}"
        shops.append(shop)

    catalog = {"cards": None, "avg_content_rating": None,
               "cards_errored": None, "errored": [], "store_blocked": [],
               "needs_placement": [], "health_classifier": "unavailable"}
    try:
        cards = hands.offer_cards_status(business_id, limit=100)
        if isinstance(cards, list):
            catalog["cards"] = len(cards)
            rates = [c.get("contentRating") for c in cards
                     if isinstance(c.get("contentRating"), (int, float))]
            if rates:
                catalog["avg_content_rating"] = round(sum(rates) / len(rates), 1)
            # ЖИВАЯ СВЕРКА: те же карточки → здоровье (0₽, БЕЗ второго запроса). Дважды ограждено —
            # классификатор ведёт параллельная линия, её мид-фикс не должен ронять суточное чтение.
            # Разрыв → health_classifier="unavailable" + cards_errored=None (не фейковый 0).
            try:
                import ymarket_cabinet_health_v1 as cab_health
                h = cab_health.card_health(cards)
                catalog["cards_errored"] = h.get("cards_errored")
                catalog["errored"] = h.get("errored") or []
                catalog["store_blocked"] = h.get("store_blocked") or []
                catalog["needs_placement"] = h.get("needs_placement") or []
                catalog["health_classifier"] = h.get("classifier")
            except Exception as e:
                catalog["health_error"] = f"{type(e).__name__}: {e}"
    except Exception:
        pass

    return {"shops": shops, "shops_total": len(shops),
            "offers_live": offers_live_total, "disabled": disabled_total, "catalog": catalog}


def collect_kpis(st, shift_report, cabinet=None, zaliv=None):
    """Свести KPI дня из ЖИВОГО кабинета (если прочитан), само-модели и доклада смены. Только факты.

    ПРИОРИТЕТ ПРАВДЫ: прочитан кабинет живьём → витринные KPI берём ИЗ НЕГО, а не из памяти
    само-модели («SOCC регулирует правду»). То, чего в живом снимке нет (ошибки контента, заказы,
    остатки), по-прежнему берём из само-модели/смены — данные не теряем.

    zaliv — сводка готовности партии к заливу (ymarket_zaliv_source.readiness). Прогнали донор через
    сухую сборку → ready_to_publish берём из РЕАЛЬНОГО числа «полетит», а не из памяти (тот же
    приоритет живой правды). ready is None (донора нет / сборка не прошла) → память сохраняем.
    """
    k = (st or {}).get("kpis", {})
    steps = (shift_report or {}).get("steps", {})
    disp = steps.get("DISPATCHER") or {}
    stock = steps.get("STOCKMAN") or {}
    ctrl = steps.get("CONTROLLER") or {}
    quality = None
    if isinstance(ctrl.get("rating"), (int, float)):
        quality = ctrl["rating"]
    elif isinstance(ctrl.get("worst_rating"), (int, float)):
        quality = ctrl["worst_rating"]
    out = {
        "cards_tracked": k.get("cards_tracked"),
        "cards_live": k.get("cards_live"),
        "cards_live_verified": k.get("cards_live_verified"),
        "cards_errored": k.get("cards_errored"),          # цель 0
        "ready_to_publish": k.get("ready_to_publish"),
        "avg_content_rating": k.get("avg_content_rating"),
        "urgent_orders": disp.get("urgent"),
        "stock_unknown": stock.get("unknown_source"),
        "quality_index": quality,                          # индекс качества магазина (<40 = отключение)
    }
    # ЖИВАЯ ПРАВДА кабинета перекрывает память — только там, где кабинет реально прочитан.
    if cabinet:
        cat = cabinet.get("catalog") or {}
        if cat.get("cards") is not None:
            out["cards_tracked"] = cat["cards"]
        if cabinet.get("offers_live") is not None:
            out["cards_live"] = cabinet["offers_live"]
        if cat.get("avg_content_rating") is not None:
            out["avg_content_rating"] = cat["avg_content_rating"]
        # ЖИВАЯ СВЕРКА перекрывает память ТОЛЬКО когда классификатор реально отработал (не None).
        # None = кабинет прочитан, но здоровье недостижимо → оставляем память, не врём «живьём».
        if cat.get("cards_errored") is not None:
            out["cards_errored"] = cat["cards_errored"]
        out["shops_total"] = cabinet.get("shops_total")
        out["showcase_disabled"] = cabinet.get("disabled")  # товары, снятые с витрины (проверка ЯМ)
    # ЖИВАЯ ГОТОВНОСТЬ партии перекрывает память — только когда сухая сборка реально прошла.
    # ready is None (донора нет / сборка не прошла) → память сохраняем. Тот же анти-ложь, что у СВЕРКИ:
    # None ≠ 0 (0 = «собрал партию, но ничего не полетело»; None = «не собирал»). Провенанс — в day.
    if zaliv and zaliv.get("ready") is not None:
        out["ready_to_publish"] = zaliv["ready"]
    return out


# ── РЕЦЕПТ ЛЕЧЕНИЯ (рунг 4c СВЕРКИ): живая заморозка → ТОЧНАЯ команда починки ──
# Команда указывает на РЕАЛЬНУЮ руку точечного ремонта (ymarket_runner_v1 --skus). Значения ниже —
# пути, НЕ секреты (логировать безопасно). Интерпретатор — тот, где живёт openpyxl (живой чтец
# донорского XLSX): Apple /usr/bin/python3. Путь к раннеру — абсолютный, чтобы команда копировалась
# и запускалась из любой папки.
RUNNER_PY = "/usr/bin/python3"                       # Apple python3 + openpyxl — живой чтец донора
RUNNER_PATH = str(HERE / "ymarket_runner_v1.py")


def _heal_command(skus, available=False):
    """ТОЧНАЯ команда точечного ремонта раннера для конкретных offerId.

    --skus заполнен РЕАЛЬНЫМИ SKU (та работа, которую иначе оператор собирал бы руками из логов).
    <ДОНОР.xlsx> и <SLUG> — плейсхолдеры ОПЕРАТОРА: реестр хранит offerId↔поставщик, но НЕ путь
    выгрузки и НЕ slug (не выдумываем). --not-available по умолчанию: безопасный первый RUBICON —
    пере-собрать карточку, НЕ делая её покупаемой (витрина ещё на ре-модерации; карточки не включаем,
    пока оператор не откроет магазин).
    """
    csv = ",".join(str(s) for s in skus if s)
    cmd = f"{RUNNER_PY} {RUNNER_PATH} <ДОНОР.xlsx> --slug <SLUG> --donor --skus {csv} --commit"
    if not available:
        cmd += " --not-available"
    return cmd


def _heal_provenance(skus, lookup_fn=None):
    """Обогатить SKU происхождением из РЕЕСТРА (поставщик, ссылка на донора) — чтобы оператору было
    очевидно, ЧЬЮ выгрузку и slug подставить. Всё ограждено: нет реестра/битый → без обогащения."""
    if lookup_fn is None:
        try:
            import ymarket_registry_v1 as reg
            lookup_fn = reg.lookup
        except Exception:
            lookup_fn = None
    prov = []
    for s in skus:
        rec = {}
        if lookup_fn is not None:
            try:
                rec = lookup_fn(s) or {}
            except Exception:
                rec = {}
        prov.append({"offerId": s, "supplier": rec.get("supplier"),
                     "donor_url": rec.get("donor_url"), "donor_pid": rec.get("donor_pid")})
    return prov


def build_heal(cabinet, kpis=None, source="none", lookup_fn=None):
    """РЕЦЕПТ ЛЕЧЕНИЯ замороженных карточек (рунг 4c): живая заморозка → ТОЧНАЯ команда. 0₽, только текст.

    RUBICON зашит ФИЗИЧЕСКИ: цикл НИКОГДА не выполняет эту команду — это рецепт для ОПЕРАТОРА
    (у автопилота нет commit-пути). Возврат всегда одной формы; `needed`:
      True  — есть что чинить и SKU НАЗВАНЫ (из живого errored) → команда готова (xlsx/slug — плейсхолдеры);
      False — чинить нечего (витрина чиста ИЛИ ошибок нет);
      None  — сверка НЕПОЛНА: точные SKU назвать нельзя (классификатор упал ИЛИ ошибки лишь «из памяти»).

    rebuild — карточки С ОШИБКОЙ (frozen/error_fixable), планка YM1 «ноль ошибок»: патч одного поля
    молча гибнет → полный пере-билд. place — needs_placement: контент готов, но не в кампании; НЕ
    ошибка (не горит), но СВЕРКА обязана назвать. Обе лечит одна и та же точечная команда раннера.
    """
    cat = (cabinet or {}).get("catalog") or {}
    errored = cat.get("errored") or []
    to_place = cat.get("needs_placement") or []
    live = source == "cabinet_live"

    heal = {"needed": False, "source": source, "rebuild": None, "place": None, "note": None,
            "rubicon": "цикл НЕ выполняет эту команду сам — это рецепт оператору (commit-пути нет)"}

    if live and errored:
        skus = [r.get("offerId") for r in errored if r.get("offerId")]
        if skus:
            heal["rebuild"] = {
                "count": len(skus), "skus": skus,
                "command": _heal_command(skus, available=False),
                "provenance": _heal_provenance(skus, lookup_fn=lookup_fn),
                "why": "карточки с ошибкой (frozen/error_fixable): патч одного поля молча гибнет — "
                       "лечится полным пере-билдом (offer-mappings→cards→campaign)",
            }
    if live and to_place:
        skus = [r.get("offerId") for r in to_place if r.get("offerId")]
        if skus:
            heal["place"] = {
                "count": len(skus), "skus": skus,
                "command": _heal_command(skus, available=False),
                "why": "контент готов, карточка не размещена в кампании (NO_CARD_ADD_TO_CAMPAIGN) — "
                       "та же точечная команда до-разместит",
            }

    heal["needed"] = bool(heal["rebuild"] or heal["place"])

    # Честные оговорки о ПОЛНОТЕ сверки — перекрывают needed на None, когда точные SKU назвать нельзя.
    ce = (kpis or {}).get("cards_errored")
    if not live and ce:
        heal["needed"] = None
        heal["note"] = (f"{ce} карточек с ошибкой ИЗ ПАМЯТИ — точные SKU не назвать без живого чтения "
                        "кабинета (read_cabinet=True; автопилот уже читает живьём)")
    elif live and cat.get("cards_errored") is None:
        heal["needed"] = None
        heal["note"] = ("здоровье кабинета недостижимо (классификатор write мид-фикс?) — "
                        "сверка неполна, точные SKU не названы")
    elif heal["rebuild"]:
        prov = heal["rebuild"]["provenance"]
        sup = {p.get("supplier") for p in prov if p.get("supplier")}
        if len(sup) == 1:
            heal["note"] = (f"все SKU от поставщика «{next(iter(sup))}» — подставьте его выгрузку "
                            "в <ДОНОР.xlsx> и его slug в <SLUG>")

    return heal


def run_day(shift_fn=None, tick_fn=None, trend_source_fn=None, head_source_fn=None, head_city=None,
            cabinet_read_fn=None, read_cabinet=False, preflight_fn=None, planner_fn=None,
            target_sku=None, risk_cap_rub=None,
            business_id=None, campaign_id=None, dry=True, commit=False, remember=True, use_env=True,
            **shift_kw):
    """Провести день: смена ролей + тик управляющего + стратег + трендскаут + ГОЛОВА → единый отчёт.

    shift_fn/tick_fn — швы (для тестов и для запуска без сети). По умолчанию берём настоящих
    БРИГАДИРА и УПРАВЛЯЮЩЕГО. Каждый шаг обёрнут в _safe: провал одного не роняет день (B2).
    head_source_fn — шов источника кандидатов для ГОЛОВЫ (нос спроса, напр. wb_scout). Не подключён →
    ГОЛОВА честно докладывает NO_HEAD_SOURCE (не «предлагать нечего», а «нам не дали источник», H1).
    use_env=True — подтянуть ключи из arbiter/.env и id кабинета/магазина из окружения (нужно для
    запуска по расписанию). Явно переданные business_id/campaign_id имеют приоритет.
    preflight_fn — шов ИСТОЧНИКА ЗАЛИВА (ymarket_zaliv_source.build_preflight_fn): thunk без аргументов,
    сухо собирает партию из донора и возвращает готовность → ready_to_publish берётся из РЕАЛЬНОГО
    «полетит», а не из памяти. Не подключён → ready_to_publish остаётся из памяти (обратная совм.), как
    у head_source_fn/cabinet_read_fn. 0₽: thunk лишь собирает карточки в памяти (publish_card dry, commit=False).
    planner_fn — шов ПЛАНЁРКИ (ymarket_plannerka_v1.build_plan, шаг 0 «УТРО ПРЕЖДЕ РАБОТ»): thunk без
    аргументов, строит ПЛАН ДНЯ из реальных сторов (0₽, только ЧТЕНИЕ). OFF по умолчанию (None) →
    обратная совместимость: день ведёт себя как раньше, day['plan']=None. Здесь план только СТРОИТСЯ;
    запись плана/интэйк заданий — за вызывающим (автопилот/__main__ под своим правилом), не run_day.
    Возвращает дневной отчёт (dict) — его печатает/шлёт ymarket_report_v1.
    """
    ts = _now()
    env_picked = load_env_file() if use_env else []
    if use_env:
        business_id, campaign_id = _resolve_ids(business_id, campaign_id)
    day = {
        "schema": DAY_SCHEMA,
        "ts": ts,
        "date": ts[:10],
        "dry": dry, "commit": commit,
        "business_id_known": bool(business_id),
        "campaign_id_known": bool(campaign_id),
        "env_loaded": env_picked,          # только ИМЕНА переменных, не значения
        "roles": {}, "failures": [], "escalations": [],
    }
    if not business_id:
        day["failures"].append(
            "businessId неизвестен — ДИСПЕТЧЕР и КОНТРОЛЁР слепы (нет YANDEX_BUSINESS_ID "
            "в окружении и ни в одном .env: mint/.env, SOCC/.env, arbiter/.env)")

    # ── 0. ПЛАНЁРКА (УТРО) ПРЕЖДЕ РАБОТ: собрать ПЛАН ДНЯ из сторов (0₽, только read) ──
    # planner_fn — шов ПЛАНЁРКИ (ymarket_plannerka_v1.build_plan thunk). OFF по умолчанию (None) →
    # обратная совместимость: день ведёт себя как раньше, 'plan' пусто. Здесь ПЛАН только СТРОИТСЯ
    # (чтение сторов, 0₽); запись плана/интэйк заданий делает вызывающий (автопилот/__main__ под
    # своим commit-правилом), НЕ run_day. Провал планёрки не роняет день (B2): честно в failures.
    plan = None
    if planner_fn is not None:
        rp = _safe("PLANNERKA", planner_fn)
        if rp["ok"]:
            plan = rp["result"]
        else:
            day["failures"].append(f"ПЛАНЁРКА упала: {rp['error']}")
    day["plan"] = plan          # ПЛАН ДНЯ в отчёт (или None, если планёрка не подключена)

    # ── 1. Смена бригады (роли) ──
    shift_report = None
    if shift_fn is not False:
        fn = shift_fn
        if fn is None:
            try:
                import ymarket_brigade_v1 as brigade
                fn = brigade.shift
            except Exception as e:
                day["failures"].append(f"БРИГАДИР недоступен: {type(e).__name__}: {e}")
                fn = None
        if fn is not None:
            r = _safe("BRIGADE", fn, business_id, campaign_id=campaign_id,
                      dry=dry, commit=commit, **shift_kw)
            if r["ok"]:
                shift_report = r["result"]
                day["roles"]["BRIGADE"] = {
                    "ok": True,
                    "steps": {n: {kk: vv for kk, vv in s.items() if kk != "human"}
                              for n, s in (shift_report.get("steps") or {}).items()},
                    "human": {n: s.get("human") for n, s in (shift_report.get("steps") or {}).items()
                              if s.get("human")},
                }
                day["escalations"].extend(shift_report.get("escalations") or [])
                day["failures"].extend(shift_report.get("errors") or [])
            else:
                day["roles"]["BRIGADE"] = {"ok": False, "error": r["error"]}
                day["failures"].append(f"смена бригады упала: {r['error']}")

    # ── 2. Тик управляющего (карточки/индекс/память) ──
    if tick_fn is not False:
        fn = tick_fn
        if fn is None:
            try:
                import ymarket_manager_v1 as manager
                fn = manager.tick
            except Exception as e:
                day["failures"].append(f"УПРАВЛЯЮЩИЙ недоступен: {type(e).__name__}: {e}")
                fn = None
        if fn is not None:
            # quiet=True: у дня свой единый отчёт, тик не должен печатать поверх него.
            # Проверяем сигнатуру явно: _safe глотает исключения, поэтому try/except тут не помог бы,
            # а старый тик без параметра должен продолжать работать (обратная совместимость).
            kw = {"dry": dry, "commit": commit}
            try:
                import inspect
                if "quiet" in inspect.signature(fn).parameters:
                    kw["quiet"] = True
            except (TypeError, ValueError):
                pass
            r = _safe("MANAGER_TICK", fn, **kw)
            if r["ok"]:
                t = r["result"] or {}
                day["roles"]["MANAGER_TICK"] = {"ok": True, "action": t.get("action"),
                                                "tick_id": t.get("tick_id"),
                                                "errors": t.get("errors") or []}
                day["failures"].extend(t.get("errors") or [])
            else:
                day["roles"]["MANAGER_TICK"] = {"ok": False, "error": r["error"]}
                day["failures"].append(f"тик управляющего упал: {r['error']}")

    # ── 3. Само-модель (KPI живут здесь) ──
    doc = state.load()
    r = _safe("SELF", self_mod.self_status, doc)
    st = r["result"] if r["ok"] else {}
    if not r["ok"]:
        day["failures"].append(f"само-модель упала: {r['error']}")

    # ── 4. СТРАТЕГ: где недобранные деньги ──
    r = _safe("STRATEGIST", strategist.plan, doc, shift_report, target_sku)
    strat = r["result"] if r["ok"] else None
    day["roles"]["STRATEGIST"] = ({"ok": True, "agg": strat["agg"],
                                   "moves": strat["moves"], "need_sources": strat["need_sources"],
                                   "human": strategist.render(strat)}
                                  if r["ok"] else {"ok": False, "error": r["error"]})
    if not r["ok"]:
        day["failures"].append(f"СТРАТЕГ упал: {r['error']}")

    # ── 5. ТРЕНД-СКАУТ: окна спроса ──
    r = _safe("TRENDSCOUT", trendscout.scan, trend_source_fn, risk_cap_rub)
    trend = r["result"] if r["ok"] else None
    day["roles"]["TRENDSCOUT"] = ({"ok": bool(trend and trend.get("ok")),
                                   "agg": (trend or {}).get("agg"),
                                   "candidates": (trend or {}).get("candidates", []),
                                   "need_source": (trend or {}).get("need_source"),
                                   "human": trendscout.render(trend)}
                                  if r["ok"] else {"ok": False, "error": r["error"]})
    if not r["ok"]:
        day["failures"].append(f"ТРЕНД-СКАУТ упал: {r['error']}")

    # ── 5b. ГОЛОВА: свести спрос+физику+окно в суточный шорт-лист «предложить» (переиспользуем trend) ──
    # Идёт ПОСЛЕ трендскаута намеренно (H4): окно уже посчитано — не зовём скаут второй раз. Источник
    # кандидатов (head_source_fn) не подключён → ГОЛОВА честно вернёт NO_HEAD_SOURCE (не роняет день).
    r = _safe("HEAD", head.plan_day, head_source_fn=head_source_fn, trend_result=trend, city=head_city)
    hres = r["result"] if r["ok"] else None
    day["roles"]["HEAD"] = ({"ok": bool(hres and hres.get("ok")),
                             "agg": (hres or {}).get("agg"),
                             "shortlist": (hres or {}).get("shortlist", []),
                             "blocked": (hres or {}).get("blocked", []),
                             "reason": (hres or {}).get("reason"),
                             "need_source": (hres or {}).get("need_source"),
                             "human": head.render(hres)}
                            if r["ok"] else {"ok": False, "error": r["error"]})
    if not r["ok"]:
        day["failures"].append(f"ГОЛОВА упала: {r['error']}")

    # ── 5c. ЖИВОЕ ЧТЕНИЕ КАБИНЕТА (провязка СВЕРКИ в цикл): реальный errors[] важнее памяти ──
    # cabinet_read_fn — явный шов (тесты/кастом), имеет приоритет. read_cabinet=True строит штатный
    # ридер сам, когда знаем businessId. Обе ветки — ЧТЕНИЕ, 0₽, RUBICON цел (наружу ничего, денег нет).
    # Провал чтения не роняет день (B2): честно в failures, cards_errored останется из памяти.
    if cabinet_read_fn is None and read_cabinet and business_id:
        cabinet_read_fn = lambda: _read_cabinet(business_id, campaign_id)
    cabinet = None
    if cabinet_read_fn is not None:
        rc = _safe("CABINET_READ", cabinet_read_fn)
        if rc["ok"]:
            cabinet = rc["result"]
        else:
            day["failures"].append(f"живое чтение кабинета упало: {rc['error']}")
    day["cabinet"] = cabinet          # снимок кабинета в отчёт (или None, если не читали)

    # ── 5d. ГОТОВНОСТЬ ПАРТИИ К ЗАЛИВУ (провязка ВЫБОР→ЗАЛИВ): сухо собрать донор → «сколько полетит» ──
    # preflight_fn — шов ИСТОЧНИКА ЗАЛИВА (thunk). Ленив и 0₽: собирает карточки в памяти
    # (publish_card dry, commit=False — наружу ничего, денег нет). Донор бывает двумя видами:
    # XLSX-файл (читается локально, 0 GET) или cargo-avto slug (живой GET листинга, 0₽, fail-soft —
    # сеть легла → честный блокер, не краш). Не подключён → zaliv=None, ready_to_publish останется из
    # памяти (обратная совм.). Провал сборки не роняет день (B2): честно в failures — день НЕ соврёт
    # «партия готова», если сухая сборка упала.
    zaliv = None
    if preflight_fn is not None:
        rz = _safe("ZALIV_PREFLIGHT", preflight_fn)
        if rz["ok"]:
            zaliv = rz["result"]
        else:
            day["failures"].append(f"сухая сборка партии к заливу упала: {rz['error']}")
    day["zaliv"] = zaliv          # сводка готовности партии (или None, если источник не подключён)

    # ── 6. KPI + дельта ко вчера ──
    day["kpis"] = collect_kpis(st, shift_report, cabinet=cabinet, zaliv=zaliv)
    # Провенанс числа ошибок: живая СВЕРКА кабинета или память само-модели. Отчёт не должен врать,
    # ОТКУДА взялось «карточек с ошибкой» — это сердце планки YM1 «ни одной карточки с ошибкой».
    _cat = (cabinet or {}).get("catalog") or {}
    day["cards_errored_source"] = "cabinet_live" if _cat.get("cards_errored") is not None else "memory"
    # Провенанс готовности к заливу: живая сухая сборка партии или память (та же честность, что выше).
    day["ready_to_publish_source"] = "zaliv_live" if (zaliv and zaliv.get("ready") is not None) else "memory"
    hist = _read_journal()
    yesterday = hist[-1] if hist else None
    day["delta"] = _delta(day["kpis"], (yesterday or {}).get("kpis"))
    day["compared_to"] = (yesterday or {}).get("date")

    # ── 6b. РЕЦЕПТ ЛЕЧЕНИЯ: живая заморозка → ТОЧНАЯ команда починки (рунг 4c). 0₽, только текст. ──
    # RUBICON: цикл НИКОГДА не выполняет эту команду — это рецепт для оператора (commit-пути нет).
    day["heal"] = build_heal(cabinet, day["kpis"], day["cards_errored_source"])

    # ── 7. Что горит (то, что нельзя отложить) ──
    burning = []
    k = day["kpis"]
    if isinstance(k.get("quality_index"), (int, float)) and k["quality_index"] < 40:
        burning.append({"what": "индекс качества ниже 40 — магазин отключат на 7 дней",
                        "action": "STOP: разобрать причины отмен/опозданий", "owner": "ОПЕРАТОР"})
    if k.get("urgent_orders"):
        burning.append({"what": f"{k['urgent_orders']} заказов горят по таймеру 60 мин",
                        "action": "собрать сейчас", "owner": "ОПЕРАТОР"})
    if k.get("cards_errored"):
        _src = "живьём" if day.get("cards_errored_source") == "cabinet_live" else "из памяти"
        _rb = (day.get("heal") or {}).get("rebuild") or {}
        if _rb.get("skus"):
            _shown = ", ".join(str(s) for s in _rb["skus"][:8]) + ("…" if len(_rb["skus"]) > 8 else "")
            burning.append({
                "what": f"{k['cards_errored']} карточек с ошибкой ({_src}): {_shown} (закон YM1: цель 0)",
                "action": _rb["command"], "owner": "УПРАВЛЯЮЩИЙ", "heal_ref": "day.heal.rebuild"})
        else:
            _note = (day.get("heal") or {}).get("note") or "включите live-чтение кабинета для точных SKU"
            burning.append({
                "what": f"{k['cards_errored']} карточек с ошибкой ({_src}; закон YM1: цель 0)",
                "action": _note, "owner": "УПРАВЛЯЮЩИЙ", "heal_ref": "day.heal"})
    # Партия к заливу собрана СУХО, но часть карточек не встала (ошибка сборки/категория) — планка YM1
    # «льём только 0 ошибок» ловится ДО публикации: называем SKU, не даём залить бракованную партию.
    z = day.get("zaliv")
    if z and z.get("errors"):
        _zsk = z.get("error_skus") or []
        _ztail = (": " + ", ".join(str(s) for s in _zsk[:8]) + ("…" if len(_zsk) > 8 else "")) if _zsk else ""
        burning.append({
            "what": f"партия к заливу: {z['errors']} карточек не собрались{_ztail} "
                    f"(из {z.get('total')} — закон YM1: льём только 0 ошибок)",
            "action": "пересобрать эти SKU до залива (сухо, 0₽); бракованную партию не публиковать",
            "owner": "УПРАВЛЯЮЩИЙ", "zaliv_ref": "day.zaliv.error_skus"})
    for e in day["escalations"][:10]:
        burning.append({"what": e.get("why") or e.get("kind"), "action": e.get("action"),
                        "owner": "ОПЕРАТОР", "role": e.get("role")})
    day["burning"] = {"count": len(burning), "items": burning}

    # ── 8. Куда растём (стремление стать больше) ──
    moves = (strat or {}).get("moves") or []
    day["growth"] = {
        "top_move": (moves[0]["lever"] if moves else None),
        "top_move_why": (moves[0]["why"] if moves else None),
        "top_move_action": (moves[0]["next_action"] if moves else None),
        "ceiling_rub": ((strat or {}).get("agg") or {}).get("ceiling_rub"),
        "moves_total": len(moves),
        "need_sources": (strat or {}).get("need_sources") or [],
        "trend_candidates": ((trend or {}).get("agg") or {}).get("candidates", 0),
        "head_proposed": ((hres or {}).get("agg") or {}).get("proposed", 0),
        "next_lawful_step": (st or {}).get("next_lawful_step"),
    }

    day["ok"] = not day["failures"]
    if remember:
        day["_journaled"] = _append_journal(day)
    return day


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="СУТОЧНЫЙ ЦИКЛ — утренняя смена органа (dry по умолчанию, 0₽)")
    ap.add_argument("--commit", action="store_true", help="реальный режим (READ/WRITE по гейту)")
    ap.add_argument("--target-sku", type=int, default=None, help="цель по числу SKU (для СТРАТЕГА)")
    ap.add_argument("--risk-cap", type=float, default=None, help="лимит риска на хайп-закупки, ₽")
    ap.add_argument("--business-id", default=None)
    ap.add_argument("--campaign-id", default=None)
    # Источник кандидатов ГОЛОВЫ. По умолчанию ВЫКЛЮЧЕН (none) — как trend_source_fn: без флага
    # ГОЛОВА честно докладывает NO_HEAD_SOURCE и сеть не трогается. `wb` подключает живой нос спроса
    # (ЧТЕНИЕ публичного WB, 0₽, RUBICON цел — предлагает, не публикует). Оператор включает по слову.
    ap.add_argument("--head-source", choices=("none", "wb"), default="none",
                    help="источник кандидатов ГОЛОВЫ: none (по умолч., без сети) | wb (живое ЧТЕНИЕ WB, 0₽)")
    ap.add_argument("--head-city", default=None, help="город для источника ГОЛОВЫ (по умолч. msk)")
    ap.add_argument("--cabinet-health", action="store_true",
                    help="живая СВЕРКА: cards_errored из реального errors[] кабинета, не из памяти (READ, 0₽)")
    # ПРОВЯЗКА ВЫБОР→ЗАЛИВ. По умолчанию ВЫКЛ (нет донора) — как --head-source: день ведёт себя как раньше.
    # С донором цикл сухо собирает партию (0₽, publish_card dry) и ready_to_publish берёт из «сколько полетит».
    # Донор: XLSX-путь (0 GET) ЛИБО cargo-avto slug категории (живой GET листинга, 0₽, бюджет по умолч.).
    ap.add_argument("--donor-zaliv", default=None,
                    help="донор партии: XLSX-путь ИЛИ cargo-avto slug (живой скан) — сухо собрать и "
                         "показать «сколько полетит» → ready_to_publish (0₽)")
    ap.add_argument("--zaliv-slug", default=None, help="slug категории для сухой сборки партии (нужен с --donor-zaliv)")
    ap.add_argument("--zaliv-city", default=None, help="город для сухой сборки партии залива")
    ap.add_argument("--zaliv-limit", type=int, default=20, help="сколько строк донора собрать в партию (сухо)")
    ap.add_argument("--plannerka", action="store_true",
                    help="УТРО ПРЕЖДЕ РАБОТ (шаг 0): собрать ПЛАН ДНЯ из реальных сторов (0₽, read). "
                         "С --commit дополнительно сохранить план и внести решения в реестр заданий")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    head_source_fn = None
    if args.head_source == "wb":
        import ymarket_head_source_v1 as head_source
        head_source_fn = head_source.build_source_fn(city=args.head_city)   # thunk ленив: сеть — при вызове

    preflight_fn = None
    if args.donor_zaliv:
        if not args.zaliv_slug:
            ap.error("--donor-zaliv требует --zaliv-slug (без slug КАТЕГОРИЙЩИК не соберёт карточку)")
        import ymarket_zaliv_source_v1 as zaliv_source
        preflight_fn = zaliv_source.build_preflight_fn(
            args.donor_zaliv, args.zaliv_slug, city=args.zaliv_city,
            limit=args.zaliv_limit)                              # thunk ленив: сборка партии — при вызове

    planner_fn = None
    if args.plannerka:
        import ymarket_plannerka_v1 as _pk
        # thunk ленив: план строится ВНУТРИ run_day (шаг 0) чтением реальных сторов, 0₽
        planner_fn = lambda: _pk.build_plan()

    d = run_day(target_sku=args.target_sku, risk_cap_rub=args.risk_cap,
                business_id=args.business_id, campaign_id=args.campaign_id,
                head_source_fn=head_source_fn, head_city=args.head_city,
                read_cabinet=args.cabinet_health, preflight_fn=preflight_fn,
                planner_fn=planner_fn,
                dry=not args.commit, commit=args.commit)
    if args.commit and planner_fn is not None and (d.get("plan") or {}).get("schema"):
        import ymarket_plannerka_v1 as _pk
        _pk.save_plan(d["plan"], commit=True)                    # запись плана (локально, PL5)
        _pk.seed_from_plan(d["plan"], commit=True)               # интэйк решений в реестр (PL4, локально)
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        import ymarket_report_v1 as report
        print(report.render_day(d))
