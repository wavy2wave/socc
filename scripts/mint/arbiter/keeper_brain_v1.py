#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
МОЗГ БИБЛИОТЕКАРЯ (keeper_brain_v1) — AGI-слой над ХРАНИТЕЛЕМ ДАННЫХ (keeper_v1).

Оператор (wavy, 2026-09-10): «сделай библиотеку ахуеть какого левела ++ АГИ уровень,
сотвори немыслимое». Ответ: библиотека не просто ОТВЕЧАЕТ — она ДУМАЕТ:
свободные вопросы по-русски → факты с перекрёстной проверкой; ставит диагноз
здоровью системы; ищет расхождения между полками (целостность); помнит эволюцию
(записанные ходы → накопленное знание и готовые рецепты). 0₽, чистый read.

Плоскости (чистые функции над живыми сторами через родных читателей keeper_v1):
  health()     — ЗДОРОВЬЕ: балл 0..100, свежесть полок, дрейфы, разрывы, действия.
  integrity()  — ЦЕЛОСТНОСТЬ: перекрёстные сверки полок (матрица↔goods↔магазины↔залив↔процессы).
  evolution()  — ЭВОЛЮЦИЯ: записанные ходы → знание категорий, скорость, РЕЦЕПТЫ
                 (как повторить ход одной командой) — система лучше ВСЕГДА.
  ask(q)       — ВОПРОС: свободная русская фраза → намерение → факты из живых сторов
                 → связанный ответ + честные разрывы (KP5: отвечает всегда).
  report()     — ЛИЦО: синтез-брифинг оператору (что есть / здорово / утекает / что дальше).

Законы (наследуем KP1-KP6 keeper_v1; добавляем KB):
  KB1 мозг чист: 0 записей, 0 сети (те же гейты, что ХРАНИТЕЛЬ; экспорт — только явный --out).
  KB2 честность: полка пуста/бита → «нет» + причина; классификация не выдумывает (KP4).
  KB3 перекрёстность: цифры ТОЛЬКО из живых сторов через родных читателей keeper_v1
      (env-перекрытия уважаем: песочницы/тесты работают без касания канона).
  KB4 эволюция не врёт: знание/скорость/рецепты считаются ТОЛЬКО из записанных ходов
      (шов register_cycle1/register_pour уже гарантирует all-PASS — FAIL ходом не стал).
  KB5 ответ всегда: нет сигнала в вопросе → честный пульс + подсказка, не тишина.

Использование (0₽, сухо):
  python3 keeper_brain_v1.py                        # ЛИЦО (синтез-брифинг)
  python3 keeper_brain_v1.py здоровье               # диагноз
  python3 keeper_brain_v1.py целостность            # перекрёстные сверки
  python3 keeper_brain_v1.py эволюция               # накопленное знание + рецепты
  python3 keeper_brain_v1.py вопрос "сколько коробок в магазине film?"
  python3 keeper_brain_v1.py "какие ходы были 8 сентября?"   # свободная фраза → ask
  python3 keeper_brain_v1.py все                     # полный тур (здоровье+целостность+эволюция+лицо)
"""
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "keeper.brain.v1"
_CREATED = "2026-09-10"

# Слова явного входа в мозг — ЕДИНСТВЕННЫЙ источник маршрутизации (home.py берёт отсюда).
# Каждое слово обязано быть обработано cmd(): иначе молчаливый тупик (проводник шлёт → cmd не знает).
BRAIN_KEYS = (
    "мозг", "brain",
    "вопрос", "спроси", "ask", "q",
    "здоровье", "health", "диагноз",
    "целостность", "integrity",
    "эволюция", "evolution", "навыки", "skills", "уроки",
    "сводка", "report", "синтез", "брифинг", "лицо",
    "тур", "tour", "все", "всё", "пульс", "pulse",
)

# ── Магазины из вопроса: латинские слова — ТОЛЬКО целиком (film ≠ filming);
#    русские алиасы — СТЕМА + окончания (скотч → «скотча», «скотчем»);
#    гомографы («лента новостей» — не про скотч-полку) не считаются магазином (KB2).
_STORE_SLUGS = ("atlas-express-film", "atlas-express-tape")
_LATIN_STORE_WORDS = {"film": "atlas-express-film", "tape": "atlas-express-tape",
                      "vpp": "atlas-express-film"}
_RU_STEM_TO_SLUG = {
    "фильм": "atlas-express-film",
    "плёнк": "atlas-express-film",
    "пленк": "atlas-express-film",
    "пузырьк": "atlas-express-film",
    "пузырчат": "atlas-express-film",
    "скотч": "atlas-express-tape",
    "лент": "atlas-express-tape",
}
# (стема, недопустимые соседи) — слово-двойник вне товарного контекста → НЕ магазин
_HOMOGRAPH_BLOCK = (("лент", ("новост",)),)
_OZON_ALIASES = ("ozon", "озон", "озоне", "оzon-express", "ozon-express")
_RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


# ──────────────────────────────────────────────────────────────────────────
# Живой снимок (перекрёстность KB3): один проход родных читателей keeper_v1
# ──────────────────────────────────────────────────────────────────────────
def _snap():
    import keeper_v1 as K
    out = {"shelves": {}}
    for name, fn in K._READERS.items():  # noqa: SLF001 — реюз родных читателей (KP3)
        ok, path, doc, why = fn()
        out["shelves"][name] = dict(ok=ok, path=path, doc=doc, why=why)
    out["stores"] = K.stores_now()
    hs, _hnote = K.hods()
    out["hods"] = hs
    return out


def _mtime_age(path):
    try:
        mt = datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc)
        return (datetime.now(timezone.utc) - mt).total_seconds() / 86400.0
    except Exception:  # noqa: BLE001
        return None


def _age_label(days):
    if days is None:
        return "неизвестно"
    if days < 1:
        return f"свежее ({days * 24:.0f} ч)"
    if days <= 2:
        return f"{days:.0f} дн"
    return f"СТАРО {days:.0f} дн"


# ──────────────────────────────────────────────────────────────────────────
# Общие помощники для матрицы (сверка «строка ↔ карточка goods», KP2-честно)
# ──────────────────────────────────────────────────────────────────────────
def _good_index(goods):
    by_off, by_art = {}, {}
    for g in goods.values():
        if g.get("offerId"):
            by_off.setdefault(str(g["offerId"]), g)
        if g.get("article"):
            by_art.setdefault(str(g["article"]), g)
    return by_off, by_art


def _pass_of(g):
    return bool(g and (g.get("last_verified") or {}).get("verdict") == "PASS")


def _uncovered_note(uncovered):
    if not uncovered:
        return "все покрыты витринной матрицей"
    legacy = [u for u in uncovered if str(u).startswith("ARB-")]
    if len(legacy) == len(uncovered):
        return (f"{len(uncovered)} карточек ARB-* — прошлое поколение серии, заменены ARB2-* "
                "09.09 (карантин цен) — в леджере, вне матрицы; кандидаты на архив")
    return f"{len(uncovered)} карточек вне витринной матрицы"


def _matrix_gaps(goods, rows):
    """(витрина_без_pass, строки_без_карточки, карточки_вне_матрицы, сводка_покрытия)"""
    by_off, by_art = _good_index(goods)
    vitrine_no_pass, rows_orphan = [], []
    covered_goods = set()
    for rid, r in rows.items():
        g = by_off.get(r.get("offer_id")) or by_art.get(str(r.get("article")))
        if g:
            covered_goods.add(g.get("offerId") or str(g.get("article")))
        else:
            rows_orphan.append(rid)
        if r.get("status") == "на-витрине" and not _pass_of(g):
            vitrine_no_pass.append(rid)
    uncovered = [g.get("offerId") or str(g.get("article"))
                 for g in goods.values()
                 if (g.get("offerId") or str(g.get("article"))) not in covered_goods]
    return vitrine_no_pass, rows_orphan, uncovered


# ──────────────────────────────────────────────────────────────────────────
# Плоскость ЗДОРОВЬЕ
# ──────────────────────────────────────────────────────────────────────────
def health():
    """Диагноз системы: балл 0..100, свежесть полок, дрейфы/разрывы, действия."""
    S = _snap()
    shelves = []
    for name in ("ym-goods", "ym-matrix", "ym-stores", "ozon-matrix", "ozon-pour",
                 "ozon-tape", "process"):
        s = S["shelves"].get(name, {})
        age = _mtime_age(s.get("path")) if s.get("ok") else None
        shelves.append(dict(name=name, ok=s.get("ok", False), n=None, why=s.get("why", ""),
                            age=age, fresh=(age is not None and age <= 2)))
    # счётчики для наглядности
    sh = S["shelves"]
    gd = (sh.get("ym-goods") or {}).get("doc") or {}
    goods = gd.get("goods", {}) if sh.get("ym-goods", {}).get("ok") else {}
    md = (sh.get("ym-matrix") or {}).get("doc") or {}
    rows = md.get("rows", {}) if sh.get("ym-matrix", {}).get("ok") else {}
    pd = (sh.get("ozon-pour") or {}).get("doc") or {}
    pour = pd if isinstance(pd, dict) else {}

    vit_no_pass, rows_orphan, uncovered = _matrix_gaps(goods, rows)
    stores = S["stores"]
    store_slugs = {s["slug"] for s in stores if s["kind"] == "ym"}
    goods_slugs = {g.get("store_slug") for g in goods.values()}
    slug_miss = sorted(goods_slugs - store_slugs)

    pour_selling = sum(1 for v in pour.values() if isinstance(v, dict) and v.get("shelf") == "Продаётся")
    pour_hidden = sum(1 for v in pour.values()
                      if isinstance(v, dict) and "скрыт" in str(v.get("shelf", "")))
    photo_gap = sum(1 for g in goods.values() if (g.get("n_photos") or 0) < 1)
    runs = S["hods"]

    # дрейфы (диагноз)
    drift, gaps = [], []
    if vit_no_pass:
        drift.append(f"матрица: {len(vit_no_pass)} строк «на-витрине» без свежей PASS-сверки")
    if rows_orphan:
        drift.append(f"матрица: {len(rows_orphan)} строк БЕЗ карточки в goods-леджере")
    if uncovered:
        drift.append("goods: " + _uncovered_note(uncovered))
    if slug_miss:
        drift.append(f"goods: store_slug {slug_miss} нет в манифесте магазинов")
    if photo_gap:
        drift.append(f"goods: {photo_gap} карточек без фото (n_photos=0)")
    if pour_hidden:
        drift.append(f"залив ОЗОН: {pour_hidden}/{len(pour)} карточек «скрыта» (спят), "
                     f"продаётся только {pour_selling}")
    stale = [s["name"] for s in shelves if s["ok"] and not s["fresh"]]
    dead = [s["name"] for s in shelves if not s["ok"]]
    alive = len(shelves) - len(dead)
    if stale:
        drift.append("полки давно не обновлялись: " + ", ".join(stale))
    if dead:
        drift.append("полки НЕ читаются (" + ", ".join(dead) + ") — система без них неполна")
    if not runs:
        gaps.append("процессы: записанных ходов ещё нет — следующий живой PASS ЦИКЛ-1 станет первым")
    if alive == 0:
        gaps.append("система не читается: ни одной живой полки — проверь пути/env (keeper --полки)")

    # балл (честная механика: штрафы за дрейфы; legacy ARB-* прошлого поколения — мягко)
    score = 100
    score -= min(30, 3 * len(vit_no_pass))
    score -= min(15, 3 * len(rows_orphan))
    legacy_un = sum(1 for u in uncovered if str(u).startswith("ARB-"))
    real_un = len(uncovered) - legacy_un
    score -= min(15, 2 * real_un)
    score -= min(6, legacy_un) if legacy_un else 0
    score -= min(10, 5 * len(slug_miss))
    score -= min(10, 2 * photo_gap)
    score -= min(15, 5 * len(stale))
    score -= min(45, 7 * len(dead)) if dead else 0
    # KB2-честность: ни одна полка не читается → система фактически слепа, балл не выше 10
    if alive == 0:
        score = min(score, 10)
    score = max(0, min(100, score))

    # действия (read-рекомендации, НЕ команды на запись)
    actions = []
    if vit_no_pass:
        actions.append(f"досверка витрины: {len(vit_no_pass)} строк без PASS — прогнать ЦИКЛ-1 dry "
                       "и дать PASS (механика _sync_matrix; живьё — по слову оператора)")
    if pour_hidden:
        actions.append(f"залив спит ({pour_hidden} скрыты): решить сток/цены — по слову оператора")
    if not runs:
        actions.append("записать ретро-ход залива: python3 process_artifact_v1.py --register-pour 2026-09-08 --commit")
    if dead:
        actions.append("полки не читаются (" + ", ".join(dead) + ") — проверить пути/env (см. keeper --полки)")

    return dict(schema="keeper.brain.v1.health", score=score, shelves=shelves,
                drift=drift, gaps=gaps, actions=actions,
                snapshot=dict(goods=len(goods), matrix=len(rows), stores=len(store_slugs),
                              runs=len(runs), pour=len(pour)))


def render_health(h):
    bar = _bar(h["score"])
    lines = [
        "ЗДОРОВЬЕ СИСТЕМЫ — диагноз библиотекаря",
        f"  балл: {h['score']:>3}/100  {bar}",
        "",
    ]
    lines.append("  полки:")
    for s in h["shelves"]:
        mark = "✔" if s["ok"] else "✖"
        age = _age_label(s["age"]) if s["ok"] else f"причина: {s['why']}"
        lines.append(f"    {mark} {s['name']:<10} {age}")
    if h["drift"]:
        lines.append("")
        lines.append("  дрейфы:")
        for d in h["drift"]:
            lines.append(f"    ○ {d}")
    if h["gaps"]:
        lines.append("")
        lines.append("  разрывы:")
        for g in h["gaps"]:
            lines.append(f"    ▲ {g}")
    if h["actions"]:
        lines.append("")
        lines.append("  что дальше (совет):")
        for a in h["actions"]:
            lines.append(f"    → {a}")
    else:
        lines.append("")
        lines.append("  что дальше: всё сверено, система здорова. Следующий ход — по твоему слову.")
    lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────
# Плоскость ЦЕЛОСТНОСТЬ (перекрёстные сверки полок)
# ──────────────────────────────────────────────────────────────────────────
def integrity():
    """Сверки между полками. Каждая → {name, ok, n, detail}. Всё из живых сторов."""
    S = _snap()
    sh = S["shelves"]
    checks = []

    goods = (sh.get("ym-goods") or {}).get("doc") or {}
    goods = goods.get("goods", {}) if sh.get("ym-goods", {}).get("ok") else {}
    rows = (sh.get("ym-matrix") or {}).get("doc") or {}
    rows = rows.get("rows", {}) if sh.get("ym-matrix", {}).get("ok") else {}
    vit_no_pass, rows_orphan, uncovered = _matrix_gaps(goods, rows)
    stores = S["stores"]
    ym_stores = [s for s in stores if s["kind"] == "ym"]
    store_slugs = {s["slug"] for s in ym_stores}
    goods_slugs = {g.get("store_slug") for g in goods.values()}

    # 1. матрица ↔ goods (сироты)
    checks.append(dict(name="матрица ↔ goods", ok=not rows_orphan, n=len(rows_orphan),
                       detail=("каждая строка матрицы имеет карточку в goods-леджере"
                               if not rows_orphan else f"сирот: {rows_orphan}")))
    # 2. goods ↔ матрица (непокрытые)
    checks.append(dict(name="goods ↔ матрица", ok=not uncovered, n=len(uncovered),
                       detail=_uncovered_note(uncovered)))
    # 3. витрина ↔ PASS
    checks.append(dict(name="витрина ↔ PASS", ok=not vit_no_pass, n=len(vit_no_pass),
                       detail=("все «на-витрине» сверены PASS"
                               if not vit_no_pass else f"без PASS: {len(vit_no_pass)} строк")))
    # 4. stores ↔ матрица (у каждого магазина есть витрина)
    no_vit = [s["slug"] for s in ym_stores
              if not any(r.get("category") == (s["profile"].get("builder_slug") or "")
                         for r in rows.values())]
    checks.append(dict(name="stores ↔ матрица", ok=not no_vit, n=len(no_vit),
                       detail=("у каждого магазина есть строки витрины"
                               if not no_vit else f"без витрины: {no_vit}")))
    # 5. goods ↔ stores (все карточки чьи-то)
    checks.append(dict(name="goods ↔ stores", ok=not (goods_slugs - store_slugs),
                       n=len(goods_slugs - store_slugs),
                       detail=("каждая карточка приписана магазину манифеста"
                               if not (goods_slugs - store_slugs)
                               else f"вне манифеста: {sorted(goods_slugs - store_slugs)}")))
    # 6. залив ↔ матрица ОЗОН (покрытие файла живыми product_id)
    pour_ok = sh.get("ozon-pour", {}).get("ok")
    if not pour_ok:
        checks.append(dict(name="залив ОЗОН ↔ product_id", ok=False, n=None,
                           detail="полка залива не читается — сверка невозможна"))
    else:
        pd = (sh.get("ozon-pour") or {}).get("doc") or {}
        pour = pd if isinstance(pd, dict) else {}
        with_pid = sum(1 for v in pour.values() if isinstance(v, dict) and v.get("product_id"))
        checks.append(dict(name="залив ОЗОН ↔ product_id", ok=with_pid == len(pour),
                           n=len(pour) - with_pid,
                           detail=(f"{with_pid}/{len(pour)} карточек журнала получили product_id"
                                   if len(pour) else "журнал пуст")))
    # 7. скотч-полка ↔ матрица ЯМ (карточки партии vs строки витрины скотча)
    tape_ok = sh.get("ozon-tape", {}).get("ok")
    if not tape_ok:
        checks.append(dict(name="скотч-канон ↔ витрина ЯМ", ok=False, n=None,
                           detail="полка скотч-канона не читается — сверка невозможна"))
    else:
        td = (sh.get("ozon-tape") or {}).get("doc") or {}
        tape_cards = int((td.get("stats") or {}).get("cards", 0))
        tape_matrix = sum(1 for r in rows.values() if r.get("category") == "klejkaya-lenta")
        checks.append(dict(name="скотч-канон ↔ витрина ЯМ", ok=tape_cards == tape_matrix,
                           n=abs(tape_cards - tape_matrix),
                           detail=f"канон {tape_cards} карточек ↔ матрица {tape_matrix} строк"))
    # 8. процессы ↔ читаемые отчёты (.md)
    runs = S["hods"]
    md_missing = []
    from process_artifact_v1 import report_path
    for r in runs:
        if not report_path(r).exists():
            md_missing.append(r.get("id"))
    checks.append(dict(name="процессы ↔ .md-отчёты", ok=not md_missing, n=len(md_missing),
                       detail=("каждый ход имеет читаемый отчёт runs/"
                               if not md_missing else f"без отчёта: {md_missing}")))
    # 9. фото
    photo_gap = sum(1 for g in goods.values() if (g.get("n_photos") or 0) < 1)
    checks.append(dict(name="фото-покрытие goods", ok=photo_gap == 0, n=photo_gap,
                       detail=(f"{len(goods) - photo_gap}/{len(goods)} карточек с фото"
                               if len(goods) else "нет goods")))

    failed = [c for c in checks if not c["ok"]]
    verdict = "ВСЁ СВЕРЕНО" if not failed else f"{len(failed)} расхождений — смотри ниже"
    return dict(schema="keeper.brain.v1.integrity", checks=checks, verdict=verdict,
                n_checks=len(checks), n_fail=len(failed))


def render_integrity(it):
    lines = ["ЦЕЛОСТНОСТЬ — перекрёстные сверки полок (0₽, живые сторы)", ""]
    for c in it["checks"]:
        mark = "✔" if c["ok"] else "✖"
        lines.append(f"  {mark} {c['name']:<22} · {c['detail']}"
                     + (f"  [остаток: {c['n']}]" if c["n"] else ""))
    lines.append("")
    lines.append(f"  вердикт: {it['verdict']}")
    lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────
# Плоскость ЭВОЛЮЦИЯ (записанные ходы → знание, скорость, рецепты; KB4)
# ──────────────────────────────────────────────────────────────────────────
def evolution():
    """Накопленное из записанных ходов: знание категорий, скорость, РЕЦЕПТЫ повтора.
    KB4: в расчёт идут ТОЛЬКО все-PASS ходы (шов); не-PASS записи честно помечаем skipped."""
    S = _snap()
    all_runs = S["hods"]
    runs = [r for r in all_runs if (r.get("result") or {}).get("verdict") == "PASS"]
    skipped = len(all_runs) - len(runs)
    by_kind, by_market, by_state = Counter(), Counter(), Counter()
    recipes, learned = [], []
    speed = []
    for r in runs:
        kind = r.get("kind") or "?"
        by_kind[kind] += 1
        by_market[r.get("market") or "?"] += 1
        by_state[r.get("state") or "?"] += 1
        recipes.append(_recipe(r))
        res = r.get("result") or {}
        nms = res.get("node_ms")
        if isinstance(nms, dict) and nms:
            tot = sum(float(v) for v in nms.values())
            speed.append(dict(id=r.get("id"), kind=kind, total_ms=tot,
                              n=len(nms), avg_ms=tot / len(nms)))
        k = (r.get("knowledge") or {}).get("category") or {}
        if k:
            oz = k.get("ozon") or {}
            learned.append(dict(run=r.get("id"), slug=k.get("slug"), name=k.get("name"),
                                dci=oz.get("dci"), tid=oz.get("tid"),
                                warehouse=oz.get("warehouse"),
                                top_sizes=(k.get("top_sizes") or [])[:3],
                                price_band=k.get("price_band") or {},
                                pour=k.get("pour") or {}))
    return dict(schema="keeper.brain.v1.evolution", n=len(runs), skipped=skipped,
                by_kind=dict(by_kind),
                by_market=dict(by_market), by_state=dict(by_state),
                recipes=recipes, learned=learned, speed=speed,
                invariant="шов: ходом становится ТОЛЬКО все-PASS прогон (FAIL не фиксируется)")


def _recipe(r):
    kind, market = r.get("kind"), r.get("market")
    slug = (r.get("params") or {}).get("store") or ""
    date = r.get("date") or ""
    base = "python3 scripts/mint/arbiter/"
    if kind == "cycle1" and market == "ym":
        cmd = f"{base}ymarket_cycle1_v1.py --store {slug} --commit"
    elif kind == "pour" and market == "ozon":
        cmd = f"{base}process_artifact_v1.py --register-pour {date} --commit"
    else:
        cmd = f"process_artifact_v1.py --show {r.get('id')}"
    return dict(id=r.get("id"), kind=kind, market=market, what=r.get("what", ""),
                date=date, rerun=cmd, state=r.get("state"), decision=(r.get("decision") or {}).get("word"))


def render_evolution(ev):
    lines = ["ЭВОЛЮЦИЯ — записанные ходы делают систему лучше ВСЕГДА (0₽, из process_library)", ""]
    lines.append(f"  записанных ходов: {ev['n']} · {_dict_str(ev['by_kind'])} · "
                 f"market {_dict_str(ev['by_market'])}")
    lines.append(f"  инвариант: {ev['invariant']}")
    if ev.get("skipped"):
        lines.append(f"  ⚠ отброшено как НЕ все-PASS: {ev['skipped']} записей (не считаем их знанием)")
    if ev["speed"]:
        lines.append("")
        lines.append("  скорость:")
        for s in ev["speed"]:
            lines.append(f"    ⏱ {s['id']} [{s['kind']}] {s['n']} узлов · {s['total_ms']:.0f} мс · "
                         f"{s['avg_ms']:.0f} мс/узел")
    if ev["learned"]:
        lines.append("")
        lines.append("  знание категорий (переиспользуемо):")
        for k in ev["learned"]:
            sz = ", ".join(f"{s}x" for s, _c in k["top_sizes"])
            pb = k.get("price_band") or {}
            band = f"{pb.get('min')}–{pb.get('max')}₽" if pb else "—"
            lines.append(f"    {k['name']}: dci {k['dci']} · tid {k['tid']} · {k['warehouse'] or '—'}")
            lines.append(f"      размеры {sz or '—'} · цена {band} · залито {k['pour'].get('cards', '—')}")
    if ev["recipes"]:
        lines.append("")
        lines.append("  рецепты (готовые ходы = навыки системы):")
        for r in ev["recipes"]:
            lines.append(f"    • {r['id']} [{r['kind']}] {r['date']} · {r['what'][:56]}")
            lines.append(f"      повторить: {r['rerun']}")
            if r["decision"]:
                lines.append(f"      слово: {r['decision'][:60]}")
    lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────
# Плоскость ВОПРОС (свободная русская фраза → факты; KB5 отвечает всегда)
# ──────────────────────────────────────────────────────────────────────────
# Намерения: (regex, ключ). Регистрируем намерения, собираем факты, синтезируем.
_INTENT_HEALTH = (re.compile(r"здоров|состояни|диагноз|как дела|плохо|хорошо|балл"), "health")
_INTENT_INTEGRITY = (re.compile(r"целостн|расхожд|сверк|дыр|гармон|проверь полк"), "integrity")
_INTENT_EVOL = (re.compile(r"эволюц|навык|скилл|урок|знани|узна|быстре|лучше|опыт|рецепт"), "evolution")
_INTENT_TYPES = (re.compile(r"короб|рулон|лент|скотч|плёнк|пленк|тип|размер|класс|виды|сорт"), "types")
_INTENT_VITR = (re.compile(r"витрин|published|выставлен|на витрине"), "vitrina")
_INTENT_PHOTO = (re.compile(r"фото|картин|изображен|без фото"), "photo")
_INTENT_PASS = (re.compile(r"сверк|pass|проверен|верифицирован"), "pass")
_INTENT_STORES = (re.compile(r"магазин|товар|карточк|артикул|каталог|ассортимент|ям\b|яндекс"), "stores")
_INTENT_HODS = (re.compile(r"ход|цикл|прогон|залив|артефакт|P-[0-9a-f]"), "hods")
_INTENT_REPORT = (re.compile(r"свод|итог|отчёт|резюме|обзор|картина|брифинг|всё"), "report")
_INTENT_PULSE = (re.compile(r"пульс|библиотек|полки|что есть|инвентарь"), "pulse")

_ALL_INTENTS = (_INTENT_HEALTH, _INTENT_INTEGRITY, _INTENT_EVOL, _INTENT_TYPES, _INTENT_VITR,
                _INTENT_PHOTO, _INTENT_PASS, _INTENT_STORES, _INTENT_HODS, _INTENT_REPORT,
                _INTENT_PULSE)


def _blocked_homograph(ql):
    """Гомограф-ловушка: «лента НОВОСТЕЙ» — не наша скотч/упаковка (KB2: не гадать).
    Срабатывает, когда триггерный ствол («лент») стоит перед чужим словом-блокером."""
    return any(
        re.search(rf"{re.escape(hstem)}[а-яё]*[ \t]+{re.escape(bl)}[а-яё]*", ql)
        for hstem, blocks in _HOMOGRAPH_BLOCK for bl in blocks
    )


def _store_of(q):
    """Магазин из вопроса (slug) или None. Слова-точки (латиница) — только целиком
    (film НЕ матчит «filming»); русские алиасы — стема + русские окончания
    («скотча» → скотч); гомографы («лента новостей») — НЕ магазин (KB2)."""
    ql = q.lower()
    for slug in _STORE_SLUGS:
        if re.search(rf"(?<![a-z]){re.escape(slug)}(?![a-z])", ql):
            return slug
    for word, slug in _LATIN_STORE_WORDS.items():
        if re.search(rf"(?<![a-zа-яё0-9]){re.escape(word)}(?![a-zа-яё0-9])", ql):
            return slug
    for stem, slug in _RU_STEM_TO_SLUG.items():
        if not re.search(rf"(?<![a-zа-яё0-9]){re.escape(stem)}[а-яё]*(?![a-zа-яё0-9])", ql):
            continue
        if stem == "лент" and _blocked_homograph(ql):
            continue
        return slug
    return None


def _ozon_of(q):
    return any(a in q.lower() for a in _OZON_ALIASES)


def _kind_of(q):
    if re.search(r"залив|pour", q.lower()):
        return "pour"
    if re.search(r"цикл|cycle", q.lower()):
        return "cycle1"
    return None


def _date_of(q):
    ql = q.lower()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", q)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"\b(\d{1,2})[/.](\d{1,2})\b", q)
    if m:
        return f"2026-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    # «8 сентября», «8 сентября 2026», «сентября 8»
    mon_pat = "|".join(_RU_MONTHS)
    m = re.search(rf"\b(\d{{1,2}})\s+({mon_pat})(?:\s+(\d{{4}}))?", ql)
    if m:
        return f"{m.group(3) or '2026'}-{_RU_MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}"
    m = re.search(rf"\b({mon_pat})\s+(\d{{1,2}})\b", ql)
    if m:
        return f"2026-{_RU_MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    if "вчера" in ql:
        from datetime import timedelta
        return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    return None


def ask(question):
    """Свободный вопрос → (answer_text, facts). KB5: нет сигнала → честный пульс."""
    q = (question or "").strip()
    if not q:
        return _suggest(), []
    hits = [key for rx, key in _ALL_INTENTS if rx.search(q.lower())]
    facts, seen = [], set()
    store = _store_of(q)
    oz = _ozon_of(q)
    kind = _kind_of(q)
    date = _date_of(q)

    # Гомограф-ловушка без магазина («лента новостей»): это НЕ наш скотч — не гадаем
    # (KB2), показываем подсказку (KB5), а не фейк-ответ про типы.
    if not store and _blocked_homograph(q.lower()):
        return _suggest(), []

    S = _snap()
    sh = S["shelves"]

    def add(f):
        k = f.get("k")
        if k not in seen:
            seen.add(k)
            facts.append(f)

    # ── факты по намерениям ──
    for key in hits:
        if key == "stores" or key == "vitrina" or key == "pass":
            goods = {}
            if sh.get("ym-goods", {}).get("ok"):
                goods = (sh["ym-goods"]["doc"] or {}).get("goods", {})
            rows = {}
            if sh.get("ym-matrix", {}).get("ok"):
                rows = (sh["ym-matrix"]["doc"] or {}).get("rows", {})
            if store:
                gs = [g for g in goods.values() if g.get("store_slug") == store]
                passed = sum(1 for g in gs if _pass_of(g))
                bs = next((s["profile"].get("builder_slug") for s in S["stores"]
                           if s["kind"] == "ym" and s["slug"] == store), "")
                on_v = sum(1 for r in rows.values()
                           if r.get("category") == bs and r.get("status") == "на-витрине")
                if key == "stores":
                    prof = next((s["profile"] for s in S["stores"]
                                 if s["kind"] == "ym" and s["slug"] == store), {}) or {}
                    bid = prof.get("business_id")
                    biz = f"бизнес {_fmt(bid)}" if bid else "бизнес = мамы (наследование)"
                    add(dict(k="stores", text=f"магазин {store}: {len(gs)} карточек · "
                                              f"на-витрине {on_v} · PASS {passed} · {biz}"))
                if key == "vitrina":
                    add(dict(k="vitrina", text=f"витрина {store}: {on_v} строк на-витрине"
                                               f" (сверено PASS {passed})"))
                if key == "pass":
                    add(dict(k="pass", text=f"сверка {store}: PASS {passed}/{len(gs)}"
                                            f" ({len(gs) - passed} ждут)"))
            elif oz:
                # OZON — не ЯМ: матрица донора + живой залив (KB2: не подменять предмет ответа)
                od = sh.get("ozon-matrix") or {}
                o_total = "?"
                if od.get("ok"):
                    odo = od["doc"] or {}
                    o_total = odo.get("total_rows") or (odo.get("summary") or {}).get("total_rows") or "?"
                pd2 = (sh.get("ozon-pour") or {}).get("doc") or {}
                pour = pd2 if isinstance(pd2, dict) else {}
                if key == "stores":
                    add(dict(k="stores", text=f"OZON: матрица донора {o_total} строк · "
                                              f"залив {len(pour)} карточек журнала"))
                if key == "vitrina":
                    selling = sum(1 for v in pour.values()
                                  if isinstance(v, dict) and v.get("shelf") == "Продаётся")
                    add(dict(k="vitrina", text=f"витрина OZON: продаётся {selling}/{len(pour)} "
                                               f"карточек залива (остальные спят)"))
                if key == "pass":
                    with_pid = sum(1 for v in pour.values()
                                   if isinstance(v, dict) and v.get("product_id"))
                    add(dict(k="pass", text=f"сверка OZON: {with_pid}/{len(pour)} карточек залива "
                                            f"с product_id (заявка ушла на ОЗОН)"))
            else:
                vit_no_pass, rows_orphan, uncovered = _matrix_gaps(goods, rows)
                on_vit = sum(1 for r in rows.values() if r.get("status") == "на-витрине")
                if key == "stores":
                    tot = len(goods)
                    ym = [s for s in S["stores"] if s["kind"] == "ym"]
                    per = " · ".join(f"{s['slug']}: {s['articles']}" for s in ym)
                    add(dict(k="stores", text=f"ЯМ всего: {tot} карточек · витрина {on_vit} строк · "
                                              f"магазинов {len(ym)} · {per}"))
                if key == "vitrina":
                    add(dict(k="vitrina", text=f"витрина ЯМ: {on_vit} строк «на-витрине» из "
                                               f"{len(rows)} · без PASS {len(vit_no_pass)}"))
                if key == "pass":
                    add(dict(k="pass", text=f"сверка: PASS у {on_vit - len(vit_no_pass)}/{on_vit} "
                                            f"витринных строк ({len(vit_no_pass)} ждут)"))
        elif key == "types":
            od = sh.get("ozon-matrix") or {}
            o_total = "?"
            if od.get("ok"):
                odo = od["doc"] or {}
                o_total = odo.get("total_rows") or (odo.get("summary") or {}).get("total_rows") or "?"
            if oz:
                # явный «озон» перебивает алиас ЯМ-магазина (KB3: не подменять рынок)
                items = _types_ozon()
                add(dict(k="types", text=f"матрица ОЗОН ({o_total} строк): " + _fmt_types(items)))
            elif store:
                items, note = _types_store(store)
                add(dict(k="types", text=f"типы {store}: " + (note or _fmt_types(items))))
            else:
                items = _types_ozon()
                line = "типы по матрице ОЗОН: " + _fmt_types(items) + " ·"
                line += " в ЯМ-магазинах коробок нет (рулоны/ленты), коробки/конверты — только в доноре ОЗОН"
                add(dict(k="types", text=line))
        elif key == "photo":
            goods = {}
            if sh.get("ym-goods", {}).get("ok"):
                goods = (sh["ym-goods"]["doc"] or {}).get("goods", {})
            gap = sum(1 for g in goods.values() if (g.get("n_photos") or 0) < 1)
            add(dict(k="photo", text=f"фото ЯМ: {len(goods) - gap}/{len(goods)} карточек с фото"
                                     f" ({gap} без)"))
            orecs = []
            if sh.get("ozon-matrix", {}).get("ok"):
                doc = sh["ozon-matrix"]["doc"] or {}
                orecs = doc.get("records") or [] if isinstance(doc.get("records"), list) else []
            if orecs:
                wimg = sum(1 for r in orecs if r.get("images"))
                add(dict(k="photo", text=f"фото ОЗОН: {wimg}/{len(orecs)} строк матрицы с картинкой"))
        elif key == "hods":
            runs = S["hods"]
            sel = runs
            if kind:
                sel = [r for r in sel if r.get("kind") == kind]
            if date:
                sel = [r for r in sel if r.get("date") == date]
            pid = re.search(r"P-[0-9a-fA-F]{4,}", q)
            if pid:
                from process_artifact_v1 import show as pa_show
                tok = pid.group(0)
                rec = pa_show(tok)
                if not rec:  # допускаем частичный id (оператор печатает начало)
                    rec = next((r for r in runs
                                if str(r.get("id", "")).upper().startswith(tok.upper())), None)
                if rec:
                    body = "\n".join(_pa_report(rec))
                    add(dict(k="hods", text=f"ход {rec.get('id')}:\n{body}"))
                else:
                    add(dict(k="hods", text=f"хода {tok} нет в библиотеке"))
            elif sel:
                top = " · ".join(f"{r.get('id')} [{r.get('kind')}] {r.get('date')} {r.get('what','')[:40]}"
                                 for r in sel[:6])
                add(dict(k="hods", text=f"ходы ({len(sel)}): {top}"))
            else:
                add(dict(k="hods", text=f"ходов по срезу нет (kind={kind or '—'} date={date or '—'}) — "
                                        "шов готов: следующий живой PASS ЦИКЛ-1 станет ходом"))
        elif key == "health":
            h = health()
            add(dict(k="health", text=f"здоровье: балл {h['score']}/100 · дрейфов {len(h['drift'])} · "
                                      f"советов {len(h['actions'])}"))
        elif key == "integrity":
            it = integrity()
            add(dict(k="integrity", text=f"целостность: {it['n_checks']} сверок · {it['verdict']}"))
        elif key == "evolution":
            ev = evolution()
            add(dict(k="evolution", text=f"эволюция: ходов {ev['n']} · "
                                         f"рецептов {len(ev['recipes'])} · "
                                         f"знаний {len(ev['learned'])}"))
        elif key == "report":
            add(dict(k="report", text="синтез ниже", full=True))
        elif key == "pulse":
            add(dict(k="pulse", text="библиотека системы жива: см. полки/счётчики ниже", full=True))

    # ── нет сильного сигнала → синтез-пульс (KB5) ──
    if not facts:
        return _suggest(), []

    body = "\n".join(f"  • {f['text']}" for f in facts if not f.get("full"))
    if any(f.get("full") for f in facts) or len(facts) >= 4:
        body += "\n\n" + "\n".join("  " + l for l in report().splitlines())
    head = f"ВОПРОС «{q}»"
    src = _sources_used(hits)
    return f"{head}\n{body}\n\n  {src}\n", facts


def _sources_used(hits):
    return "0₽ · из живых сторов · перекрёстно: " + ", ".join(sorted(set(hits))) if hits else "0₽"


def _suggest():
    return ("БИБЛИОТЕКАРЬ: не понял вопрос — вот что я умею (0₽, живые сторы)\n"
            "  • «сколько товаров в магазине film?» / «…tape?» / «…на озоне?»\n"
            "  • «сколько коробок / рулонов / лент / плёнки?» (матрица ОЗОН + магазины ЯМ)\n"
            "  • «какие ходы были?» / «ход P-f7ea1dc1» / «что за залив 8 сентября?»\n"
            "  • «как здоровье системы?» / «есть расхождения?» / «что узнали за ходы?»\n"
            "  • «покажи сводку» / «пульс» / «всё» (полный тур)\n"
            "  или: здоровье · целостность · эволюция · сводка\n\n")


# ──────────────────────────────────────────────────────────────────────────
# Плоскость ЛИЦО (синтез-брифинг оператору)
# ──────────────────────────────────────────────────────────────────────────
def report():
    """Инвестор-брифинг: что есть / здорово / утекает / что дальше. Из живых сторов."""
    S = _snap()
    sh = S["shelves"]
    h = health()

    gd = (sh.get("ym-goods") or {}).get("doc") or {}
    goods = gd.get("goods", {}) if sh.get("ym-goods", {}).get("ok") else {}
    md = (sh.get("ym-matrix") or {}).get("doc") or {}
    rows = md.get("rows", {}) if sh.get("ym-matrix", {}).get("ok") else {}
    odo = (sh.get("ozon-matrix") or {}).get("doc") or {}
    osum = odo.get("summary") or {}
    o_total = odo.get("total_rows") or osum.get("total_rows") or "?"
    pd = (sh.get("ozon-pour") or {}).get("doc") or {}
    pour = pd if isinstance(pd, dict) else {}
    td = (sh.get("ozon-tape") or {}).get("doc") or {}
    tstat = td.get("stats") or {}
    runs = S["hods"]
    stores = S["stores"]
    ym = [s for s in stores if s["kind"] == "ym"]
    ym_arts = sum(s["articles"] for s in ym)
    ym_vit = sum(s["on_vitrine"] for s in ym)
    vit_no_pass, rows_orphan, uncovered = _matrix_gaps(goods, rows)
    pour_selling = sum(1 for v in pour.values() if isinstance(v, dict) and v.get("shelf") == "Продаётся")

    L = []
    L.append("ЛИЦО БИБЛИОТЕКАРЯ — сводка по системе (0₽, читано из живых сторов)")
    L.append("")
    L.append(f"  библиотека есть — ЯМ {ym_arts} карточек (витрина {ym_vit}) · ОЗОН "
             f"{o_total} в матрице файла · "
             f"залив {len(pour)} · скотч-полка {tstat.get('groups', 0)} групп")
    L.append(f"  магазины: " + " · ".join(f"{s['slug']} ({s['articles']})" for s in ym))
    L.append(f"  записанные ходы: {len(runs)} — " + (
        " · ".join(f"{r.get('id')} [{r.get('kind')}]" for r in runs[:4]) if runs else "ещё нет"))
    L.append("")
    L.append("  здоровье: " + ("хорошее" if h["score"] >= 80 else "требует внимания")
             + f" — балл {h['score']}/100")
    if vit_no_pass:
        L.append(f"  ⚠ утекает: {len(vit_no_pass)} витринных строк без свежей PASS-сверки")
    if rows_orphan:
        L.append(f"  ⚠ утекает: {len(rows_orphan)} строк матрицы без карточки goods")
    if uncovered:
        legacy = [u for u in uncovered if str(u).startswith("ARB-")]
        if len(legacy) == len(uncovered):
            L.append(f"  ◌ знание: {len(uncovered)} карточек ARB-* — прошлое поколение серии "
                     f"(заменены ARB2-* 09.09), в матрице их больше нет — кандидаты на архив")
        else:
            L.append(f"  ⚠ утекает: {len(uncovered)} карточек вне витринной матрицы")
    if pour:
        L.append(f"  ⚠ спит: {len(pour) - pour_selling} карточек залива не на витрине "
                 f"(продаётся {pour_selling})")
    L.append("")
    L.append("  что дальше:")
    for a in h["actions"] or ["все полки сверены — следующий ход по твоему слову"]:
        L.append(f"    → {a}")
    L.append("")
    L.append("  перекрёстно: циферки согласованы между полками (целостность — "
             f"{integrity()['n_fail']} расхождений); эволюция помнит ходы (рецепты готовы).")
    return "\n".join(L)


def _fmt(v):
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    return v or "?"


def _dict_str(d):
    return " · ".join(f"{k}={v}" for k, v in sorted(d.items()))


def _bar(score):
    n = round(score / 10)
    return "█" * n + "░" * (10 - n)


def _pa_report(rec):
    from process_artifact_v1 import render_report
    return render_report(rec)


def _types_store(slug):
    import keeper_v1 as K
    items, note = K.types_for(slug)
    return items, note


def _types_ozon():
    import keeper_v1 as K
    items, note = K.types_for("ozon")
    return items if not note else []


def _fmt_types(items):
    if not items:
        return "не распознан"
    return " · ".join(f"{it['klass']} {it['n']}" for it in items)


# ──────────────────────────────────────────────────────────────────────────
# Тур (всё сразу) + CLI
# ──────────────────────────────────────────────────────────────────────────
def tour():
    parts = [render_health(health()), render_integrity(integrity()),
             render_evolution(evolution()), report()]
    return "\n".join(parts)


def cmd(argv):
    """Главная плоскость мозга: (text, rc). Без аргументов → ЛИЦО (брифинг).
    Каждое слово BRAIN_KEYS обязано быть обработано здесь (проводник шлёт сюда)."""
    argv = argv or []
    if not argv:
        return report(), 0
    tok = argv[0].lstrip("-").lower()
    if tok in ("вопрос", "спроси", "ask", "q"):
        q = " ".join(argv[1:])
        text, _f = ask(q)
        return text, 0
    if tok in ("мозг", "brain"):
        return tour(), 0
    if tok in ("здоровье", "health", "диагноз"):
        return render_health(health()), 0
    if tok in ("целостность", "integrity"):
        return render_integrity(integrity()), 0
    if tok in ("эволюция", "evolution", "навыки", "skills", "уроки"):
        return render_evolution(evolution()), 0
    if tok in ("сводка", "report", "синтез", "брифинг", "лицо"):
        return report(), 0
    if tok in ("все", "всё", "тур", "tour"):
        return tour(), 0
    if tok in ("пульс", "pulse"):
        return ask("что есть")[0], 0
    # свободная фраза → вопрос
    text, _f = ask(" ".join(argv))
    return text, 0


def main():
    text, rc = cmd(sys.argv[1:])
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    sys.exit(rc)


if __name__ == "__main__":
    main()
