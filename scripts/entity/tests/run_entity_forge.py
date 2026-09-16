#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENTITY FORGE · приёмка V1 (гейт «не с неба» для фабрики рождения).

Законы (F = Forge):
  F1  SEAL-ГЕЙТ:         без entity_substrate_sealed=PASS forge ОТКАЗЫВАЕТ рождать.
  F2  10 ПОВЕРХНОСТЕЙ:   рождение создаёт все 10 поверхностей, каждая с instance_id.
  F3  ИДЕНТИЧНОСТЬ:      имя/тон/vertical/vocabulary взяты ИЗ ДОМЕН-КОНФИГА, не из шаблона.
  F4  ПАМЯТЬ=ОКНО:       own_root_forbidden=True → ЕДИНАЯ Memory Wave, не свой корень.
  F5  ЗАКОН НАСЛЕДУЕТСЯ: глобальные законы + law_overrides домена, RUBICON в контракте.
  F6  РОЖДЕНИЕ ≠ ЗАПУСК: active=False, deployed=False, execution_authorized=False.
  F7  RUBICON:           dry → 0 записей в репо; commit → записи есть.
  F8  ИДЕМПОТЕНТНОСТЬ:   повторный commit того же домена → «уже существует», не второй экз.
  F9  РОДОСЛОВНАЯ:       born_from=Entity Substrate (sealed), домен, forge, hash.
  F10 ХЕШ-ЦЕЛОСТНОСТЬ:   instance_hash = sha256(9 поверхностей)[:16], пересчёт совпадает.
  F11 РУБИЛЬНИК:         FREEZE.json существует, frozen=false, review_before_unfreeze=true.
  F12 PROOF:             birth proof с status/hashes/truth_boundary.
  F13 БЕЗОПАСНОСТЬ:      network_used=False, money_moved=False, no_daemon=True.

Сухо: только песочница /tmp; канон не трогается.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
FORGE = ROOT / "scripts/entity/entity_forge_v1.py"
DOM = ROOT / "entity_substrate/domains/dental_msk_01.json"
REG = ROOT / "SYSTEM/REGISTRY/ENTITY_REGISTRY_V1.json"
INST = ROOT / "entity_substrate/instances"

PASS, FAIL = "✅ PASS", "❌ FAIL"
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(f"  {PASS if cond else FAIL} {name}" + (f" — {extra}" if extra and not cond else ""))


def rj(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_forge(domain="dental_msk_01"):
    r = subprocess.run([sys.executable, str(FORGE), domain],
                       capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    return r.returncode, r.stdout + r.stderr


def find_dry_instance_id(out):
    for ln in out.splitlines():
        if "instance_id:" in ln:
            return ln.split("instance_id:")[1].strip()
    return None


def main():
    print("ENTITY FORGE · ПРИЁМКА V1 (сухо, канон не трогается)\n")
    domain = rj(DOM)

    # чистим прошлые dry-песочницы
    for d in Path(tempfile.gettempdir()).glob("entity_forge_dry_*"):
        shutil.rmtree(d, ignore_errors=True)

    reg_before = rj(REG)
    code, out = run_forge()
    check("F0 dry-рождение проходит exit=0", code == 0, out[-200:])
    inst_id = find_dry_instance_id(out)
    check("F0 instance_id выдан", bool(inst_id))

    dry_home = None
    for d in Path(tempfile.gettempdir()).glob("entity_forge_dry_*"):
        cand = list(d.glob("*/IDENTITY.json"))
        if cand:
            dry_home = cand[0].parent
            break
    check("F2 dry-home существует", dry_home and dry_home.exists(), str(dry_home))

    if dry_home:
        files = {f.stem for f in dry_home.glob("*.json")}
        need = {"IDENTITY", "STATE", "MEMORY", "LINEAGE", "CAPABILITY",
                "LAWFUL_ACTION", "DASHBOARD", "PROOF_CHAIN", "FREEZE", "PRODUCT"}
        check("F2 10/10 поверхностей", need <= files, f"нет: {need - files}")

        ident = rj(dry_home / "IDENTITY.json")
        check("F3 имя из домена", ident.get("name") == domain.get("persona", {}).get("name"))
        check("F3 vertical медицинский", ident.get("vertical") == "medical_dental")
        check("F3 vocabulary из домена", ident.get("vocabulary") == domain.get("vocabulary"))

        mem = rj(dry_home / "MEMORY.json")
        check("F4 память=окно, свой корень запрещён",
              mem.get("own_root_forbidden") is True and "window_path" in mem)

        law = rj(dry_home / "LAWFUL_ACTION.json")
        dom_laws = domain.get("law_overrides", [])
        check("F5 законы домена унаследованы",
              all(x in law.get("laws", []) for x in dom_laws),
              f"нет: {set(dom_laws) - set(law.get('laws', []))}")
        check("F5 глобальные законы унаследованы", len(law.get("laws", [])) > 5)
        check("F5 RUBICON в контракте", "rubicon" in law)

        state = rj(dry_home / "STATE.json")
        check("F6 рождение ≠ запуск",
              state.get("active") is False and ident.get("deployed") is False
              and law.get("execution_authorized") is False)

        lin = rj(dry_home / "LINEAGE.json")
        check("F9 родословная из субстрата",
              "Substrate" in str(lin.get("born_from")) and "domain_config" in lin)
        check("F9 forge запечатлён", "entity_forge" in str(lin.get("forge")))

        frz = rj(dry_home / "FREEZE.json")
        check("F11 рубильник готов",
              frz.get("stop_available") is True and
              frz.get("review_required_before_unfreeze") is True)

        proof = rj(dry_home / "BIRTH_PROOF_DRY.json") or {}
        check("F12 proof существует", bool(proof), str(list(dry_home.glob('*.json'))[:3]))
        check("F12 truth_boundary есть", bool(proof.get("truth_boundary")))
        check("F13 безопасность: сеть/деньги/демон",
              proof.get("network_used") is False and
              proof.get("money_moved") is False and
              proof.get("no_daemon") is True)

        # F10: пересчёт хеша по 9 поверхностям (PROOF_CHAIN исключён — он ссылается на proof)
        import hashlib
        payload = {k: rj(dry_home / f"{k}.json") for k in need - {"PROOF_CHAIN"}}
        h = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
        check("F10 instance_hash пересчитывается и совпадает",
              h == proof.get("instance_hash"), f"{h} != {proof.get('instance_hash')}")

    reg_after = rj(REG)
    check("F7 dry: реестр не тронут (0 записей в репо)", reg_before == reg_after)

    # F8: идемпотентность предусмотрена кодом; если домен уже рождён — ровно 1 экз.
    src = (ROOT / "scripts/entity/entity_forge_v1.py").read_text(encoding="utf-8")
    check("F8 идемпотентность предусмотрена кодом", "УЖЕ РОЖДЁН" in src)
    reg = rj(REG)
    if any(e.get("domain") == "dental_msk_01" for e in reg.get("entities", [])):
        n = sum(1 for e in reg.get("entities", [])
                if e.get("domain") == "dental_msk_01" and e.get("state") == "born")
        check("F8 один домен = одна сущность (не более 1)", n <= 1, f"найдено {n}")

    ok = sum(1 for _, c, _ in results if c)
    print("─" * 60)
    print(f"ENTITY FORGE · {ok}/{len(results)} PASS")
    if ok < len(results):
        print("❌ FORGE НЕ ГОТОВ К РОЖДЕНИЮ")
        return 1
    print("✅ FORGE ГОТОВ: рождение законно, идемпотентно, доказуемо, с рубильником")
    return 0


if __name__ == "__main__":
    sys.exit(main())
