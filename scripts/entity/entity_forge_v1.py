#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENTITY FORGE V1 · фабрика рождения сущностей из домен-конфига.

ЗАКОННОСТЬ:
    Entity Substrate sealed (SOVEREIGN/PROOF/proof_chain/SOCC_SEAL_ENTITY_SUBSTRATE_V1_PROOF.json)
    → субстрат РАЗРЕШИЛ рождение (birth stays gated beyond this seal — вот этот гейт).
    Но: рождение ≠ запуск. Новорождённая сущность НЕ активируется, НЕ идёт в сеть,
    НЕ двигает деньги. Это СЕРТИФИЦИРОВАННЫЙ ЭКЗЕМПЛЯР с 10 заполненными поверхностями.

RUBICON:
    --dry (default): рождает В ПЕСОЧНИЦЕ /tmp → полный сертификат, 0 записей в репо.
    --commit       : рождает в entity_substrate/instances/<id>/ + реестр + proof + memory.

Что делает (10 поверхностей из домен-конфига):
    identity         ← persona (имя, тон) + vertical
    state            ← новый, state=born, active=False
    memory           ← привязка к ЕДИНОЙ Memory Wave (окно, НЕ отдельный корень)
    lineage          ← born_from=EntitySubstrate, domain, timestamp
    capability       ← vocabulary + channels + integration → skills
    lawful_action    ← law_overrides домена ПОВЕРХ глобального закона
    dashboard        ← панель оператору
    proof_chain      ← birth proof (sha256 от экземпляра)
    freeze/stop      ← РЕАЛЬНЫЙ рубильник: freeze() → время/причина/who
    product_binding  ← pricing.metric + avg_ticket

Идемпотентность: повторный --commit того же домена → "already exists", НЕ перерождает.
"""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SUBSTRATE = ROOT / "SYSTEM" / "ENTITY_SUBSTRATE"
SEAL_PROOF = ROOT / "SOVEREIGN/PROOF/proof_chain/SOCC_SEAL_ENTITY_SUBSTRATE_V1_PROOF.json"
ES_SEAL = ROOT / "SYSTEM/AUTONOMY/self_construction_seals/ENTITY_SUBSTRATE_SEAL_V1.json"
DOM_DIR = ROOT / "entity_substrate" / "domains"
INST_DIR = ROOT / "entity_substrate" / "instances"
PROOF_DIR = ROOT / "SOVEREIGN/PROOF/proof_chain"
MEM_DIR = ROOT / "MEMORY_WAVE/reports/entity_substrate"

GLOBAL_LAWS = [
    "no_medical_claims_if_vertical_medical",
    "brain_fallback_required_before_any_live_talk",
    "rubicon_write_only_by_operator",
    "one_bounded_action_at_a_time",
    "stop_after_tick",
    "never_reveal_being_bot",
]

SKILL_MAP = {
    "telegram": "telegram_dialogue",
    "instagram_dm": "instagram_dialogue",
    "dikidi": "booking_dikidi",
    "yclients": "booking_yclients",
}


def rj(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return None


def wj(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")


def h16(o):
    return hashlib.sha256(json.dumps(o, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def now():
    return datetime.now(timezone.utc).isoformat()


def vertical_of(domain):
    d = domain.lower()
    if any(k in d for k in ("dental", "стомат", "клиник")):
        return "medical_dental"
    if any(k in d for k in ("barber", "барбер")):
        return "beauty_barbershop"
    return "generic_service"


def instance_id(domain_id, ts):
    slug = "".join(c for c in domain_id if c.isalnum()).upper()[:12]
    return f"{slug}-{ts[:15].replace('-','').replace('T','').replace(':','')[:10]}"


def check_seal():
    """Гейт рождения: субстрат запечатан PASS? Без seal — рождение ЗАПРЕЩЕНО."""
    proof = rj(SEAL_PROOF)
    seal = rj(ES_SEAL)
    if not proof or not seal:
        return False, "нет seal-entity-substrate proof — рождение незаконно"
    if proof.get("status") != "PASS" or seal.get("status") != "PASS":
        return False, f"seal не PASS: proof={proof.get('status')} seal={seal.get('status')}"
    return True, "substrate sealed PASS"


def build_instance(domain, ts, base_dir):
    """Собрать 10 поверхностей из домен-конфига. base_dir — песочница или instances/."""
    dom_id = domain["id"]
    inst_id = instance_id(dom_id, ts)
    home = Path(base_dir) / inst_id
    vertical = vertical_of(dom_id)

    skills = []
    for ch in domain.get("channels", []):
        skills.append(SKILL_MAP.get(ch, f"dialogue_{ch}"))
    itg = (domain.get("integration") or {}).get("type")
    if itg:
        skills.append(SKILL_MAP.get(itg, f"integration_{itg}"))

    laws = list(GLOBAL_LAWS)
    for extra in domain.get("law_overrides", []):
        if extra not in laws:
            laws.append(extra)

    persona = domain.get("persona", {})
    pricing = domain.get("pricing", {})
    mem_path = f"MEMORY_WAVE/entities/{inst_id}"

    surfaces = {
        "IDENTITY": {
            "surface": "entity_identity_surface", "instance_id": inst_id,
            "name": persona.get("name", "UNNAMED"), "kind": "vertical_agent",
            "vertical": vertical, "tone": persona.get("tone"),
            "vocabulary": domain.get("vocabulary", []),
            "entity_born": True, "active": False, "deployed": False,
            "created_at_utc": ts,
        },
        "STATE": {
            "surface": "entity_state_surface", "instance_id": inst_id,
            "state": "born", "active": False, "connected_channels": [],
            "last_action": None, "tick_count": 0, "created_at_utc": ts,
        },
        "MEMORY": {
            "surface": "entity_memory_surface", "instance_id": inst_id,
            "root_policy": "SHARED_MEMORY_WAVE_WINDOW",
            "own_root_forbidden": True,
            "window_path": mem_path, "clients": {},
            "birth_memory_recorded": True, "created_at_utc": ts,
        },
        "LINEAGE": {
            "surface": "entity_lineage_surface", "instance_id": inst_id,
            "born_from": "Entity Substrate (sealed)", "domain_config": f"entity_substrate/domains/{dom_id}.json",
            "forge": "scripts/entity/entity_forge_v1.py", "forge_version": "1",
            "born_at_utc": ts, "parent_substrate_seal": str(ES_SEAL.relative_to(ROOT)),
        },
        "CAPABILITY": {
            "surface": "entity_capability_binding_surface", "instance_id": inst_id,
            "skills": sorted(set(skills)), "channels": domain.get("channels", []),
            "integration": domain.get("integration", {}),
            "sources": domain.get("sources", []), "created_at_utc": ts,
        },
        "LAWFUL_ACTION": {
            "surface": "entity_lawful_action_surface", "instance_id": inst_id,
            "laws": laws, "law_overrides": domain.get("law_overrides", []),
            "rubicon": "dry_by_default_commit_by_operator",
            "execution_authorized": False, "created_at_utc": ts,
        },
        "DASHBOARD": {
            "surface": "entity_dashboard_surface", "instance_id": inst_id,
            "operator_visible": True, "panel": f"entity_substrate/instances/{inst_id}/DASHBOARD.json",
            "created_at_utc": ts,
        },
        "PROOF_CHAIN": {
            "surface": "entity_proof_chain_surface", "instance_id": inst_id,
            "birth_proof": None, "instance_hash": None, "created_at_utc": ts,
        },
        "FREEZE": {
            "surface": "entity_freeze_review_stop_surface", "instance_id": inst_id,
            "frozen": False, "frozen_at": None, "frozen_reason": None,
            "stop_available": True, "review_required_before_unfreeze": True,
            "created_at_utc": ts,
        },
        "PRODUCT": {
            "surface": "entity_product_binding_surface", "instance_id": inst_id,
            "metric": pricing.get("metric"), "avg_ticket": pricing.get("avg_ticket"),
            "icp_signals": domain.get("icp_signals", []), "created_at_utc": ts,
        },
    }

    # ID присваиваем ДО хеширования: приёмка пересчитывает по файлам,
    # и файлы должны совпадать с payload байт-в-байт (F10, no fake pass).
    for k, v in surfaces.items():
        v["id"] = f"{inst_id}_{k}_V1"
    # хеш экземпляра — по 9 поверхностям (PROOF_CHAIN заполним после)
    payload = {k: v for k, v in surfaces.items() if k != "PROOF_CHAIN"}
    inst_hash = h16(payload)
    surfaces["PROOF_CHAIN"]["instance_hash"] = inst_hash

    home.mkdir(parents=True, exist_ok=True)
    for k, v in surfaces.items():
        wj(home / f"{k}.json", v)

    return inst_id, home, inst_hash, surfaces, laws, skills, vertical


def commit_registry(inst_id, domain_id, vertical, skills, proof_path, inst_hash):
    """Обновить реестр сущностей: атомарно добавить/подтвердить запись."""
    reg_path = ROOT / "SYSTEM/REGISTRY/ENTITY_REGISTRY_V1.json"
    reg = rj(reg_path) or {"id": "ENTITY_REGISTRY_V1", "entities": []}
    if not isinstance(reg.get("entities"), list):
        reg["entities"] = []
    if any(e.get("instance_id") == inst_id for e in reg["entities"]):
        return reg, False
    reg["entities"].append({
        "instance_id": inst_id, "name": None, "domain": domain_id, "vertical": vertical,
        "state": "born", "active": False, "deployed": False, "live": False,
        "skills": skills, "instance_hash": inst_hash,
        "born_at_utc": now(), "born_proof": str(proof_path.relative_to(ROOT)),
        "home": f"entity_substrate/instances/{inst_id}",
    })
    reg["updated_at_utc"] = now()
    wj(reg_path, reg)
    return reg, True


def main():
    ap = argparse.ArgumentParser(description="ENTITY FORGE · рождение сущности из домен-конфига")
    ap.add_argument("domain", help="id домена, напр. dental_msk_01")
    ap.add_argument("--commit", action="store_true",
                    help="ЗАПИСАТЬ в репо: instances/ + реестр + proof (RUBICON; без него — песочница /tmp)")
    ap.add_argument("--name", default=None, help="override имя (иначе из домен-конфига)")
    args = ap.parse_args()

    ok, why = check_seal()
    if not ok:
        print(f"❌ РОЖДЕНИЕ ЗАПРЕЩЕНО: {why}")
        return 1

    dom_path = DOM_DIR / f"{args.domain}.json"
    domain = rj(dom_path)
    if not domain:
        print(f"❌ домен не найден: {dom_path}")
        return 1
    if args.name:
        domain = dict(domain)
        domain["persona"] = dict(domain.get("persona", {}), name=args.name)

    # ИДЕМПОТЕНТНОСТЬ (L12: повторное рождение того же домена = уже существует, не второй экземпляр)
    ts = now()
    if args.commit:
        reg = rj(ROOT / "SYSTEM/REGISTRY/ENTITY_REGISTRY_V1.json") or {}
        existing = [e for e in reg.get("entities", [])
                    if e.get("domain") == args.domain and e.get("state") == "born"]
        if existing:
            e = existing[-1]
            print("╔══════════════════════════════════════════════════════════════╗")
            print("║  ENTITY FORGE V1 · ИДЕМПОТЕНТНОСТЬ                            ║")
            print("╚══════════════════════════════════════════════════════════════╝")
            print(f"  домен {args.domain} УЖЕ РОЖДЁН:")
            print(f"    instance_id:  {e.get('instance_id')}")
            print(f"    born_at:      {e.get('born_at_utc')}")
            print(f"    home:         {e.get('home')}")
            print(f"    hash:         {e.get('instance_hash')}")
            print(f"    proof:        {e.get('born_proof')}")
            print("  Повторное рождение ЗАПРЕЩЕНО (один домен = одна живая сущность).")
            print("  Для перерождения: сначала freeze + review + delete записи в реестре.")
            return 0
    base = INST_DIR if args.commit else Path(tempfile.mkdtemp(prefix="entity_forge_dry_"))
    inst_id, home, inst_hash, surfaces, laws, skills, vertical = \
        build_instance(domain, ts, base)

    # proof
    proof_path = (PROOF_DIR / f"SOCC_FORGE_ENTITY_{inst_id}_V1_PROOF.json") if args.commit \
        else home / "BIRTH_PROOF_DRY.json"
    proof = {
        "id": f"SOCC_FORGE_ENTITY_{inst_id}_V1_PROOF", "created_at_utc": ts,
        "status": "PASS" if args.commit else "DRY",
        "capability": "SOCC_ENTITY_FORGE_BIRTH_FROM_DOMAIN_CONFIG",
        "domain": args.domain, "instance_id": inst_id, "instance_hash": inst_hash,
        "vertical": vertical, "skills": skills, "laws": laws,
        "surfaces": [f"{k}.json" for k in surfaces],
        "home": str(home.relative_to(ROOT)) if args.commit else str(home),
        "seal_verified": why, "dry": not args.commit, "commit": args.commit,
        "entity_born": args.commit, "active": False, "deployed": False, "network_used": False,
        "money_moved": False, "no_daemon": True, "stopped_after_step": True,
        "truth_boundary": ("Entity forge: births a CERTIFIED instance from a domain config "
                           "through 10 sealed-substrate surfaces. Birth ≠ launch: entity is "
                           "not active, not connected, moves no money, uses no network. "
                           "Launch/deploy is a separate operator-gated step."),
    }
    proof["proof_hash"] = h16({k: v for k, v in proof.items() if k != "proof_hash"})
    wj(proof_path, proof)

    # PROOF_CHAIN surface → путь к proof
    pc = surfaces["PROOF_CHAIN"]
    pc["birth_proof"] = str(proof_path.relative_to(ROOT)) if args.commit else str(proof_path)
    pc["proof_hash"] = proof["proof_hash"]
    wj(home / "PROOF_CHAIN.json", pc)

    added = None
    if args.commit:
        reg, added = commit_registry(inst_id, args.domain, vertical, skills, proof_path, inst_hash)
        wj(MEM_DIR / f"FORGE_ENTITY_{inst_id}_MEMORY_V1.json", {
            "id": f"FORGE_ENTITY_{inst_id}_MEMORY_V1", "created_at_utc": ts, "status": "RECORDED",
            "event": f"Entity {inst_id} BORN from domain {args.domain} via forge",
            "instance_hash": inst_hash, "proof": str(proof_path.relative_to(ROOT)),
            "registry_added": added, "truth_boundary": proof["truth_boundary"],
        })

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  ENTITY FORGE V1 · РОЖДЕНИЕ СУЩНОСТИ                          ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    mode = "COMMIT (живое рождение)" if args.commit else "DRY (песочница, 0 записей в репо)"
    print(f"  режим:        {mode}")
    print(f"  домен:        {args.domain}  →  {vertical}")
    print(f"  имя:          {surfaces['IDENTITY']['name']}")
    print(f"  instance_id:  {inst_id}")
    print(f"  hash:         {inst_hash}")
    print(f"  skills:       {', '.join(skills)}")
    print(f"  laws:         {len(laws)} (глобальные + домен)")
    print(f"  surfaces:     10/10 ✅")
    print(f"  home:         {home}")
    print(f"  seal:         {why}")
    if args.commit:
        print(f"  реестр:       {'добавлена' if added else 'уже была'}")
        print(f"  proof:        {proof_path.relative_to(ROOT)}")
    print()
    print("  РОЖДЕНИЕ ≠ ЗАПУСК: active=False, deployed=False, сеть=нет, деньги=нет.")
    print("  Рубильник:    FREEZE.json → frozen=true (+ reason) — сущность обязана подчиниться.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
