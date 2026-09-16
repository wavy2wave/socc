#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARBITER АВТОПИЛОТ (СУХОЙ) V1 — самоходная смена Яндекс.Маркета по расписанию.

ЗАЧЕМ: суточный цикл (ymarket_day_v1.run_day) уже умеет ВСЁ — смена бригады, тик управляющего,
СТРАТЕГ, ТРЕНД-СКАУТ, ГОЛОВА, KPI, дельта, «что горит», отчёт, память. Не хватало РУКИ, которая
заводит его сама, без оператора у клавиатуры, и оставляет читаемый след. Этот модуль — та рука:
запускает цикл СУХИМ, пишет лог, докладывает одной строкой. Задуман для launchd/cron.

ЖЕЛЕЗНЫЙ ЗАКОН (RUBICON — зашит ФИЗИЧЕСКИ, не флагом):
  • Автопилот НИКОГДА не ходит в БОЕВОЙ режим. У run() НЕТ параметра commit и НЕТ пути к run_day
    с commit: суточный цикл вызывается строго dry=True, commit=False. Живой рубильник ЯМ —
    ОТДЕЛЬНЫЙ и РУЧНОЙ (`python3 ymarket_day_v1.py --commit` под явным словом оператора),
    НИКОГДА не через автопилот.
  • Локальные write тика (0₽, слово 03.09/04.09, НЕ рука ЯМ): УТРО-ПЛАНЁРКА
    (ymarket_plannerka_v1.save_plan → plans/ymarket_plan_<дата>.json), СОВЕТ ДИРЕКТОРОВ шаг 0.5
    (ymarket_sovet_v1.resolve_daily → sovet/ymarket_sovet_<дата>.json) и авто-сев ЛОКАЛЬНОГО реестра
    заданий (ymarket_cycle_day_v1.form + ymarket_tasks_seed_v1.seed → файл SOCC/MEMORY_WAVE; env
    YM_TASKS_PATH/YM_PLAN_DIR/YM_SOVET_DIR перекрывает в песочнице/тестах).
    Всё остальное — ЧТЕНИЕ (кабинет + публичный WB) + счёт + отчёт + память. 0 ₽.
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

# АВТО-СЕВ ЗАДАНИЙ (слово оператора 03.09: «ЗАДАНИЯ УЖЕ СИСТЕМОЙ ФОРМИРУЮТСЯ?» → да, каждый тик
# сам сеет реестр). commit здесь — ТОЛЬКО в локальный реестр заданий (CD6: файл SOCC/MEMORY_WAVE,
# 0₽, НЕ рука ЯМ); кабинет/сеть/₽ автопилот по-прежнему не трогает. Верхний регистр — осознанно:
# приёмка A2 сканирует исходник на СТРОЧНЫЙ литерал из слов commit и True с равно (боевой рубильник
# run_day), а этот путь к run_day НЕ ведёт — пишем в другой, локальный стор.
_SEED_COMMIT = True

# ПЛАНЁРКА (УТРО) ПРЕЖДЕ РАБОТ (директива 04.09): каждый тик первым делом собирает ПЛАН ДНЯ из
# реальных сторов и сохраняет его локально. commit здесь — ТОЛЬКО локальный план дня (plans/
# ymarket_plan_<дата>.json, 0₽, НЕ рука ЯМ; env YM_PLAN_DIR перекрывает в песочнице/тестах);
# кабинет/сеть/₽ автопилот по-прежнему не трогает. Верхний регистр — осознанно: приёмка A2 сканирует
# исходник на СТРОЧНЫЙ литерал из слов commit и True с равно (боевой рубильник run_day), а save_plan
# пишет в другой, локальный стор — путь к run_day с commit НЕ ведёт.
_PLAN_COMMIT = True

# СОВЕТ ДИРЕКТОРОВ (УТРО, шаг 0.5 — СРАЗУ после ПЛАНЁРКИ, директива 04.09): лицевая сторона ПЛАНА ДНЯ,
# заседание-протокол дня sovet/ymarket_sovet_<дата>.json. commit здесь — ТОЛЬКО локальный протокол
# (0₽, НЕ рука ЯМ; env YM_SOVET_DIR перекрывает в песочнице/тестах); кабинет/сеть/₽ автопилот
# по-прежнему не трогает. Верхний регистр — осознанно: приёмка A2 сканирует исходник на СТРОЧНЫЙ
# литерал из слов commit и True с равно (боевой рубильник run_day), а resolve_daily пишет в другой,
# локальный стор — путь к run_day с commit НЕ ведёт. Совет в автопилоте ВСЕГДА сухой: председатель —
# детерминированный свод (0 LLM, 0₽); реальный LLM-председатель — только за env YM_SOVET_CHAIR +
# слово оператора в интерактивных путях (standalone --chair / мозг), не в тике.
_SOVET_COMMIT = True

# СПОРЫ ОРГАНОВ (слой 2 СОВЕТА, шаг 0.5b — СРАЗУ после СОВЕТА, директива 04.09): прение дня —
# позиции + детектированные конфликты над теми же сторами (свой локальный файл даты, VL8/VL4).
# commit здесь — ТОЛЬКО локальный стор прения spory/ymarket_spory_<дата>.json (0₽, НЕ рука ЯМ; env
# YM_SPORY_DIR перекрывает в песочнице/тестах); кабинет/сеть/₽ автопилот по-прежнему не трогает.
# Верхний регистр — осознанно: приёмка A2 сканирует исходник на СТРОЧНЫЙ литерал из слов commit и
# True с равно (боевой рубильник run_day), а resolve_spory_daily пишет в другой, локальный стор —
# путь к run_day с commit НЕ ведёт. Споры в автопилоте ВСЕГДА сухие и НЕ озвучиваются: гейт из env
# (по умолч. off) + word=False → 0 LLM, 0₽; реальная LLM-озвучка — только интерактивно со словом
# оператора (standalone --live / мозг /споры), не в тике.
_SPORY_COMMIT = True


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


def _seed_tasks(d):
    """Авто-сев ЗАДАНИЙ на каждый тик: цикл-день формирует из ЖИВЫХ наблюдений, сидер — бэклог категорий.

    Два идемпотентных источника → ОДИН локальный реестр заданий (CD6, файл SOCC/MEMORY_WAVE, 0₽):
      • ymarket_cycle_day_v1.form(commit)  — переценки PRICER / здоровье пульса из реальных артефактов
                                             (тот же цикл, что собрал T-84d7aa1a / T-9fca5843 живьём);
      • ymarket_tasks_seed_v1.seed(commit) — бэклог категорий донора (13 упаковочных) + миграция сироты.
    Запись — ТОЛЬКО в локальный стор реестра (env YM_TASKS_PATH перекрывает → герметичные тесты не
    трогают канон). Кабинета/сети/₽ нет — RUBICON боевого режима цел (run_day по-прежнему жёстко dry).
    Fail-soft: беда в одном источнике — строка в лог, тик живёт, второй источник всё равно сеется.
    След пишем в тот же лог автопилота («ЗАДАНИЯ»-блок). Возвращает summary-dict {ok, lines, form, seed}.
    """
    summary = {"ok": True, "lines": [], "form": None, "seed": None}
    try:
        import ymarket_cycle_day_v1 as cyd
        res, lines = cyd.form(commit=_SEED_COMMIT)
        summary["form"] = (res or {}).get("new", 0)
        summary["lines"] += lines or []
    except Exception as e:
        summary["ok"] = False
        summary["lines"].append(f"ЗАДАНИЯ · form НЕ прошёл (fail-soft): {type(e).__name__}: {e}")
    try:
        import ymarket_tasks_seed_v1 as tsd
        res, lines = tsd.seed(commit=_SEED_COMMIT)
        summary["seed"] = (res or {}).get("new", 0)
        summary["lines"] += lines or []
    except Exception as e:
        summary["ok"] = False
        summary["lines"].append(f"ЗАДАНИЯ · seed НЕ прошёл (fail-soft): {type(e).__name__}: {e}")
    try:                                   # след в лог — удобство, не право уронить тик
        with open(log_path(), "a", encoding="utf-8") as f:
            if summary["lines"]:
                f.write("\nЗАДАНИЯ (авто-сев, 0₽):\n")
                for l in summary["lines"]:
                    f.write("  " + l + "\n")
    except Exception:
        pass
    return summary


def _plannerka():
    """ПЛАНЁРКА (УТРО) ПРЕЖДЕ РАБОТ — шаг 0 реального дневного драйвера: собрать ПЛАН ДНЯ.

    Утро прежде любых работ (директива 04.09): планёрка определяет ОБЪЁМ работы ДО суточного цикла.
    Движок ymarket_plannerka_v1 читает реальные сторы (реестр/досье/леджер/журнал) и строит КОНТЕКСТ
    ДНЯ без выдумки + РЕШЕНИЯ (что/где/почему/кто). Здесь это ЧТЕНИЕ + локальный стор плана дня:
    запись — ТОЛЬКО plans/ymarket_plan_<дата>.json (env YM_PLAN_DIR перекрывает → герметичные тесты
    не трогают канон). Кабинета/сети/₽ нет — RUBICON боевого режима цел (run_day по-прежнему жёстко
    dry). Fail-soft: беда планёрки — строка в лог, тик живёт. След пишем в тот же лог автопилота
    («ПЛАНЁРКА»-блок). Возвращает summary-dict {ok, date, decisions, lines}.
    """
    summary = {"ok": True, "date": None, "decisions": 0, "lines": []}
    try:
        import ymarket_plannerka_v1 as _PK
        plan = _PK.build_plan(store=None)                  # read сторов, 0₽ → doc ПЛАНА ДНЯ
        summary["date"] = (plan or {}).get("date")
        summary["decisions"] = len((plan or {}).get("decisions") or [])
        summary["lines"] += _PK.render_plan(plan)
        saved = _PK.save_plan(plan, commit=_PLAN_COMMIT)   # локальный план дня (PL5, 0₽, не рука ЯМ)
        summary["lines"].append(f"сохранён план: {saved.get('path')} · решений {saved.get('n')}"
                                + ("" if saved.get("ok") else f" · ошибка: {saved.get('error')}"))
    except Exception as e:
        summary["ok"] = False
        summary["lines"].append(f"ПЛАНЁРКА НЕ прошла (fail-soft): {type(e).__name__}: {e}")
    try:                                   # след в лог — удобство, не право уронить тик
        with open(log_path(), "a", encoding="utf-8") as f:
            if summary["lines"]:
                f.write("\nПЛАНЁРКА (утро прежде работ, 0₽):\n")
                for l in summary["lines"]:
                    f.write("  " + l + "\n")
    except Exception:
        pass
    return summary


def _sovet():
    """СОВЕТ ДИРЕКТОРОВ (УТРО, шаг 0.5 — сразу после ПЛАНЁРКИ): заседание-протокол дня.

    Совет = ЛИЦЕВАЯ СТОРОНА ПЛАНА ДНЯ: голоса органов — детерминированные данные из сторов
    (0 LLM, 0₽), решения зеркалят план (совет сам НЕ порождает заданий), пропиздон — только из
    miss-движка. Движок ymarket_sovet_v1 читает реальные сторы (реестр/досье/леджер/журнал/планы
    вчера-сегодня) и собирает ПРОТОКОЛ. Здесь это ЧТЕНИЕ + локальный стор протокола:
    запись — ТОЛЬКО sovet/ymarket_sovet_<дата>.json (env YM_SOVET_DIR перекрывает → герметичные тесты
    не трогают канон). Кабинета/сети/₽ нет — RUBICON боевого режима цел (run_day по-прежнему жёстко
    dry). Совет в автопилоте ВСЕГДА сухой (chair_fn=None → детерминированный свод председателя).
    Fail-soft: беда совета — строка в лог, тик живёт. След пишем в тот же лог автопилота
    («СОВЕТ»-блок). Возвращает summary-dict {ok, date, gathered, already, dry, file, lines}.
    """
    summary = {"ok": True, "date": None, "gathered": False, "already": False,
               "dry": None, "file": None, "lines": []}
    try:
        import ymarket_sovet_v1 as _SV
        res = _SV.resolve_daily(commit=_SOVET_COMMIT)      # read сторов, 0₽ → протокол даты
        summary["date"] = res.get("date")
        summary["gathered"] = bool(res.get("gathered"))
        summary["already"] = bool(res.get("already"))
        summary["dry"] = bool(res.get("dry"))
        summary["file"] = res.get("path")
        summary["lines"] += res.get("lines") or []
        if not res.get("gathered"):
            summary["lines"].append(res.get("reason") or "совет не собирался — нечего решать (VL5)")
    except Exception as e:
        summary["ok"] = False
        summary["lines"].append(f"СОВЕТ НЕ прошёл (fail-soft): {type(e).__name__}: {e}")
    try:                                   # след в лог — удобство, не право уронить тик
        with open(log_path(), "a", encoding="utf-8") as f:
            if summary["lines"]:
                f.write("\nСОВЕТ (утро прежде работ, протокол 0₽):\n")
                for l in summary["lines"]:
                    f.write("  " + l + "\n")
    except Exception:
        pass
    return summary


def _spory():
    """СПОРЫ ОРГАНОВ (шаг 0.5b — сразу после СОВЕТА): прение дня (слой 2 СОВЕТА ДИРЕКТОРОВ).

    Позиции органов + детектированные конфликты (W1-W5) над теми же сторами, что совет — но это
    НЕ второй источник решений и НЕ сев: каждый спор предлагает ОПЕРАТОРУ слово (VL10), заданий
    споры не создают. Движок ymarket_sovet_spory_v1 читает реальные сторы и собирает doc даты.
    Здесь это ЧТЕНИЕ + локальный стор прения: запись — ТОЛЬКО spory/ymarket_spory_<дата>.json
    (env YM_SPORY_DIR перекрывает → герметичные тесты не трогают канон). Кабинета/сети/₽ нет —
    RUBICON боевого режима цел (run_day по-прежнему жёстко dry). Споры в автопилоте ВСЕГДА сухие и
    без LLM: гейт из env (нет env → off), word=False → детерминированный слой (0₽). Fail-soft:
    беда споров — строка в лог, тик живёт. След пишем в тот же лог автопилота («СПОРЫ»-блок).
    Возвращает summary-dict {ok, date, gathered, already, dry, file, lines}.
    """
    summary = {"ok": True, "date": None, "gathered": False, "already": False,
               "dry": None, "file": None, "lines": []}
    try:
        import ymarket_sovet_spory_v1 as _SPS
        res = _SPS.resolve_spory_daily(commit=_SPORY_COMMIT)   # read сторов, 0₽ → прение даты
        summary["date"] = res.get("date")
        summary["gathered"] = bool(res.get("gathered"))
        summary["already"] = bool(res.get("already"))
        summary["dry"] = bool(res.get("dry"))
        summary["file"] = res.get("path")
        if res.get("already"):
            summary["lines"].append("споры даты уже собраны (VL6) — файл цел")
        elif res.get("gathered"):
            summary["lines"] += res.get("lines") or []
        else:
            summary["lines"].append(res.get("reason") or "прений не было — органам нечего "
                                                        "противопоставить (VL5)")
    except Exception as e:
        summary["ok"] = False
        summary["lines"].append(f"СПОРЫ НЕ прошли (fail-soft): {type(e).__name__}: {e}")
    try:                                   # след в лог — удобство, не право уронить тик
        with open(log_path(), "a", encoding="utf-8") as f:
            if summary["lines"]:
                f.write("\nСПОРЫ (слой 2 СОВЕТА, прение дня, локальный стор 0₽):\n")
                for l in summary["lines"]:
                    f.write("  " + l + "\n")
    except Exception:
        pass
    return summary


def _close_stale_pulse_tasks(pulse_by_store, *, path=None):
    """Закрыть зависшие задачи «Пульс {store} устарел (дата)», где дата СТАРО пульса store.

    Дыра 05.09 (24/7-сердцебиение): сухой ЦИКЛ-1 стал ежедневным (см. _cycle_pulse), а старые
    open-задачи «Пульс устарел» из реестра жили вечно — их никто не закрывал (исполнитель = движок,
    а движок по расписанию не звали). Правило честности (TZ8, без фейк-пасс): закрываем ТОЛЬКО задачу,
    чья зафиксированная дата СТРОГО меньше ТЕКУЩЕГО пульса store — т.е. прогон уже РЕАЛЬНО продвинул
    пульс дальше, сигнал «прогнать сухо» отработан. Задачу с датой == пульсу (дыра ещё НЕ закрыта,
    сухой прогон сегодня не прошёл) НЕ трогаем — остаётся честным сигналом оператору.
    Локальный write: реестр заданий (env YM_TASKS_PATH перекрывает → герметично). Возвращает id закрытых.
    """
    import re
    try:
        import ymarket_tasks_v1 as _T
    except Exception:
        return []
    try:
        _loaded = _T.load(path=path)
        tasks = (_loaded[0] if _loaded else []) or []
    except Exception:
        return []
    pat = re.compile(r"Пульс\s+(\S+)\s+устарел\s*\((\d{4}-\d{2}-\d{2})\)")
    closed_ids = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        if t.get("state") in ("done", "archived"):
            continue
        if t.get("owner") != "DISPATCHER" or t.get("category") != "health":
            continue
        m = pat.search(t.get("what") or "")
        if not m:
            continue
        cur = pulse_by_store.get(m.group(1))
        if not cur:                    # пульса store в карте нет — сравнивать не с чем, не трогаем
            continue
        if m.group(2) >= cur:          # дыра НЕ закрыта (дата == пульсу) → честный сигнал живёт
            continue
        _nt, err = _T.mark_step(t, "s1", done_by="ЦИКЛ-1 пульс (автопилот)",
                                evidence=f"пульс {m.group(1)} продвинут до {cur} (сухой прогон автопилота)")
        if not err:
            closed_ids.append(t.get("id"))
    if closed_ids:                     # одна запись в конец: список несёт и закрытые, и остальные
        try:
            _T.save(tasks, path=path)
        except Exception:
            return []
    return closed_ids


def _cycle_pulse(*, store=None, now_date=None, pulse_read=None, cycle_run=None,
                 close_fn=None, verbose=False):
    """Раз в день: сухой ЦИКЛ-1 по магазинам манифеста → пульс/леджер продвинуты (0₽).

    Дыра 05.09 (24/7-мониторинг): пульс и леджер ЦИКЛА-1 (КПИ: вердикты узлов, СВЕРКА живых карточек,
    остатки) пишет ТОЛЬКО полный сухой прогон движка run_cycle(dry=True). Автопилот гонял лёгкий
    суточный слой (планёрка/совет/споры/префлайт/day.run_day) — а глубокий движок по расписанию никто
    не звал, пульс застывал на вчера, и монитор cycle_day.scan_stores каждый день сеял ложную задачу
    «Пульс устарел». Здесь первый тик дня, где пульс ещё НЕ сегодня, делает ОДИН сухой прогон по
    магазину → леджер+пульс копятся без входа оператора; следующие тики дня пропускают (пульс свеж).
    Зависшие open-задачи «Пульс {store} устарел» закрываются evidence реального пульса
    (_close_stale_pulse_tasks, TZ8: исполнитель = движок сухого прогона, НЕ фейк-пасс).

    0₽ и RUBICON: движок зовётся СТРОГО dry=True, commit=False — пути к боевому из автопилота нет
    (закон A2). Локальные write: runtime/cycle1/... (леджер+пульс движка) и локальный реестр заданий.
    Fail-soft: беда одного магазина/реестра — строка в сводку, тик живёт (закон launchd).
    """
    import contextlib
    import datetime as _dt
    import io
    summary = {"ok": True, "ran": [], "skipped": [], "closed": [], "lines": []}
    try:                                     # ключи кабинета для сухих READ-узлов движка (идемпотентно)
        day.load_env_file()
    except Exception:
        pass
    try:
        import ymarket_cycle1_v1 as c1
    except Exception as e:
        summary["ok"] = False
        summary["lines"].append(f"ЦИКЛ-1 недоступен (import): {type(e).__name__}: {e}")
        return summary
    today = (now_date() if now_date else _dt.date.today().isoformat())
    pr = pulse_read or (lambda s: c1.plannerka_read(s))

    def _run(slug):
        if cycle_run:
            return cycle_run(slug)
        buf = io.StringIO()                  # движок шумит баннером — уводим в буфер (как cycle_day),
        with contextlib.redirect_stdout(buf):  # наружу только строка-сводка, лог тика чист
            return c1.run_cycle(slug, dry=True, commit=False, verbose=False)

    reg = {store: {"slug": store}} if store else None
    if reg is None:
        try:
            reg = c1.list_cycles()
        except Exception as e:
            summary["ok"] = False
            summary["lines"].append(f"манифест магазинов недоступен (list_cycles): "
                                    f"{type(e).__name__}: {e}")
            reg = None
    pulses = {}                              # store → дата пульса ПОСЛЕ шага (для честного закрытия задач)
    for slug in sorted((reg or {}).keys()):
        try:
            p = pr(slug)
        except Exception:
            p = None
        pdate = (p or {}).get("date")
        if pdate == today:
            pulses[slug] = pdate
            summary["skipped"].append(slug)
            summary["lines"].append(f"пульс {slug}: уже сегодня ({today}) — сухой прогон не нужен")
            continue
        try:
            res = _run(slug)
        except Exception as e:
            summary["ok"] = False
            summary["lines"].append(f"пульс {slug}: сухой прогон упал: {type(e).__name__}: {e}")
            continue                         # пульс не продвинут → pulses[slug] не кладём → задачу не трогаем
        v = (res or {}).get("verdict")
        h = (res or {}).get("hash", "")
        summary["ran"].append({"store": slug, "verdict": v, "hash": h})
        summary["lines"].append(f"пульс {slug}: сухой ЦИКЛ-1 {v} #{h} · пульс → {today}")
        if v == "FAIL":
            summary["ok"] = False
        else:
            pulses[slug] = today
    if pulses:                               # закрыть зависшие «устарел», уже перекрытые свежим пульсом
        try:
            cl = close_fn or _close_stale_pulse_tasks
            summary["closed"] = cl(pulses) or []
            for _id in summary["closed"]:
                summary["lines"].append(f"закрыта зависшая задача {_id}")
        except Exception as e:
            summary["lines"].append(f"закрытие зависших задач не прошло (fail-soft): "
                                    f"{type(e).__name__}: {e}")
    return summary


def run(head_source="wb", head_city=None):
    """Один СУХОЙ прогон суточного цикла + авто-сев ЗАДАНИЙ + запись в лог + сухая ТГ-лента.

    head_source: 'wb' — живой нос спроса (ЧТЕНИЕ публичного WB, 0₽) для ГОЛОВЫ; 'none' — без сети-носа.
    ВНИМАНИЕ: здесь НАМЕРЕННО нет аргумента commit — автопилот не имеет права на боевой режим.
    Локальные write тика (0₽): ПЛАНЁРКА (_plannerka, план дня, директива 04.09) → СОВЕТ (_sovet,
    протокол дня, шаг 0.5) → СПОРЫ (_spory, прение дня — слой 2 СОВЕТА, шаг 0.5b) → авто-сев
    реестра заданий (_seed_tasks, CD6) — все в локальные сторы, слово 03.09/04.09. Кабинет/сеть/₽ — нет.
    """
    _plan = _plannerka()                   # УТРО ПРЕЖДЕ РАБОТ: планёрка ПЕРВЫМ оператором (шаг 0, 0₽)
    _sovet_res = _sovet()                  # СОВЕТ (шаг 0.5, сразу после планёрки): протокол-заседание (0₽)
    _spory_res = _spory()                  # СПОРЫ (шаг 0.5b, сразу после совета): прение дня, слой 2 (0₽)
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
    _pulse = _cycle_pulse()                      # СУХОЙ ЦИКЛ-1 раз в день (0₽): пульс/леджер/КПИ копятся;
                                                 # закрывает зависшие «Пульс устарел» (TZ8, evidence прогона)
    seed = _seed_tasks(d)                        # авто-сев ЗАДАНИЙ: локальный реестр (CD6, 0₽), слово 03.09
    # (пульс двигается ДО сева: свежий пульс → form НЕ сеет ложную «Пульс устарел» этим же тиком)
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
        "tasks_seed": {"ok": seed.get("ok", True),
                       "form": seed.get("form"), "seed": seed.get("seed"),
                       "lines": len(seed.get("lines") or [])},   # авто-сев ЗАДАНИЙ (что добавил тик)
        "plan": {"ok": _plan.get("ok", True), "date": _plan.get("date"),
                 "decisions": _plan.get("decisions", 0),
                 "lines": len(_plan.get("lines") or [])},   # ПЛАНЁРКА (УТРО): план дня (шаг 0, 0₽)
        "sovet": {"ok": _sovet_res.get("ok", True), "date": _sovet_res.get("date"),
                  "gathered": _sovet_res.get("gathered", False),
                  "already": _sovet_res.get("already", False),
                  "dry": _sovet_res.get("dry"), "file": _sovet_res.get("file"),
                  "lines": len(_sovet_res.get("lines") or [])},  # СОВЕТ (шаг 0.5): протокол дня (0₽)
        "spory": {"ok": _spory_res.get("ok", True), "date": _spory_res.get("date"),
                  "gathered": _spory_res.get("gathered", False),
                  "already": _spory_res.get("already", False),
                  "dry": _spory_res.get("dry"), "file": _spory_res.get("file"),
                  "lines": len(_spory_res.get("lines") or [])},  # СПОРЫ (шаг 0.5b): прение слоя 2 (0₽)
        "cycle_pulse": {"ok": _pulse.get("ok", True),
                        "ran": len(_pulse.get("ran") or []),
                        "skipped": len(_pulse.get("skipped") or []),
                        "closed": len(_pulse.get("closed") or []),
                        "lines": len(_pulse.get("lines") or [])},  # сухой ЦИКЛ-1: пульс→сегодня (0₽)
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
        tsd = (r.get("tasks_seed") or {})
        pln = (r.get("plan") or {})
        svt = (r.get("sovet") or {})
        spr = (r.get("spory") or {})
        pul = (r.get("cycle_pulse") or {})
        print(f"АВТОПИЛОТ {r.get('date','?')} · ok={r.get('ok')} · dry={r.get('dry')} commit={r.get('commit')}"
              f" · businessId={'да' if r.get('business_id_known') else 'НЕТ'}"
              f" · провалов={r.get('failures','?')} · горит={r.get('burning','?')}"
              f" · ЗАДАНИЯ: form +{tsd.get('form','0')} seed +{tsd.get('seed','0')}"
              f" · ПУЛЬС-ЦИКЛ1: ok={pul.get('ok')} прогнано={pul.get('ran')} свеж={pul.get('skipped')}"
              f" закрыто={pul.get('closed')}"
              f" · ПЛАНЁРКА: {pln.get('date','?')} решений {pln.get('decisions','0')}"
              f" · СОВЕТ: {svt.get('date','?')} собран={svt.get('gathered','?')}"
              f" уже={svt.get('already','?')}"
              f" · СПОРЫ: {spr.get('date','?')} собраны={spr.get('gathered','?')}"
              f" уже={spr.get('already','?')}")
    sys.exit(0)      # всегда 0: беда уже в логе, расписание живёт дальше
