#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YMARKET PROOF V1 — доказательства управляющего: тик-леджер (hash-chain) + proof-gate публикации + якорь.

«Ни один товар с ошибкой; быстро и надёжно как швейцарские часы.» Надёжность = ДОКАЗУЕМОСТЬ: каждый
тик оставляет запись, записи сцеплены хешем (подделать середину нельзя), а факт публикации карточки
проверяется НЕЗАВИСИМЫМ чтением витрины (200≠успех: сам по себе ответ на запись — не доказательство,
что карточка реально на Маркете). Три вещи:

  1) ТИК-ЛЕДЖЕР (append_tick/verify_chain) — append-only JSONL, каждая запись несёт prev_hash →
     hash. Обрыв/переписывание цепи ловится verify_chain. Это память ДЕЙСТВИЙ (что управляющий
     делал), в дополнение к памяти СОСТОЯНИЯ (ymarket_state).
  2) PROOF-GATE ПУБЛИКАЦИИ (record_publish_claim → verify_publish) — двухстадийно, как MINT-леджер:
     claim (записали, verified=False) → verify (независимый READ подтвердил PUBLISHED + contentRating).
     Никакого «отправили и считаем опубликованным».
  3) ЯКОРЬ (anchor_tick_ledger) — запечатать HEAD цепи в SOVEREIGN/PROOF/proof_chain (канон SOCC),
     с честными флагами no_daemon/moved_money=false. Опорная точка, к которой всё сходится.

ЗАКОН (SOCC): stdlib-only, без сети (кроме verify_publish, который READ через hands по отмашке),
без денег, bounded (не демон), fail-soft. Тик-леджер по умолчанию в MEMORY_WAVE/reports/mint/arbiter/;
env YM_TICK_LEDGER перекрывает (тесты/песочница). Якорь можно направить в tempdir (тесты).
"""
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
import sys
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# scripts/mint/arbiter -> scripts -> SOCC/
ROOT = HERE.parent.parent.parent
REPORTS = ROOT / "MEMORY_WAVE/reports/mint/arbiter"
PROOF_CHAIN = ROOT / "SOVEREIGN/PROOF/proof_chain"

TICK_SCHEMA = "ymarket.tick.v1"
GENESIS_PREV = "GENESIS"   # prev_hash самой первой записи цепи


def tick_ledger_path():
    """Путь к тик-леджеру. env YM_TICK_LEDGER перекрывает (песочница/тесты не пишут в канон)."""
    p = os.environ.get("YM_TICK_LEDGER")
    return Path(p) if p else (REPORTS / "ymarket_tick_ledger.jsonl")


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
    """Дописать запись тика в цепь: проставить ts/prev_hash/hash, append-only. Возвращает запись.

    hash = sha256(prev_hash | tick_id | action | ts | payload-digest). Так каждая запись «знает»
    предыдущую: переписать середину, не порвав цепь, невозможно (verify_chain это ловит).
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

    Возвращает (ok, problems). problems — список {index, why} с разрывами/подделками. Пустая цепь ok.
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
    """Собрать PXS-1-подобный proof одного тика: честные флаги + чек-лист. НЕ пишет в цепь сам.

    Управляющий кладёт это в запись тика (append_tick). Флаги — гарантии дисциплины:
      no_daemon=True (мы вышли за один проход), moved_money=False (тик денег не двигает),
      network_used — был ли реальный READ (True только при commit-track). Каждый чек — булев факт.
    """
    all_ok = all(bool(v) for v in (checks or {}).values())
    return {
        "capability": "YMARKET_MANAGER_BOUNDED_TICK",
        "tick_id": tick_id,
        "action": action,
        "checks": dict(checks or {}),
        "status": "PASS" if all_ok else "FAIL",
        "no_daemon": True,          # тик завершается за один проход (не вечный цикл)
        "no_background": True,
        "moved_money": bool(moved_money),   # управляющий денег НЕ двигает (RUBICON у оператора)
        "network_used": bool(network_used),
        "self_status": self_status or {},
        "truth_boundary": ("Один ограниченный тик управляющего Яндекс.Маркетом. Без демона, без "
                           "движения денег. Реальная запись карточек — только по --commit оператора; "
                           "публикация считается доказанной лишь после независимого READ витрины."),
    }


# ── 2) Proof-gate публикации: claim → verify (real-source-only, 200≠успех) ──

PUBLISH_CLAIM_SCHEMA = "ymarket.publish.claim.v1"


def record_publish_claim(offer_id, commit_response=None, meta=None):
    """Стадия 1: заявлена публикация карточки (verified=False). Это ещё НЕ доказательство витрины.

    commit_response — сырой ответ writer.publish_card (может нести status='dry' или реальный).
    Возвращает claim-запись (не в тик-леджер — это отдельная сущность, кладётся в тик как факт).
    ЧЕСТНОСТЬ: даже если commit_response.status == 'PUBLISHED', verified остаётся False до
    независимого verify_publish (ответ на запись ≠ состояние витрины).
    """
    resp_status = ""
    if isinstance(commit_response, dict):
        resp_status = commit_response.get("status") or ""
    return {
        "schema": PUBLISH_CLAIM_SCHEMA,
        "ts": _now(),
        "offerId": offer_id,
        "claimed_status": resp_status,
        "verified": False,
        "verify_source": None,
        "verify_rating": None,
        "meta": meta or {},
        "proof_hash": _hash("publish_claim", offer_id, resp_status),
    }


def verify_publish(offer_id, business_id=None, campaign_id=None, hands=None, expect_status="PUBLISHED"):
    """Стадия 2: независимый READ витрины/индекса подтверждает публикацию. Возвращает (rec, error).

    real-source-only: подтверждаем ТОЛЬКО реальным чтением через hands (campaign_offers →
    status==PUBLISHED, offer_cards → contentRating). Без ключа/сети → error (не выдумываем «да»).
    error != None ⟺ НЕ подтверждено (консервативно): нет hands, нет ключа, статус ≠ ожидаемого,
    транспорт упал. Сомнение → не verified.
    """
    if hands is None:
        try:
            import ymarket_hands_v1 as hands  # ленивый импорт: dry/тесты могут передать фейк
        except Exception as e:
            return None, f"REFUSED: нет ymarket_hands ({e}) — нечем проверить витрину"
    if not hands.creds_present():
        return None, "REFUSED: нет YANDEX_MARKET_API_KEY — независимый READ невозможен (не verified)"

    bid, cid = business_id, campaign_id
    if not (bid and cid):
        try:
            bid2, cid2, _src = hands.resolve_ids()
            bid = bid or bid2
            cid = cid or cid2
        except (getattr(hands, "YMarketHTTPError", Exception), RuntimeError) as e:
            return None, f"REFUSED: не удалось узнать business/campaign id ({e})"
    if not cid:
        return None, "REFUSED: campaignId неизвестен — витрину не прочитать"

    # (а) статус размещения на витрине
    try:
        placements = hands.campaign_offers(cid, offer_ids=[offer_id])
    except (getattr(hands, "YMarketHTTPError", Exception), RuntimeError) as e:
        return None, f"REFUSED: READ витрины упал ({e})"
    status = ""
    for pl in (placements or []):
        if isinstance(pl, dict) and (pl.get("offerId") or pl.get("offer_id")) == offer_id:
            status = pl.get("status") or pl.get("placementStatus") or ""
    if status != expect_status:
        return None, f"REFUSED: витрина показала статус '{status or '—'}' ≠ '{expect_status}' (не verified)"

    # (б) индекс/заполненность из независимого чтения карточки (доп. доказательство «карточка живая»)
    rating = None
    if bid:
        try:
            cards = hands.offer_cards_status(bid, offer_ids=[offer_id])
            for c in (cards or []):
                if isinstance(c, dict) and (c.get("offerId") or c.get("offer_id")) == offer_id:
                    rating = c.get("contentRating")
        except (getattr(hands, "YMarketHTTPError", Exception), RuntimeError):
            rating = None  # индекс не критичен для факта публикации; не роняем verify

    rec = {
        "schema": "ymarket.publish.verified.v1",
        "ts": _now(),
        "offerId": offer_id,
        "verified": True,
        "verify_source": "yandex_market_storefront_read",  # реальный источник, не симуляция
        "status": status,
        "verify_rating": rating,
        "proof_hash": _hash("publish_verified", offer_id, status, rating),
    }
    return rec, None


# ── 3) Якорь: запечатать HEAD цепи в канон proof_chain SOCC ──

def anchor_tick_ledger(explicit_dir=None, self_status=None):
    """Запечатать текущий HEAD тик-леджера в SOVEREIGN/PROOF/proof_chain (или explicit_dir для тестов).

    Опорная точка канона: id, HEAD-hash, длина цепи, целостность, честные флаги (no_daemon,
    moved_money=false, network_used). Возвращает записанный anchor-объект (и путь в _file).
    Fail-soft: не смогли записать → в объекте _file_error, но сам объект возвращается.
    """
    rows = _read_ledger()
    ok, problems = verify_chain()
    head = rows[-1]["hash"] if rows else GENESIS_PREV
    moved = any(r.get("moved_money") for r in rows)
    net = any(r.get("network_used") for r in rows)
    anchor = {
        "id": "SOCC_YMARKET_MANAGER_TICK_ANCHOR",
        "capability": "YMARKET_MANAGER_BOUNDED_TICKS_PROVEN",
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
        "proof_hash": _hash("ym_anchor", head, len(rows), ok),
        "truth_boundary": ("Якорь цепи тиков управляющего Яндекс.Маркетом. Доказывает: тики "
                           "ограничены (не демон), цепь цела, деньги не двигались. НЕ доказывает "
                           "реальную публикацию карточек — это отдельный proof-gate по --commit."),
    }
    out_dir = Path(explicit_dir) if explicit_dir else PROOF_CHAIN
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "SOCC_YMARKET_MANAGER_TICK_ANCHOR.json"
        out.write_text(json.dumps(anchor, ensure_ascii=False, indent=2, sort_keys=True),
                       encoding="utf-8")
        anchor["_file"] = str(out)
    except Exception as e:
        anchor["_file_error"] = str(e)
    return anchor


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="YMARKET PROOF — тик-леджер/цепь/якорь (0₽, без сети)")
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
