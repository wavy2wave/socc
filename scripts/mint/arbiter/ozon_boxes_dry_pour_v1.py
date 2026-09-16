#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ОЗОН · КОРОБКИ · ШАГ 3 — СУХОЙ ПРОБНЫЙ ПЕРЕЛИВ (0₽, RUBICON цел).

План resilient-gathering-bonbon, Шаг 3 («Пробуй. Возьмём коробки картонные»). НИЧЕГО наружу
не пишет: create_product только с dry=True; живые write — по слову оператора и ОТДЕЛЬНЫМ шагом.

Что делает честно (без fake-pass):
  1) ЖИВОЙ резолв категории: тянет /v1/description-category/tree и для каждой ГОТОВО-строки
     артефакта инвентаря ищет ПАРУ (description_category_id, «Тип»-значение) как лист дерева.
       • dci нет в живом дереве            → NEED_MAPPING, причина «категория мертва» (не выдумываем);
       • dci есть, но «Тип» нет среди листьев → NEED_MAPPING, причина «тип не существует» + доступные.
     (Закон OZ2: авто-категории у Ozon нет; мы не гадаем.)
  2) ПРОФИЛЬ ПРОХОЖДЕНИЯ: для реально ливабельных пар (dci,type_id) читает обязательные атрибуты
     (category/attribute) → показывает, чего не хватает до «карточка просто прошла».
  3) TWIN-ГАРД (дух #38): read_shelf по offer_id кандидатов — что уже живёт в кабинете ключа,
     НЕ пересоздаём. Если чтение витрины упало/нет ключа → честный FAIL, залив вслепую запрещён.
  4) СБОРКА: ozon_card_v1.to_item(prod c явной категорией) для НОВЫХ; фото = свой cdn1.ozone URL
     из строки как есть (медиа оператора); имя 1-в-1; ОВХ мм/г из артефакта; штрихкода в строке нет
     → не шлём (не выдумываем).
  5) create_product(items, dry=True) батчами ≤100 → сухой манифест.
Вердикт + манифест — оператору. Живой commit — ТОЛЬКО по RUBICON (плюс ротация ключа ДО записи).

Артефакты: runtime/ozon_boxes/ozon_korobki_dry_pour_<DATE>.{json,md}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ozon_card_v1 as C           # noqa: E402
import ozon_category_scout_v1 as S # noqa: E402
import ozon_hands_write_v1 as H    # noqa: E402

DATE = "2026-09-09"
BASE = HERE / "runtime" / "ozon_boxes" / "ozon_korobki_base_2026-09-08.json"
OUT_JSON = HERE / "runtime" / "ozon_boxes" / f"ozon_korobki_dry_pour_{DATE}.json"
OUT_MD = HERE / "runtime" / "ozon_boxes" / f"ozon_korobki_dry_pour_{DATE}.md"

CREATE_BATCH = 100
SHELF_BATCH = 500


# ── 1. живой резолв (dci, «Тип») → type_id по дереву ───────────────────────────

def _types_by_dci(tree):
    """dci → {type_name: type_id} для ЛИСТЬЕВ живого дерева. Лист без dci не кандидат (OZ2)."""
    out = {}
    for leaf in S._walk_leaves(S._roots(tree)):
        dci = leaf["description_category_id"]
        if dci is None:
            continue
        out.setdefault(dci, {})[leaf["type_name"]] = leaf["type_id"]
    return out


def _resolve_type(types_by_dci, dci, type_val):
    """Точное/регистро-норм совпадение имени типа в ЖИВОМ дереве. Слабо → None (не выдумываем)."""
    pool = types_by_dci.get(dci)
    if not pool:
        return None, "нет-категории"
    exact = pool.get(type_val)
    if exact is not None:
        return exact, "ok"
    norm = {k.lower(): v for k, v in pool.items()}
    low = (type_val or "").strip().lower()
    if low in norm:
        return norm[low], "ok"
    return None, "нет-типа"


def _classify(rows, types_by_dci):
    """Делит ГОТОВО-строки: resolved (тип найден) vs need_mapping (причина + доступные типы)."""
    resolved, need = [], []
    for p in rows:
        try:
            dci = int(p["dci"])
        except (TypeError, ValueError):
            need.append({**p, "need_reason": f"dci не число: {p.get('dci')!r}",
                         "available_types": []})
            continue
        tid, rc = _resolve_type(types_by_dci, dci, p.get("type"))
        if rc == "ok" and tid is not None:
            resolved.append({**p, "dci": dci, "type_id": int(tid)})
            continue
        avail = sorted(types_by_dci.get(dci, {}).keys())
        reason = ("категория {dci} отсутствует в живом дереве категорий (на {DATE})".format(dci=dci, DATE=DATE)
                  if rc == "нет-категории" else
                  "«Тип» {t!r} не существует в категории {dci}".format(t=p.get("type"), dci=dci))
        need.append({**p, "dci": dci, "need_reason": reason, "available_types": avail})
    return resolved, need


# ── 3. twin-гард по живому кабинету ────────────────────────────────────────────

def _twin_guard(offer_ids):
    """read_shelf по offer_id. Живое = не пересоздаём. Чтение упало/нет ключа → честный отказ."""
    if not H.creds_present():
        raise RuntimeError("нет OZON_* ключей в env — twin-чтение невозможно, залив отменён")
    live, absent, errs = {}, [], []
    for i in range(0, len(offer_ids), SHELF_BATCH):
        chunk = offer_ids[i:i + SHELF_BATCH]
        r = H.read_shelf(chunk)
        if not r.get("ok"):
            raise RuntimeError("read_shelf упал: {e} — «уже живёт?» не доказано, не пишем".format(
                e=r.get("_error", "ok=False")))
        for card in r.get("cards", []):
            oid = card.get("offer_id")
            if oid and card.get("product_id") not in (None, 0):
                live[oid] = card
        errs.extend(r.get("cards", []))
    already = {oid for oid in offer_ids if oid in live}
    new = [oid for oid in offer_ids if oid not in already]
    return {"already": sorted(already), "new": new,
            "live_cards": {k: {"product_id": v.get("product_id"),
                               "visible": v.get("visible"),
                               "moderation": v.get("moderation")}
                           for k, v in live.items()}}


# ── сборка + сухой залив ───────────────────────────────────────────────────────

def _to_prod(row):
    o = row["ovh"] or {}
    prod = {
        "offer_id": str(row["art"]),
        "name": str(row["name"]),
        "price": float(row["price"]),
        "description_category_id": int(row["dci"]),
        "type_id": int(row["type_id"]),
        "images": list(row["photos"] or []),
    }
    dims = {}
    for src, key in (("d_mm", "depth"), ("w_mm", "width"), ("h_mm", "height"), ("weight_g", "weight")):
        try:
            v = float(o.get(src))
        except (TypeError, ValueError):
            v = 0.0
        if not (v > 0):
            return None, f"нет ОВХ поля {src} у {row['art']} — карточку не собрать"
        dims[key] = v
    prod["dimensions"] = dims
    return prod, None


def _build_new(resolved_new):
    items, meta, skipped = [], [], []
    for row in resolved_new:
        prod, err = _to_prod(row)
        if err:
            skipped.append({"art": row["art"], "reason": err})
            continue
        try:
            out = C.to_item(prod)          # категория explicit уже в prod
        except C.CardError as e:
            skipped.append({"art": row["art"], "reason": f"CardError: {e}"})
            continue
        m = out["meta"]
        if m.get("need_mapping"):
            skipped.append({"art": row["art"], "reason": "to_item: need_mapping (без категории)"})
            continue
        if out["item"] is not None:
            items.append(out["item"])
            meta.append(m)
    return items, meta, skipped


def _dry_import(items):
    batches, dry_res = [], []
    for i in range(0, len(items), CREATE_BATCH):
        chunk = items[i:i + CREATE_BATCH]
        batches.append(len(chunk))
        dry_res.append(H.create_product(chunk, dry=True, commit=False))
    return batches, dry_res


def main():
    data = json.loads(BASE.read_text())
    products = data["products"]
    ready = [p for p in products if "ГОТОВО" in (p.get("readiness") or [])]
    print(f"артефакт: {BASE.name} · ГОТОВО строк: {len(ready)}")

    print("\n[1/4] живой резолв категории (0₽ GET /description-category/tree)…")
    if not H.creds_present():
        print("  ОТКАЗ: нет OZON_* ключей в env — резолв невозможен.")
        return 2
    tree = H.category_tree()
    types_by_dci = _types_by_dci(tree)
    resolved, need = _classify(ready, types_by_dci)
    print(f"  resolved (пара в живом дереве): {len(resolved)}")
    print(f"  need_mapping: {len(need)}")
    from collections import Counter
    for (dci, reason), n in Counter((r["dci"], r["need_reason"]) for r in need).most_common():
        print(f"    {n:5}  dci={dci} · {reason[:70]}")

    # профиль прохождения по каждой ливабельной паре (обязательные атрибуты)
    print("\n[2/4] обязательные атрибуты ливабельных пар (0₽)…")
    gaps_report = []
    for dci, tid in sorted({(r["dci"], r["type_id"]) for r in resolved}):
        attrs = H.category_attributes(dci, tid)
        required = [a for a in attrs if isinstance(a, dict) and a.get("is_required")]
        names = [a.get("name") for a in required if isinstance(a, dict)]
        print(f"  dci={dci} type_id={tid}: required-атрибутов {len(names)}"
              + (f" → не заполнено: {', '.join(names[:12])}{'…' if len(names) > 12 else ''}"
                 if names else " → всё покрыто"))
        gaps_report.append({"dci": dci, "type_id": tid,
                            "required_missing": names})
    # каких обязательных атрибутов категории НЕ покрывает сборка без профиля — пункты для живого шага

    print("\n[3/4] twin-гард по живому кабинету (0₽ read_shelf)…")
    offer_ids = [str(r["art"]) for r in resolved]
    try:
        tw = _twin_guard(offer_ids)
    except RuntimeError as e:
        print("  ОТКАЗ:", e)
        return 2
    print(f"  кандидатов: {len(offer_ids)} · уже-жив: {len(tw['already'])} · новых: {len(tw['new'])}")
    if tw["already"]:
        print(f"  примеры уже-живых offer_id: {tw['already'][:8]}")

    by_id = {str(r["art"]): r for r in resolved}
    resolved_new = [by_id[o] for o in tw["new"]]
    print("\n[4/4] сборка + сухой залив (0₽, dry=True)…")
    items, meta, skipped = _build_new(resolved_new)
    print(f"  собрано item: {len(items)} · пропущено сборкой: {len(skipped)}")
    for sk in skipped[:5]:
        print("    skip:", sk["art"], "—", sk["reason"][:90])
    batches, dry_res = _dry_import(items)
    print(f"  dry-батчей: {len(batches)} · размеры: {batches}")
    summary = {
        "date": DATE,
        "base_artifact": BASE.name,
        "ready_total": len(ready),
        "resolved": len(resolved),
        "need_mapping": len(need),
        "already_live_skipped": len(tw["already"]),
        "new_candidates": len(tw["new"]),
        "items_built": len(items),
        "items_skipped_build": len(skipped),
        "dry_batches": batches,
        "dry_ok": all(r.get("status") == "dry" for r in dry_res),
    }
    manifest = {
        "summary": summary,
        "type_resolution": {f"{r['dci']}|{r['type']}": r["type_id"] for r in resolved},
        "required_gaps": gaps_report,
        "twin_guard": {"already_count": len(tw["already"]), "already_sample": tw["already"][:20],
                       "new_count": len(tw["new"])},
        "need_mapping": [{"art": r["art"], "name": r["name"][:80], "dci": r["dci"],
                          "type": r.get("type"), "reason": r["need_reason"],
                          "available_types": r["available_types"][:8]} for r in need[:200]],
        "meta_sample": meta[:3],
        "would_send_sample": items[:2],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    _write_md(manifest, tw, by_id, items)
    print(f"\nманифест: {OUT_JSON.name} + .md")

    print("\n──────── ВЕРДИКТ (СУХОЙ, 0₽) ────────")
    if not summary["dry_ok"]:
        print("✗ create_product(dry) вернул не-dry — проверь выше.")
    print(f"из {len(ready)} ГОТОВО только {len(resolved)} сейчас ливабельны как есть "
          f"({len(need)} ждут ре-маппинга категории/типа).")
    print(f"из {len(resolved)} ливабельных {len(tw['already'])} уже живут в кабинете (не льём), "
          f"новых кандидатов {len(items)} собрано в item.")
    print("живой залив — ТОЛЬКО по слову оператора (RUBICON) + ротация ключа ДО записи.")
    return 0


def _write_md(manifest, tw, by_id, items):
    L = []
    L.append(f"# ОЗОН КОРОБКИ — СУХОЙ ПРОБНЫЙ ПЕРЕЛИВ {DATE} (0₽)")
    L.append("")
    L.append(f"- ГОТОВО строк артефакта: {manifest['summary']['ready_total']}")
    L.append(f"- resolved (пара в живом дереве): {manifest['summary']['resolved']}")
    L.append(f"- need_mapping: {manifest['summary']['need_mapping']}")
    L.append(f"- уже-жив (twin-гард, не льём): {len(tw['already'])}")
    L.append(f"- новых кандидатов в item: {len(items)} (dry)")
    L.append("")
    L.append("## need_mapping (ре-маппинг категории/типа нужен — не выдумываем)")
    for r in manifest["need_mapping"][:40]:
        L.append(f"- `{r['art']}` {r['name'][:60]} · dci={r['dci']} тип={r.get('type')!r} — {r['reason'][:80]}")
    if len(manifest["need_mapping"]) > 40:
        L.append(f"- … и ещё {len(manifest['need_mapping']) - 40}")
    L.append("")
    L.append("## ливабельные пары → обязательные атрибуты для «просто прошла»")
    for g in manifest["required_gaps"]:
        L.append(f"- dci={g['dci']} type_id={g['type_id']}: не заполнено → {', '.join(g['required_missing'][:15])}")
    OUT_MD.write_text("\n".join(L))
    return True


if __name__ == "__main__":
    raise SystemExit(main())
