#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SOCC · ЯМ · ДОСЬЕ ДОНОР-КАТЕГОРИЙ — ПРИЁМКА (0₽, канон НЕ трогает).

Зачем: орган-слой «сделанной работы» (оператор: важное созданное → артефакт, переиспользуем в
любой момент). Проверяем на ПЛОСКОСТИ, которую видит оператор: реальный канон-стор читается,
зеркало .md не отстаёт, чистый мерж не мутирует вход, запись идёт только в env-песочницу (tmp),
валидатор ловит нечестный маппинг (D1: need_mapping=false при id=null — фейк).

Законы:
  D1  честность_маппинга  D2  вердикт_из_первоисточника  D3  зеркало_детерминировано
  D4  read_не_пишет (чтение/рендер/валидация не трогают канон)
Канон-стор: MEMORY_WAVE/reports/mint/arbiter/ymarket_categorist_dossiers.json
Запуск: python3 scripts/mint/arbiter/tests/run_dossiers_acceptance.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

SOCC = Path(__file__).resolve().parents[4]  # tests → arbiter → mint → scripts → SOCC
ARB = SOCC / "scripts/mint/arbiter"
if str(ARB) not in sys.path:
    sys.path.insert(0, str(ARB))

import ymarket_categorist_dossiers_v1 as D  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    print("📋 ЯМ · ДОСЬЕ ДОНОР-КАТЕГОРИЙ · приёмка (0₽, канон не трогает)")
    steps = []
    canon = D.dossier_path()

    # A1 канон читается и валиден
    d, err = D.load()
    ok = (not err) and (d or {}).get("schema") == D.SCHEMA
    ok_v, verr = (True, []) if ok else (False, ["стора нет"])
    if ok:
        ok_v, verr = D.validate(d)
    steps.append((f"A1 канон {canon.name}: schema OK · validate {'OK' if ok_v else verr}",
                  ok and ok_v))

    # A2 честное содержимое — DATA-AGNOSTIC инварианты. Автопилот/CATEGORIST 24/7 законно двигают
    #    досье (сухие сканы добавляются/пересканируются, маппинги подтверждаются): приёмка НЕ
    #    пинит число сканов/вердиктов/id, а проверяет САМОСОГЛАСОВАННОСТЬ стора + согласие с
    #    cats-каноном (анти-эхо, D1: id живёт ТОЛЬКО в cats — досье ссылается, не выдумывает).
    sub = []
    cats_canon = {}
    _cats = ARB / "ymarket_cats_v1.json"
    if _cats.exists():
        cats_canon = json.loads(_cats.read_text(encoding="utf-8")).get("categories") or {}
    _recs = list(d["categories"].items())
    n_total = len(_recs)
    n_done = sum(1 for _, r in _recs if r.get("state") == "done")
    n_open = sum(1 for _, r in _recs if r.get("state") != "done")
    n_scanned = sum(1 for _, r in _recs if r.get("scan"))   # тот же предикат, что в D.stats
    n_need_mapping = sum(1 for _, r in _recs if (r.get("mapping") or {}).get("need_mapping"))
    n_confirmed = sum(1 for _, r in _recs
                      if (r.get("mapping") or {}).get("market_category_id") is not None)
    st = D.stats(d)
    # (1) очередь не пуста и done+open==total; сводка модуля == пересчёт по записям (числам на
    #     слово не верим). Точные пины не ставим — очередь может законно расти.
    sub.append(n_total >= 6)
    sub.append((n_done + n_open) == n_total)
    sub.append(st == {"categories": n_total, "done": n_done, "open": n_open,
                      "scanned": n_scanned, "need_mapping": n_need_mapping,
                      "confirmed": n_confirmed})
    # (2) D1-самосогласованность маппинга: need_mapping=false ⇒ id задан, need_mapping=true ⇒ id
    #     null (фейк «гейт снят, а id не дали» и «ждём слова при уже данном id» = падение)
    sub.append(all((r.get("mapping") or {}).get("need_mapping") is False
                   and (r.get("mapping") or {}).get("market_category_id") is not None
                   for _, r in _recs if (r.get("mapping") or {}).get("need_mapping") is False))
    sub.append(all((r.get("mapping") or {}).get("need_mapping") is True
                   and (r.get("mapping") or {}).get("market_category_id") is None
                   for _, r in _recs if (r.get("mapping") or {}).get("need_mapping") is True))
    # (3) АНТИ-ЭХО по ВСЕМ подтверждённым id: где cats-канон дал id по ключу (mapping.cats_key,
    #     иначе слог) — досье обязано СОВПАСТЬ (связь = прямое имя слога или cats_key); разрыв
    #     ключа → id обязан хотя бы СУЩЕСТВОВАТЬ в cats (подмножество). Досье-выдумка (id нигде
    #     в cats) = падение — validate() этого не ловит (у него нет ссылки на cats).
    cats_id_by_key = {k: (v or {}).get("market_category_id") for k, v in cats_canon.items()}
    cats_id_set = {c for c in cats_id_by_key.values() if c is not None}
    anti_echo = True
    for _slug, _r in _recs:
        _m = _r.get("mapping") or {}
        _cid = _m.get("market_category_id")
        if _cid is None:
            continue
        _cats_ref = cats_id_by_key.get(_m.get("cats_key") or _slug)
        if _cats_ref is not None:
            anti_echo = anti_echo and _cid == _cats_ref     # cats решает — досье совпадает
        else:
            anti_echo = anti_echo and _cid in cats_id_set   # разрыв ключа — id всё равно из cats
    sub.append(bool(cats_canon) and anti_echo)
    # (4) scan-ИНТЕГРИТИ: каждый scan — dict с when/dry/verdict; каждая запись scan_history —
    #     dict с verdict (пустой scan={} / «забытая» история = падение)
    scan_integrity = True
    for _slug, _r in _recs:
        _sc = _r.get("scan")
        if _sc is None:
            continue
        scan_integrity = scan_integrity and isinstance(_sc, dict) \
            and all(k in _sc for k in ("when", "dry", "verdict"))
        for _h in _r.get("scan_history") or []:
            scan_integrity = scan_integrity and isinstance(_h, dict) and "verdict" in _h
    sub.append(scan_integrity)
    # уроки накапливаются (только растут) — падает, если орган срезал историю
    sub.append(len(d.get("lessons", [])) >= 6)
    steps.append((f"A2 содержимое самосогласовано: категорий {n_total} · done {n_done} + "
                  f"open {n_open} · scanned {n_scanned} · need_mapping {n_need_mapping} · "
                  f"confirmed {n_confirmed} · маппинги=CATS(анти-эхо) · scan-интегрити · "
                  f"lessons 6 → {'OK' if all(sub) else sub}", all(sub)))

    # A3 зеркало .md не отстало (рендер == файл, байт-в-байт)
    md = D.md_path()
    synced = md.exists() and md.read_text(encoding="utf-8") == "\n".join(D.render(d)) + "\n"
    steps.append((f"A3 зеркало .md синхронно с JSON (render==файл, D3): {md.name} "
                  f"{'OK' if synced else 'STALE'}", synced))

    # A4 чистый мерж record_scan: вход НЕ мутируется + прежний скан уходит в scan_history
    #    (хронология, D2 — история, не выдумка). DATA-AGNOSTIC: цели из РАНТАЙМА — (а) категория
    #    со scan:null (свежий скан без истории), (б) любая просканированная (перезапись вердикта).
    #    Глубокая сверка стора (json round-trip) до/после — вход обязан остаться байт-в-байт цел.
    _snap = json.loads(json.dumps(d))                      # глубокая копия стора (round-trip)
    _none_slugs = [s for s, r in d["categories"].items() if r.get("scan") is None]
    _scan_slugs = [s for s, r in d["categories"].items() if r.get("scan") is not None]
    _fake = {"when": "2026-09-05 00:00:00", "dry": True, "verdict": "ready_shortlist",
             "artifacts": ["x.json"], "readiness": {"ready": 1}}
    a4_ok = True
    # (а) свежий скан поверх scan:null → истории не добавилось, вход цел, вердикт смёржен
    if _none_slugs:
        tgt = _none_slugs[0]
        _hist_before = len(D.get(d, tgt).get("scan_history") or [])
        merged = D.record_scan(d, tgt, _fake)
        rec = D.get(merged, tgt)
        a4_ok = a4_ok and (d == _snap) and rec["scan"]["verdict"] == "ready_shortlist" \
            and len(rec.get("scan_history") or []) == _hist_before
    # (б) ПЕРЕЗАПИСЬ просканированной: прежний вердикт честно дописывается в ХВОСТ scan_history
    #     (append; у streich уже 2 записи) — история не теряется при законном ре-скане
    if _scan_slugs:
        tgt = _scan_slugs[0]
        _prev = D.get(d, tgt)["scan"]
        _h0 = len(D.get(d, tgt).get("scan_history") or [])
        merged = D.record_scan(d, tgt,
                               {"when": "2026-09-05 00:00:00", "dry": True, "verdict": "blocked"})
        rec = D.get(merged, tgt)
        _hist = rec.get("scan_history") or []
        a4_ok = a4_ok and (d == _snap) and rec["scan"]["verdict"] == "blocked" \
            and len(_hist) == _h0 + 1 and _hist[-1] == _prev    # прежний вердикт цел, в хвосте
    steps.append((f"A4 чистый мерж: вход НЕ мутирован ({d == _snap}) · цель из рантайма "
                  f"{(_none_slugs or ['-'])[0]}/{(_scan_slugs or ['-'])[0]} · вердикт смёржен · "
                  f"прежний скан в истории", a4_ok))

    # A5 запись герметична: env YM_DOSSIERS_PATH → tmp; канон не меняется
    h_before = sha(canon)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "dossiers.json"
        res = D.save(merged, path=tmp)
        ok_save = bool(res.get("ok")) and tmp.exists()
        back, berr = D.load(path=tmp)
        roundtrip = (not berr) and back == merged
        md_tmp_synced = tmp.with_suffix(".md").exists()
    h_after = sha(canon)
    steps.append((f"A5 песочница: save в tmp ({ok_save}) · round-trip байт-в-байт ({roundtrip}) · "
                  f".md-зеркало рядом ({md_tmp_synced}) · канон НЕ изменён "
                  f"({h_before == h_after})", ok_save and roundtrip and md_tmp_synced and h_before == h_after))

    # A6 валидатор ловит нечестный маппинг (D1: need_mapping=false при id=null)
    bad = {k: v for k, v in d["categories"].items()}
    bad["streich-plenka"] = {"donor_category": "streich-plenka", "state": "open",
                             "mapping": {"need_mapping": False, "market_category_id": None}}
    okb, verrb = D.validate({"schema": D.SCHEMA, "categories": bad})
    caught = (not okb) and any("D1" in e for e in verrb)
    steps.append((f"A6 валидатор ловит фейк (need_mapping=false, id=null) → {'OK' if caught else 'MISS'}",
                  caught))

    # A7 CLI read-рендер жив и 0-записей (подкапотная проверка render). DATA-AGNOSTIC: слоги из
    #    РАНТАЙМА — просканированная (вердикт виден, НЕ маркер «не была») и, если есть, ещё не
    #    просканированная (честный маркер «НЕ прогонялась», D2). Все просканированы → честное
    #    all-scanned состояние: маркера нет ни у одной.
    _marker = "НЕ прогонялась"
    _scanned_slug = next((s for s, r in d["categories"].items() if r.get("scan") is not None), None)
    _unscanned_slug = next((s for s, r in d["categories"].items() if r.get("scan") is None), None)
    full = "\n".join(D.render(d))
    scanned_ok = False
    if _scanned_slug is not None:
        _verdict = (D.get(d, _scanned_slug).get("scan") or {}).get("verdict")
        _one_scanned = "\n".join(D.render(d, slug=_scanned_slug))
        scanned_ok = (_verdict is not None and f"## {_scanned_slug}" in _one_scanned
                      and _verdict in _one_scanned and _marker not in _one_scanned)
    if _unscanned_slug is not None:
        _one_open = "\n".join(D.render(d, slug=_unscanned_slug))
        open_ok = f"## {_unscanned_slug}" in _one_open and _marker in _one_open
    else:                                                   # все просканированы (честно)
        open_ok = all(_marker not in "\n".join(D.render(d, slug=s)) for s in d["categories"])
    _sc_txt = (f"просканированная '{_scanned_slug}' видит вердикт" if _scanned_slug
               else "просканированных нет")
    _op_txt = (f"открытая '{_unscanned_slug}' честно НЕ прогонялась" if _unscanned_slug
               else "все просканированы: маркера нет нигде")
    steps.append((f"A7 render: полный {len(full)} симв · {_sc_txt} ({scanned_ok}) · "
                  f"{_op_txt} ({open_ok})", scanned_ok and open_ok))

    all_ok = True
    for label, okstep in steps:
        print(f"   {'✅' if okstep else '❌'} {label}")
        all_ok = all_ok and okstep
    print("\nИтого: " + ("✅ Досье-канон жив: читается · честен · зеркало синхронно · мерж чист · запись только в песочницу" if all_ok else "❌ есть падения"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
