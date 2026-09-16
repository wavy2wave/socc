#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""СУТОЧНЫЙ ЦИКЛ ОЗОН (ozon_day_v1) — день органа ОЗОН-МЕНЕДЖЕР: единый отчёт, один журнал.

Зеркало ymarket_day_v1 (проверенный образец ЯМ-линии) ПОД ОЗОН: меняем транспорт/смыслы под
Ozon Seller API и одну-единственную структуру (один кабинет, без манифеста стора) — поэтому
ЦИКЛ-1-мультистора НЕ зеркалим: для ОЗОН день И ЕСТЬ движок.

Что просил оператор (общее у ЯМ и ОЗОН): «утром я захожу и вижу каждый день 100% отчёт —
свои KPI и стремление стать больше». День органа:
  0. УПРАВЛЯЮЩИЙ делает тик (ozon_manager.tick) — лестница решений по памяти: FIX_ERRORS →
     RESOLVE_MAPPING → OBSERVE → PUBLISH(закрыт) → FIX_INDEX → HOLD. Доказательства в proof-леджер.
  1. ОТДЕЛЫ (6, ozon_departments.assess_all) — ТОВАРОВЕД/ЦЕНОВИК-ИНДЕКС/ЗАЛИВЩИК/СНАБЖЕНЕЦ/
     ОТГРУЗЧИК/КОНТРОЛЁР: каждая цепь «не с неба взял» (ozon_evidence ground → grounded True/False/None)
     и прогнозы цветов. Падение отдела НЕ роняет день (закон B2) — провал честно в отчёт.
  2. ДОЗНАНИЕ (0₽ ЖИВОЙ, ТОЛЬКО если live_read): ozon_truth.analyze_cabinet — факт продаж/нетто/
     доставки из РЕАЛЬНОГО кабинета. Read-only; деньги/витрину не двигает. Гейт: live_read=False по
     умолчанию (dry тик сети не зовёт); включает вызывающий (автопилот/--live-read, env OZON_LIVE).
  3. KPI + НОРМА ДНЯ: карточки ведём/на-витрине/с-ошибкой(цель 0)/ждут-категорию/готовы/красный-
     индекс + дневные нормы залито/отгружено/доставлено/починено (state.daily). Только факты.
  4. ДЕЛЬТА ко вчера (рост виден только в сравнении) — из журнала дней.
  5. Что горит + куда растём → ОДИН человеко-отчёт; день дописывается в журнал.

ЗАКОН RUBICON (зашит ФИЗИЧЕСКИ, не флагом): у run_day НЕТ параметра commit и НЕТ пути к живому
write. Тик менеджера зовётся СТРОГО commit=False. Реальный write Озона (публикация/цена/отгрузка) —
отдельный ЖИВОЙ день по слову оператора ПОСЛЕ ротации ключа (ключ Ozon был скомпрометирован 06.08;
до ротации никакие write не открываем). Всё, что пишет этот модуль, — ЛОКАЛЬНО (память/журнал/отчёт,
0₽): файлы памяти органа, не рука Ozon.

ЗАКОН ЧЕСТНОСТИ: «нет данных» ≠ 0; сухой прогон не притворяется живым; живой read провалился — честно
в failures, не выдумываем витрину.

Журнал: MEMORY_WAVE/reports/mint/arbiter/ozon_day_journal.jsonl (env OZON_DAY_JOURNAL — песочница/тесты).
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

import ozon_state_v1 as state              # noqa: E402  (память SKU + дневные нормы)
import ozon_manager_v1 as manager          # noqa: E402  (УПРАВЛЯЮЩИЙ: bounded tick + лестница)
import ozon_departments_v1 as departments  # noqa: E402  (6 отделов: assess_all + render + resolve)
import ozon_evidence_v1 as evidence        # noqa: E402  (ground/replay — «не с неба взял»)
import ozon_self_v1 as self_mod            # noqa: E402  (само-модель + следующий законный шаг)

ROOT = HERE.parent.parent.parent
REPORTS = ROOT / "MEMORY_WAVE/reports/mint/arbiter"
DAY_SCHEMA = "ozon.day.v1"


def journal_path():
    """Журнал дней (для дельты «вчера→сегодня»). env OZON_DAY_JOURNAL перекрывает (тесты)."""
    p = os.environ.get("OZON_DAY_JOURNAL")
    return Path(p) if p else (REPORTS / "ozon_day_journal.jsonl")


# Ключи кабинета, наличие которых цикл докладывает в env_loaded (только ИМЕНА, не значения).
_KNOWN_ENV = ("OZON_CLIENT_ID", "OZON_API_KEY")

# СЫРЫЕ ключи KPI из state.kpis (память). tracked в day докладываем как cards_tracked (стиль
# само-модели) — переименование в collect_kpis. Нормы дня добавляем префиксом daily_*.
_KPI_KEYS = ("tracked", "cards_on_shelf", "cards_errored", "need_mapping",
             "ready_to_publish", "index_red")


def load_env_file(path=None):
    """Подтянуть ключи органа из .env — БЕЗ перезаписи уже заданных переменных.

    Один магазин → нужен только OZON_CLIENT_ID + OZON_API_KEY. ДВА ИСТОЧНИКА как у ymarket_day:
      (A) общий загрузчик MINT (socc_mint_env_v1) — знает mint/.env/SOCC/.env;
      (B) локальный arbiter/.env (исторический путь, совместимость).
    ЗАКОН: уже заданное окружение НИКОГДА не перетирается (иначе тесты/песочница потеряют изоляцию),
    любая беда — молча (fail-soft): загрузчик секретов не имеет права уронить цикл. Возврат — список
    ИМЁН подхваченных переменных (без значений: секреты не логируем).
    """
    picked = []
    before = {k for k in _KNOWN_ENV if os.environ.get(k)}
    _menv = None
    try:
        import socc_mint_env_v1 as _menv          # noqa: F811
    except Exception:
        try:
            mint = str(MINT)
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


def _resolve_client_id(client_id):
    """id кабинета Ozon: аргумент → окружение. Не выдумываем — None остаётся None."""
    if not client_id:
        client_id = os.environ.get("OZON_CLIENT_ID") or None
    return client_id


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _safe(name, fn, *a, **kw):
    """Запустить шаг дня. Провал одного шага НЕ роняет день (закон B2): его беда честно в отчёт.

    Возвращает {"ok": True, "result": ...} либо {"ok": False, "error": "...", "step": name}.
    """
    try:
        return {"ok": True, "result": fn(*a, **kw)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "step": name}


# ── журнал дней ────────────────────────────────────────────────────────────────

def _read_journal(limit=30):
    """Последние строки журнала (для дельты). Нет файла/битый → [] (честно, не выдумываем)."""
    p = journal_path()
    if not p.exists():
        return []
    rows = []
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows[-int(limit):] if limit else rows


def _append_journal(day):
    """Дописать день в журнал (slim-строка: KPI + дельта берётся завтра отсюда). Локально, 0₽."""
    k = day.get("kpis") or {}
    slim = {
        "schema": DAY_SCHEMA,
        "ts": day.get("ts"), "date": day.get("date"),
        "dry": day.get("dry"), "ok": day.get("ok"),
        "action": (day.get("roles") or {}).get("MANAGER_TICK", {}).get("action"),
        "kpis": k,
        "departments": (day.get("departments") or {}).get("summary"),
        "truth": (day.get("truth") or {}).get("slim"),
        "failures": len(day.get("failures") or []),
        "burning": (day.get("burning") or {}).get("count"),
        "compared_to": day.get("compared_to"),
    }
    p = journal_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(slim, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def _delta(today_kpis, yesterday_kpis):
    """Дельта ко вчера ТОЛЬКО по числовым полям, где значение реально изменилось (≠ 0 «изменений»).

    yesterday_kpis None (вчерашнего дня в журнале нет) → None: без вчера нет «роста». Поле, значение
    которого не изменилось, НЕ печатаем («ноль изменений» не выдумываем).
    """
    if not isinstance(yesterday_kpis, dict) or not today_kpis:
        return None
    out = {}
    for kk, v in today_kpis.items():
        if not isinstance(v, (int, float)):
            continue
        yv = yesterday_kpis.get(kk)
        if isinstance(yv, (int, float)) and yv != v:
            out[kk] = {"from": yv, "to": v, "delta": round(v - yv, 4)}
    return out or None


# ── KPI дня ────────────────────────────────────────────────────────────────────

def collect_kpis(doc=None):
    """Свести KPI дня из СЫРОЙ памяти (state.kpis) — только факты, ничего не выдумываем.

    Ключи в стиле self-модели (cards_tracked/...): день докладывает так, как принято у органа.
    Нормы дня (daily_*) — дневные счётчики state (кто залил/отгрузил/доставил/починил).
    """
    doc = state.load() if doc is None else doc
    raw = state.kpis(doc)
    out = {}
    for kk in _KPI_KEYS:
        if kk == "tracked":
            out["cards_tracked"] = raw.get(kk)   # само-модель говорит cards_tracked, память — tracked
        else:
            out[kk] = raw.get(kk)
    daily = state.daily_norm(doc)
    for kk, v in daily.items():
        out[f"daily_{kk}"] = v
    return out


# ── человеко-отчёт ─────────────────────────────────────────────────────────────

def render_day(day):
    """Один человеко-отчёт дня (строки). Ничего не пишет, не зовёт сеть — чистая сводка."""
    lines = []
    k = day.get("kpis") or {}
    roles = day.get("roles") or {}
    mt = roles.get("MANAGER_TICK") or {}
    dp = roles.get("DEPARTMENTS") or {}

    mode = "СУХО (0₽)" if day.get("dry") else "живой"
    lines.append(f"📆 ДЕНЬ ОЗОН · {day.get('date')} · {day.get('ts','')[:19]} UTC · {mode}"
                 f" · commit-пути НЕТ (RUBICON)")
    if day.get("live_read"):
        lines.append("   живое дознание кабинета: ВКЛ (0₽ READ)")
    lines.append(f"   кабинет: {'Client-Id известен' if day.get('client_id_known') else 'Client-Id НЕ известен (нет OZON_CLIENT_ID в .env)'}"
                 + (f" · ключи в env: {', '.join(day.get('env_loaded') or [])}" if day.get("env_loaded") else ""))
    lines.append("")

    if not mt.get("ok"):
        lines.append("УПРАВЛЯЮЩИЙ · не смог отработать: " + str(mt.get("error")))
    else:
        note = ""
        res = (mt.get("result") or {}) if isinstance(mt.get("result"), dict) else {}
        note = res.get("note") or ""
        lines.append(f"УПРАВЛЯЮЩИЙ · {mt.get('action')} · тик {mt.get('tick_id')}"
                     + (f"\n   {note}" if note else ""))

    lines.append("")
    lines.append("САМО-МОДЕЛЬ (память) ·" + _kpis_line(k))

    if dp.get("ok"):
        lines.append("")
        lines.append(dp.get("human") or "ОТДЕЛЫ · отработали (без текста)")
    else:
        lines.append("")
        lines.append("ОТДЕЛЫ · не смогли отработать: " + str(dp.get("error")))

    an = roles.get("DONOR_ANCHOR") or {}
    lines.append("")
    if not an.get("ok"):
        lines.append("ПУПОВИНА · не сверена: " + str(an.get("error")))
    elif an.get("live") is False and an.get("human"):
        lines.append("ПУПОВИНА · шаг пропущен (шов False)")
    else:
        lines.append(f"ПУПОВИНА «карточка⇄донор» · {an.get('bound')} связаны"
                     f" ({an.get('canon_rolls')} рулонов канона), {an.get('unbound')} без якоря,"
                     f" убыточных {an.get('unprofitable')}, ширина сохранена {an.get('width_keep')}"
                     + (f" · ⚠ {len(an.get('errors') or [])} замечаний" if an.get("errors") else ""))

    tr = day.get("truth")
    lines.append("")
    if day.get("live_read"):
        if tr is None:
            lines.append("ДОЗНАНИЕ · читать не стали (ошибка подключения)")
        elif tr.get("error"):
            lines.append("ДОЗНАНИЕ · недоступно: " + str(tr["error"]))
        else:
            lines.append(f"ДОЗНАНИЕ (факт кабинета) · продаж {tr.get('sales_count')} за {tr.get('days')}д"
                         f" · выручка {tr.get('total_revenue')}₽ · чистыми {tr.get('total_net')}₽"
                         f" · комиссия {tr.get('commission_pct')}% · доставка-нетто {tr.get('delivery_net')}₽")
    else:
        lines.append("ДОЗНАНИЕ · сухой тик: живой READ кабинета не звали (--live-read / автопилот)")

    d = day.get("delta")
    lines.append("")
    lines.append("НОРМА ДНЯ · " + _daily_line(k)
                 + (" · вчера: " + _delta_line(d) if d else " · вчерашнего дня в журнале нет"))

    burn = (day.get("burning") or {}).get("items") or []
    lines.append("")
    if burn:
        lines.append(f"ЧТО ГОРИТ · {len(burn)}:")
        for b in burn:
            who = f"[{b.get('owner')}]" if b.get("owner") else ""
            lines.append(f"   🔥 {b.get('what')} → {b.get('action')} {who}")
    else:
        lines.append("ЧТО ГОРИТ · ничего — держать строй")

    g = day.get("growth") or {}
    lines.append("")
    next_step = g.get("next_lawful_step")
    lines.append("КУДА РАСТЁМ · следующий законный шаг: " + (next_step or "—"))

    lines.append("")
    if day.get("ok"):
        lines.append(f"ИТОГ · день прошёл (ok=True) · провалов 0 · журнал: "
                     f"{'записан' if day.get('_journaled') else 'НЕ записан (беда файла)'}")
    else:
        lines.append(f"ИТОГ · день прошёл с провалами ({len(day.get('failures') or [])}), B2 не роняет день:")
        for f in day.get("failures") or []:
            lines.append("   ⚠ " + str(f))
    return "\n".join(lines)


def _kpis_line(k):
    return (f"ведём {k.get('cards_tracked')} · НА ВИТРИНЕ {k.get('cards_on_shelf')} · "
            f"С ОШИБКОЙ {k.get('cards_errored')} (цель 0) · ждут категорию {k.get('need_mapping')} · "
            f"готовы к заливу {k.get('ready_to_publish')} · красный индекс {k.get('index_red')}")


def _daily_line(k):
    return (f"залито {k.get('daily_uploaded', 0)} · отгружено {k.get('daily_shipped', 0)} · "
            f"доставлено {k.get('daily_delivered', 0)} · починено {k.get('daily_fixed', 0)}")


def _delta_line(d):
    bits = []
    for kk, ch in d.items():
        fr, to = ch.get("from"), ch.get("to")
        if fr is None or to is None:
            continue
        bits.append(f"{kk}: {fr}→{to} ({ch.get('delta'):+})")
    return " · ".join(bits) if bits else "(без числовых изменений)"


# ── ПРОВЕДЕНИЕ ДНЯ ─────────────────────────────────────────────────────────────

def run_day(*, dry=True, live_read=False, truth_days=7,
            client_id=None, remember=True, use_env=True,
            manager_tick_fn=None, departments_fn=None, truth_fn=None,
            anchor_fn=None):
    """Провести день ОЗОН: тик УПРАВЛЯЮЩЕГО → ОТДЕЛЫ(6) → ДОЗНАНИЕ(если live_read) → KPI → отчёт.

    manager_tick_fn/departments_fn/truth_fn/anchor_fn — ШВЫ (для тестов и запуска без сети):
    по умолчанию берём настоящих УПРАВЛЯЮЩЕГО/ОТДЕЛЫ/ДОЗНАНИЕ/ПУПОВИНУ. False — шаг пропустить.
    Каждый шаг обёрнут в _safe: провал одного не роняет день (закон B2), беда честно в failures.

    live_read — включить ЖИВОЕ ДОЗНАНИЕ кабинета (0₽ READ, ozon_truth.analyze_cabinet). По умолчанию
    False: сухой тик сети не зовёт. Включает вызывающий (автопилот, --live-read, env OZON_LIVE=1).
    truth_days — окно дознания (дней). use_env=True — подтянуть ключи .env и id кабинета из окружения
    (нужно для запуска по расписанию); явно переданный client_id имеет приоритет.

    ВОЗВРАТ: дневной отчёт (dict). Его печатает render_day / зовёт автопилот. RUBICON физически:
    commit-параметра нет, тик зовётся commit=False — этот модуль не может открыть write-путь Озона.
    """
    ts = _now()
    env_picked = load_env_file() if use_env else []
    if use_env:
        client_id = _resolve_client_id(client_id)
    day = {
        "schema": DAY_SCHEMA,
        "ts": ts,
        "date": ts[:10],
        "dry": dry, "commit": False,          # физически НЕТ commit-пути (см. докстринг закона)
        "live_read": bool(live_read),
        "truth_days": truth_days,
        "client_id_known": bool(client_id),
        "env_loaded": env_picked,             # только ИМЕНА переменных, не значения
        "roles": {}, "failures": [], "escalations": [],
    }
    if not client_id:
        day["failures"].append(
            "Client-Id неизвестен — УПРАВЛЯЮЩИЙ слеп на реальный кабинет (нет OZON_CLIENT_ID "
            "в окружении и ни в одном .env: mint/.env, SOCC/.env, arbiter/.env)")

    # ── 1. УПРАВЛЯЮЩИЙ: bounded-тик (лестница решений, proof-леджер, локальная память) ──
    # Вывод тика перехватываем (redirect_stdout): у дня ОДИН единый отчёт, тик не печатает поверх.
    # Провал тика не роняет день (B2) — честно в failures, KPI останутся из памяти.
    if manager_tick_fn is not False:
        fn = manager_tick_fn
        if fn is None:
            try:
                fn = manager.tick
            except Exception as e:
                day["failures"].append(f"УПРАВЛЯЮЩИЙ недоступен: {type(e).__name__}: {e}")
                fn = None
        if fn is not None:
            r = _safe("MANAGER_TICK", _quiet_call, fn, dry=dry, commit=False)
            if r["ok"]:
                t = r["result"]["result"] or {}
                out = r["result"]["out"]
                day["roles"]["MANAGER_TICK"] = {
                    "ok": not (t.get("errors") or []), "action": t.get("action"),
                    "tick_id": t.get("tick_id"), "result": t.get("result"),
                    "errors": t.get("errors") or [], "print": (out or "")[:500],
                }
                day["escalations"].extend(t.get("escalations") or [])
                day["failures"].extend(t.get("errors") or [])
            else:
                day["roles"]["MANAGER_TICK"] = {"ok": False, "error": r["error"]}
                day["failures"].append(f"тик управляющего упал: {r['error']}")

    # ── 2. Память (само-модель): следующий законный шаг + сырые KPI ──
    doc = state.load()
    r = _safe("SELF", self_mod.self_status, doc)
    st = r["result"] if r["ok"] else {}
    if not r["ok"]:
        day["failures"].append(f"само-модель упала: {r['error']}")

    # ── 3. ОТДЕЛЫ (6): цепь+grounded+прогноз по текущему срезу памяти (0₽, сети нет) ──
    # Живой cabinet/orders/postings в этот заход дознание не даёт (только финансы) → прогнозы
    # отделов остаются pending (resolve_predictions сверяет цвет ТОЛЬКО с фактом карточки; факта
    # нет — честно pending, не выдумываем hit/miss).
    if departments_fn is not False:
        fn = departments_fn
        if fn is None:
            fn = lambda: departments.assess_all(doc=doc)
        rd = _safe("DEPARTMENTS", fn)
        if rd["ok"]:
            ass = rd["result"] or {}
            day["roles"]["DEPARTMENTS"] = {
                "ok": True,
                "human": departments.render(ass),
                "live": ass.get("live"),
                "groundedness": ass.get("groundedness"),
                "predictions": len(ass.get("predictions") or []),
                "summary": _dept_summary(ass),
            }
            day["departments"] = day["roles"]["DEPARTMENTS"]
        else:
            day["roles"]["DEPARTMENTS"] = {"ok": False, "error": rd["error"]}
            day["failures"].append(f"отделы не отработали: {rd['error']}")
    else:
        day["roles"]["DEPARTMENTS"] = {"ok": True, "live": False,
                                       "human": "ОТДЕЛЫ · шаг пропущен (шов False)"}

    # ── 3b. ПУПОВИНА «карточка ⇄ донор» (ЗАКОН СИСТЕМЫ 09.09) — dry-сверка, 0₽, канон с диска ──
    # Каждая позиция ВСЕГДА получает якорь донора (ширина примарна, материал ярус-2, цена ярус-3);
    # убыточный якорь не молчит (ПРОФИТ-ЗАКОН). Провал шага не роняет день (B2).
    if anchor_fn is not False:
        fn = anchor_fn
        if fn is None:
            fn = _default_anchor
        ra = _safe("DONOR_ANCHOR", fn)
        if ra["ok"]:
            an = ra["result"] or {}
            day["roles"]["DONOR_ANCHOR"] = {
                "ok": not (an.get("errors") or []),
                "canon_rolls": an.get("canon_rolls"),
                "bound": an.get("bound"), "unbound": an.get("unbound"),
                "unprofitable": an.get("unprofitable"),
                "width_keep": an.get("width_keep"),
                "errors": an.get("errors") or [],
            }
            if an.get("unprofitable"):
                day["escalations"].append({
                    "kind": f"ПУПОВИНА: {an['unprofitable']} карточек с УБЫТОЧНЫМ якорем донора",
                    "why": "профит-закон: цена карточки < cost_total закупки — нельзя лить как есть",
                    "role": "ЦЕНОВИК", "owner": "ОПЕРАТОР"})
            day["failures"].extend(an.get("errors") or [])
        else:
            day["roles"]["DONOR_ANCHOR"] = {"ok": False, "error": ra["error"]}
            day["failures"].append(f"пуповина донора не сверена: {ra['error']}")
    else:
        day["roles"]["DONOR_ANCHOR"] = {"ok": True, "live": False,
                                        "human": "ПУПОВИНА · шаг пропущен (шов False)"}

    # ── 4. ДОЗНАНИЕ (0₽ живой READ кабинета) — ТОЛЬКО при явном live_read ──
    # truth_fn — шов (тесты подкладывают факт). Провал дознания не роняет день (B2): честно
    # в failures — день НЕ соврёт «продаж N», если живой факт недостижим.
    if live_read:
        fn = truth_fn
        if fn is None:
            fn = _default_truth(truth_days)
        rt = _safe("TRUTH", fn)
        if rt["ok"]:
            tr = rt["result"] or {}
            if tr.get("error"):
                day["failures"].append(f"дознание кабинета недоступно: {tr['error']}")
            day["truth"] = {"result": tr, "slim": _truth_slim(tr)}
        else:
            day["failures"].append(f"дознание кабинета упало: {rt['error']}")
            day["truth"] = None

    # ── 5. KPI + дельта ко вчера ──
    day["kpis"] = collect_kpis(doc)
    hist = _read_journal()
    yesterday = hist[-1] if hist else None
    day["delta"] = _delta(day["kpis"], (yesterday or {}).get("kpis"))
    day["compared_to"] = (yesterday or {}).get("date")

    # ── 6. Что горит (то, что нельзя отложить) ──
    burning = []
    k = day["kpis"]
    if k.get("cards_errored"):
        ids = (day.get("roles", {}).get("MANAGER_TICK", {}).get("result") or {}).get("errored_ids")
        shown = ", ".join(str(s) for s in (ids or [])[:8]) if ids else ""
        burning.append({"what": f"{k['cards_errored']} карточек с errors[] (закон OZ1: цель 0)"
                                + (f": {shown}" + ("…" if len(ids) > 8 else "") if ids else ""),
                        "action": "точечная починка карточки (руками/fix_one — M2+; OZ1)",
                        "owner": "КОНТРОЛЁР"})
    if k.get("need_mapping"):
        burning.append({"what": f"{k['need_mapping']} карточек ждут category_id + обязательные атрибуты",
                        "action": "глаза оператора/АРХИТЕКТОРА: id не выдумываем (OZ2)",
                        "owner": "ОПЕРАТОР"})
    if k.get("index_red"):
        ids = (day.get("roles", {}).get("MANAGER_TICK", {}).get("result") or {}).get("index_red_ids")
        shown = ", ".join(str(s) for s in (ids or [])[:8]) if ids else ""
        burning.append({"what": f"{k['index_red']} карточек в КРАСНОМ индексе — их прячут из органики"
                                + (f": {shown}" + ("…" if len(ids) > 8 else "") if ids else ""),
                        "action": "снизить цену (пол маржи) или снять (OZ5); реальная правка — после ротации ключа",
                        "owner": "ЦЕНОВИК"})
    for e in day["escalations"][:10]:
        burning.append({"what": e.get("kind") or e.get("why"), "action": "эскалация",
                        "owner": "ОПЕРАТОР", "role": e.get("role")})
    day["burning"] = {"count": len(burning), "items": burning}

    # ── 7. Куда растём (единственный законный шаг из само-модели) ──
    day["growth"] = {
        "next_lawful_step": (st or {}).get("next_lawful_step"),
        "action": (day.get("roles", {}).get("MANAGER_TICK") or {}).get("action"),
    }

    day["ok"] = not day["failures"]
    if remember:
        day["_journaled"] = _append_journal(day)
    return day


def _quiet_call(fn, *a, **kw):
    """Вызвать fn, перехватив stdout (StringIO) → (возврат, перехваченный текст). Не роняет ничего."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        res = fn(*a, **kw)
    return {"result": res, "out": buf.getvalue()}


def _default_truth(truth_days):
    """Живой ридер дознания (thunk ленив: сеть только при вызове). Никаких write."""
    try:
        import ozon_truth_v1 as truth
        return lambda: truth.analyze_cabinet(days=truth_days)
    except Exception:
        return lambda: {"error": "озон_truth_v1 недоступен (import)"}


def _default_anchor():
    """ПУПОВИНА: dry-сверка библиотеки с донором (0₽, канон с диска, сети нет). Никаких write.

    Закон: каждая ПРИМАРНАЯ позиция (pour_flag) получает якорь. Строки-не-литья (нет size,
    pour_flag=False) в ошибки не идут — это не карточки залива, а служебная библиотека."""
    import ozon_donor_anchor_v1 as anchor
    rolls = anchor.load_latest_donor_rolls()
    if not rolls:
        return {"error": "канон рулонов донора не найден (нет donor-rolls-*.json)",
                "canon_rolls": 0}
    lib = anchor._load_library()
    res = anchor.bind_library(lib, rolls)
    errs = []
    pour_unbound = sum(1 for b in res["blocks"] if _rec_is_pour(lib, b.get("article")))
    if pour_unbound:
        errs.append(f"{pour_unbound} карточек ЛИТЬЯ (pour_flag) без якоря донора")
    if res["stats"].get("unprofitable"):
        errs.append(f"{res['stats']['unprofitable']} карточек с убыточным якорем донора")
    return {
        "canon_rolls": len(rolls),
        "bound": len(res["ok"]), "unbound": len(res["blocks"]),
        "pour_unbound": pour_unbound,
        "unprofitable": res["stats"].get("unprofitable", 0),
        "width_keep": sum(1 for a in res["ok"].values() if a.get("mode") == "same-width"),
        "errors": errs,
    }


def _rec_is_pour(lib, article):
    for rec in lib:
        if str(rec.get("article")) == str(article):
            return bool(rec.get("pour_flag"))
    return False


def _truth_slim(tr):
    """Компактный слепок дознания для журнала. Ошибка → {'error': ...} (не притворяемся фактом)."""
    if not isinstance(tr, dict) or tr.get("error"):
        return {"ok": False, "error": (tr or {}).get("error")}
    return {"ok": True, "sales_count": tr.get("sales_count"), "days": tr.get("days"),
            "total_revenue": tr.get("total_revenue"), "total_net": tr.get("total_net"),
            "commission_pct": tr.get("commission_pct"), "delivery_net": tr.get("delivery_net")}


def _dept_summary(ass):
    """Короткая сводка отдела (для консоли/журнала): кто, что увидел, заземлено ли, сколько прогнозов."""
    out = []
    for r in (ass.get("departments") or []):
        out.append({"dept": r.get("dept"), "name_ru": r.get("name_ru"), "emoji": r.get("emoji"),
                    "ok": r.get("ok", True), "human": r.get("human"),
                    "grounded": r.get("grounded"), "source": r.get("source"),
                    "preds": len(r.get("predictions") or []),
                    "error": r.get("error")})
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="СУТОЧНЫЙ ЦИКЛ ОЗОН — день органа (dry по умолчанию, 0₽, БЕЗ commit-пути)")
    ap.add_argument("--dry", action="store_true", default=False,
                    help="сухой день (всегда сухо: commit-пути НЕТ физически; флаг — явное подтверждение)")
    ap.add_argument("--live-read", action="store_true",
                    help="включить ЖИВОЕ ДОЗНАНИЕ кабинета (0₽ READ: факт продаж/нетто/доставки)")
    ap.add_argument("--truth-days", type=int, default=7, help="окно дознания, дней (по умолчанию 7)")
    ap.add_argument("--json", action="store_true", help="машинный вывод отчёта")
    args = ap.parse_args()

    live = args.live_read or os.environ.get("OZON_LIVE", "").lower() in ("1", "true", "yes")
    # RUBICON: день ВСЕГДА сухой — коммит-пути в run_day нет; --dry существует как явное
    # подтверждение режима (без инверсии: раньше `dry=not args.dry` с default=True давал «живой»).
    d = run_day(dry=True, live_read=live, truth_days=args.truth_days)
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_day(d))
