#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · КОРОБКИ · ЖИВОЙ ЗАЛИВ ЗАМОРОЖЕННОГО МАНИФЕСТА (RUBICON дан, дозы ≤100).

Льёт РОВНО те payload'ы, что сухо-прогнаны манифестом ozon_korobki_card_manifest_v1 (988 картон,
5 обязательных атрибутов 85/9048/8229/23536/22232 на каждом) — из файла .items.json, БЕЗ пересборки.
Это устраняет дрейф «сухой показал одно — живой ушёл другое»: живой орган ничего не достраивает.

Механика (дословно проверенная в ozon_film_zaliv_v1 / ozon_zaliv):
  1) TWIN-ГАРД: read_shelf по всем offer_id манифеста → уже-живущие в кабинете НЕ пересоздаём.
     Чтение упало/нет ключа → честный отказ (залив вслепую запрещён).
  2) ДОЗЫ ≤100: create_product(chunk, dry=not commit, commit=commit).
     Живой ответ {'status':'sent'} → response.result.task_id → опрос import_info до не-pending.
     Успех item = status=='imported' AND product_id>0 AND errors==[] (200≠успех).
  3) ВИТРИНА (закон OZ3: DONE=на витрине): verify_shelf по импортированным → «Продаётся»
     ТОЛЬКО при живом visible=True; иначе честный статус (на модерации/ошибки/скрыта).
  4) ЗАПИСЬ pour-library (коробочная, идемпотентно по offer_id, атомарно tmp+replace) — только
     после ЖИВОГО импорта; пустой imported → НЕ пишем.
  5) АРТЕФАКТ korobki_POUR_LIVE_<DATE>.{json,md} + отчёт оператору.

По умолчанию dry=True/commit=False (0₽, двойной гейт РУБИКОНА). Живой залив — только --commit.
--limit N  → залить не больше N НОВЫХ offer_id (канарейка: первый живой батч ≤100, потом долгие).
Безопасно перезапускать: twin-гард + идемпотентная запись библиотеки не дадут дублей.

Ключи OZON_* ТОЛЬКО из env / gitignored .env (SOCC/scripts/mint/.env), в коде их нет.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ozon_hands_write_v1 as W     # noqa: E402  (create_product/import_info/read_shelf — единые руки)

DATE = date.today().isoformat()
RUNTIME = HERE / "runtime" / "ozon_boxes"
# Что льём по умолчанию: СВЕЖИЙ манифест резолвера «склад из дона» (честные габариты сложенной
# упаковки). Прежний дефолт korobki_CARD_LIVE_2026-09-09 нёс габариты ИИ-филлера base.ovh
# (все карточки ~13×14×16 см независимо от товара) — лить их живьём нельзя.
ITEMS_DEFAULT_GLOB = "korobki_FOLDED_*.items.json"
ITEMS_JSON = None                       # разрешается в load_frozen() по args.items/_latest
OUT_JSON = RUNTIME / f"korobki_POUR_LIVE_{DATE}.json"
OUT_MD = RUNTIME / f"korobki_POUR_LIVE_{DATE}.md"
LIB_PATH = RUNTIME / "pour-library-korobki.json"

CREATE_BATCH = 100      # лимит /v3/product/import на вызов
SHELF_BATCH = 500       # read_shelf за вызов
POLL_ATTEMPTS = 24      # ~3 мин на дозу
POLL_DELAY = 8          # сек между опросами import_info

# ── ПИН КАБИНЕТА: коробки живут ТОЛЬКО в Express Box (…8715) ─────────────────
# Старый кабинет …3485 скомпрометирован 06.08 — писать туда запрещено. Опора на внешний
# OZON_ACCOUNT молчалива: забыл env → орган ушёл бы в …3485. Пин снимает эту дыру:
# кабинет выставляется сам, и его Client-Id ДОКАЗЫВАЕТСЯ до первого живого вызова.
BOX_ACCOUNT = "box"
BOX_CLIENT_TAIL = "8715"


def pin_box_account(account=BOX_ACCOUNT, tail=BOX_CLIENT_TAIL):
    """Выставить OZON_ACCOUNT=box и вернуть (совпал_хвост, хвост_Client_Id). Значения не печатаем."""
    os.environ["OZON_ACCOUNT"] = account
    cid, _key = W._account_creds()
    got = str(cid or "").strip()[-4:] or None
    return (got == tail), got


def _latest(pattern, skip=()):
    """Свежий артефакт по маске — вход ищем ПО НАЛИЧИЮ, а не по календарю."""
    hits = [p for p in sorted(RUNTIME.glob(pattern)) if not any(s in p.name for s in skip)]
    return hits[-1] if hits else None


def load_frozen():
    """Замороженные item'ы манифеста → (items, metas). Отсутствие файла → честный FAIL (не 0)."""
    global ITEMS_JSON
    if ITEMS_JSON is None:
        ITEMS_JSON = _latest(ITEMS_DEFAULT_GLOB)
        if ITEMS_JSON is None:
            raise RuntimeError(f"нет манифеста по маске {ITEMS_DEFAULT_GLOB} — сначала резолвер (0₽)")
    if not ITEMS_JSON.exists():
        raise RuntimeError(f"нет замороженных items: {ITEMS_JSON.name} — сначала манифест (0₽)")
    d = json.loads(ITEMS_JSON.read_text(encoding="utf-8"))
    items, metas = d.get("items") or [], d.get("metas") or []
    if not items:
        raise RuntimeError("замороженный файл без items — манифест пуст, залив отменён")
    return items, metas


# ── twin-гард: что уже живёт в кабинете ключа (не пересоздаём) ──────────────

def twin_guard(offer_ids):
    """offer_ids → (already_oids, live_cards). Живое = product_id>0 на витрине чтения.
    Чтение упало/нет ключа → RuntimeError (залив вслепую запрещён, честно)."""
    if not W.creds_present():
        raise RuntimeError("нет OZON_* ключей в env — twin-чтение невозможно, залив отменён")
    live = {}
    for i in range(0, len(offer_ids), SHELF_BATCH):
        chunk = offer_ids[i:i + SHELF_BATCH]
        r = W.read_shelf(chunk)
        if not r.get("ok"):
            raise RuntimeError("read_shelf упал: {e} — «уже живёт?» не доказано, не пишем".format(
                e=r.get("_error", "ok=False")))
        for card in r.get("cards", []):
            oid = card.get("offer_id")
            if oid and card.get("product_id") not in (None, 0):
                live[str(oid)] = card
    already = [oid for oid in offer_ids if oid in live]
    new = [oid for oid in offer_ids if oid not in already]
    return already, live, new


# ── статус витрины (зеркало PASS-гейта: «Продаётся» = ТОЛЬКО живой visible=True) ──

def shelf_status_of(card):
    """read_shelf-карточка → статус витрины. НИКОГДА не «Продаётся» без visible=True."""
    if not isinstance(card, dict):
        return "не найдена"
    if card.get("_error"):
        return f"сверка недоступна: {card['_error']}"
    if card.get("visible"):
        return "Продаётся"
    errs = card.get("errors") or []
    if errs:
        return "ошибки: " + "; ".join(str(e) for e in errs[:3])
    mod = card.get("moderation")
    if mod in ("approved", None, ""):
        return "одобрена, но скрыта"
    return "на модерации"


def verify_shelf(imported, timeout=30):
    """Живая сверка витрины (0₽ GET): импортированные → «Продаётся»/иное. Fail-soft честно."""
    offered = [str(i.get("offer_id") or "").strip() for i in (imported or [])
               if str(i.get("offer_id") or "").strip() and (i.get("product_id") or 0) > 0]
    if not offered:
        return {"ok": False, "report": {}, "_error": "нет импортированных с product_id — сверять нечего"}
    try:
        res = W.read_shelf(offered, timeout=timeout)
    except Exception as e:
        return {"ok": False, "report": {}, "_error": f"{type(e).__name__}: {e}"}
    by_oid = {str(c.get("offer_id")): c for c in res.get("cards", [])}
    report = {oid: shelf_status_of(by_oid.get(oid)) for oid in offered}
    if not res.get("ok"):
        return {"ok": False, "report": report, "_error": res.get("_error") or "сверка недоступна"}
    return {"ok": True, "report": report}


# ── pour-library коробок (своя; идемпотентно по offer_id, атомарно) ─────────

def _read_lib():
    try:
        data = json.loads(LIB_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_lib(lib):
    try:
        LIB_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = LIB_PATH.with_name(LIB_PATH.name + ".tmp")
        tmp.write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(LIB_PATH)
        return True
    except Exception:
        return False


def record_pour(imported, metas_by_oid, shelf=None):
    """Записать в pour-library успешно импортированные (идемпотентно по offer_id). Пусто → НЕ пишем."""
    if not imported:
        return {"ok": False, "written": 0, "_error": "нет импортированных — записывать нечего"}
    lib = _read_lib()
    written = 0
    for it in imported:
        oid = str(it.get("offer_id") or "").strip()
        if not oid or (it.get("product_id") or 0) <= 0:
            continue
        m = metas_by_oid.get(oid) or {}
        rec = lib.get(oid) or {}
        rec.update({
            "offer_id": oid,
            "name": str(m.get("name") or "")[:120],
            "price": m.get("price"),
            "old_price": m.get("old_price"),
            "tn_ved": m.get("tn_ved"),
            "type_id": m.get("type_id"),
            "material_how": m.get("material_how"),
            "images": m.get("images"),
            "donor_pid": m.get("donor_pid"),
            "donor_url": m.get("donor_url"),
            "donor_status": m.get("donor_status"),
            "donor_price": m.get("donor_price"),
            "stitch": m.get("stitch"),
            "product_id": it.get("product_id"),
            "status": str(it.get("status")),
            "shelf": (shelf or {}).get(oid),
            "recorded": DATE,
        })
        lib[oid] = rec
        written += 1
    if not written:
        return {"ok": False, "written": 0, "_error": "импортированные без product_id — не пишем"}
    if not _write_lib(lib):
        return {"ok": False, "written": written, "_error": f"не записать {LIB_PATH.name}"}
    return {"ok": True, "written": written, "total": len(lib), "path": str(LIB_PATH)}


# ── доза: живой import + опрос import_info ──────────────────────────────────

def _fill_dose(chunk, commit):
    """Одна доза ≤100: create_product → task_id → import_info → (imported, failures)."""
    res = W.create_product(chunk, dry=not commit, commit=commit)
    if not commit:
        return [], [], {"dry": True, "count": len(chunk)}
    if res.get("status") != "sent":
        err = res.get("_error") or res.get("status")
        return [], [{"offer_id": "?", "status": "transport", "errors": [str(err)]}], {}
    resp = res.get("response") or {}
    task_id = (resp.get("result") or {}).get("task_id") or resp.get("task_id")
    if task_id is None:
        return [], [{"offer_id": "?", "status": "no-task-id",
                     "errors": ["task_id не получен — карточка НЕ создана"]}], {}
    items_info = []
    for _ in range(POLL_ATTEMPTS):
        items_info = W.import_info(task_id)
        if not items_info:
            time.sleep(POLL_DELAY)
            continue
        if all(str(i.get("status")) != "pending" for i in items_info):
            break
        time.sleep(POLL_DELAY)
    if not items_info:
        return [], [{"offer_id": "?", "status": "no-info",
                     "errors": [f"import_info пуст за {POLL_ATTEMPTS} попыток — итог неизвестен"]}], {}
    imported, failures = [], []
    for it in items_info:
        st = str(it.get("status"))
        pid = it.get("product_id") or 0
        errs = [str(e) for e in (it.get("errors") or [])]
        if st == "imported" and pid and not errs:
            imported.append(it)
        else:
            failures.append({"offer_id": it.get("offer_id"), "status": st,
                             "errors": errs, "product_id": pid})
    return imported, failures, {"task_id": task_id}


# ── отчёты ──────────────────────────────────────────────────────────────────

def render_dose(imported, failures, idx, commit):
    L = [f"ДОЗА {idx}: {'ЖИВОЙ' if commit else 'СУХО (0₽)'} · импортировано {len(imported)} · "
         f"ошибок {len(failures)}"]
    for it in imported:
        L.append(f"  ✅ {it.get('offer_id')} → product_id={it.get('product_id')}")
    for f in failures:
        L.append(f"  ❌ {f.get('offer_id')} · status={f.get('status')} · errors={f.get('errors')}")
    return "\n".join(L)


def render_shelf_report(report):
    on = sum(1 for s in report.values() if s == "Продаётся")
    L = [f"ВИТРИНА · сверено {len(report)} · «Продаётся» {on}/{len(report)}"]
    for oid in sorted(report):
        st = report[oid]
        L.append(f"  {('🟢' if st == 'Продаётся' else '🔴')} {oid} · {st}")
    return "\n".join(L)


def write_artifacts(summary, doses, shelf_report, lib_res):
    manifest = {
        "date": DATE,
        "frozen": ITEMS_JSON.name,
        "commit": summary["commit"],
        "new_count": summary["new"],
        "already_live": summary["already"],
        "doses": doses,
        "imported_total": summary["imported_total"],
        "failures_total": summary["failures_total"],
        "shelf_report": shelf_report,
        "pour_library": lib_res,
        "required_ids": sorted({85, 9048, 8229, 23536, 22232}),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    L = [f"# ОЗОН КОРОБКИ · ЖИВОЙ ЗАЛИВ {DATE}",
         "",
         f"- frozen: {ITEMS_JSON.name} · commit={'ЖИВОЙ' if summary['commit'] else 'СУХО (0₽)'}",
         f"- новых к заливу: {summary['new']} · уже-жив (twin-гард, не льём): {summary['already']}",
         f"- импортировано: {summary['imported_total']} · ошибок: {summary['failures_total']}",
         "",
         "## ВИТРИНА (DONE = «Продаётся» при живом visible=True)",
         ]
    for oid in sorted(shelf_report or {}):
        st = shelf_report[oid]
        L.append(f"- {('🟢' if st == 'Продаётся' else '🔴')} `{oid}` · {st}")
    L.append("")
    L.append("## Ошибки доз (если есть)")
    for d in doses:
        for f in d.get("failures", []):
            L.append(f"- `{f.get('offer_id')}` status={f.get('status')} errors={f.get('errors')}")
    OUT_MD.write_text("\n".join(L))
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Живой залив коробок (дозы ≤100, twin-гард, витрина).")
    ap.add_argument("--commit", action="store_true", help="ОТКРЫТЬ гейт: реальная запись в Ozon.")
    ap.add_argument("--items", default=None,
                    help="путь к замороженному .items.json (по умолч. korobki_CARD_LIVE; можно лить "
                         "подмножество, напр. только сшитые с донором).")
    ap.add_argument("--limit", type=int, default=0,
                    help="залить не больше N новых offer_id (0 = все; канарейка: 100).")
    args = ap.parse_args(argv)

    if args.items:
        global ITEMS_JSON                      # load_frozen() читает модульную переменную
        ITEMS_JSON = Path(args.items).resolve()
    # ПИН: кабинет коробок — Express Box (…8715). Не тот Client-Id → живой шаг не идёт.
    tail_ok, tail = pin_box_account()
    print(f"[кабинет] OZON_ACCOUNT={BOX_ACCOUNT} · Client-Id …{tail} · "
          f"{'ПИН ОК' if tail_ok else 'ПИН НЕ СОВПАЛ'}")
    if not tail_ok:
        print(f"  ОТКАЗ: ожидался Client-Id с хвостом …{BOX_CLIENT_TAIL} (Express Box). "
              f"Активен …{tail}. Писать в другой кабинет нельзя — залив отменён.")
        return 2
    items, metas = load_frozen()
    print(f"артефакт заморозки: {ITEMS_JSON.name}")
    by_oid = {str(m.get("art") or m.get("offer_id") or "").strip(): m for m in metas}
    # у item'ов offer_id есть всегда; у metas ключ «art» (== offer_id манифеста)
    for it in items:
        oid = str(it.get("offer_id") or "").strip()
        if oid and oid not in by_oid:
            by_oid[oid] = {**({"name": it.get("name"), "price": it.get("price"),
                               "old_price": it.get("old_price")} if oid else {})}
    print(f"заморожено item: {len(items)}")

    print("\n[twin-гард] читаю витрину кабинета (0₽ read_shelf)…")
    offer_ids = [str(it["offer_id"]) for it in items]
    try:
        already, live, new_ids = twin_guard(offer_ids)
    except RuntimeError as e:
        print("  ОТКАЗ:", e)
        return 2
    print(f"  кандидатов {len(offer_ids)} · уже-жив {len(already)} · новых {len(new_ids)}")
    if already:
        print(f"  примеры уже-живых: {already[:8]}")

    # порядок доз = порядок манифеста (детерминированно)
    order = {oid: i for i, oid in enumerate(offer_ids)}
    new_ids_sorted = sorted(new_ids, key=lambda o: order.get(o, 0))
    if args.limit > 0:
        new_ids_sorted = new_ids_sorted[:args.limit]
        print(f"  --limit {args.limit}: беру {len(new_ids_sorted)} новых")

    if not new_ids_sorted:
        print("\nнечего заливать (всё уже живёт или лимит 0). Вердикт: 0 новых.")
        summary = {"commit": args.commit, "new": 0, "already": len(already),
                   "imported_total": 0, "failures_total": 0}
        write_artifacts(summary, [], {}, {"ok": True, "written": 0})
        print(f"артефакт: {OUT_JSON.name} (+md)")
        return 0

    by_id_item = {str(it["offer_id"]): it for it in items}
    doses_report, imported_all, failures_all = [], [], []
    for idx, i in enumerate(range(0, len(new_ids_sorted), CREATE_BATCH), start=1):
        chunk_oids = new_ids_sorted[i:i + CREATE_BATCH]
        chunk = [by_id_item[o] for o in chunk_oids]
        print(f"\n[{idx}] доза {len(chunk)} ({'ЖИВОЙ' if args.commit else 'СУХО 0₽'})…")
        imported, failures, extra = _fill_dose(chunk, args.commit)
        imported_all += imported
        failures_all += failures
        doses_report.append({"batch": idx, "count": len(chunk),
                             "imported": len(imported), "failures": failures,
                             "dry": not args.commit, **extra})
        print(render_dose(imported, failures, idx, args.commit))

    shelf_report = {}
    if args.commit and imported_all:
        print("\n[витрина] сверяю импортированные (закон OZ3: DONE=«Продаётся»)…")
        vs = verify_shelf(imported_all)
        shelf_report = vs.get("report", {})
        print(render_shelf_report(shelf_report))
        if not vs.get("ok") and not shelf_report:
            print("  ⚠ сверка витрины не удалась:", vs.get("_error"))

    lib_res = {"ok": False, "written": 0}
    if args.commit and imported_all:
        print("\n[запись] pour-library коробок (идемпотентно по offer_id)…")
        lib_res = record_pour(imported_all, by_oid, shelf_report)
        print(f"  записано {lib_res.get('written')} · всего в библиотеке {lib_res.get('total')}"
              + (f" · {lib_res['path']}" if lib_res.get('path') else ""))

    summary = {"commit": args.commit, "new": len(new_ids_sorted),
               "already": len(already),
               "imported_total": len(imported_all),
               "failures_total": len(failures_all)}
    write_artifacts(summary, doses_report, shelf_report, lib_res)
    print(f"\nартефакт: {OUT_JSON.name} (+md)")

    print("\n──────── ВЕРДИКТ ────────")
    if not args.commit:
        print("СУХО (0₽): payload из заморозки готов к живому шагу. Живой залив — только --commit.")
    else:
        print(f"новых залито доз: {len(doses_report)} · импортировано {len(imported_all)} · "
              f"ошибок {len(failures_all)}")
        on = sum(1 for s in shelf_report.values() if s == "Продаётся")
        if shelf_report:
            print(f"на витрине «Продаётся»: {on}/{len(shelf_report)} (DONE только при visible=True)")
        print(f"pour-library записей: {lib_res.get('written')} (всего {lib_res.get('total')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
