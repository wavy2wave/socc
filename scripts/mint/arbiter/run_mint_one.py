#!/usr/bin/env python3
"""Разовый минт одной карточки через forge() напрямую (CLI не отдаёт tag).

Использование: python3 run_mint_one.py --dry|--live [--tag X] [--facts '<json>']
Без --live = сухой гейт 0₽. --live = тратит ₽ из уже оплаченного канала.
"""
import argparse
import json
import sys

import photo_forge_v1 as pf

pf._ensure_env()

DEFAULT_FACTS = {
    "вид": "воздушно-пузырьковая плёнка в рулоне",
    "форма": "компактный рулон плёнки на картонной втулке",
    "цвет": "прозрачная",
    "материал": "тонкий полиэтилен с круглыми воздушными пузырьками",
    "ширина полотна": "40 см",
    "длина полотна": "2 м",
}

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--tag", default="ARB-56925082")
    ap.add_argument("--facts", default="")
    args = ap.parse_args(argv)

    facts = {}
    if args.facts:
        try:
            facts = json.loads(args.facts)
        except Exception as e:
            print("!! --facts не JSON:", e)
            return 2
    if not facts:
        facts = DEFAULT_FACTS

    dry = not args.live
    res = pf.forge(source=None, facts=facts, mode="generate", dry=dry,
                   model=None, out_dir="state/forged", tag=args.tag, canon=True)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1

if __name__ == "__main__":
    sys.exit(main())
