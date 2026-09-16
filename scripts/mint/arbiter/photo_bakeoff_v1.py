#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""КУЗНИЦА ФОТО · ЗАМЕР (bake-off): какие модели коннектора РЕАЛЬНО дают годный кадр и за сколько секунд.

Оператор 09-15: «Проверь коннектор по кузнице фото. Нужна быстрая скорость работы и охуенное лучшее
качество + наша инфографика, пробуем все!!!»

Что делает: гоняет ОДИН и тот же реальный товар (коробка) через КАЖДУЮ generate-модель активного
коннектора, меряет СТЕННОЕ ВРЕМЯ и приёмку канона (белый фон + 4:5), складывает кадры в папку и
пишет артефакт. Победитель потом идёт в нашу инфографику (photo_infographic_v1).

Законы органа:
  · dry=True по умолчанию — 0₽; живой замер ТОЛЬКО по --live (двойной гейт, как у кузницы).
  · retries=0 по умолчанию: одна попытка на модель — иначе «скорость» меряется с ретраями и врёт.
  · 200 ≠ успех: годным считаем только tier из verify_canon/verify_output, а не HTTP-код.
  · ключи ТОЛЬКО из env / gitignored .env; значения не печатаем.
  · запускать ИМЕННО фото-venv'ом (~/.venvs/photoforge/bin/python) — иначе canon-броня без PIL.

Прогон:  ~/.venvs/photoforge/bin/python photo_bakeoff_v1.py --live
Артефакт: runtime/ozon_boxes/BAKEOFF_<DATE>.{json,md} + кадры в runtime/ozon_boxes/bakeoff_<DATE>/
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
RUNTIME = HERE / "runtime" / "ozon_boxes"
DATE = date.today().isoformat()
OUT_DIR = RUNTIME / f"bakeoff_{DATE}"
OUT_JSON = RUNTIME / f"BAKEOFF_{DATE}.json"
OUT_MD = RUNTIME / f"BAKEOFF_{DATE}.md"

# Кандидаты активного коннектора (ru_openai → VseGPT), цены сняты с /v1/models 15.09 — не выдуманы.
# Порядок: от дешёвого к дорогому. «наша сейчас» — то, чем куём по умолчанию.
MODELS = [
    ("img-flux/flux-2-klein-4b",         3.9,  "наша сейчас (самая дешёвая)"),
    ("img-openai/gpt-image-1-mini",      5.0,  "OpenAI мини"),
    ("img-google/imagen4-preview-fast",  5.9,  "Google Imagen 4 Fast"),
    ("img-bytedance/seedream-v4",        6.9,  "ByteDance Seedream 4"),
    ("img-google/flash-25",              9.9,  "Nano Banana 2.5"),
    ("img-flux/flux-2-pro",             10.0,  "FLUX 2 Pro"),
    ("img-openai/gpt-image-2",          10.0,  "OpenAI GPT-Image 2"),
    ("img-flux/flux-2-klein-9b",        10.0,  "Flux 2 klein 9B"),
    ("img-bytedance/seedream-v4.5",     13.9,  "Seedream 4.5"),
    ("img-google/nano-banana-2",        19.9,  "Nano Banana 2"),
    ("img-google/imagen4-preview-ultra", 20.0, "Imagen 4 Ultra"),
    ("img-google/nano-banana-pro",      29.9,  "Nano Banana Pro (топ)"),
]

# Реальный товар кабинета коробок — замер на нём, а не на выдумке.
DEFAULT_SUBJECT = {
    "art": "i1_ex_cargo_103",
    "name": "Коробка картонная самосборная Т-23 Е 70х70х60",
    "facts": {
        "name": "Коробка картонная самосборная Т-23 Е 70х70х60 мм",
        "материал": "гофрокартон Т-23 Е, бурый",
        "тип": "самосборная (4-клапанная), без скотча",
        "назначение": "упаковка для маркетплейсов и переезда",
    },
}


def _subject(arg):
    """Товар для замера. --subject art:<артикул> тянет реальное имя из живого артефакта связей."""
    if not arg:
        return DEFAULT_SUBJECT
    if arg.startswith("art:"):
        art = arg[4:]
        p = RUNTIME / f"korobki_DONOR_LINKS_{DATE}.json"
        if not p.exists():
            hits = sorted(RUNTIME.glob("korobki_DONOR_LINKS_*.json"))
            p = hits[-1] if hits else None
        if p:
            for r in json.loads(p.read_text(encoding="utf-8")).get("rows", []):
                if r.get("art") == art:
                    nm = r.get("name") or art
                    return {"art": art, "name": nm, "facts": {"name": nm}}
        raise SystemExit(f"артикул {art} не найден в связях донора")
    return {"art": "custom", "name": arg, "facts": {"name": arg}}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Замер моделей кузницы: скорость + приёмка канона (0₽ без --live).")
    ap.add_argument("--live", action="store_true", help="БОЕВОЙ замер — тратит ₽ на каждой модели")
    ap.add_argument("--models", default="", help="подмножество слагов через запятую (по умолч. все)")
    ap.add_argument("--subject", default="", help="товар для замера: art:<артикул> или свободное имя")
    ap.add_argument("--retries", type=int, default=0, help="попыток на модель (по умолч. 0 — честная скорость)")
    ap.add_argument("--no-canon", action="store_true", help="без брони канона (быстрее, но кадр не по стилю)")
    args = ap.parse_args(argv)

    import photo_forge_v1 as pf
    pf._ensure_env()

    subj = _subject(args.subject)
    want = [m.strip() for m in args.models.split(",") if m.strip()] or [m[0] for m in MODELS]
    plan = [m for m in MODELS if m[0] in want]
    prov = pf._provider()
    est = sum(m[1] for m in plan)

    print("ФОТО-КУЗНИЦА · ЗАМЕР (bake-off)")
    print(f"   коннектор:   {prov} · {pf._base_url()}")
    print(f"   товар:       {subj['name']}  [{subj['art']}]")
    print(f"   моделей:     {len(plan)} · оценка расхода: ~{est:.1f}₽ за прогон")
    print(f"   режим:       {'ЖИВОЙ (тратит ₽)' if args.live else 'СУХОЙ (0₽)'} · "
          f"канон: {'выкл' if args.no_canon else 'вкл'} · попыток на модель: {args.retries + 1}")

    if not args.live:
        print("\n   СУХОЙ ГЕЙТ: наружу ничего не ушло (0₽). Живой замер — только --live.")
        for mid, rub, note in plan:
            r = pf.forge(facts=subj["facts"], mode="generate", dry=True, model=mid,
                         canon=not args.no_canon, out_dir=str(OUT_DIR), tag=subj["art"])
            print(f"     {rub:>5.1f}₽  {mid:<36} {note:<26} форма: {'ok' if r.get('ok') else 'FAIL'}")
        print(f"\n   итого к трате при --live: ~{est:.1f}₽")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, (mid, rub, note) in enumerate(plan, 1):
        print(f"\n[{i}/{len(plan)}] {mid}  (~{rub}₽) · {note}")
        t0 = time.time()
        try:
            r = pf.forge(facts=subj["facts"], mode="generate", dry=False, model=mid,
                         retries=args.retries, canon=not args.no_canon,
                         out_dir=str(OUT_DIR), tag=f"{subj['art']}_{mid.replace('/', '_')}")
        except Exception as e:                                   # сеть/шлюз — честный провал, не «0»
            r = {"ok": False, "why": f"{type(e).__name__}: {e}"}
        secs = round(time.time() - t0, 2)
        ok = bool(r.get("ok"))
        row = {"model": mid, "note": note, "price_rub": rub, "seconds": secs,
               "ok": ok, "tier": r.get("tier"), "path": r.get("path"),
               "cost_usd": r.get("cost_usd"), "cost_source": r.get("cost_source"),
               "why": r.get("why") or (r.get("verdict") or {}).get("why"),
               "attempts": r.get("attempts")}
        rows.append(row)
        mark = "✅" if ok else "❌"
        print(f"      {mark} {secs:>6.1f}с · tier={row['tier']} · {row['path'] or row['why'] or ''}")

    good = [r for r in rows if r["ok"]]
    good_by_speed = sorted(good, key=lambda r: r["seconds"])
    good_by_price = sorted(good, key=lambda r: r["price_rub"])
    spent_rub = sum(r["price_rub"] for r in rows if r["tier"])       # платили и за отбитые кадры
    out = {"date": DATE, "provider": prov, "base_url": pf._base_url(),
           "subject": {"art": subj["art"], "name": subj["name"]},
           "canon": not args.no_canon, "retries": args.retries,
           "models_tried": len(plan), "models_ok": len(good),
           "spent_rub_est": spent_rub,
           "fastest": good_by_speed[0]["model"] if good_by_speed else None,
           "cheapest": good_by_price[0]["model"] if good_by_price else None,
           "rows": rows}
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    L = [f"# КУЗНИЦА ФОТО · ЗАМЕР {DATE}", "",
         f"- коннектор: `{prov}` · {pf._base_url()}",
         f"- товар: {subj['name']} `{subj['art']}`",
         f"- канон: {'вкл' if not args.no_canon else 'выкл'} · годных {len(good)}/{len(plan)}"
         f" · расход ~{spent_rub:.1f}₽",
         "", "| модель | ₽ | сек | итог | tier | кадр |", "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (not r["ok"], r["seconds"])):
        L.append(f"| `{r['model']}` | {r['price_rub']:.1f} | {r['seconds']:.1f} | "
                 f"{'✅' if r['ok'] else '❌'} | {r['tier'] or '—'} | {Path(r['path']).name if r['path'] else '—'} |")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print("\n──────── ЗАМЕР ────────")
    print(f"годных: {len(good)}/{len(plan)} · расход ~{spent_rub:.1f}₽")
    if good_by_speed:
        print(f"самая быстрая: {good_by_speed[0]['model']} — {good_by_speed[0]['seconds']}с")
    if good_by_price:
        print(f"самая дешёвая: {good_by_price[0]['model']} — {good_by_price[0]['price_rub']}₽")
    print(f"артефакт: {OUT_JSON.name} (+md) · кадры: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
