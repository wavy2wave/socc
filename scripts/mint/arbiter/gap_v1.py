#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GAP V1 — стадия GAP+ECON органа ARBITER: где ЕСТЬ МЕСТО ЗАЛЕТЕТЬ + доказанные связки (dry, 0₽).

ЗАЧЕМ (слова создателя): агенты видят спрос на разных МП и решают, КУДА добавить товар.
«Место залететь» = высокий спрос на источнике (WB) × слабое покрытие на Ozon/ЯМ (мало карточек,
легко ранжироваться). GAP это считает и РАНЖИРУЕТ связки, ECON (PROSPECTOR) проверяет маржу,
WARDEN режет незаконное — и только сквозь все гейты связка становится ДОКАЗАННОЙ ГИПОТЕЗОЙ.

Три слоя:
  ozon_search(query)  — публичный зонд покрытия Ozon (сколько карточек уже есть). fail-soft:
                        Ozon бот-защищён → known=False ОЖИДАЕМО, не падаем; тогда честная деградация.
  slot_score(...)     — 0..100: спрос_WB × «открытость слота» Ozon. Покрытие неизвестно → скидка+флаг.
  prove(candidate)    — прогон через PROSPECTOR.falsifiable_test + WARDEN.gate + slot →
                        verdict PROVEN|REJECTED. commit_proven() пишет ТОЛЬКО PROVEN в канон (dry).

ГРАНИЦА ЧЕСТНОСТИ: PROVEN — это доказанная ГИПОТЕЗА (спрос+маржа+закон+слот), НЕ доход. Деньги
появляются лишь при verified=true в revenue_ledger (стадии FULFILL/SETTLE). Здесь 0₽, только чтение.

Переиспользует PROSPECTOR (маржа/тест) и WARDEN (красные линии) — не дублирует. stdlib-only, fail-soft.
"""
import sys
import json
import argparse
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
MINT = HERE.parent                       # SOCC/scripts/mint
ROOT = MINT.parent.parent                # SOCC
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import socc_mint_prospect_v1 as prospector   # noqa: E402
import socc_mint_warden_v1 as warden          # noqa: E402
import supplier_scout_v1 as scout             # noqa: E402

try:
    from suppliers import http_get_json        # noqa: E402
except ImportError:
    from suppliers.base_v1 import http_get_json  # noqa: E402

PROVEN_DIR = ROOT / "MEMORY_WAVE/reports/mint/arbiter"
PROVEN_PATH = PROVEN_DIR / "proven_connections.jsonl"

OZON_SEARCH = "https://www.ozon.ru/api/composer-api.bv2/page/json/v2?url="
SATURATION_FULL = 100    # ≥100 конкурентных карточек ≈ слот насыщен (ранжироваться тяжело)
DEFAULT_LEGAL_FORM = "самозанятость"  # легальная сущность оператора (MN2 WARDEN); переопределяемо
# TODO(фаза E, ДО реальных денег): это ДЕКЛАРАЦИЯ, а не проверенный факт. Гейт MN2 сейчас проходит
# по строке-константе: если фактическая форма оператора не соответствует сделке (напр. самозанятый
# перепродаёт чужой товар — а это не его режим), WARDEN пропустит связку, потому что ему сказали
# «самозанятость». Нужен проверяемый источник (реквизиты/статус ФНС), а не хардкод.
# Виджеты composer-api, которым доверяем счётчик выдачи. ТОЛЬКО поисковая сетка —
# не табы/корзина/баннеры/отзывы. Иначе выдумаем покрытие (нарушим закон честности).
SEARCH_WIDGET_HINTS = ("searchresultsv2", "tilegrid", "megapaginator", "searchresults")


def _now():
    return datetime.now(timezone.utc).isoformat()


def ozon_search(query, limit=36):
    """Публичный зонд покрытия Ozon: сколько карточек уже под запрос (= насыщенность слота).

    Ozon бот-защищён — публичный composer часто отдаёт пусто/капчу. Это ОЖИДАЕМО: возвращаем
    {known: False} и вниз честно деградируем (слот-скор считаем от спроса WB со скидкой+флагом),
    НЕ выдумываем число конкурентов. Если ответ живой — вытаскиваем счётчик найденного.
    """
    page = f"/search/?text={urllib.parse.quote(query)}&from_global=true"
    url = OZON_SEARCH + urllib.parse.quote(page, safe="")
    payload = http_get_json(url, timeout=15)
    if not payload:
        return {"query": query, "known": False, "cards": None,
                "note": "Ozon не ответил публично (бот-защита) — покрытие неизвестно, деградируем честно"}
    total = _extract_total(payload)
    if total is None:
        return {"query": query, "known": False, "cards": None,
                "note": "Ozon ответил, но счётчик не найден в разметке — покрытие неизвестно"}
    return {"query": query, "known": True, "cards": int(total),
            "note": "покрытие Ozon прочитано из публичной выдачи"}


def _extract_total(payload):
    """Число найденных товаров ТОЛЬКО из виджета поисковой выдачи Ozon (composer widgetStates).

    Честность (закон): доверяем счётчику, лишь если он лежит ВНУТРИ виджета результатов поиска
    (searchResultsV2 / tileGrid / megaPaginator). Любой другой count/total (таб, корзина, баннер,
    отзывы) игнорируем — иначе выдумаем покрытие. Bool — не число (isinstance(False,int) is True).
    Строго не нашли → None → известность=False → честная деградация вверх по стеку.
    """
    try:
        states = payload.get("widgetStates")
        if not isinstance(states, dict):
            return None
        for key, raw in states.items():
            if not any(h in str(key).lower() for h in SEARCH_WIDGET_HINTS):
                continue
            inner = raw
            if isinstance(raw, str):
                try:
                    inner = json.loads(raw)
                except Exception:
                    continue
            if not isinstance(inner, dict):
                continue
            for field in ("totalFound", "total", "count"):
                v = inner.get(field)
                if isinstance(v, int) and not isinstance(v, bool):
                    return v
    except Exception:
        return None
    return None


def slot_score(demand_signal, coverage):
    """0..100: «место залететь» = сила спроса WB × открытость слота Ozon.

    coverage.known=True И cards — валидное число → openness = 1 - min(cards, FULL)/FULL (мало карточек = открыто).
    coverage.known=False ЛИБО cards не число → покрытие неизвестно: спрос со скидкой 0.7 + флаг
    (НЕ выдумываем слот). cards=None при known=True — противоречие разметки → тоже честная деградация.
    """
    strength = float((demand_signal or {}).get("strength", 0) or 0)
    cov = coverage or {}
    raw_cards = cov.get("cards")
    cards_valid = isinstance(raw_cards, int) and not isinstance(raw_cards, bool)
    if cov.get("known") and cards_valid:
        cards = int(raw_cards)
        openness = 1.0 - min(cards, SATURATION_FULL) / float(SATURATION_FULL)
        score = strength * (0.3 + 0.7 * openness)   # даже в насыщенном слоте спрос что-то стоит
        return round(min(100.0, score), 1), openness, False
    score = strength * 0.7                            # покрытие неизвестно/противоречиво → честная скидка
    return round(min(100.0, score), 1), None, True


# Явные булевы флаги связки, которые WARDEN.gate проверяет напрямую (FLAG_RULES).
_WARDEN_FLAGS = ("handles_third_party_funds", "resells_platform_access",
                 "impersonates_real_person", "deceives_customer")


def _to_connection(cand, legal_form):
    """Кандидат SCOUT → объект связки для WARDEN.gate.

    База — честное описание легального арбитража. НО текст/механизм/теги/флаги, заявленные в самом
    кандидате, ПОДМЕШИВАЮТСЯ (а не затираются): незаконная суть, приехавшая в кандидате (мул /
    перепродажа доступа / самозванство / обман), обязана дойти до гейта. Иначе WARDEN отбеливается —
    любой кандидат читался бы как «легальный арбитраж» и незаконная связка стала бы PROVEN.
    """
    name = cand.get("name", "")
    base_desc = (f"розничный арбитраж: закупка «{name}» у поставщика, "
                 f"честная карточка-витрина на Ozon FBS/DBS, легальная перепродажа")
    base_mech = "легальный дропшип-арбитраж (свой товар, своя карточка, честная суть сделки)"
    extra_desc = str(cand.get("description", "") or "")
    extra_mech = str(cand.get("mechanism", "") or "")
    tags = ["retail", "arbitrage", cand.get("source_market", "")]
    tags += [str(t) for t in (cand.get("tags") or [])]
    conn = {
        "venture": "ozon-dropship-RU",
        "legal_form": legal_form,
        "description": (base_desc + " " + extra_desc).strip(),
        "mechanism": (base_mech + " " + extra_mech).strip(),
        "tags": tags,
    }
    for flag in _WARDEN_FLAGS:          # явные булевы флаги кандидата → напрямую в связку
        if cand.get(flag):
            conn[flag] = True
    return conn


def _price_gate(cand, ozon_coverage, pricing):
    """ОПЦИОНАЛЬНЫЙ ценовой гейт поверх prove(): pricing_v1.decide_price даёт честную цену+индекс.

    Связывает три пути создателя (голубая вода / уникализовано-несвязываемо / matchable-floor) с
    ГАРАНТИЕЙ ПЛЮСА после комиссии+доставки. pricing — dict опций (yandex_coverage, uniqueize_report,
    delivery, min_multiple, target_multiple, net_coeff, unlink_risk_ceiling) ЛИБО True (дефолты).

    Ленивый импорт + fail-soft: если движок цены недоступен/упал — {ok:False, why:...}, конвейер жив
    (ценовой сбой НЕ роняет вечную машину). Возврат — dict decide_price или причина отказа.
    """
    opts = pricing if isinstance(pricing, dict) else {}
    try:
        import pricing_v1 as price_engine
    except Exception as e:
        return {"ok": False, "strategy": "price_engine_unavailable",
                "why": f"движок цены недоступен: {e}"}
    try:
        return price_engine.decide_price(
            cand,
            ozon_coverage=ozon_coverage,
            yandex_coverage=opts.get("yandex_coverage"),
            uniqueize_report=opts.get("uniqueize_report"),
            min_multiple=opts.get("min_multiple", price_engine.MIN_MULTIPLE),
            target_multiple=opts.get("target_multiple", price_engine.TARGET_MULTIPLE),
            delivery=opts.get("delivery", prospector.DELIVERY_NET),
            net_coeff=opts.get("net_coeff"),
            unlink_risk_ceiling=opts.get("unlink_risk_ceiling", 25),
        )
    except Exception as e:
        return {"ok": False, "strategy": "price_gate_error",
                "why": f"ценовой гейт упал на кандидате: {e}"}


def prove(cand, profit_target=600, min_profit=200, legal_form=DEFAULT_LEGAL_FORM, coverage=None,
          pricing=None):
    """Прогнать связку через все гейты: ECON (PROSPECTOR) + закон (WARDEN) + слот (GAP).

    verdict PROVEN ⟺ falsifiable_test.passed И profit_net≥min_profit И WARDEN=PASS.
    Слот НЕ блокирует (низкий слот = хуже ранг, но связка законна и прибыльна) — он ранжирует.

    pricing (ОПЦИОНАЛЬНО, обратносовместимо): None → поведение 1:1 как раньше (M2 зелёный).
    dict/True → добавляется ЦЕНОВОЙ ГЕЙТ: decide_price считает честную цену+индекс+гарантию плюса.
    Гейт может лишь ужесточить (PROVEN→REJECTED, если цена невозможна с плюсом) — НИКОГДА не мягчит.

    ФАЗА A (доставка): когда pricing задан, доставка прокидывается в ECON ДО falsifiable_test —
    иначе порог min_profit применялся к числу без ₽325 издержек, и связка с реальными +₽1
    проходила как «PROVEN, чист ₽210». Теперь порог и вердикт меряют одну величину с ценой.
    """
    cand = dict(cand)
    cand.setdefault("profit_target", profit_target)
    cand.setdefault("min_profit", min_profit)

    # Доставка в ECON: явная в кандидате — сильнее; иначе из pricing; при pricing без ключа —
    # факт кабинета, а НЕ молчаливый ноль. pricing=None и нет ключа → 0 (обратная совместимость).
    # Затем ОДНО число уходит и в ECON, и в ценовой гейт — чтобы вердикт и цена не разъезжались.
    if pricing:
        _popts = dict(pricing) if isinstance(pricing, dict) else {}
        if cand.get("delivery") is None:
            cand["delivery"] = _popts.get("delivery", prospector.DELIVERY_NET)
        _popts["delivery"] = float(cand["delivery"] or 0)
        pricing = _popts

    # fail-soft (закон вечной машины): битый кандидат (cost=None/'abc') не должен ронять конвейер.
    # ECON падает → связка деградирует в REJECTED с причиной, find_gaps/scout_gap живут дальше.
    try:
        econ = prospector.falsifiable_test(cand)
    except Exception as e:
        econ = {"passed": False, "why": [f"ECON упал на кандидате: {e}"],
                "margin": {"profit_net": 0, "price_sell": 0, "cost_buy": cand.get("cost"), "fee": 0}}
    try:
        ward = warden.gate(_to_connection(cand, legal_form))
    except Exception as e:
        ward = {"status": "FAIL", "hard_failures": ["WARDEN_error"],
                "reasons": [f"WARDEN упал на кандидате: {e}"]}
    sscore, openness, degraded = slot_score(cand.get("demand_signal"), coverage)

    pnet = econ["margin"]["profit_net"]
    reasons = []
    if not econ["passed"]:
        reasons.append("ECON: " + ", ".join(econ["why"]))
    elif pnet < float(min_profit):
        reasons.append(f"ECON: маржа ₽{pnet} < порога ₽{min_profit}")
    if ward["status"] != "PASS":
        reasons += ["WARDEN: " + r for r in ward["reasons"]]

    verdict = "PROVEN" if (econ["passed"] and pnet >= float(min_profit)
                           and ward["status"] == "PASS") else "REJECTED"

    # ОПЦИОНАЛЬНЫЙ ценовой гейт (обратносовместим: pricing=None → блок не исполняется вовсе).
    # Может лишь УЖЕСТОЧИТЬ: PROVEN, у которого нет честной цены с плюсом → REJECTED (защита маржи).
    price = None
    if pricing:
        price = _price_gate(cand, coverage, pricing)
        if verdict == "PROVEN" and not price.get("ok"):
            verdict = "REJECTED"
            reasons.append("PRICE: " + str(price.get("why", "честная цена с плюсом невозможна")))

    return {
        "verdict": verdict,
        "name": cand.get("name"), "sku": cand.get("sku"), "url": cand.get("url"),
        "cost": cand.get("cost"), "supplier": cand.get("source_market"),
        "econ": {"passed": econ["passed"], "profit_net": pnet,
                 "price_sell": econ["margin"]["price_sell"], "why": econ["why"],
                 # два разных числа больше не зовутся одинаково (фаза A):
                 "delivery": econ["margin"].get("delivery", 0.0),
                 "profit_net_before_delivery": econ["margin"].get("profit_net_before_delivery", pnet)},
        "warden": {"status": ward["status"], "hard_failures": ward["hard_failures"]},
        "slot": {"score": sscore, "openness": openness, "coverage_degraded": degraded,
                 "coverage": coverage},
        "price": price,
        "demand_signal": cand.get("demand_signal"),
        "reasons": reasons,
        "proved_at": _now(),
    }


def _conn_key(rec):
    """Стабильный ключ дедупа. sku — главный идентификатор; нет sku → url (тоже уникален у товара).

    Раньше ключ был supplier|sku|ozon — но supply_real проходит по url ИЛИ sku, значит url-only
    связки все имели sku=None и схлопывались в один ключ → доказанные терялись. Теперь fallback на url.
    """
    ident = rec.get("sku") or rec.get("url")
    return f"{rec.get('supplier')}|{ident}|ozon"


def commit_proven(proven, path=None, dry=True):
    """Записать ТОЛЬКО PROVEN-связки в канон ARBITER (JSONL), дедуп по supplier|sku|ozon.

    dry=True (по умолчанию M2) — деньги/Ozon не трогаем, пишем лишь ДОКАЗАННЫЕ ГИПОТЕЗЫ.
    Возвращает {written, skipped_dup, path}. Канон растёт только чистыми связками.
    """
    path = Path(path) if path else PROVEN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(_conn_key(json.loads(line)))
            except Exception:
                continue
    written, dup, no_id = 0, 0, 0
    lines = []
    for rec in proven:
        if rec.get("verdict") != "PROVEN":
            continue
        if not (rec.get("sku") or rec.get("url")):
            no_id += 1          # ни sku, ни url — идентифицировать связку нечем, НЕ схлопываем в None
            continue
        k = _conn_key(rec)
        if k in seen:
            dup += 1
            continue
        seen.add(k)
        lines.append(json.dumps(dict(rec, dry=dry, kind="proven_hypothesis"), ensure_ascii=False))
        written += 1
    if lines:
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return {"written": written, "skipped_dup": dup, "skipped_no_id": no_id, "path": str(path)}


def find_gaps(candidates, profit_target=600, min_profit=200, legal_form=DEFAULT_LEGAL_FORM,
              probe_ozon=True, coverage_by_query=None, pricing=None):
    """Ранжированный список связок: каждый кандидат сквозь ECON+WARDEN+слот. PROVEN вперёд, по слот-скору.

    pricing (опц., обратносовместимо): None → поведение 1:1 как раньше. dict/True → ЦЕНОВОЙ ГЕЙТ
    (фаза A: доставка прокидывается в ECON, порог min_profit меряет правильную величину).
    """
    coverage_by_query = coverage_by_query or {}
    out = []
    for c in candidates:
        q = c.get("name", "")
        cov = coverage_by_query.get(q)
        if cov is None and probe_ozon:
            cov = ozon_search(q)
            coverage_by_query[q] = cov
        out.append(prove(c, profit_target, min_profit, legal_form, cov, pricing))
    out.sort(key=lambda r: (r["verdict"] == "PROVEN", r["slot"]["score"]), reverse=True)
    return out


def scout_gap(query, supplier="wildberries", city="msk", limit=40, profit_target=600,
              min_profit=200, legal_form=DEFAULT_LEGAL_FORM, probe_ozon=True, commit=False, dry=True,
              pricing=None):
    """Живой сквозной проход: SCOUT(query) → find_gaps → (опц.) commit PROVEN в канон.

    pricing (опц.) прокидывается до prove(): без него на этом пути ценового гейта нет вовсе.
    """
    res = scout.scout(supplier, query=query, city=city, limit=limit,
                      profit_target=profit_target, min_profit=min_profit)
    cands = res.get("candidates", [])
    ranked = find_gaps(cands, profit_target, min_profit, legal_form, probe_ozon, pricing=pricing)
    proven = [r for r in ranked if r["verdict"] == "PROVEN"]
    commit_res = commit_proven(proven, dry=dry) if commit else None
    return {"query": query, "supplier": supplier, "city": city,
            "scanned": len(cands), "proven": len(proven), "rejected": len(ranked) - len(proven),
            "ranked": ranked, "committed": commit_res}


def _main(argv=None):
    ap = argparse.ArgumentParser(description="GAP V1 — место залететь + доказанные связки (dry, 0₽)")
    ap.add_argument("--query", required=True, help="категория/запрос: 'дождевик'")
    ap.add_argument("--supplier", default="wildberries")
    ap.add_argument("--city", default="msk")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--profit-target", type=int, default=600)
    ap.add_argument("--min-profit", type=int, default=200)
    ap.add_argument("--legal-form", default=DEFAULT_LEGAL_FORM, help="легальная сущность оператора (MN2)")
    ap.add_argument("--no-ozon-probe", action="store_true", help="не звать Ozon (быстро, слот от спроса)")
    ap.add_argument("--commit", action="store_true", help="записать PROVEN в канон (dry-гипотезы)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    res = scout_gap(args.query, args.supplier, args.city, args.limit, args.profit_target,
                    args.min_profit, args.legal_form, probe_ozon=not args.no_ozon_probe,
                    commit=args.commit, dry=True)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    print(f"🎯 GAP [{res['supplier']}→ozon]  q=«{res['query']}»  город={res['city']}")
    print(f"   отсканировано {res['scanned']} · ДОКАЗАНО {res['proven']} · отклонено {res['rejected']}")
    for r in res["ranked"][:12]:
        mark = "✅" if r["verdict"] == "PROVEN" else "⛔"
        cov = r["slot"]["coverage"] or {}
        cov_s = (f"озон-карт={cov.get('cards')}" if cov.get("known")
                 else "озон=неизв(деград)")
        e = r["econ"]
        print(f"   {mark} слот[{r['slot']['score']:>5.1f}] чист ₽{e['profit_net']:>6.0f}  "
              f"спрос[{(r['demand_signal'] or {}).get('strength', 0):>3}]  {cov_s:<18}  {r['name'][:34]}")
        if r["verdict"] != "PROVEN":
            print(f"        причина: {'; '.join(r['reasons'])[:96]}")
    if res["committed"]:
        c = res["committed"]
        print(f"   💾 в канон: записано {c['written']}, дублей пропущено {c['skipped_dup']} → {c['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
