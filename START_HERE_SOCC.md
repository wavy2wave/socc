# START HERE — SOCC (agents)

ROOT: `/Users/wavysexy/SOCC`

## Decision (2026-07-13)

**Main cash path: Mint first verified ₽** (Telegram auto-reply bot ~1500 ₽).  
ANNA: background key/health only until M1 closed.  
Do not expand SOCC meta, cold clinics, or new top-level folders.

## Operator surfaces

- Human map: `START_HERE.md`
- Order: `SYSTEM/STATUS/CURRENT_PROJECT_ORDER_V1.md`
- Goal: `SOCC_GOAL.json`
- Line: `ln-cee92000` (M1)

## Code assets for cash

```bash
cd scripts/mint/botfactory
.venv/bin/python socc_botfactory_v1.py --check config.demo_prodazha.json
# BOT_TOKEN=... .venv/bin/python socc_botfactory_v1.py config.demo_prodazha.json
# after real payment + NPD:
# python3 scripts/mint/socc_mint_record_v1.py --service "..." --amount 1500 ... --commit
```

## Rule

Prefer marketplace replies and deal close over new code. Code only if bot delivery is broken.
