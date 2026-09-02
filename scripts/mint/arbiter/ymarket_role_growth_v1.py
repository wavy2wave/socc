#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СКАУТ РОСТА (ymarket_role_growth_v1) — где орган ещё НЕ присутствует.

Оператор дословно: «всегда ищи как масштабироваться законно: модели, города, ассортимент. Всегда цель расти.»
СТРАТЕГ (ymarket_role_strategist_v1) уже добирает деньги на ОСИ АССОРТИМЕНТА (карточки, остатки, цена, индекс).
Но две другие названные оси — ГОРОДА и МОДЕЛИ — были слепыми: никто не предлагал «зайти в новый город»
или «оживить спящую модель сбыта». Этот скаут закрывает ровно их. Ассортимент не трогаем — не дублируем СТРАТЕГА.

ЧТО ДЕЛАЕТ: смотрит снимок кабинета (магазины/склады/модели/города) и называет ЗАКОННЫЕ ходы роста —
  • МОДЕЛИ: спящий магазин (DBS заведён, но молчит), выключенная модель на складе (Express/DBS off);
  • ГОРОДА: Express живёт лишь в N городах — каждый новый город это новый пул спроса рядом с покупателем;
           города, которых мерчандайзер не знает габаритно (берёт консервативный дефолт → режет годный товар).

ЗАКОНЫ (наследуем у органа, growth-профиль):
  G1  гипотеза без числа — не гипотеза: нет ₽ → честный needs_source, не выдуманный доход.
  G2  спрос из воздуха не берём: город/модель без источника спроса — это НЕ обещание денег, а лишь открытая дверь.
  G3  READ-ONLY: скаут НИКОГДА не пишет в кабинет. Он только называет законный следующий шаг и ЧЕЙ он.
  G4  оси роста этого скаута — ГОРОДА и МОДЕЛИ (ассортимент — у СТРАТЕГА; не дублируем).
  G5  fail-soft: битый/частичный снимок не роняет скаут (закон L6).
  G6  честный блокер: если рост упирается в руки (склад в кабинете) или в слово (write-гейт) — это помечено blocked_by.

ГРАНИЦА (RUBICON цел): ни одной записи в маркетплейс. Живой режим только ЧИТАЕТ (склады/магазины). 0₽.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(HERE.parent), str(HERE.parent.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

CHARTER = {
    "id": "YM_GROWTH_SCOUT",
    "name_ru": "СКАУТ РОСТА",
    "mandate": ("находить ЗАКОННЫЕ двери роста по осям ГОРОДА и МОДЕЛИ — там, где орган ещё не присутствует "
                "или присутствует спящим — и давать оператору точный следующий шаг и честно недостающее число."),
    "owns": "карта присутствия: активные каналы (магазин×модель), города Express, слепые для мерчандайзера города.",
    "inputs": "снимок кабинета: магазины (placements/активность), склады (модели/город), города с известными лимитами.",
    "outputs": "ранжированные ходы роста {lever, why, next_action, owner, effort, needs_source, blocked_by} + агрегат.",
    "laws": [
        "G1 гипотеза без числа — не гипотеза (нет ₽ → needs_source)",
        "G2 спрос из воздуха не берём (город/модель без источника = открытая дверь, не деньги)",
        "G3 READ-ONLY: скаут не пишет в кабинет, только называет законный шаг и его владельца",
        "G4 оси = ГОРОДА и МОДЕЛИ (ассортимент — у СТРАТЕГА, не дублируем)",
        "G5 fail-soft: битый снимок не роняет скаут (L6)",
        "G6 честный блокер: руки-в-кабинете / write-гейт / слово оператора помечены blocked_by",
    ],
    "kpi": "DAY: активных каналов, городов Express, слепых городов. WEEK/MONTH: рост этих чисел.",
    "proves_by": "tests/run_yandex_growth.py — законы падают при нарушении (сухо, 0₽, без сети).",
}

# Стоимость усилия хода (те же единицы, что у СТРАТЕГА — сопоставимость ходов между ролями).
EFFORT = {"trivial": 1, "low": 2, "medium": 5, "high": 12}

# Оси роста этого скаута (ассортимент сознательно НЕ здесь — его ведёт СТРАТЕГ).
AXIS_CITY = "ГОРОДА"
AXIS_MODEL = "МОДЕЛИ"

# Модели размещения Маркета (зеркало ymarket_trade_hands_v1.PLACEMENTS).
MODELS = ("FBS", "DBS", "EXPRESS")


# ─────────────────────────── fail-soft примитивы (закон L6) ───────────────────────────

def _asdict(v):
    return v if isinstance(v, dict) else {}


def _aslist(v):
    return v if isinstance(v, (list, tuple)) else []


def _city(v):
    """Город к сравнимому виду: строка, lower, trim. Не строка/пусто → ''. """
    if not isinstance(v, str):
        return ""
    return v.strip().lower()


def _known_cities_default():
    """Города, для которых мерчандайзер реально знает габаритные лимиты (не консервативный дефолт).

    Читаем из ymarket_role_merchandiser_v1.CITY_LIMITS (минус служебный 'default'). Нет модуля → пусто.
    """
    try:
        import ymarket_role_merchandiser_v1 as merch
        return [k for k in _asdict(merch.CITY_LIMITS).keys() if k != "default"]
    except Exception:
        return []


# ─────────────────────────── единый ход (как у СТРАТЕГА) ───────────────────────────

def _lever(axis, lever, why, next_action, owner, effort,
           expected_rub=None, formula=None, facts=None, needs_source=None, blocked_by=None):
    """Один ход роста. score=₽/усилие; на осях ГОРОДА/МОДЕЛИ дохода из воздуха нет → expected_rub=None,
    честный needs_source (G1/G2). Ходы без числа сортируются по дешевизне законного шага."""
    units = EFFORT.get(effort, 5)
    score = (expected_rub / units) if isinstance(expected_rub, (int, float)) and not isinstance(expected_rub, bool) else None
    return {
        "axis": axis, "lever": lever, "why": why,
        "expected_rub": expected_rub, "formula": formula,
        "next_action": next_action, "owner": owner,
        "effort": effort, "effort_units": units, "score": score,
        "facts": facts or {}, "needs_source": needs_source, "blocked_by": blocked_by,
    }


# ─────────────────────────── снимок кабинета ───────────────────────────

def _norm_snapshot(snap):
    """Привести снимок к устойчивому виду (любой мусор → безопасные пустые формы, закон G5/L6)."""
    snap = _asdict(snap)
    shops = [_asdict(s) for s in _aslist(snap.get("shops"))]
    whs = [_asdict(w) for w in _aslist(snap.get("warehouses"))]
    known = snap.get("known_cities")
    known = [_city(c) for c in _aslist(known)] if known is not None else _known_cities_default()
    return {
        "business_id": snap.get("business_id"),
        "shops": shops,
        "warehouses": whs,
        "known_cities": [c for c in known if c],
    }


def _derive(snap):
    """Из снимка вывести карту присутствия. Ничего не выдумываем — только то, что в данных."""
    active_channels, dormant_shops, unknown_shops = [], [], []
    for s in snap["shops"]:
        sid = str(s.get("id") or "?")
        placements = [str(p).upper() for p in _aslist(s.get("placements")) if str(p).strip()]
        active = s.get("active")
        if active is False:
            dormant_shops.append({"id": sid, "placements": placements})
        elif active is True:
            for p in placements:
                active_channels.append({"shop": sid, "model": p})
        else:
            unknown_shops.append({"id": sid, "placements": placements})  # активность не читали — не судим

    disabled_models, served_cities, express_cities = [], set(), set()
    for w in snap["warehouses"]:
        wid = str(w.get("id") or "?")
        wname = str(w.get("name") or wid)
        city = _city(w.get("city"))
        if city:
            served_cities.add(city)
        for m, status in _asdict(w.get("models")).items():
            mu, st = str(m).upper(), str(status).upper()
            if mu == "EXPRESS" and st == "ENABLED" and city:
                express_cities.add(city)
            if st in ("DISABLED", "DISABLING"):
                disabled_models.append({"warehouse": wname, "warehouse_id": wid, "city": city, "model": mu})

    known = set(snap["known_cities"])
    return {
        "active_channels": active_channels,
        "dormant_shops": dormant_shops,
        "unknown_shops": unknown_shops,
        "disabled_models": disabled_models,
        "served_cities": sorted(served_cities),
        "express_cities": sorted(express_cities),
        "blind_cities": sorted(served_cities - known),   # орган возит туда, но мерчандайзер город не знает
        "known_cities": sorted(known),
    }


# ─────────────────────────── ходы по осям ───────────────────────────

def _lever_dormant_shops(d):
    """МОДЕЛИ: магазин заведён, но спит — готовый канал сбыта без нового склада (оператор пометил active=False)."""
    out = []
    for s in d["dormant_shops"]:
        models = ", ".join(s["placements"]) or "неизвестная модель"
        out.append(_lever(
            AXIS_MODEL, f"ОЖИВИТЬ_МАГАЗИН_{s['id']}",
            why=f"магазин {s['id']} ({models}) заведён, но молчит — это уже готовый канал сбыта, "
                f"не требует нового склада и новых карточек, только включения.",
            next_action=f"оператор: реши, идём ли в {models}; если да — включи предложения в магазине {s['id']} "
                        f"(это отдельный канал, свои остатки/цены — по обычному гейту органа).",
            owner="ОПЕРАТОР", effort="medium",
            needs_source=f"спрос по модели {models} (нет числа — не обещаем доход, G2)",
            facts={"shop_id": s["id"], "placements": s["placements"]},
            blocked_by="слово оператора (новый канал сбыта)",
        ))
    return out


def _lever_disabled_models(d):
    """МОДЕЛИ: склад умеет модель, но она выключена — включение открывает ещё один способ доставки без затрат."""
    out = []
    for m in d["disabled_models"]:
        where = f"{m['warehouse']}" + (f" ({m['city']})" if m["city"] else "")
        out.append(_lever(
            AXIS_MODEL, f"ВКЛЮЧИТЬ_{m['model']}_НА_{m['warehouse_id']}",
            why=f"склад «{where}» умеет модель {m['model']}, но она выключена — включение даёт ещё один способ "
                f"доставки на том же складе, без новых вложений.",
            next_action=(f"ПИШУЩИЙ шаг: set_warehouse_model(business_id, '{m['warehouse_id']}', '{m['model']}', "
                         f"enabled=True) — только по --commit и слову оператора. "
                         f"ВАЖНО: если модель выключил сам Маркет, через API её не вернуть — только кабинет."),
            owner="ОПЕРАТОР", effort="low",
            needs_source=f"спрос под модель {m['model']}" + (f" в городе {m['city']}" if m["city"] else ""),
            facts={"warehouse_id": m["warehouse_id"], "model": m["model"], "city": m["city"]},
            blocked_by="write-гейт (not dry AND commit) + слово оператора",
        ))
    return out


def _lever_express_cities(d):
    """ГОРОДА: Express живёт лишь в N городах — каждый новый город это новый пул спроса рядом с покупателем."""
    cities = d["express_cities"]
    where = ", ".join(cities) if cities else "нигде (нет включённого Express-склада)"
    return [_lever(
        AXIS_CITY, "РАСШИРИТЬ_ГОРОДА_EXPRESS",
        why=f"Express сейчас в: {where} ({len(cities)} гор.). Каждый новый город — новый пул спроса "
            f"с быстрой доставкой рядом с покупателем; это самый прямой рост по оси ГОРОДА.",
        next_action="1) выбери город с подтверждённым спросом (нужен источник трендов/аналитики — из воздуха не берём); "
                    "2) заведи склад в кабинете РУКАМИ — API склад не создаёт (create_warehouse_refused), "
                    "проверка Express 6–8 ч; 3) привяжи модель EXPRESS к новому складу.",
        owner="ОПЕРАТОР", effort="high",
        needs_source="город с подтверждённым спросом (источник трендов/аналитики)",
        facts={"express_cities": cities, "count": len(cities)},
        blocked_by="склад создаётся руками в кабинете (API отказывает) + проверка Express 6–8 ч",
    )]


def _lever_blind_cities(d):
    """ГОРОДА: орган возит в город, но мерчандайзер его габаритно НЕ знает → консервативный дефолт режет товар.

    Единственный ход роста в НАШИХ руках (без кабинета и без слова) — правка лимитов в коде."""
    blind = d["blind_cities"]
    if not blind:
        return []
    known = ", ".join(d["known_cities"]) or "только дефолт"
    return [_lever(
        AXIS_CITY, "ОТКРЫТЬ_ГОРОДА_В_МЕРЧАНДАЙЗЕРЕ",
        why=f"мерчандайзер знает габаритные лимиты только для: {known}. Для {', '.join(blind)} он берёт "
            f"консервативный дефолт и может резать годный товар/завышать доставку — это тормозит рост там.",
        next_action=f"добавить город(а) {', '.join(blind)} в CITY_LIMITS мерчандайзера с реальными лимитами "
                    f"(правка кода, обратносовместимо — расширяет карту, ничего не ломает).",
        owner="СОКК", effort="low",
        needs_source="официальные лимиты вес/габариты по городу от Маркета",
        facts={"blind_cities": blind, "known_cities": d["known_cities"]},
        blocked_by=None,   # в наших руках: не нужен ни кабинет, ни слово оператора
    )]


# ─────────────────────────── план + отчёт ───────────────────────────

def _sort_key(m):
    """Сначала ходы с числом (score убыв.), потом безчисловые — по дешевизне законного шага (усилие возр.)."""
    has_score = m["score"] is not None
    return (0 if has_score else 1, -(m["score"] or 0), m["effort_units"])


def plan(snapshot=None, *, business_id=None, timeout=30):
    """Построить план роста по осям ГОРОДА+МОДЕЛИ из снимка кабинета.

    snapshot=None → пытаемся собрать ЖИВОЙ снимок (только READ) через trade_hands/hands; нет сети/данных →
    честный пустой план с недостающими источниками. Для офлайн-тестов передаём snapshot напрямую.
    """
    live_error = None
    if snapshot is None:
        snapshot, live_error = _gather_live(business_id=business_id, timeout=timeout)

    snap = _norm_snapshot(snapshot)
    d = _derive(snap)

    moves = []
    moves += _lever_dormant_shops(d)
    moves += _lever_disabled_models(d)
    moves += _lever_express_cities(d)
    moves += _lever_blind_cities(d)
    moves.sort(key=_sort_key)

    need_sources = []
    for m in moves:
        if m.get("needs_source") and m["needs_source"] not in need_sources:
            need_sources.append(m["needs_source"])

    have_data = bool(snap["shops"] or snap["warehouses"])
    agg = {
        "axes": [AXIS_CITY, AXIS_MODEL],
        "active_channels": len(d["active_channels"]),
        "dormant_shops": len(d["dormant_shops"]),
        "unknown_shops": len(d["unknown_shops"]),
        "express_cities": len(d["express_cities"]),
        "served_cities": len(d["served_cities"]),
        "blind_cities": len(d["blind_cities"]),
        "disabled_models": len(d["disabled_models"]),
        "moves": len(moves),
        "need_source": len(need_sources),
        "top_move": (moves[0]["lever"] if moves else None),
    }
    return {
        "ok": True, "role": CHARTER["name_ru"], "have_data": have_data,
        "live_error": live_error, "business_id": snap["business_id"],
        "map": d, "moves": moves, "need_sources": need_sources, "agg": agg,
    }


def _gather_live(business_id=None, timeout=30):
    """ЖИВОЙ снимок только чтением (склады + магазины). Ошибка/нет ключа → (пустой снимок, текст ошибки)."""
    try:
        import ymarket_trade_hands_v1 as th
        import ymarket_hands_v1 as h
    except Exception as e:
        return {}, f"нет модулей рук органа: {e}"
    try:
        bid = business_id
        if not bid:
            bid, _cid, _src = h.resolve_ids(timeout=timeout)
        whs = th.warehouses(bid, timeout=timeout) if bid else []
        camps = h.campaigns(timeout=timeout)
    except Exception as e:
        return {}, f"живой READ не прошёл (ключ/сеть; LIVE только /usr/bin/python3): {e}"

    shops = []
    for c in _aslist(camps):
        c = _asdict(c)
        pt = c.get("placementType") or c.get("placement")
        placements = [str(pt).upper()] if pt else []
        # активность магазина по API дёшево не читаем → active=None (спящий канал не судим без данных, G2)
        shops.append({"id": str(c.get("id") or "?"), "placements": placements, "active": None})
    return {"business_id": bid, "shops": shops, "warehouses": _aslist(whs)}, None


def render(res):
    """Человеческий отчёт скаута — что открыто для роста и какой следующий законный шаг."""
    if not res or not res.get("ok"):
        return "🧭 СКАУТ РОСТА: отчёта нет."
    a = res["agg"]
    L = [f"🧭 {res['role']} · оси: {' + '.join(a['axes'])}",
         f"карта: активных каналов {a['active_channels']} · спящих магазинов {a['dormant_shops']} · "
         f"городов Express {a['express_cities']} · слепых городов {a['blind_cities']} · "
         f"выключенных моделей {a['disabled_models']}"]
    if not res["have_data"]:
        L.append("⚠️ нет снимка кабинета — подключи снимок или живой READ.")
        if res.get("live_error"):
            L.append(f"   [живой READ: {res['live_error']}]")
    if not res["moves"]:
        L.append("Открытых дверей роста по этим осям сейчас не вижу (или нет данных).")
        return "\n".join(L)
    L.append("")
    L.append("Двери роста (сначала самый дешёвый законный шаг):")
    for i, m in enumerate(res["moves"], 1):
        rub = "нужен источник ₽" if m["expected_rub"] is None else f"~{int(m['expected_rub'])}₽"
        L.append(f" {i}. [{m['axis']}] {m['lever']} · {rub} · усилие: {m['effort']} · владелец: {m['owner']}")
        L.append(f"     почему: {m['why']}")
        L.append(f"     шаг: {m['next_action']}")
        if m.get("needs_source"):
            L.append(f"     ❓ нужен источник: {m['needs_source']}")
        if m.get("blocked_by"):
            L.append(f"     ⛔ упирается в: {m['blocked_by']}")
    if res["need_sources"]:
        L.append("")
        L.append("Чтобы превратить двери в деньги — нужны источники:")
        for s in res["need_sources"]:
            L.append(f"   • {s}")
    return "\n".join(L)


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser(description="СКАУТ РОСТА — двери роста по осям ГОРОДА и МОДЕЛИ (READ-ONLY, 0₽)")
    ap.add_argument("--live", action="store_true", help="собрать живой снимок кабинета (только READ; LIVE = /usr/bin/python3)")
    ap.add_argument("--business-id", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    res = plan(snapshot=None if args.live else {}, business_id=args.business_id)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render(res))
