#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot-Factory acceptance V1 — фальсифицируемые тесты фабрики (BF-T1..BF-T5). Чистый stdlib, без aiogram/сети.

Зелёный набор ⟺ фабрика работает: валидный конфиг проходит, кривой режется, FAQ матчит, заявка собирается
корректно, новый клиент создаётся одной командой.
"""
import sys
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import socc_botfactory_v1 as bf  # noqa: E402


def check(name, passed, detail=""):
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))
    return passed


def run():
    results = []
    sample = bf.load_config(HERE / "config.sample.json")

    # BF-T1 config-valid: образец проходит валидацию.
    results.append(check("BF-T1 config-valid", bf.validate_config(sample) == [], "sample.json валиден"))

    # BF-T2 config-rejects: кривые конфиги режутся (каждый — отдельная провальная проверка).
    no_name = dict(sample); no_name.pop("business_name")
    empty_menu = dict(sample); empty_menu["menu"] = []
    lead_no_cfg = {"business_name": "x", "welcome": "w",
                   "menu": [{"label": "Заявка", "answer": bf.LEAD}]}  # __LEAD__ без lead/owner
    bad_owner = dict(sample); bad_owner["owner_chat_id"] = "не число"
    rej = [bf.validate_config(c) != [] for c in (no_name, empty_menu, lead_no_cfg, bad_owner)]
    results.append(check("BF-T2 config-rejects", all(rej), "нет имени / пустое меню / __LEAD__ без lead / owner не число"))

    # BF-T3 faq-match: свободный текст матчит ответ; мусор → None (покажется меню).
    hit = bf.match_faq(sample, "а сколько стоит стрижка?")
    miss = bf.match_faq(sample, "погода сегодня хорошая")
    results.append(check("BF-T3 faq-match", bool(hit) and miss is None, f"'сколько' → ответ про цену; мусор → None"))

    # BF-T4 lead-payload: заявка владельцу содержит данные + отметку согласия.
    p = bf.lead_payload(sample, {"Имя": "Пётр", "Телефон": "+79990001122"}, ts="2026-06-30 10:00 UTC")
    t4 = "Пётр" in p and "+79990001122" in p and "Согласие" in p and sample["business_name"] in p
    results.append(check("BF-T4 lead-payload", t4, "имя+телефон+согласие в сообщении владельцу"))

    # BF-T5 scaffold: новый клиент = одна команда → валидный конфиг.
    with tempfile.TemporaryDirectory() as d:
        path = bf.scaffold_new("Кафе Уют", out_dir=d)
        new_cfg = bf.load_config(path)
        t5 = path.exists() and new_cfg["business_name"] == "Кафе Уют" and bf.validate_config(new_cfg) == []
    results.append(check("BF-T5 scaffold-new", t5, "scaffold_new → валидный конфиг нового клиента"))

    print()
    ok = all(results)
    print(f"ИТОГО: {sum(results)}/{len(results)} зелёных — "
          f"{'ФАБРИКА БОТОВ ГОТОВА' if ok else 'ФАБРИКА КРИВАЯ — ЧИНИТЬ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
