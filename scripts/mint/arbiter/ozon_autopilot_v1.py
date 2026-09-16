#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""АВТОПИЛОТ ОЗОН (ozon_autopilot_v1) — сухой день под расписание (launchd/cron), 0₽, БЕЗ commit.

Зеркало ymarket_autopilot_v1 ПОД ОЗОН, но НАМЕРЕННО легче: у ЯМ тик тащит планёрку/совет/споры/сев/
ленту — у ОЗОН нет планёрки-совета-ТГ (этих слоёв ещё нет в линии, появятся отдельным словом). Здесь
автопилот делает РОВНО то, зачем стоит под расписанием: прогоняет СУТОЧНЫЙ ДЕНЬ органа
(ozon_day.run_day) — тик УПРАВЛЯЮЩЕГО → 6 ОТДЕЛОВ → KPI/нормы → журнал + человеко-лог.

ЗАКОН RUBICON (зашит ФИЗИЧЕСКИ): у run() НЕТ параметра commit и НЕТ пути к живому дню Озона.
День зовётся СТРОГО dry=True, commit=False. Всё, что пишет автопилот, — ЛОКАЛЬНО (память/журнал/
лог, 0₽): файлы органа, не рука Ozon. Живой READ кабинета (дознание: факт продаж/нетто/доставка,
0₽ GET) — вкл по умолчанию, чтобы утро видело РЕАЛЬНЫЕ цифры; выключается env
OZON_AUTOPILOT_LIVE_READ=0 (герметичные тесты) или отсутствием ключа (день честно доложит провал,
не выдумает). Реальный write Ozon — только по слову оператора ПОСЛЕ ротации ключа (06.08).

Лог: OZON_AUTOPILOT_LOG или <день.REPORTS>/ozon_autopilot.log (человеко-отчёт + JSON). Ротация >2МБ.
Fail-soft: любая беда — в лог, exit 0 (расписание живёт, рестарт-шторма нет).

launchd: com.wavy.socc.ozon_autopilot.plist (3×/сутки MSK 08:07/14:17/20:47, как ЯМ) — рядом в этом
каталоге; НЕ загружается без слова оператора.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path
from datetime import timezone

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

LOG_ROTATE_BYTES = 2_000_000          # >2 МБ → отложить старый лог в .1 (вечная машина не пухнет)


def _now():
    return datetime.datetime.now(timezone.utc).isoformat()


def log_path():
    """Куда писать человеко-читаемый лог. OZON_AUTOPILOT_LOG перекрывает (тесты/оператор)."""
    p = os.environ.get("OZON_AUTOPILOT_LOG")
    if p:
        return Path(p)
    try:
        import ozon_day_v1 as day
        return day.REPORTS / "ozon_autopilot.log"
    except Exception:
        return HERE / "ozon_autopilot.log"


def _rotate(lp):
    """Простая ротация: раздулся лог — сдвигаем в .1 (fail-soft, беда молча пропускается)."""
    try:
        if lp.exists() and lp.stat().st_size > LOG_ROTATE_BYTES:
            lp.replace(lp.with_suffix(lp.suffix + ".1"))
    except Exception:
        pass


def _write_log(d):
    """Записать человеко-отчёт дня + компактную JSON-строку. Никогда не роняем смену из-за лога."""
    try:
        import ozon_day_v1 as day
        human = day.render_day(d)
    except Exception as e:
        human = f"[отчёт не отрендерился: {type(e).__name__}: {e}]"
    compact = {k: d.get(k) for k in ("ts", "date", "ok", "dry", "commit")}
    compact["failures"] = len(d.get("failures") or [])
    compact["burning"] = (d.get("burning") or {}).get("count")
    compact["kpis"] = d.get("kpis")
    try:
        lp = log_path()
        lp.parent.mkdir(parents=True, exist_ok=True)
        _rotate(lp)
        with open(lp, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 72 + "\n")
            f.write(f"АВТОПИЛОТ ОЗОН (СУХОЙ) запуск {_now()}\n")
            f.write(human.rstrip() + "\n")
            f.write("JSON " + json.dumps(compact, ensure_ascii=False) + "\n")
    except Exception:
        pass          # лог — удобство, не право уронить смену
    return compact


def _resolve_live(live_read):
    """Дознание автопилота: True по умолчанию (0₽ GET кабинета, утро видит реальные цифры);
    env OZON_AUTOPILOT_LIVE_READ=0/off — выключить (герметика/нет сети); флаг явный — приоритет."""
    if live_read is not None:
        return bool(live_read)
    off = os.environ.get("OZON_AUTOPILOT_LIVE_READ", "").lower()
    return off not in ("0", "false", "no", "off")


def run(*, live_read=None, day_fn=None):
    """Один СУХОЙ прогон суточного дня ОЗОН + запись в лог.

    live_read — включить живое дознание кабинета (0₽ READ). None → авто-решение по env
    (OZON_AUTOPILOT_LIVE_READ=0 выключает; по умолчанию ВКЛ, см. _resolve_live).
    day_fn — ШОВ для тестов (подкладывают день без сети и без касания канонической памяти).

    ВНИМАНИЕ: здесь НАМЕРЕННО нет аргумента commit — автопилот не имеет права на боевой режим.
    Локальные write (0₽): память/журнал дня, лог автопилота — файлы органа, не рука Ozon.
    """
    if day_fn is None:
        import ozon_day_v1 as day
        day_fn = day.run_day
    live = _resolve_live(live_read)
    d = day_fn(dry=True, live_read=live)   # <<< RUBICON: жёстко сухо; пути к commit из автопилота НЕТ
    compact = _write_log(d)
    return {
        "ts": d.get("ts"), "date": d.get("date"),
        "ok": d.get("ok"), "dry": d.get("dry"), "commit": False,
        "client_id_known": d.get("client_id_known"),
        "live_read": d.get("live_read"),
        "failures": len(d.get("failures") or []),
        "burning": (d.get("burning") or {}).get("count"),
        "action": (d.get("roles") or {}).get("MANAGER_TICK", {}).get("action"),
        "kpis": d.get("kpis"),
        "journaled": bool(d.get("_journaled")),
    }


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="ОЗОН СУХОЙ автопилот — самоходный день органа (0₽, БЕЗ commit, для launchd/cron)")
    ap.add_argument("--live-read", dest="live_read", action="store_true", default=None,
                    help="включить живое дознание кабинета (0₽ READ) [по умолч. вкл; env OZON_AUTOPILOT_LIVE_READ=0 выкл]")
    ap.add_argument("--no-live-read", dest="live_read", action="store_false",
                    help="выключить живое дознание (только память, 0₽ вообще)")
    ap.add_argument("--json", action="store_true", help="машинный вывод (иначе — одна человеческая строка)")
    args = ap.parse_args(argv)
    try:
        r = run(live_read=args.live_read)
    except Exception as e:               # fail-soft: launchd не должен уходить в рестарт-шторм
        r = {"ok": False, "error": f"{type(e).__name__}: {e}", "dry": True, "commit": False,
             "date": _now()[:10]}
        try:
            lp = log_path()
            lp.parent.mkdir(parents=True, exist_ok=True)
            with open(lp, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*72}\nАВТОПИЛОТ ОЗОН упал {_now()}: {r['error']}\n")
        except Exception:
            pass
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        k = r.get("kpis") or {}
        print(f"АВТОПИЛОТ ОЗОН {r.get('date','?')} · ok={r.get('ok')} · dry=True commit=False"
              f" · live-read={r.get('live_read')} · client_id={'да' if r.get('client_id_known') else 'НЕТ'}"
              f" · упр {r.get('action')} · провалов={r.get('failures','?')} · горит={r.get('burning','?')}"
              f" · карточек {k.get('cards_tracked')} · витрина {k.get('cards_on_shelf')}"
              f" · ошибки {k.get('cards_errored')}")
    return 0      # всегда 0: беда уже в логе, расписание живёт дальше


if __name__ == "__main__":
    sys.exit(_main())
