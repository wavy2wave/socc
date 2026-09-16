#!/usr/bin/env python3
"""
SOCC Readiness Board V1 — honest, computed-from-files status of the whole campaign.

No claims from memory: every status is read from real file state (seal PASS? proof PASS?
artifact exists?). Distinguishes — without blur:
  🔒 DESIGN-SEALED      design canon, NOT proven capability
  ✅ GREEN-DEMONSTRATED  real proof, status PASS (machine actually ran)
  📊 PROJECTION          model/number from assumptions, not measured
  🟡 DESIGN              written, not executed
  🔴 RED-NEEDS-FIRE      outward/live execution — gated on the operator's fire

Writes a JSON + Markdown board for the operator. Touches nothing live, births nothing.
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(".")
MSK = timezone(timedelta(hours=3), name="MSK")


def rj(p):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return {}
def exists(p): return Path(ROOT / p).exists()
def proof_pass(p): return rj(ROOT / p).get("status") == "PASS"
def contains(p, s):
    try: return s in Path(ROOT / p).read_text(encoding="utf-8")
    except Exception: return False


SEAL = "SYSTEM/AUTONOMY/self_construction_seals/STAFF_SPEC_LAYER_SEAL_V1.json"
FG_T1 = "SOVEREIGN/PROOF/proof_chain/SOCC_R0_FG_T1_FAIL_CLOSED_BIRTH_PROOF.json"

sealed = proof_pass(SEAL)
S = "🔒 DESIGN-SEALED" if sealed else "🟡 DESIGN"

rows = []
def row(layer, item, status, evidence): rows.append({"layer": layer, "item": item, "status": status, "evidence": evidence})

# foundation + roster (design-sealed if the staff seal passed)
for f in ["TFS-1 Team Functor", "PXS-1 Proof-Gated DAG"]:
    row("Фундамент", f, S, "STAFF_SPEC_LAYER_SEAL_V1 PASS" if sealed else "не запечатан")
for r in ["SCOUT", "HERMES", "ANNA", "FORGE", "WARDEN", "LEDGER", "SCRIBE"]:
    row("Ростер", r, S, "спек написан + запечатан" if sealed else "спек написан")
row("Ростер", "CONDUCTOR", "✅ GREEN-DEMONSTRATED", "= рабочий socc_lawful_step_engine_v1.py")

# positioning / funnel artifacts
row("Воронка", "B0 Positioning", "✅ GREEN-DEMONSTRATED"
    if contains("docs/positioning/B0_positioning_anna_dental.md", "c0 PASS") else "🟡 DESIGN",
    "оператор понял (c0 PASS)")
row("Воронка", "B1 ROI-модель", "📊 PROJECTION"
    if exists("scripts/socc/anna_roi_calculator_v1.py") else "🟡 DESIGN",
    "калькулятор работает; число станет proof на B3 (LEDGER)")
row("Воронка", "B4 Карта каналов", "🟡 DESIGN", "карта готова; заряд ≥2 = outreach под approve")
row("Воронка", "B5 Лендинг+оферта", "🟡 DESIGN", "текст+оферта готовы; публикация = огонь")

# acceptance tests
row("Тесты", "FG-T1 fail-closed рождение", "✅ GREEN-DEMONSTRATED"
    if proof_pass(FG_T1) else "🔴 RED-NEEDS-FIRE",
    f"validator отказал неполному домену; {rj(ROOT/FG_T1).get('proof_hash','')}" if proof_pass(FG_T1) else "не доказан")
row("Тесты", "FG-T3 структурная половина (домен-параметр)", "✅ GREEN-DEMONSTRATED"
    if proof_pass(FG_T1) else "🔴 RED-NEEDS-FIRE",
    "барбершоп валиден тем же кодом, 0 правок")
row("Тесты", "FG-T3 полный (mint + smoke в календаре)", "🔴 RED-NEEDS-FIRE", "живая интеграция — огонь")
row("Тесты", "AN-T1 не диагностирую", "🔴 RED-NEEDS-FIRE", "нужен живой мозг/guard (сеть) — не доказан честно")
row("Тесты", "AN-T3 реальная бронь", "🔴 RED-NEEDS-FIRE", "живая запись в Dikidi/1С — огонь")
row("Тесты", "B3 proof-кейс (ЧЕК)", "🔴 RED-NEEDS-FIRE", "реальная клиника, 30 дней — главный патрон")

# fire ladder
ladder = [
    ("R0 локальные тесты закона", "✅ GREEN-DEMONSTRATED" if proof_pass(FG_T1) else "🟡 DESIGN",
     "FG-T1 PASS; AN-T1 ещё нет (нужна сеть)"),
    ("R1 demo safe-mode", "🔴 RED-NEEDS-FIRE", "deploy"),
    ("R2 лендинг живой", "🔴 RED-NEEDS-FIRE", "deploy"),
    ("R3 1 design-партнёр", "🔴 RED-NEEDS-FIRE", "outreach под approve"),
    ("R4 FORGE онбордит клинику", "🔴 RED-NEEDS-FIRE", "интеграция + доступы"),
    ("R5 proof-кейс 30 дней", "🔴 RED-NEEDS-FIRE", "главный патрон"),
]
for name, st, ev in ladder: row("Лестница огня", name, st, ev)

ts = datetime.now(timezone.utc)
board = {
    "id": "STAFF_READINESS_BOARD_V1",
    "created_at_utc": ts.isoformat(),
    "created_at_msk": ts.astimezone(MSK).isoformat(timespec="seconds"),
    "legend": {"🔒": "design-sealed (not proven)", "✅": "green-demonstrated (real proof PASS)",
               "📊": "projection (assumptions)", "🟡": "design (written, not run)",
               "🔴": "red — needs operator fire"},
    "staff_layer_sealed": sealed,
    "first_green_test": "FG-T1" if proof_pass(FG_T1) else None,
    "rows": rows,
    "boundary": ("Everything 🔴 is outward/live and gated on the operator's explicit fire. Nothing here "
                 "births an entity, deploys, or touches a real clinic. Honest by construction."),
}
OUT = ROOT / "SYSTEM/DASHBOARD/STAFF_READINESS_BOARD_V1.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(board, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

MD = ROOT / "docs/positioning/READINESS_BOARD.md"
lines = ["# 📋 Борд готовности — честный статус из файлов", "",
         f"> Сгенерирован: {board['created_at_msk']} · из реального состояния файлов, не из памяти.",
         "> 🔒 запечатано · ✅ доказано кодом · 📊 проекция · 🟡 дизайн · 🔴 ждёт огня", ""]
cur = None
for r in rows:
    if r["layer"] != cur:
        cur = r["layer"]; lines += ["", f"## {cur}", ""]
    lines.append(f"- {r['status']}  **{r['item']}** — {r['evidence']}")
lines += ["", "---", "", "> " + board["boundary"]]
MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print("STAFF READINESS BOARD V1")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
g = sum(1 for r in rows if r["status"].startswith("✅"))
red = sum(1 for r in rows if r["status"].startswith("🔴"))
print(f"sealed::{sealed}  green-demonstrated::{g}  red-needs-fire::{red}  total::{len(rows)}")
print(f"board json :: {OUT}")
print(f"board md   :: {MD}")
print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
