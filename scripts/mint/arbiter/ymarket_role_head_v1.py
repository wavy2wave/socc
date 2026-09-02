#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РОЛЬ · ГОЛОВА (YM_HEAD) — сводит выводы трёх осей в ОДИН суточный шорт-лист «что предложить».

Канон роли SOCC (TFS-1, 9 полей) — см. CHARTER ниже.

Зачем. У органа уже есть три независимых носа спроса/пригодности, но НИКТО не сводил их в одно
решение «сегодня стоит завести вот это»:
  • wb_scout        — НОС СПРОСА: живой сигнал спроса (demand_signal.strength) + закуп + маржа-вход;
  • ТОВАРОВЕД       — ГЕЙТ ФИЗИКИ: отгружаемо ли по габаритам города и осмысленно ли по тарифу;
  • ТРЕНД-СКАУТ     — ГЕЙТ ОКНА: растёт ли спрос ещё или окно уже закрылось (late/пик).
Каждый говорит своё, оператор держал синтез в голове. ГОЛОВА и есть этот синтез, вынесенный в код:
читает три вывода, СЛИВАЕТ по одному кандидату, РАНЖИРУЕТ и кладёт суточный шорт-лист как
«предложено». Это ЕДИНСТВЕННЫЙ net-new — само ранжирование делегируется portfolio_v1 (не дублируем
формулу маржа×спрос×скорость), физику считает ТОВАРОВЕД, окно — ТРЕНД-СКАУТ. ГОЛОВА только сводит.

Что делает (и чего НЕ делает).
  rank(wb, merch, trend)  — ЧИСТАЯ сборка: три вывода → один ранжированный шорт-лист (0₽, без I/O).
  plan_day(head_source_fn, trend_result) — суточный ход: тянет кандидатов из шва, гоняет ТОВАРОВЕДа,
      переиспользует уже посчитанный вывод ТРЕНД-СКАУТА, сливает+ранжирует, по желанию — пишет в стор.
  save_day/load_day       — свой стор предложений (НЕ реестр идентификаторов): один шорт-лист на дату.

ГЛАВНЫЙ ЗАКОН (H5): ГОЛОВА ПРЕДЛАГАЕТ, а не публикует. Состояние записи всегда «предложено»; денег
не двигает, наружу ничего не шлёт. Реальный залив предложенного — отдельной отмашкой оператора через
существующий ymarket_runner (RUBICON цел по построению).

ЗАКОНЫ (механические, покрыты приёмкой):
  H1 не выдумываем: шорт-лист собирается ТОЛЬКО из данного тремя источниками. Нет источника → честный
     пустой шорт-лист (это не падение и не «кандидатов нет вообще» — это «нам их не дали»).
  H2 ноль дублей формул: ранг = portfolio_v1.justified_score/select_per_category; ГОЛОВА не считает
     маржу/спрос/скорость сама (иначе два расходящихся источника правды).
  H3 гейт физики (ТОВАРОВЕД): verdict=reject → в шорт-лист НЕ попадает (нечего предлагать неотгружаемое).
     needs_data → попадает, но помечено «нужны данные» и рангом ниже одобренных (данные можно донести).
  H4 гейт окна (ТРЕНД-СКАУТ): action=SKIP (late/пик/протух) → НЕ предлагаем. Скаут молчит (нет
     источника трендов) → окно нейтрально, кандидата НЕ штрафуем (иначе занулим весь шорт-лист зря).
  H5 предлагает, не публикует: state=«предложено», 0₽, наружу ничего (см. выше).
  H6 идемпотентность суток: один шорт-лист на дату; повторный прогон за те же сутки ПЕРЕЗАПИСЫВАЕТ
     запись даты, а не плодит дубли.
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import portfolio_v1 as portfolio                 # noqa: E402  (ранг: justified_score — H2, не дублируем)
import ymarket_role_merchandiser_v1 as merch     # noqa: E402  (гейт физики — H3)

ROOT = HERE.parent.parent.parent
REPORTS = ROOT / "MEMORY_WAVE/reports/mint/arbiter"
SCHEMA = "ymarket.head.proposals.v1"
STATE_PROPOSED = "предложено"

DEFAULT_SHORTLIST = 8       # суточный шорт-лист «что предложить» (в духе 5-8 обоснованных)

CHARTER = {
    "id": "YM_HEAD",
    "name_ru": "ГОЛОВА",
    "mandate": "свести спрос+физику+окно в один суточный шорт-лист «что предложить», не публикуя",
    "owns": ["суточный шорт-лист предложений", "слияние выводов трёх осей", "порядок предложения"],
    "inputs": ["кандидаты со спросом (wb_scout)", "вердикты ТОВАРОВЕДа (физика/тариф)",
               "фазы окна ТРЕНД-СКАУТа", "лимиты города/справочник категорий"],
    "outputs": ["суточный шорт-лист «предложено» → оператор", "заблокированные с причиной → оператор",
                "запрос недостающих источников/данных → оператор"],
    "laws": [
        "H1 не выдумываем: шорт-лист только из данного источниками; нет источника → честный пустой",
        "H2 ноль дублей формул: ранг делегируем portfolio_v1.justified_score, свою не считаем",
        "H3 гейт физики: ТОВАРОВЕД reject → не предлагаем; needs_data → предлагаем ниже, с флагом",
        "H4 гейт окна: ТРЕНД-СКАУТ SKIP → не предлагаем; скаут молчит → окно нейтрально, не штрафуем",
        "H5 предлагает, не публикует: state=предложено, 0₽, наружу ничего (RUBICON у оператора)",
        "H6 идемпотентность суток: один шорт-лист на дату, повторный прогон перезаписывает",
    ],
    "kpi": [
        {"metric": "доля предложенного, дошедшего до залива", "target": "рост",
         "source_of_truth": "реестр артикулов (залитые offerId) против шорт-листов ГОЛОВЫ"},
        {"metric": "предложено неотгружаемого (reject проскочил)", "target": "0",
         "source_of_truth": "вердикт ТОВАРОВЕДа по каждому пункту шорт-листа"},
        {"metric": "предложено в фазе late", "target": "0",
         "source_of_truth": "фаза окна ТРЕНД-СКАУТа на момент предложения"},
    ],
    "proves_by": "каждый пункт: сигнал спроса → вердикт физики → фаза окна → ранг → state=предложено",
}


# ── ключ слияния ──────────────────────────────────────────────────────────────
# Один кандидат в трёх источниках опознаётся по sku (если есть), иначе по нормализованному имени.
# Это НЕ выдумывание связи: sku приходит из одного источника (wb_scout) и переживает screen ТОВАРОВЕДа
# (тот работает на ТЕХ ЖЕ dict). ТРЕНД-СКАУТ приходит из другого источника — не совпал → окно нейтрально.

def _key(item):
    if not isinstance(item, dict):
        return None
    sku = item.get("sku") or item.get("offerId")
    if sku:
        return ("sku", str(sku))
    name = str(item.get("name") or "").strip().lower().replace("ё", "е")
    return ("name", name) if name else None


def _merch_index(merch_result):
    """Вывод ТОВАРОВЕДа → {ключ: {verdict, reasons, economics}}. Пустой/None → {} (H1)."""
    idx = {}
    if not isinstance(merch_result, dict):
        return idx
    for group in ("approved", "rejected", "needs_data"):
        for r in merch_result.get(group) or []:
            k = _key(r)
            if k:
                idx[k] = {"verdict": r.get("verdict"), "reasons": r.get("reasons") or [],
                          "economics": r.get("economics")}
    return idx


def _trend_index(trend_result):
    """Вывод ТРЕНД-СКАУТа → {ключ: {phase, action, margin_x, why}}. Пустой/None → {} (H4-нейтрально)."""
    idx = {}
    if not isinstance(trend_result, dict):
        return idx
    rows = list(trend_result.get("candidates") or [])
    for s in trend_result.get("skipped") or []:      # skipped тоже несёт фазу (late/пик/шум)
        if isinstance(s, dict) and s.get("phase"):
            rows.append(s)
    for r in rows:
        k = _key(r)
        if k:
            idx[k] = {"phase": r.get("phase"), "action": r.get("action"),
                      "margin_x": r.get("margin_x"), "why": r.get("why")}
    return idx


# порядок предпочтения окна как ТАЙБРЕЙК (не число в счёт — H2: окно не подмешиваем в justified_score)
_WINDOW_RANK = {"open": 0, "watch": 1, None: 2}


def rank(wb_candidates=None, merch_result=None, trend_result=None, shortlist_size=DEFAULT_SHORTLIST,
         profit_target=600, min_profit=200, velocity_map=None):
    """ЧИСТАЯ сборка: три вывода → один ранжированный суточный шорт-лист «предложено». 0₽, без I/O.

    wb_candidates — база вселенной (несёт demand_signal + cost, вход для portfolio/prospector);
    merch_result  — вывод merch.screen (гейт физики, H3); trend_result — вывод trendscout.scan (окно, H4).
    Ранг делегирован portfolio_v1.select_per_category (H2). Возвращает {ok, role, shortlist, blocked,
    agg, need_sources}.
    """
    wb_candidates = list(wb_candidates or [])
    merch_idx = _merch_index(merch_result)
    trend_idx = _trend_index(trend_result)

    # источники, которых нет — честно называем (H1): пустой шорт-лист должен объяснять, ПОЧЕМУ пуст
    need_sources = []
    if not wb_candidates:
        need_sources.append("нет кандидатов со спросом (wb_scout не дал источник) — предлагать нечего")
    if merch_result is None:
        need_sources.append("нет вывода ТОВАРОВЕДа — физика/тариф не проверены (гейт H3 пропущен)")
    if not trend_idx:
        need_sources.append("нет фаз ТРЕНД-СКАУТа — окно спроса нейтрально (не штрафуем, H4)")

    if not wb_candidates:
        return {"ok": True, "role": CHARTER["id"], "shortlist": [], "blocked": [],
                "need_sources": need_sources,
                "agg": {"universe": 0, "ranked": 0, "proposed": 0, "blocked": 0, "needs_data": 0,
                        "best_score": None,
                        "sources_present": {"wb": False, "merch": merch_result is not None,
                                            "trend": bool(trend_idx)}}}

    # РАНГ (H2): гейт спроса+маржи и justified_score — целиком из portfolio (не дублируем). top_k берём
    # с запасом (вся вселенная), чтобы гейты физики/окна ГОЛОВЫ не резали ДО собственной отсечки.
    ranked = portfolio.select_per_category(
        wb_candidates, top_k=len(wb_candidates), profit_target=profit_target,
        min_profit=min_profit, velocity_map=velocity_map)

    survivors, blocked = [], []
    for item in ranked:
        k = _key(item)
        mv = merch_idx.get(k) if k else None
        tv = trend_idx.get(k) if k else None

        verdict = (mv or {}).get("verdict")
        feasible = True if verdict == "approve" else (False if verdict == "reject" else None)
        needs_data = verdict == "needs_data"

        action = (tv or {}).get("action")
        window = {"ENTER": "open", "SKIP": "closed", "WATCH": "watch"}.get(action)  # нет tv → None

        row = dict(item)
        row.update({
            "feasible": feasible, "needs_data": needs_data,
            "merch_verdict": verdict, "merch_reasons": (mv or {}).get("reasons") or [],
            "window": window if window != "closed" else "closed",
            "trend_phase": (tv or {}).get("phase"), "trend_margin_x": (tv or {}).get("margin_x"),
            "state": STATE_PROPOSED,
        })

        # ── ГЕЙТ ФИЗИКИ (H3): reject не предлагаем ──
        if feasible is False:
            reason = (mv["reasons"][0] if (mv and mv.get("reasons")) else "ТОВАРОВЕД: не отгружаемо")
            blocked.append({**row, "blocked_by": "ТОВАРОВЕД", "why": reason})
            continue
        # ── ГЕЙТ ОКНА (H4): SKIP не предлагаем; молчание скаута = нейтрально ──
        if window == "closed":
            blocked.append({**row, "blocked_by": "ТРЕНД-СКАУТ",
                            "why": (tv or {}).get("why") or "окно спроса закрыто (late/пик/протух)"})
            continue

        row["why"] = _why(row)
        survivors.append(row)

    # ярус: одобренные физикой (feasible True) выше, чем «нужны данные»/непроверенные (None).
    # Внутри яруса — по justified_score (ранг portfolio), при равенстве окно open как тайбрейк (H2).
    def _tier(r):
        return 0 if r.get("feasible") is True else 1
    survivors.sort(key=lambda r: (_tier(r), _WINDOW_RANK.get(r.get("window")),
                                  -float(r.get("justified_score") or 0)))
    shortlist = survivors[: int(shortlist_size)]

    proposed_needs = sum(1 for r in shortlist if r.get("needs_data"))
    best = shortlist[0]["justified_score"] if shortlist else None
    return {
        "ok": True, "role": CHARTER["id"], "shortlist": shortlist, "blocked": blocked,
        "need_sources": need_sources,
        "agg": {"universe": len(wb_candidates), "ranked": len(ranked),
                "proposed": len(shortlist), "blocked": len(blocked), "needs_data": proposed_needs,
                "best_score": best,
                "sources_present": {"wb": True, "merch": merch_result is not None,
                                    "trend": bool(trend_idx)}},
    }


def _why(row):
    """Одна строка обоснования пункта: спрос → физика → окно → ранг. Только из данного, без выдумки."""
    parts = []
    ds = row.get("demand_signal") or {}
    if ds.get("strength") is not None:
        parts.append(f"спрос[{ds.get('strength')}]")
    m = row.get("margin") or {}
    if isinstance(m.get("profit_net"), (int, float)):
        parts.append(f"чист ₽{m['profit_net']:.0f}")
    if row.get("feasible") is True:
        parts.append("физика: отгружаемо")
    elif row.get("needs_data"):
        parts.append("физика: НУЖНЫ ДАННЫЕ (габариты/категория)")
    else:
        parts.append("физика: не проверена")
    win = row.get("window")
    if win == "open":
        x = row.get("trend_margin_x")
        parts.append(f"окно ОТКРЫТО{f' (x{x})' if x else ''}")
    elif win == "watch":
        parts.append("окно: наблюдать (плато)")
    if row.get("justified_score") is not None:
        parts.append(f"ранг {row['justified_score']:.0f}")
    return " · ".join(parts)


# ── суточный ход (тянет кандидатов из шва, гоняет физику, сливает) ─────────────

def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def plan_day(head_source_fn=None, trend_result=None, city=None, cats=None,
             shortlist_size=DEFAULT_SHORTLIST, profit_target=600, min_profit=200,
             velocity_map=None, persist=False, date=None):
    """Суточный ход ГОЛОВЫ: источник кандидатов (шов) → ТОВАРОВЕД → слить с окном → шорт-лист.

    head_source_fn — шов адаптера (функция без аргументов → список кандидатов уровня wb_scout).
    Нет источника → честный отказ (H1), как у ТРЕНД-СКАУТА (не «кандидатов нет», а «нам их не дали»).
    trend_result — уже посчитанный вывод ТРЕНД-СКАУТА (переиспользуем, не зовём второй раз в цикле дня).
    persist=True → записать шорт-лист в свой стор под датой (H6, идемпотентно).
    """
    if head_source_fn is None:
        return {"ok": False, "role": CHARTER["id"], "reason": "NO_HEAD_SOURCE",
                "shortlist": [], "blocked": [],
                "need_source": ("источник кандидатов не подключён (H1): нужен адаптер — wb_scout "
                                "(нос спроса оси ARBITER) или выгрузка поставщика"),
                "note": "ГОЛОВА не выдумывает кандидатов: без источника шорт-лист пуст (честный ноль)",
                "agg": {"universe": 0, "proposed": 0, "blocked": 0}}
    try:
        wb_candidates = head_source_fn() or []
    except Exception as e:
        return {"ok": False, "role": CHARTER["id"], "error": f"{type(e).__name__}: {e}",
                "shortlist": [], "blocked": [],
                "note": "источник кандидатов упал — НЕ считаем, что предлагать нечего (разные вещи)",
                "agg": {"universe": 0, "proposed": 0, "blocked": 0}}

    # ГЕЙТ ФИЗИКИ (H3): ТОВАРОВЕД просеивает те же кандидаты (габариты города/тариф/категория).
    try:
        merch_result = merch.screen(wb_candidates, city=city, cats=cats)
    except Exception:
        merch_result = None                          # физика не проверилась — гейт H3 честно пропущен

    res = rank(wb_candidates, merch_result=merch_result, trend_result=trend_result,
               shortlist_size=shortlist_size, profit_target=profit_target,
               min_profit=min_profit, velocity_map=velocity_map)
    res["date"] = date or _today()
    res["city"] = city

    if persist and res.get("ok"):
        try:
            res["_saved"] = bool(save_day(res["date"], res))
        except Exception:
            res["_saved"] = False                    # стор упал — шорт-лист всё равно вернём (fail-soft)
    return res


# ── стор предложений (СВОЙ, не реестр идентификаторов) ────────────────────────

def store_path():
    """Путь к стору предложений. env YM_HEAD_PROPOSALS_PATH перекрывает (песочница/тесты)."""
    p = os.environ.get("YM_HEAD_PROPOSALS_PATH")
    return Path(p) if p else (REPORTS / "ymarket_head_proposals.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _blank():
    return {"schema": SCHEMA, "created_at": _now(), "updated_at": _now(), "days": {}}


def load():
    """Загрузить стор (fail-soft: нет файла/битый/чужой JSON → чистый бланк). Всегда валидная схема."""
    p = store_path()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
            base = _blank()
            if isinstance(doc, dict) and isinstance(doc.get("days"), dict):
                base["days"] = doc["days"]           # спасаем что можем, не затираем молча
            return base
        base = _blank()
        base["created_at"] = doc.get("created_at") or base["created_at"]
        base["days"] = doc.get("days") if isinstance(doc.get("days"), dict) else {}
        return base
    except FileNotFoundError:
        return _blank()
    except Exception:
        return _blank()


def write_atomic(doc):
    """Атомарно записать стор: tmp в той же папке + os.replace (без полу-файла). Возвращает путь."""
    doc["updated_at"] = _now()
    doc.setdefault("schema", SCHEMA)
    p = store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".ymhead_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return p


def _slim(result):
    """Ужать результат для стора: сам шорт-лист + агрегат (без раздувания вселенной)."""
    def pick(r):
        return {k: r.get(k) for k in ("sku", "name", "url", "cost", "source_market",
                                      "justified_score", "feasible", "needs_data", "window",
                                      "trend_phase", "state", "why")}
    return {
        "ts": _now(),
        "shortlist": [pick(r) for r in result.get("shortlist") or []],
        "blocked_count": len(result.get("blocked") or []),
        "agg": result.get("agg"),
        "need_sources": result.get("need_sources") or result.get("need_source"),
        "city": result.get("city"),
    }


def save_day(date, result, path=None):
    """Записать суточный шорт-лист под датой. Идемпотентно (H6): та же дата ПЕРЕЗАПИСЫВАется, не дублит."""
    doc = load()
    doc.setdefault("days", {})[str(date)] = _slim(result)
    return write_atomic(doc)


def load_day(date):
    """Прочитать суточный шорт-лист по дате или None."""
    return (load().get("days") or {}).get(str(date))


# ── человеческий вид ──────────────────────────────────────────────────────────

def render(res):
    """Человеческий доклад ГОЛОВЫ (для дневного отчёта/фида)."""
    if not res:
        return "ГОЛОВА: нет данных"
    if not res.get("ok"):
        if res.get("reason") == "NO_HEAD_SOURCE":
            return ("ГОЛОВА · источник кандидатов НЕ подключён — предлагать нечего (честный ноль).\n"
                    f"  → {res.get('need_source')}")
        return f"ГОЛОВА: источник упал — {res.get('error')} (это не «предлагать нечего»)"
    a = res.get("agg") or {}
    lines = [f"ГОЛОВА · предложено {a.get('proposed', 0)} "
             f"(из вселенной {a.get('universe', 0)}) · заблокировано {a.get('blocked', 0)}"
             f"{f' · нужны данные {a['needs_data']}' if a.get('needs_data') else ''}"]
    for r in res.get("shortlist", [])[:5]:
        lines.append(f"  • {r.get('name')} — {r.get('why') or ''}  [{STATE_PROPOSED}]")
    blk = res.get("blocked") or []
    if blk:
        b = blk[0]
        lines.append(f"  не предлагаем ({len(blk)}): напр. {b.get('name')} — {b.get('blocked_by')}: "
                     f"{b.get('why')}")
    for n in (res.get("need_sources") or [])[:2]:
        lines.append(f"  ⚠ {n}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ГОЛОВА — суточный шорт-лист предложений (0₽, без сети)")
    ap.add_argument("--charter", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if args.charter:
        print(json.dumps(CHARTER, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Сухая демонстрация (0₽, наружу ничего): 3 кандидата со спросом, физика + окно из «выводов».
    demo_wb = [
        {"sku": "W1", "name": "Плёнка тонировочная Карбон 3D", "cost": 350.0,
         "url": "https://sp.cargo-avto.ru/catalog/9603273/", "source_market": "wildberries",
         "profit_target": 600, "min_profit": 200,
         "demand_signal": {"kind": "wb_public_proxy", "strength": 78, "feedbacks": 1200}},
        {"sku": "W2", "name": "Антигравийная плёнка рулон", "cost": 900.0,
         "url": "https://sp.cargo-avto.ru/catalog/9602037/", "source_market": "wildberries",
         "profit_target": 600, "min_profit": 200,
         "demand_signal": {"kind": "wb_public_proxy", "strength": 55, "feedbacks": 300}},
        {"sku": "W3", "name": "Стеллаж металлический негабарит", "cost": 2500.0,
         "url": "https://sp.cargo-avto.ru/catalog/1/", "source_market": "wildberries",
         "profit_target": 600, "min_profit": 200,
         "demand_signal": {"kind": "wb_public_proxy", "strength": 40}},
    ]
    # «вывод ТОВАРОВЕДа»: W1 одобрен (габариты есть), W2 нет габаритов → needs_data, W3 негабарит → reject
    demo_merch = merch.screen([
        {"sku": "W1", "name": "Плёнка тонировочная Карбон 3D", "price": 1490, "cost": 350,
         "category_id": 100, "weight": 1.0, "length": 30, "width": 15, "height": 15,
         "stock_source": "cargo"},
        {"sku": "W2", "name": "Антигравийная плёнка рулон", "price": 1900, "cost": 900,
         "category_id": 100, "stock_source": "cargo"},
        {"sku": "W3", "name": "Стеллаж металлический негабарит", "price": 5000, "cost": 2500,
         "category_id": 100, "weight": 75.0, "length": 200, "width": 60, "height": 40,
         "stock_source": "cargo"},   # 75 кг > лимита Москвы 60 → ТОВАРОВЕД reject (гейт H3)
    ], city="Москва")
    # «вывод ТРЕНД-СКАУТА»: W1 окно открыто (ENTER), W2 плато (WATCH)
    demo_trend = {"ok": True, "candidates": [
        {"sku": "W1", "name": "Плёнка тонировочная Карбон 3D", "phase": "growth",
         "action": "ENTER", "margin_x": 4.2, "why": "рост 30% — окно ещё не закрылось"}],
        "skipped": [
        {"sku": "W2", "name": "Антигравийная плёнка рулон", "phase": "peak",
         "action": "WATCH", "why": "рост 2% — плато"}]}

    res = rank(demo_wb, merch_result=demo_merch, trend_result=demo_trend)
    print("ГОЛОВА — сухая демонстрация (0₽, наружу ничего)\n")
    print(render(res))
