# Дисциплина линий — Direction V1 (L0)  ·  RETIRED / MERGED

STATUS::RETIRED_SUPERSEDED
SUPERSEDED_BY::SYSTEM/LINE_GOVERNANCE/  (cell · line · gates · roadmap P0-P7 · genesis proof)

> 2026-06-30 (handoff оператора): этот дизайн оказался **дублем** органа `LINE_GOVERNANCE`,
> который параллельная линия довела до полноценного proof-chain органа. По решению оператора
> слито в один канон. Ничего не потеряно:
>
> - **Канон-дом** дисциплины линий: `SYSTEM/LINE_GOVERNANCE/` (формальный орган, многолетняя карта P0–P7).
> - **Рабочая реализация** (P1.5 socc-lines · P3 dedup · P4 handoff · P5 drift): `scripts/socc/socc_lines_v1.py`
>   — протестирована вживую, теперь операционный слой органа.
> - **Единый реестр**: `SYSTEM/LINE_GOVERNANCE/runtime/ACTIVE_LINES_REGISTRY_V1.json`
>   (observe-снимок P0 + операционные `lines[]`). Старый `SYSTEM/REGISTRY/LINE_REGISTRY_V1.json` — тумбстоун.
>
> Это и есть L0 в действии: дубль пойман честно, основная линия поглотила вторичную.
> Полный дизайн смотри в `SYSTEM/LINE_GOVERNANCE/LINE_GOVERNANCE_ROADMAP.md`.
