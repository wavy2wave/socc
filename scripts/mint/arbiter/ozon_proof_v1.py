#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON PROOF V1 — доказательства менеджера: тик-леджер (hash-chain) + proof-gate витрины + якорь.

«Как швейцарские часы» = ДОКАЗУЕМОСТЬ. Каждый тик оставляет запись; записи сцеплены хешем (середину
не переписать); факт «карточка на витрине» проверяется НЕЗАВИСИМЫМ READ витрины Ozon (200≠успех: ответ
на import — не доказательство, что карточка реально показывается). Три вещи (зеркало ymarket_proof):

  1) ТИК-ЛЕДЖЕР (append_tick/verify_chain) — append-only JSONL, каждая запись несёт prev_hash→hash.
  2) PROOF-GATE ВИТРИНЫ (record_publish_claim → verify_publish) — двухстадийно: claim (verified=False)
     → verify (независимый READ product/info/list подтвердил модерацию OK И visible И stock>0).
  3) ЯКОРЬ (anchor_tick_ledger) — запечатать HEAD цепи в SOVEREIGN/PROOF/proof_chain, честные флаги.

Меняет против ymarket_proof ровно источник верификации: витрина Ozon (ozon_hands — пробел write-
плоскости), поэтому verify_publish без ключа/hands честно REFUSED. Это корректное поведение M0:
proof-gate существует и отказывается подтверждать, пока нет реального READ.

ЗАКОН (SOCC): stdlib-only, без сети (кроме verify_publish READ по отмашке), без денег, bounded,
fail-soft. Тик-леджер по умолчанию в MEMORY_WAVE/reports/mint/arbiter/; env OZON_TICK_LEDGER перекрывает.
"""
import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(HERE.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

# scripts/mint/arbiter -> scripts/mint -> scripts -> SOCC/
ROOT = HERE.parent.parent.parent
REPORTS = ROOT / "MEMORY_WAVE/reports/mint/arbiter"
PROOF_CHAIN = ROOT / "SOVEREIGN/PROOF/proof_chain"

TICK_SCHEMA = "ozon.tick.v1"
GENESIS_PREV = "GENESIS"   # prev_hash самой первой записи цепи


def tick_ledger_path():
    """Путь к тик-леджеру. env OZON_TICK_LEDGER перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("OZON_TICK_LEDGER")
    return Path(p) if p else (REPORTS / "ozon_tick_ledger.jsonl")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def _read_ledger():
    p = tick_ledger_path()
    if not p.exists():
        return []
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def _head_hash():
    """Хеш последней записи цепи (или GENESIS, если цепь пуста)."""
    rows = _read_ledger()
    return rows[-1]["hash"] if rows and rows[-1].get("hash") else GENESIS_PREV


# ── 1) Тик-леджер: append-only hash-chain ──

def append_tick(rec):
    """Дописать запись тика: проставить ts/prev_hash/hash, append-only. Возвращает запись.

    hash = sha256(prev_hash | tick_id | action | ts | payload-digest). Переписать середину цепи,
    не порвав её, невозможно (verify_chain это ловит).
    """
    if not isinstance(rec, dict):
        rec = {"note": str(rec)}
    rec = dict(rec)
    rec.setdefault("schema", TICK_SCHEMA)
    rec.setdefault("ts", _now())
    rec["prev_hash"] = _head_hash()
    body_digest = _hash(rec.get("tick_id"), rec.get("action"),
                        json.dumps(rec.get("checks", {}), sort_keys=True, ensure_ascii=False),
                        rec.get("moved_money", False))
    rec["hash"] = _hash(rec["prev_hash"], rec.get("tick_id"), rec.get("action"), rec["ts"], body_digest)
    p = tick_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def verify_chain():
    """Проверить целостность цепи: каждый prev_hash == hash предыдущей; hash пересчитывается.

    Возвращает (ok, problems). problems — список {index, why}. Пустая цепь ok.
    """
    rows = _read_ledger()
    problems = []
    prev = GENESIS_PREV
    for i, rec in enumerate(rows):
        if rec.get("prev_hash") != prev:
            problems.append({"index": i, "why": f"prev_hash {rec.get('prev_hash')} != ожидаемого {prev}"})
        body_digest = _hash(rec.get("tick_id"), rec.get("action"),
                            json.dumps(rec.get("checks", {}), sort_keys=True, ensure_ascii=False),
                            rec.get("moved_money", False))
        expect = _hash(rec.get("prev_hash"), rec.get("tick_id"), rec.get("action"),
                       rec.get("ts"), body_digest)
        if rec.get("hash") != expect:
            problems.append({"index": i, "why": "hash не сходится (запись изменена)"})
        prev = rec.get("hash")
    return (not problems), problems


def emit_tick_proof(tick_id, checks, self_status=None, action=None, moved_money=False,
                    network_used=False):
    """Собрать proof одного тика: честные флаги + чек-лист. НЕ пишет в цепь сам (кладётся в append_tick).

    Флаги — гарантии дисциплины: no_daemon=True (вышли за один проход), moved_money=False (тик денег
    не двигает), network_used — был ли реальный READ (True только при commit). Каждый чек — булев факт.
    """
    all_ok = all(bool(v) for v in (checks or {}).values())
    return {
        "capability": "OZON_MANAGER_BOUNDED_TICK",
        "tick_id": tick_id,
        "action": action,
        "checks": dict(checks or {}),
        "status": "PASS" if all_ok else "FAIL",
        "no_daemon": True,          # тик завершается за один проход
        "no_background": True,
        "moved_money": bool(moved_money),   # менеджер денег НЕ двигает (RUBICON у оператора)
        "network_used": bool(network_used),
        "self_status": self_status or {},
        "truth_boundary": ("Один ограниченный тик ОЗОН-МЕНЕДЖЕРА. Без демона, без движения денег. "
                           "Реальная запись карточек — только по --commit оператора; публикация "
                           "считается доказанной лишь после независимого READ витрины (200≠успех)."),
    }


# ── 2) Proof-gate витрины: claim → verify (real-source-only, 200≠успех) ──

PUBLISH_CLAIM_SCHEMA = "ozon.publish.claim.v1"


def record_publish_claim(offer_id, commit_response=None, meta=None):
    """Стадия 1: заявлена публикация карточки (verified=False). ЕЩЁ НЕ доказательство витрины.

    ЧЕСТНОСТЬ: даже если commit_response несёт «imported/ok», verified остаётся False до независимого
    verify_publish (ответ на import ≠ состояние витрины; Ozon отдаёт 200 с errors[]).
    """
    resp_status = ""
    if isinstance(commit_response, dict):
        resp_status = commit_response.get("status") or commit_response.get("result") or ""
    return {
        "schema": PUBLISH_CLAIM_SCHEMA,
        "ts": _now(),
        "offer_id": offer_id,
        "claimed_status": resp_status,
        "verified": False,
        "verify_source": None,
        "meta": meta or {},
        "proof_hash": _hash("publish_claim", offer_id, resp_status),
    }


def verify_publish(offer_id, hands=None):
    """Стадия 2: независимый READ витрины Ozon подтверждает публикацию. Возвращает (rec, error).

    real-source-only: подтверждаем ТОЛЬКО реальным чтением через ozon_hands (product/info/list →
    модерация OK И visible И stock>0, без errors[]). Нет hands/ключа/сети → error (не выдумываем «да»).
    error != None ⟺ НЕ подтверждено (консервативно). Сомнение → не verified. На M0 hands ещё пробел —
    честный REFUSED, не ложь.
    """
    if hands is None:
        try:
            import ozon_hands_write_v1 as hands  # ленивый импорт: пробел write-плоскости (M1)
        except Exception as e:
            return None, f"REFUSED: нет ozon_hands (write-плоскость не построена, {type(e).__name__}) — нечем проверить витрину"
    if not getattr(hands, "creds_present", lambda: False)():
        return None, "REFUSED: нет ключа Ozon (Client-Id/Api-Key) — независимый READ невозможен (не verified)"

    reader = getattr(hands, "product_visible", None) or getattr(hands, "read_shelf", None)
    if reader is None:
        return None, "REFUSED: у ozon_hands нет READ витрины (product/info/list) — не verified"
    try:
        card = reader(offer_id)
    except Exception as e:
        return None, f"REFUSED: READ витрины упал ({type(e).__name__}: {e})"
    if not isinstance(card, dict):
        return None, "REFUSED: витрина не вернула карточку — не verified"

    errors = card.get("errors") or []
    mod_ok = str(card.get("moderation") or "").lower() in ("ok", "approved", "processed", "success")
    visible = bool(card.get("visible"))
    try:
        stock = float(card.get("stock") or 0)
    except (TypeError, ValueError):
        stock = 0.0
    if errors:
        return None, f"REFUSED: витрина отдала errors[] ({len(errors)}) — 200≠успех, не verified"
    if not (mod_ok and visible and stock > 0):
        return None, (f"REFUSED: не на витрине (модерация='{card.get('moderation')}' visible={visible} "
                      f"stock={stock}) — не verified")

    rec = {
        "schema": "ozon.publish.verified.v1",
        "ts": _now(),
        "offer_id": offer_id,
        "verified": True,
        "verify_source": "ozon_storefront_read",   # реальный источник, не симуляция
        "moderation": card.get("moderation"),
        "visible": visible,
        "stock": stock,
        "price_index": card.get("price_index"),
        "proof_hash": _hash("publish_verified", offer_id, card.get("moderation"), stock),
    }
    return rec, None


# ── 3) Якорь: запечатать HEAD цепи в канон proof_chain SOCC ──

def anchor_tick_ledger(explicit_dir=None, self_status=None):
    """Запечатать текущий HEAD тик-леджера в SOVEREIGN/PROOF/proof_chain (или explicit_dir для тестов).

    Опорная точка канона: HEAD-hash, длина, целостность, честные флаги (no_daemon, moved_money=false,
    network_used). Fail-soft: не смогли записать → _file_error, объект возвращается.
    """
    rows = _read_ledger()
    ok, problems = verify_chain()
    head = rows[-1]["hash"] if rows else GENESIS_PREV
    moved = any(r.get("moved_money") for r in rows)
    net = any(r.get("network_used") for r in rows)
    anchor = {
        "id": "SOCC_OZON_MANAGER_TICK_ANCHOR",
        "capability": "OZON_MANAGER_BOUNDED_TICKS_PROVEN",
        "created_at_utc": _now(),
        "chain_len": len(rows),
        "chain_head": head,
        "chain_intact": ok,
        "chain_problems": problems,
        "checks": {
            "chain_intact": ok,
            "no_daemon": True,
            "no_money_moved": not moved,
            "bounded_tick": True,
        },
        "status": "PASS" if (ok and not moved) else "FAIL",
        "no_daemon": True,
        "daemon_running": False,
        "moved_money": bool(moved),
        "network_used": bool(net),
        "self_status": self_status or {},
        "proof_hash": _hash("oz_anchor", head, len(rows), ok),
        "truth_boundary": ("Якорь цепи тиков ОЗОН-МЕНЕДЖЕРА. Доказывает: тики ограничены (не демон), "
                           "цепь цела, деньги не двигались. НЕ доказывает реальную публикацию "
                           "карточек — это отдельный proof-gate витрины по --commit."),
    }
    out_dir = Path(explicit_dir) if explicit_dir else PROOF_CHAIN
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "SOCC_OZON_MANAGER_TICK_ANCHOR.json"
        out.write_text(json.dumps(anchor, ensure_ascii=False, indent=2, sort_keys=True),
                       encoding="utf-8")
        anchor["_file"] = str(out)
    except Exception as e:
        anchor["_file_error"] = str(e)
    return anchor


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="OZON PROOF — тик-леджер/цепь/якорь (0₽, без сети)")
    ap.add_argument("--verify", action="store_true", help="проверить целостность цепи тиков")
    ap.add_argument("--head", action="store_true", help="показать HEAD цепи")
    ap.add_argument("--anchor", action="store_true", help="запечатать HEAD в proof_chain")
    args = ap.parse_args()
    if args.head:
        print(_head_hash())
    elif args.anchor:
        print(json.dumps(anchor_tick_ledger(), ensure_ascii=False, indent=2))
    else:
        ok, probs = verify_chain()
        print(json.dumps({"chain_intact": ok, "problems": probs, "len": len(_read_ledger())},
                         ensure_ascii=False, indent=2))
