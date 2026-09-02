#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARBITER АВТОПИЛОТ (СУХОЙ) V1 — самоходная смена Яндекс.Маркета по расписанию.

ЗАЧЕМ: суточный цикл (ymarket_day_v1.run_day) уже умеет ВСЁ — смена бригады, тик управляющего,
СТРАТЕГ, ТРЕНД-СКАУТ, ГОЛОВА, KPI, дельта, «что горит», отчёт, память. Не хватало РУКИ, которая
заводит его сама, без оператора у клавиатуры, и оставляет читаемый след. Этот модуль — та рука:
запускает цикл СУХИМ, пишет лог, докладывает одной строкой. Задуман для launchd/cron.

ЖЕЛЕЗНЫЙ ЗАКОН (RUBICON — зашит ФИЗИЧЕСКИ, не флагом):
  • Автопилот НИКОГДА не ходит в commit. В этом модуле НЕТ параметра commit и НЕТ пути к нему:
    run_day вызывается строго dry=True, commit=False. Живой рубильник — ОТДЕЛЬНЫЙ и РУЧНОЙ
    (`python3 ymarket_day_v1.py --commit` под явным словом оператора), НИКОГДА не через автопилот.
  • Всё, что делает автопилот, — ЧТЕНИЕ (кабинет + публичный WB) + счёт + отчёт + память. 0 ₽.
  • Fail-soft: любая беда логируется, процесс выходит 0 — расписание не должно захлёбываться алертами
    и не должно падать в цикл перезапуска из-за одной моргнувшей сети.

Лог: ARBITER_AUTOPILOT_LOG или <день.REPORTS>/ymarket_autopilot.log (человеко-читаемый отчёт + JSON).
Чистый stdlib. Ключи и id кабинета берутся из .env через штатный загрузчик суточного цикла.
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ymarket_day_v1 as day          # noqa: E402  (реюз: весь цикл + REPORTS + загрузка .env)

LOG_ROTATE_BYTES = 2_000_000          # >2 МБ → отложить старый лог в .1 (вечная машина не пухнет)

# ИСТОЧНИК ЗАЛИВА ПО УМОЛЧАНИЮ — цикл живёт БЕЗ команд (приказ оператора 2026-09-01: «цикл должен
# жить сам, имея цель ЗАРАБОТОК НА ЯНДЕКС МАРКЕТЕ»). Пара ДОКАЗАНА живьём 2026-09-01 (демо 06:42 UTC:
# партия собралась сухо, фид 10→11 постов, СБОРЩИК вышел в чат). Контракт двух слагов (F6): donor_xlsx
# = URL-путь категории на shop.cargo-avto.ru, slug = JSON-ключ ymarket_cats_v1.json (КАТЕГОРИЙЩИК).
# Env YM_ZALIV_DONOR / YM_ZALIV_SLUG ПЕРЕКРЫВАЕТ дефолт — это руль смены категории, а не отключение.
_ZALIV_DEFAULT_DONOR = "vozdushno-puzyrkovaya-plenka"
_ZALIV_DEFAULT_SLUG = "puzyrkovaya-plenka"


def _now():
    return datetime.now(timezone.utc).isoformat()


def log_path():
    """Куда писать человеко-читаемый лог автопилота. ARBITER_AUTOPILOT_LOG перекрывает (тесты/оператор)."""
    p = os.environ.get("ARBITER_AUTOPILOT_LOG")
    return Path(p) if p else (day.REPORTS / "ymarket_autopilot.log")


def _rotate(lp):
    """Простая ротация: раздулся лог — сдвигаем в .1 (fail-soft, беда чтения/переноса молча пропускается)."""
    try:
        if lp.exists() and lp.stat().st_size > LOG_ROTATE_BYTES:
            lp.replace(lp.with_suffix(lp.suffix + ".1"))
    except Exception:
        pass


def _write_log(d):
    """Записать отчёт дня + компактную JSON-строку. Никогда не роняем автопилот из-за лога."""
    try:
        import ymarket_report_v1 as report
        human = report.render_day(d)
    except Exception as e:
        human = f"[отчёт не отрендерился: {type(e).__name__}: {e}]"
    compact = {k: d.get(k) for k in ("ts", "date", "ok", "dry", "commit", "business_id_known")}
    compact["failures"] = len(d.get("failures") or [])
    compact["burning"] = (d.get("burning") or {}).get("count")
    try:
        lp = log_path()
        lp.parent.mkdir(parents=True, exist_ok=True)
        _rotate(lp)
        with open(lp, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 72 + "\n")
            f.write(f"АВТОПИЛОТ (СУХОЙ) запуск {_now()}\n")
            f.write(human.rstrip() + "\n")
            f.write("JSON " + json.dumps(compact, ensure_ascii=False) + "\n")
    except Exception:
        pass          # лог — удобство, не право уронить смену
    return compact


def _deliver_feed(d):
    """СУХАЯ ЛЕНТА ДЕЙСТВИЙ команды в Telegram (каждая роль — отдельным сообщением).

    Это «живой офис говорит»: тот самый ТГ-фид, который оператор смотрит как создатель.
    Держим строго fail-soft и БЕЗ права ронять смену — любая беда доставки уходит молча в лог.
    Без YM_TELEGRAM_BOT_TOKEN / YM_TELEGRAM_CHAT_ID НИЧЕГО не уходит (NO_CREDS), и поведение
    автопилота не меняется — ровно как раньше. Появится токен в .env → офис заговорит сам,
    без единой правки кода. RUBICON цел: это ЧТЕНИЕ-доставка уже посчитанного сухого дня,
    а не запись в кабинет — 0 ₽, никаких API-мутаций.
    """
    try:
        import ymarket_team_feed_v1 as feed
        res = feed.deliver(d, echo=False)                 # echo=False: посты идут в ТГ, не в stdout
        delivery = (res or {}).get("delivery") or {}
        sent = delivery.get("sent")
        note = delivery.get("note") or delivery.get("reason")
        line = (f"ЛЕНТА в Telegram: {delivery.get('sent_count', '?')}/{delivery.get('posts', '?')} постов"
                + ("" if sent else f" — {note}"))
    except Exception as e:
        line = f"ЛЕНТА в Telegram НЕ отправлена (fail-soft): {type(e).__name__}: {e}"
    try:
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    return line


def run(head_source="wb", head_city=None):
    """Один СУХОЙ прогон суточного цикла + запись в лог + сухая ТГ-лента. Возвращает итог (dict).

    head_source: 'wb' — живой нос спроса (ЧТЕНИЕ публичного WB, 0₽) для ГОЛОВЫ; 'none' — без сети-носа.
    ВНИМАНИЕ: здесь НАМЕРЕННО нет аргумента commit — автопилот не имеет права на боевой режим.
    """
    head_source_fn = None
    if head_source == "wb":
        try:
            import ymarket_head_source_v1 as hs
            head_source_fn = hs.build_source_fn(city=head_city)   # thunk ленив: сеть только при вызове
        except Exception:
            head_source_fn = None      # нет источника — ГОЛОВА честно скажет NO_HEAD_SOURCE, не выдумает

    # ИСТОЧНИК ЗАЛИВА — живёт САМ, без команд оператора (2026-09-01). Если env не задан — берём
    # ДОКАЗАННУЮ дефолтную пару (см. _ZALIV_DEFAULT_DONOR/SLUG выше); env перекрывает для смены
    # категории. Раньше без env preflight_fn=None и день молчал о партии — теперь тик САМ собирает
    # сухую партию и СБОРЩИК докладывает в чат. Обратная совм.: env-механика та же, добавлен лишь дефолт.
    # Сборка сухая (publish_card dry, commit=False) → 0₽, RUBICON цел: автопилот НЕ публикует.
    preflight_fn = None
    _donor = os.environ.get("YM_ZALIV_DONOR") or _ZALIV_DEFAULT_DONOR
    _zslug = os.environ.get("YM_ZALIV_SLUG") or _ZALIV_DEFAULT_SLUG
    try:
        import ymarket_zaliv_source_v1 as zs
        _zlimit = int(os.environ.get("YM_ZALIV_LIMIT") or 20)
        preflight_fn = zs.build_preflight_fn(_donor, _zslug,
                                            city=os.environ.get("YM_ZALIV_CITY") or None,
                                            limit=_zlimit)    # thunk ленив: сборка при вызове
    except Exception:
        preflight_fn = None       # источник не собрался — день честно оставит ready из памяти

    d = day.run_day(head_source_fn=head_source_fn, head_city=head_city,
                    read_cabinet=True,           # живая СВЕРКА: cards_errored из реального errors[], не из памяти (0₽ READ)
                    preflight_fn=preflight_fn,   # сухая сборка партии → «сколько полетит» (0₽, если задан донор)
                    dry=True, commit=False)      # <<< RUBICON: жёстко сухо; пути к commit из автопилота НЕТ
    _write_log(d)
    _deliver_feed(d)                             # сухая ТГ-лента (fail-soft; без YM_TELEGRAM_* — тихо NO_CREDS)
    return {
        "ts": d.get("ts"), "date": d.get("date"),
        "ok": d.get("ok"), "dry": d.get("dry"), "commit": d.get("commit"),
        "business_id_known": d.get("business_id_known"),
        "campaign_id_known": d.get("campaign_id_known"),
        "failures": len(d.get("failures") or []),
        "burning": (d.get("burning") or {}).get("count"),
        "quality_index": (d.get("kpis") or {}).get("quality_index"),
        "zaliv_ready": (d.get("zaliv") or {}).get("ready"),      # «полетит чисто» (None = источник не подключён)
        "zaliv_errors": (d.get("zaliv") or {}).get("errors"),    # планка YM1: цель 0
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="ARBITER СУХОЙ автопилот — самоходная смена ЯМ (0₽, БЕЗ commit, для launchd/cron)")
    ap.add_argument("--head-source", choices=("none", "wb"), default="wb",
                    help="источник спроса ГОЛОВЫ: wb (по умолч., живое ЧТЕНИЕ WB, 0₽) | none (без сети-носа)")
    ap.add_argument("--head-city", default=None, help="город для носа спроса (по умолч. msk)")
    ap.add_argument("--json", action="store_true", help="машинный вывод (иначе — одна человеческая строка)")
    args = ap.parse_args()
    try:
        r = run(head_source=args.head_source, head_city=args.head_city)
    except Exception as e:               # fail-soft: launchd не должен уходить в рестарт-шторм
        r = {"ok": False, "error": f"{type(e).__name__}: {e}", "dry": True, "commit": False}
        try:
            lp = log_path()
            lp.parent.mkdir(parents=True, exist_ok=True)
            with open(lp, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*72}\nАВТОПИЛОТ упал {_now()}: {r['error']}\n")
        except Exception:
            pass
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(f"АВТОПИЛОТ {r.get('date','?')} · ok={r.get('ok')} · dry={r.get('dry')} commit={r.get('commit')}"
              f" · businessId={'да' if r.get('business_id_known') else 'НЕТ'}"
              f" · провалов={r.get('failures','?')} · горит={r.get('burning','?')}")
    sys.exit(0)      # всегда 0: беда уже в логе, расписание живёт дальше
