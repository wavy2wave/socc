# CURRENT PROJECT ORDER V1

STATUS::ACTIVE  
UPDATED::2026-07-13  
DECISION::**Mint first ₽** (agent chose; operator asked to choose)

## Decision

| Rank | Path | Why |
|---|---|---|
| 1 | **Mint D2** — bot 1500 ₽ → NPD → `record --commit` | Fastest real money; runbook ready; no clinic trust wall |
| 2 | ANNA key health only | Needed later for live demo; blocked 403 today |
| later | ANNA pilot / ship | After M1 (₽) + A0 (health) |

## Active line

`ln-cee92000` · M1 · *MINT first ₽: демо-бот + отклики → сделка → чек → record*

## Assets ready

- `scripts/mint/botfactory/` — acceptance 5/5, aiogram in `.venv`
- `scripts/mint/botfactory/config.demo_prodazha.json` — sales demo config
- `scripts/mint/P3_FIRST_LEAD_RUNBOOK.md`, `M1_CLOSE.md`
- `scripts/mint/socc_mint_record_v1.py` — RUBICON writer

## Blockers

- real_money = 0 (world action, not code)
- ANNA brain DEAD 403 (parallel, ≤30 min when key exists)
- demo needs BotFather token + owner_chat_id (operator)

## Operator 48h checklist

1. [ ] BotFather token for demo bot  
2. [ ] Set `owner_chat_id` in demo config  
3. [ ] Run: `BOT_TOKEN=… .venv/bin/python socc_botfactory_v1.py config.demo_prodazha.json`  
4. [ ] 45 min demand scan  
5. [ ] ≥10 marketplace replies with demo link  
6. [ ] On payment: NPD + `socc_mint_record_v1.py --commit`  

## Warehouse

MIGRATION, MEMORY_WAVE bulk, self-building, cold clinics list, brand expansion, mint multi-universe.
