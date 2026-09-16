#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ДОМ — единый read-хаб всей системы (socc_cli/home.py).

Один вход во все органы: ЯМ-ЦИКЛ · OZON · ENTITY SUBSTRATE · ANNA · КЕРНЕЛЬ · MIGRATION.
Дом = «открыть/смотреть»: дашборд + статус-карточки + глубокие входы. 0₽, ничего
не пишет на диск, сеть не зовёт. Живые действия (--commit/создать/цикл) — только
по слову оператора за RUBICON; здесь их нет.

Входы (единый словарь всей системы):
    socc home            — на терминале: меню ДОМА; в пайпе: дашборд одним экраном
    socc ym  [дело|планёрка|задания|штаб|день|kpi|артефакты|авто|мозг|все]
    socc ym <витрина>    — экран магазина (меню на терминале / текст в пайпе)
    socc ozon [сводка]   — read-карточка OZON-менеджера (сухо)
    socc substrate       — ENTITY SUBSTRATE: направление · домены · поверхность
    socc anna            — ANNA: направление · дашборд · вход
    socc kernel          — КЕРНЕЛЬ: route authority (lawful_next)
    socc home --help     — справка

На живом терминале (tty+stdin, без --text/--plain) home/ym/витрина открывают
ИНТЕРАКТИВНЫЙ дом-меню (socc_cli.dom): стрелки/цифры/Enter, магазины → активные
задания, живые экраны с пульсом/леджером/таймером автопилота. В пайпе/StringIO —
прежний один-экран текст (HH2/CC8).

Тождественный алиас: `CYCLE` (без аргументов) == `socc home`;
`CYCLE YM <под>…` == `socc ym <под>…`. Один движок, два входа.

Канон цвета/типографики — socc_cli.style; out-aware (CC8): ANSI только на живом
tty, в пайпе/StringIO — plain. Функции чистые, с fail-soft чтением сторов.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

try:
    from socc_cli import style as S
except Exception:  # pragma: no cover
    S = None

SOCC_ROOT = Path(__file__).resolve().parent.parent
REPORTS = SOCC_ROOT / "MEMORY_WAVE/reports/mint/arbiter"
KERNEL_ROUTE = SOCC_ROOT / "core/socc/route_authority/CURRENT_ROUTE_AUTHORITY.json"

# ── типографика (out-aware, токены канона) ────────────────────────────────────
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _tty(out):
    f = getattr(out, "isatty", None)
    if f is None:
        return False
    try:
        return bool(f())
    except Exception:
        return False


def _col(out, token, text):
    if not (S and _tty(out)):
        return text
    code = getattr(S, token, "")
    return f"{code}{text}{S.R}" if code else text


def _now_msk():
    try:
        return _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=3)))
    except Exception:
        return _dt.datetime.now()


def _width(out):
    if _tty(out):
        try:
            return max(64, min(112, os.get_terminal_size().columns - 2))
        except Exception:
            pass
    return 78


def _band(out, title, right="", sub=""):
    """Шапка-лента двойной линией; в пайпе — plain текст без рамок."""
    w = _width(out)
    inner = max(10, w - 4)
    ttl = title.ljust(inner - len(right) - 1)[: inner - len(right) - 1]
    body = f" {ttl} {right}"
    top = "╔" + "═" * (w - 2) + "╗"
    mid = "║" + body.ljust(w - 2) + "║"
    bot = "╚" + "═" * (w - 2) + "╝"
    lines = [top, mid]
    if sub:
        lines.append("║" + (f" {sub}").ljust(w - 2) + "║")
    lines.append(bot)
    return "\n".join(_col(out, "CY", ln) if _tty(out) else ln for ln in lines)


def _seal(out, label=""):
    """Тонкий разделитель с подписью."""
    w = _width(out)
    if label:
        pad = max(2, w - len(label) - 6)
        return _col(out, "DIM", f"── {label} " + "─" * pad)
    return _col(out, "DIM", "─" * w)


def _j(path, default=None):
    """JSON fail-soft."""
    try:
        p = Path(path)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _last_jsonl_date(path):
    """Дата последней строки JSONL-журнала (fail-soft)."""
    try:
        p = Path(path)
        if not p.exists():
            return None
        for ln in reversed(p.read_text(encoding="utf-8").splitlines()):
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if isinstance(d, dict) and d.get("date"):
                return str(d["date"])[:10]
            if isinstance(d, dict) and d.get("ts"):
                return str(d["ts"])[:10]
        return None
    except Exception:
        return None


def _snip(text, n=64):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


# ── зонды органов (fail-soft, честно: файла нет → честная строка) ──────────────
def _probe_kernel():
    """КЕРНЕЛЬ: route authority."""
    d = _j(KERNEL_ROUTE)
    lawful = None
    if isinstance(d, dict):
        lawful = d.get("lawful_next") or d.get("real_next") or d.get("current_lawful_next")
    if not lawful:
        return ("off", "маршрут не прочитан (route authority пуст)", "socc step")
    return ("live", f"lawful_next · {lawful}", "socc step · socc observe")


def _probe_ym():
    """ЯМ-ЦИКЛ: журнал дня + матрица + автопилот."""
    day = _last_jsonl_date(REPORTS / "ymarket_day_journal.jsonl")
    mat = _j(REPORTS / "ymarket_product_matrix.json")
    counts = {}
    if isinstance(mat, dict):
        rows = mat.get("rows", mat)
        if isinstance(rows, dict):
            for r in rows.values():
                if isinstance(r, dict):
                    counts[r.get("status")] = counts.get(r.get("status"), 0) + 1
    bits = []
    if day:
        bits.append(f"журнал {day}")
    if counts:
        bits.append("собран {0}".format(counts.get("собран", 0)))
    if (REPORTS / "ymarket_autopilot.log").exists():
        bits.append("автопилот есть")
    if not bits:
        return ("off", "сторы пусты — цикла ещё не было", "socc ym дело")
    return ("live", " · ".join(bits), "socc ym  [дело|планёрка|штаб|мозг]")


def _probe_ozon():
    """OZON-менеджер: последний тик."""
    t = _j(REPORTS / "ozon_manager_tick.json")
    if not isinstance(t, dict):
        return ("off", "тиков нет — OZON-цикл ещё не шёл", "socc ozon")
    at = str(t.get("at", "?"))[:10]
    action = t.get("action", "?")
    note = _snip(t.get("result", {}).get("note", "") if isinstance(t.get("result"), dict) else "", 52)
    return ("live", f"tick {at} · {action}" + (f" · {note}" if note else ""), "socc ozon")


def _probe_substrate():
    """ENTITY SUBSTRATE: принятое направление + домены."""
    d = _j(SOCC_ROOT / "SYSTEM/ENTITY_SUBSTRATE/ACTIVE_ENTITY_SUBSTRATE_DIRECTION.json")
    stage = None
    when = None
    if isinstance(d, dict):
        stage = d.get("current_stage") or d.get("stage")
        when = str(d.get("created_at_utc", ""))[:10]
    ndom = 0
    dom_dir = SOCC_ROOT / "entity_substrate/domains"
    try:
        ndom = len([p for p in dom_dir.glob("*.json")]) if dom_dir.is_dir() else 0
    except Exception:
        ndom = 0
    if stage:
        st = stage.replace("entity_substrate_", "").replace("_", " ")
        bits = f"stage · {st}"
        if when:
            bits += f" · {when}"
        if ndom:
            bits += f" · доменов {ndom}"
        return ("live", bits, "socc substrate")
    return ("off", "направления нет в ACTIVE", "socc substrate")


def _probe_anna():
    """ANNA: принятое направление MVP + L2-кандидат + дашборд."""
    acc = _j(SOCC_ROOT / "SYSTEM/ANNA_MVP/ACTIVE_ACCEPTED_ANNA_MVP_DIRECTION.json")
    step = None
    when = None
    if isinstance(acc, dict):
        step = acc.get("authorizes_next") or acc.get("step")
        when = str(acc.get("created_at_utc", ""))[:10]
    dash = (SOCC_ROOT / "scripts/anna_dashboard_v1.py").exists()
    l2 = (SOCC_ROOT / "SYSTEM/ANNA_MVP/ANNA_L2_REAL_BOOKING_DIRECTION_V1.md").exists()
    bits = []
    if when:
        bits.append(f"направление MVP принято {when}")
    if step:
        bits.append(_snip(step, 34))
    if l2:
        bits.append("L2-запись кандидат")
    if dash:
        bits.append("дашборд 8790")
    if not bits:
        return ("off", "принятого направления нет", "socc anna")
    return ("idle", " · ".join(bits), "socc anna")


def _probe_migration():
    """MIGRATION · LINE_MIGRATOR: состояние переноски кода → GitHub/VPS.

    Чистое локальное чтение (сеть не зовёт, ничего не пишет, HH6): remote origin
    в .git/config (URL без токена — закон M2) и .gitignore (закрывает ли .env).
    """
    cfg = SOCC_ROOT / ".git/config"
    giti = SOCC_ROOT / ".gitignore"
    try:
        cfg_txt = cfg.read_text(encoding="utf-8", errors="replace") if cfg.exists() else ""
        giti_txt = giti.read_text(encoding="utf-8", errors="replace") if giti.exists() else ""
    except Exception:
        cfg_txt = giti_txt = ""
    urls = re.findall(r"(?m)^\s*url\s*=\s*(\S+)\s*$", cfg_txt)
    url = urls[-1] if urls else None
    if not url:
        return ("off", "remote origin нет — переноска кода ещё не начата", "socc migrate")
    leak = re.search(r"(github_pat_|gh[pousr]_[A-Za-z0-9]{20,}|:\S+@)", url)
    env_guarded = bool(re.search(r"(?m)^\.env\s*$", giti_txt)) or "**/.env" in giti_txt
    if leak:
        return ("off", "⚠ ТОКЕН в remote URL — чистить срочно (M2)", "socc migrate")
    if not env_guarded:
        return ("idle", "репо есть, но .gitignore не закрывает .env", "socc migrate")
    return ("live", "репо socc на GitHub · URL чист · .env закрыт", "socc migrate")


# ── карточки органов ──────────────────────────────────────────────────────────
_ORGANS = [
    dict(key="kernel", icon="🧭", title="SOCC · КЕРНЕЛЬ", tag="само-постройка · route",
         desc="observe · boot · think · ticket · run — базовый контур",
         probe=_probe_kernel, open="socc kernel"),
    dict(key="ym", icon="🛍️", title="ЯМ-ЦИКЛ", tag="MINT · маркетплейс Экспресс",
         desc="13 ролей · магазины · ДЕЛО · ЗАДАНИЯ · автопилот · мозг",
         probe=_probe_ym, open="socc ym [дело|планёрка|штаб|мозг]"),
    dict(key="ozon", icon="🚚", title="OZON", tag="MINT · зеркало донора",
         desc="менеджер-паутина · контент-стратег · dry-партии",
         probe=_probe_ozon, open="socc ozon"),
    dict(key="substrate", icon="🧬", title="ENTITY SUBSTRATE", tag="COGNITION · карта",
         desc="направление · поверхность · домены · план и гейты",
         probe=_probe_substrate, open="socc substrate"),
    dict(key="anna", icon="🩺", title="ANNA", tag="CORE · личный операционный мозг",
         desc="направление MVP · L2 реальная запись · дашборд · вход",
         probe=_probe_anna, open="socc anna"),
    dict(key="migration", icon="🛰️", title="MIGRATION", tag="LINE_MIGRATOR · переноска → GitHub/VPS",
         desc="безопасная полная миграция кода · секреты · доступ · сеть · шаги с вердиктами",
         probe=_probe_migration, open="socc migrate"),
]

GR, CY, DIM, R = getattr(S, "GR", ""), getattr(S, "CY", ""), getattr(S, "DIM", ""), getattr(S, "R", "")

_STATE = {
    "live": (GR if S else None, "ЖИВО"),
    "idle": (CY if S else None, "ДЕРЖИТ"),
    "off": (DIM if S else None, "ТИХО"),
}


def _state_tag(out, state, label):
    col = {"live": GR, "idle": CY, "off": DIM}.get(state, DIM)
    return _col(out, col, f"● {label}")


def _card(out, org):
    """Одна статус-карточка органа (две колонки, честная сигнатура)."""
    try:
        state, note, hint = org["probe"]()
    except Exception as e:
        state, note, hint = "off", f"зонд упал: {e}", org["open"]
    w = _width(out)
    name = org["icon"] + " " + _col(out, "B", org["title"])
    tag = _col(out, "DIM", f"· {org['tag']}") if _tty(out) else f"· {org['tag']}"
    state_word = _STATE.get(state, ("", state.upper()))[1]
    st = _state_tag(out, state, state_word)
    left = f"  {name} {tag}"
    pad = max(1, w - len(_ansi_strip(left)) - len(_ansi_strip(st)) - 4)
    line1 = left + " " * pad + st
    desc = f"     {_col(out, 'DIM', org['desc'])}" if _tty(out) else f"     {org['desc']}"
    sig = f"     {_col(out, 'CY', note)}" if _tty(out) else f"     {note}"
    use = f"     ввод: {_col(out, 'B', hint)}" if _tty(out) else f"     ввод: {hint}"
    return "\n".join([line1, desc, sig, use])


def _ansi_strip(t):
    return _ANSI.sub("", t)


def home_text(out=None):
    """Весь ДОМ одним экраном: лента · органы-карточки · входы · правила."""
    out = out or sys.stdout
    L = []
    now = _now_msk()
    clock = now.strftime("%d.%m %H:%M MSK")
    L.append(_band(out, "SOCC · ДОМ", right=clock,
                   sub="канон-интерфейс всей системы — открыть/смотреть · 0₽ read"))
    L.append(_seal(out, "ОРГАНЫ"))
    for org in _ORGANS:
        L.append("")
        L.append(_card(out, org))
    L.append("")
    L.append(_seal(out, "ВХОДЫ"))
    entries = [
        ("socc home", "весь ДОМ (этот экран)"),
        ("socc ym [дело|планёрка|задания|штаб|день|kpi|артефакты|авто|мозг]", "ЯМ-ЦИКЛ глубоко"),
        ("socc ozon", "OZON-менеджер (read-сводка)"),
        ("socc библиотека", "ХРАНИТЕЛЬ+МОЗГ: полки · магазины · ходы · ЗДОРОВЬЕ · ЦЕЛОСТНОСТЬ · ЭВОЛЮЦИЯ · вопрос"),
        ("socc substrate", "ENTITY SUBSTRATE"),
        ("socc anna", "ANNA · дашборд · вход"),
        ("socc задания", "ЗАДАНИЯ — весь реестр систем (топливо ДОМА)"),
        ("socc migrate", "MIGRATION · LINE_MIGRATOR · переноска кода (GitHub/VPS)"),
        ("CYCLE = socc home · CYCLE YM = socc ym", "тождественный алиас"),
    ]
    for a, b in entries:
        cmd = _col(out, "B", "  " + a) if _tty(out) else "  " + a
        L.append(cmd + (f"  {_col(out, 'DIM', '— ' + b)}" if _tty(out) else f"  — {b}"))
    L.append("")
    L.append(_seal(out, "ПРАВИЛА"))
    L.append("  0₽ read · ничего не пишет · сеть не зовёт")
    L.append("  живые действия (--commit · создать · цикл-диспетч) — только по слову оператора (RUBICON)")
    return "\n".join(L)


# ── входы ──────────────────────────────────────────────────────────────────────
def _ym_usage(out):
    return ("ЯМ-ЦИКЛ · входы:\n"
            "  socc ym              — на терминале меню магазинов; в пайпе весь экран\n"
            "  socc ym <витрина>    — экран магазина (пульс · цикл · активные задания)\n"
            "  socc ym дело         — ДЕЛО одним блоком\n"
            "  socc ym планёрка     — магазины + ЗАДАНИЯ\n"
            "  socc ym план         — ПЛАН ДНЯ (утро): что берём и почему\n"
            "  socc ym совет        — СОВЕТ ДИРЕКТОРОВ (голоса органов · пропиздоны)\n"
            "  socc ym споры        — СПОРЫ ОРГАНОВ (позиции · прения, слой 2 СОВЕТА)\n"
            "  socc ym задания      — реестр заданий\n"
            "  socc ym штаб         — 13 ролей листом\n"
            "  socc ym день|kpi|артефакты|авто\n"
            "  socc ym мозг         — интерактивный МОЗГ (навигатор)")


_SUBCMDS = {"дело", "deal", "delo", "планёрка", "plannerka", "planerka",
            "план", "пландня", "утро", "plan", "dayplan", "совет", "sovet",
            "споры", "spory", "прения",
            "задания", "zadaniya", "tasks", "штаб", "shtab", "staff",
            "день", "den", "day", "kpi", "kpis", "артефакты", "artefakty",
            "artifacts", "авто", "avto", "autopilot", "мозг", "brain",
            "все", "вся", "full", "vse", "--help", "-h", "help", "--справка"}


def _strip_ansi_text(t):
    return _ANSI.sub("", t)


def _ym_face(out, sub, args):
    """Глубокий вход в ЯМ-ЦИКЛ: агрегирует готовые read-рендеры консоли в процессе."""
    # ленивый импорт arbiter-модулей (домашний дашборд их не тянет)
    sys.path.insert(0, str(SOCC_ROOT / "scripts/mint/arbiter"))
    try:
        import ymarket_console_v1 as console
    except Exception as e:
        return _col(out, "RE", f"ЯМ-консоль не импортировалась: {e}")
    try:
        import ymarket_cycle_day_v1 as cyc_day
    except Exception:
        cyc_day = None

    if sub in ("мозг", "brain"):
        try:
            import ymarket_brain_v1 as brain
            return brain._main(args) if hasattr(brain, "_main") else brain.main(args)
        except Exception as e:
            return _col(out, "RE", f"мозг не запустился: {e}")

    if sub in ("--help", "-h", "help", "--справка"):
        return _ym_usage(out)

    def _deal():
        try:
            return console.deal_text(out=out)
        except Exception as e:
            return f"ДЕЛО упало: {e}"

    def _stores():
        if cyc_day is None:
            return "ЦИКЛ-ДНЯ не импортировался — магазины не показаны."
        try:
            lines = cyc_day.plannerka_text()
        except Exception as e:
            return f"планёрка упала: {e}"
        if not _tty(out):
            lines = [_strip_ansi_text(l) for l in lines]
        out_lines = []
        for ln in lines:
            if ln.lstrip().startswith("ЗАДАНИЯ"):
                break
            out_lines.append(ln)
        return "\n".join(out_lines) if out_lines else "планёрка пуста."

    if sub in ("", "все", "вся", "full", "vse"):
        head = _band(out, "ЯМ-ЦИКЛ · консоль", right=_now_msk().strftime("%H:%M MSK"),
                     sub="read · 0₽ · ШТАБ · магазины · ДЕЛО · ЗАДАНИЯ")
        blocks = [head]
        for label, fn in (("ШТАБ", lambda: console.staff_summary(out=out)),
                          ("МАГАЗИНЫ", _stores), ("ДЕЛО", _deal)):
            try:
                blocks.append(_seal(out, label))
                blocks.append(fn())
            except Exception as e:
                blocks.append(f"{label} упало: {e}")
        return "\n".join(blocks)

    if sub in ("дело", "deal", "delo"):
        return _deal()
    if sub in ("планёрка", "plannerka", "planerka"):
        return _stores()
    if sub in ("задания", "zadaniya", "tasks"):
        try:
            return console.tasks_text(out=out)
        except Exception as e:
            return f"задания упали: {e}"
    if sub in ("штаб", "shtab", "staff"):
        try:
            return console.staff_summary(out=out)
        except Exception as e:
            return f"штаб упал: {e}"
    if sub in ("день", "den", "day"):
        return console.day_card(out=out)
    if sub in ("kpi", "kpis"):
        return console.kpi_text(out=out)
    if sub in ("артефакты", "artefakty", "artifacts"):
        return console.artifacts_text(out=out)
    if sub in ("авто", "avto", "autopilot"):
        return console.autopilot_tail(out=out)
    if sub in ("план", "пландня", "утро", "plan", "dayplan"):
        # ПЛАН ДНЯ (утро): читаем durable план планёрки (read 0₽). Если консоль ещё не
        # вшила block (в полёте) — честная деградация, не пустой экран.
        if not hasattr(console, "plan_day_text"):
            return ("ПЛАН ДНЯ ещё не вшит в консоль (plan_day_text) — "
                    "см. socc ym дело / планёрка")
        try:
            return console.plan_day_text(out=out)
        except Exception as e:
            return f"ПЛАН ДНЯ упало: {e}"
    if sub in ("совет", "sovet"):
        # СОВЕТ ДИРЕКТОРОВ (протокол даты): голоса органов из сторов + пропиздоны + зеркало
        # плана (read 0₽, VL7: совет сам заданий не создаёт). hasattr-guard как у плана.
        if not hasattr(console, "sovet_text"):
            return ("СОВЕТ ещё не вшит в консоль (sovet_text) — см. socc ym дело / планёрка")
        try:
            return console.sovet_text(out=out)
        except Exception as e:
            return f"СОВЕТ упало: {e}"
    if sub in ("споры", "spory", "прения"):
        # СПОРЫ ОРГАНОВ (слой 2 СОВЕТА): позиции органов + прения по данным даты.
        # read 0₽ · VL10: споры наружу не пишут и заданий не создают — только слово
        # оператору. hasattr-guard как у совета (новая грань, вшивается лениво).
        if not hasattr(console, "spory_text"):
            return ("СПОРЫ ещё не вшиты в консоль (spory_text) — см. socc ym дело / планёрка")
        try:
            return console.spory_text(out=out)
        except Exception as e:
            return f"СПОРЫ упало: {e}"
    return _ym_usage(out)


def _ozon_face(out, args):
    """OZON: read-карточка + честный сухой вход (без write)."""
    L = [_band(out, "OZON · менеджер", right=_now_msk().strftime("%H:%M MSK"),
               sub="read · 0₽ · зеркало донора → dry-партии")]
    L.append(_card(out, next(o for o in _ORGANS if o["key"] == "ozon")))
    L.append(_seal(out, "ВХОД"))
    L.append("  dry-сводка (0₽):  socc ozon    ·    живые партии — по слову оператора (RUBICON)")
    return "\n".join(L)


def _keeper_face(out, args):
    """ХРАНИТЕЛЬ + МОЗГ БИБЛИОТЕКАРЯ: системная библиотека одним лицом — 0₽ read.

    Проводник: слова мозга (мозг/вопрос/спроси/здоровье/целостность/эволюция/сводка/
    тур) → напрямую в keeper_brain_v1; неизвестная команда ХРАНИТЕЛЯ (rc=2) →
    свободная фраза для мозга (ask). Остальное — родной keeper_v1.
    """
    sys.path.insert(0, str(SOCC_ROOT / "scripts/mint/arbiter"))
    args = list(args)
    # слова явного входа в мозг — из ЕДИНСТВЕННОГО источника BRAIN_KEYS (не дублируем список;
    # каждое слово там обработано cmd(): «всё», «мозг», «лицо», «пульс» — тоже)
    try:
        import keeper_brain_v1 as brain
    except Exception as e:
        out.write(f"МОЗГ не импортировался: {e}\n")
        return 1
    if args and args[0].lstrip("-").lower() in brain.BRAIN_KEYS:
        try:
            text, rc = brain.cmd(args)
        except Exception as e:
            out.write(f"МОЗГ упал: {e}\n")
            return 1
        out.write(text if text.endswith("\n") else text + "\n")
        return rc
    try:
        import keeper_v1 as keeper
    except Exception as e:
        out.write(f"ХРАНИТЕЛЬ не импортировался: {e}\n")
        return 1
    try:
        text, rc = keeper.cmd(args)
    except Exception as e:
        out.write(f"ХРАНИТЕЛЬ упал: {e}\n")
        return 1
    if rc == 2 and args:
        # свободная фраза → мозг (KB5: библиотекарь отвечает всегда)
        try:
            import keeper_brain_v1 as brain
            text, rc = brain.cmd(args)
        except Exception:
            pass
    out.write(text if text.endswith("\n") else text + "\n")
    return rc


def _substrate_face(out, args):
    d = _j(SOCC_ROOT / "SYSTEM/ENTITY_SUBSTRATE/ACTIVE_ENTITY_SUBSTRATE_DIRECTION.json")
    acc = _j(SOCC_ROOT / "SYSTEM/ENTITY_SUBSTRATE/ACTIVE_ACCEPTED_ENTITY_SUBSTRATE_DIRECTION.json")
    dom_dir = SOCC_ROOT / "entity_substrate/domains"
    try:
        domains = sorted(p.stem for p in dom_dir.glob("*.json")) if dom_dir.is_dir() else []
    except Exception:
        domains = []
    L = [_band(out, "ENTITY SUBSTRATE", right=_now_msk().strftime("%H:%M MSK"),
               sub="карта сущностей · направление · домены · гейты")]
    L.append(_card(out, next(o for o in _ORGANS if o["key"] == "substrate")))
    L.append(_seal(out, "НАПРАВЛЕНИЕ"))
    if isinstance(acc, dict):
        step = acc.get("authorizes_next") or acc.get("step") or "?"
        when = str(acc.get("created_at_utc", ""))[:10]
        L.append(f"  принято {when} · авторует: {step}")
    if isinstance(d, dict):
        stage = (d.get("current_stage") or "?").replace("_", " ")
        L.append(f"  active: {stage}")
    else:
        L.append("  активного направления нет (ACTIVE файл не прочитан)")
    L.append(_seal(out, "ДОМЕНЫ"))
    if domains:
        L.append("  " + ", ".join(domains[:12]) + (" …" if len(domains) > 12 else ""))
    else:
        L.append("  доменов ещё нет")
    return "\n".join(L)


def _anna_face(out, args):
    acc = _j(SOCC_ROOT / "SYSTEM/ANNA_MVP/ACTIVE_ACCEPTED_ANNA_MVP_DIRECTION.json")
    dash = (SOCC_ROOT / "scripts/anna_dashboard_v1.py").exists()
    L = [_band(out, "ANNA", right=_now_msk().strftime("%H:%M MSK"),
               sub="личный операционный мозг · MVP → L2 реальная запись")]
    L.append(_card(out, next(o for o in _ORGANS if o["key"] == "anna")))
    L.append(_seal(out, "ВХОД"))
    if dash:
        L.append("  дашборд:   python3 scripts/anna_dashboard_v1.py   (127.0.0.1:8790)")
    L.append("  командный вход ANNA живёт своим CLI — открой мозг по слову оператора")
    return "\n".join(L)


def _kernel_face(out, args):
    d = _j(KERNEL_ROUTE)
    lawful = None
    if isinstance(d, dict):
        lawful = d.get("lawful_next") or d.get("real_next") or d.get("current_lawful_next")
    L = [_band(out, "SOCC · КЕРНЕЛЬ", right=_now_msk().strftime("%H:%M MSK"),
               sub="route authority · само-постройка")]
    L.append(_card(out, next(o for o in _ORGANS if o["key"] == "kernel")))
    L.append(_seal(out, "МАРШРУТ"))
    L.append(f"  lawful_next :: {lawful or 'UNKNOWN'}")
    L.append("  socc step | socc observe | socc run | socc think «…»")
    return "\n".join(L)


def _migrate_face(out, args):
    """MIGRATION · LINE_MIGRATOR: read-карточка переноски кода (локально, 0₽, без сети)."""
    L = [_band(out, "MIGRATION · LINE_MIGRATOR", right=_now_msk().strftime("%H:%M MSK"),
               sub="read · 0₽ · переноска кода → GitHub/VPS · безопасность")]
    L.append(_card(out, next(o for o in _ORGANS if o["key"] == "migration")))
    cfg = SOCC_ROOT / ".git/config"
    head = SOCC_ROOT / ".git/HEAD"
    giti = SOCC_ROOT / ".gitignore"
    url = branch = None
    env_guarded = False
    try:
        if cfg.exists():
            urls = re.findall(r"(?m)^\s*url\s*=\s*(\S+)\s*$",
                              cfg.read_text(encoding="utf-8", errors="replace"))
            url = urls[-1] if urls else None
        if head.exists():
            m = re.search(r"refs/heads/(\S+)", head.read_text(encoding="utf-8", errors="replace"))
            branch = m.group(1) if m else None
        if giti.exists():
            g = giti.read_text(encoding="utf-8", errors="replace")
            env_guarded = bool(re.search(r"(?m)^\.env\s*$", g)) or "**/.env" in g
    except Exception:
        pass
    L.append(_seal(out, "РЕПО"))
    if url:
        leak = bool(re.search(r"(github_pat_|gh[pousr]_[A-Za-z0-9]{20,}|:\S+@)", url))
        L.append(f"  remote origin · {url}")
        L.append(f"  ветка · {branch or '?'}   ·   токен в URL · {'ЕСТЬ ⚠' if leak else 'нет'}")
    else:
        L.append("  remote origin не найден — переноска кода ещё не начата")
    L.append(f"  .gitignore закрывает .env (M2) · {'да' if env_guarded else 'НЕТ ⚠'}")
    L.append(_seal(out, "ГОТОВНОСТЬ"))
    L.append("  LINE_MIGRATOR знает всю SOCC (органы · graphify · внутренняя вики) и отвечает")
    L.append("  на вопросы миграции: GitHub (репо/секреты/PAT) · VPS · перенос проекта целиком.")
    L.append("  Гейты: К4+ brain/Анна и VPS-деплой — по слову оператора (M6).")
    return "\n".join(L)


_HOME_HELP = """SOCC · ДОМ — единый read-хаб системы (0₽, ничего не пишет)

  На живом терминале входы открывают МЕНЮ (socc home · socc ym · socc ym <витрина>):
  выбор органа/магазина стрелками или цифрой · q — назад · живые экраны автообновлением.
  socc ym                  меню: сколько магазинов → витрина → АКТИВНЫЕ задания
  socc ym <витрина>        экран магазина (пульс · цикл сегодня · задания)
  socc home                меню ДОМА / в пайпе — дашборд органов
  socc ym  [дело|планёрка|задания|штаб|день|kpi|артефакты|авто|мозг]
  socc ozon                OZON-менеджер (read-сводка)
  socc библиотека          ХРАНИТЕЛЬ ДАННЫХ — системная библиотека (0₽ read)
                           полки · магазины [slug] · типы <slug> · ходы · ход PID · экспорт
                           МОЗГ БИБЛИОТЕКАРЯ: здоровье · целостность · эволюция · сводка ·
                           тур «всё» · вопрос «свободная фраза» (или прямо фразой)
  socc задания             ЗАДАНИЯ — весь реестр систем (топливо ДОМА, 0₽)
  socc substrate           ENTITY SUBSTRATE
  socc anna                ANNA · дашборд · вход
  socc kernel              КЕРНЕЛЬ · route authority
  socc migrate             MIGRATION · LINE_MIGRATOR (переноска кода → GitHub/VPS)
  --text/--plain           принудительно один-экран (в пайпе и так plain)

  CYCLE = socc home · CYCLE YM = socc ym  (тождественный алиас)
"""


def dispatch(argv=None, out=None, inp=None):
    """Диспечер входа ДОМА. argv — без имени программы/рынка. Возвращает exit-код.

    На живом терминале (tty+stdin+без --text/--plain) входы открывают ИНТЕРАКТИВНЫЙ
    дом-меню (socc_cli.dom): socc home → меню органов · socc ym → меню магазинов →
    экран витрины с живыми заданиями. В пайпе/StringIO/--text — прежний один-экран
    текст (CC8/HH2, ничего не ломаем).
    """
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    out = out or sys.stdout
    inp = inp or sys.stdin
    _FLAT = ("--text", "--plain", "--no-menu")
    force_flat = any(t in argv for t in _FLAT)
    argv = [t for t in argv if t not in _FLAT]
    help_tok = ("-h", "--help", "help", "--справка", "справка", "?")

    def _live():
        return (not force_flat) and _tty(out) and _tty(inp)

    def _dom():
        from socc_cli import dom  # интерактивный слой ДОМА (лениво)
        return dom

    def _help():
        out.write(_HOME_HELP)
        return 0

    def _rc0(rc):
        return 0 if rc in (0, -1) else rc

    if not argv:
        if _live():
            return _rc0(_dom().run_home(out, inp))
        out.write(home_text(out=out) + "\n")
        return 0
    first = argv[0].lower().strip()
    if first in help_tok:
        return _help()
    if len(argv) >= 2 and argv[1].lower().strip() in help_tok:
        return _help()
    cmd = first
    rest = argv[1:]
    if cmd in ("home", "дом", "hub"):
        if _live():
            return _rc0(_dom().run_home(out, inp))
        out.write(home_text(out=out) + "\n")
        return 0
    if cmd in ("ym", "ям", "cycle-ym", "ymarket", "маркет"):
        if not rest:
            if _live():
                return _rc0(_dom().run_ym(out, inp))
            out.write(_ym_face(out, "", rest) + "\n")
            return 0
        sub0 = rest[0].lower().strip()
        if sub0 in _SUBCMDS:
            out.write(_ym_face(out, sub0, rest[1:]) + "\n")
            return 0
        # витрина по slug из манифеста: interactive → меню витрины; пайп → текст
        stores = _dom()._stores_map()
        if sub0 in stores:
            if _live():
                return _rc0(_dom().run_store(out, inp, sub0))
            out.write(_dom().store_screen_text(out, sub0) + "\n")
            return 0
        out.write(_ym_face(out, "", rest) + "\n")
        return 0
    if cmd in ("ozon", "озон"):
        out.write(_ozon_face(out, rest) + "\n")
        return 0
    if cmd in ("substrate", "sub", "субстрат", "entity-substrate"):
        out.write(_substrate_face(out, rest) + "\n")
        return 0
    if cmd in ("anna", "анна"):
        out.write(_anna_face(out, rest) + "\n")
        return 0
    if cmd in ("kernel", "ядро", "кернель", "k"):
        out.write(_kernel_face(out, rest) + "\n")
        return 0
    if cmd in ("migrate", "migration", "миграция", "line-migrator"):
        out.write(_migrate_face(out, rest) + "\n")
        return 0
    if cmd in ("задания", "zadaniya", "tasks"):
        # ЗАДАНИЯ · лицо ДОМА (топливо): tty → меню-реестр, пайп/--text → планёрка.
        from socc_cli import tasks as _tasks
        if _live():
            return _rc0(_tasks.run_tasks(out, inp))
        out.write(_tasks.tasks_text(out) + "\n")
        return 0
    if cmd in ("библиотека", "хранитель", "keeper", "lib", "биб", "хран"):
        # ХРАНИТЕЛЬ ДАННЫХ (библиотекарь): системная библиотека одним лицом, 0₽ read.
        return _keeper_face(out, rest)
    out.write(f"SOCC·ДОМ: неизвестный орган «{cmd}»\n\n" + _HOME_HELP)
    return 1


def main():
    return dispatch()


if __name__ == "__main__":
    sys.exit(dispatch())
