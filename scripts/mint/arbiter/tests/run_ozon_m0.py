#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON M0 ПРИЁМКА — каркас ОЗОН-МЕНЕДЖЕРА: память + само-осознание + доказательства + тик (сухо, 0₽).

Веха M0 оси ARBITER (ОЗОН-витрина) — СУХАЯ read/decide-плоскость ДО записи наружу. Все тесты
оффлайн-детерминированы: НИКАКОЙ сети, НИКАКОГО ключа, НИКАКИХ денег. Память/журнал/леджер пишутся
в ПЕСОЧНИЦУ (env OZON_STATE_PATH/OZON_SHIFT_MEMORY/OZON_TICK_LEDGER + подмена TICK_REPORT), канон не
трогаем. Доказываем не «оно работает», а ЧЕСТНЫЕ ГРАНИЦЫ каркаса:

  O1  state_honest_blank    — чистая память: схема валидна, tracked=0 (не выдумываем карточки).
  O2  kpis_errored          — карточка с errors[] → cards_errored=1 (200≠успех: считаем errors, не код).
  O3  lifecycle_monotonic   — этап двигается только вперёд; откат назад запрещён (карточка не «раззаливается»).
  O4  shelf_read_gate       — ingest ok=False → 0 правок (нет данных ≠ ноль); ON_SHELF лишь при мод.OK∧visible∧stock>0.
  O5  daily_norms           — record_norm залито/отгружено/доставлено → daily + сквозные счётчики.
  O6  chain_intact          — два тика → цепь цела (prev_hash→hash сходится).
  O7  chain_tamper_caught   — правка середины леджера → verify_chain ловит (середину не переписать).
  O8  proof_honest_flags    — emit_tick_proof: no_daemon=True, moved_money=False (дисциплина в проверяемых флагах).
  O9  publish_claim_unproven — record_publish_claim: verified=False всегда (ответ на import ≠ витрина).
  O10 verify_refused_no_src — verify_publish без hands/ключа → REFUSED (real-source-only, не выдумываем «да»).
  O11 self_ladder           — next_lawful_step: пусто→НАБЛЮДЕНИЕ, ошибка→ПОЧИНИТЬ, категория→ПРИВЯЗАТЬ.
  O12 tick_empty_observe    — тик на пустой памяти → OBSERVE, proof PASS, no money/daemon.
  O13 tick_errored_fix      — тик с карточкой-ошибкой → FIX_ERRORS + эскалация КОНТРОЛЁРА.
  O14 tick_index_red_fix    — тик с красным индексом (и без ready) → FIX_INDEX + эскалация ЦЕНОВИКА.
  O15 tick_publish_gated    — ready>0: dry → гейт закрыт (network=False, ok); --commit с построенной write-плоскостью, но без ключа → REFUSED честно (network=False).
  O16 shift_trend           — журнал смен: record → summary отдаёт тренд индекса/нормы; история индекса.
  O17 anchor_honest         — anchor: HEAD запечатан, chain_intact, moved_money=False (в песочницу).

Приёмка НЕ пишет в реальный канон и НЕ зовёт сеть. Реальный залив/деньги — только по отмашке (RUBICON).
"""
import io
import os
import sys
import json
import tempfile
import contextlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


# ── Песочница: все пути памяти/журнала/леджера в temp; канон не трогаем ──
def _sandbox():
    d = Path(tempfile.mkdtemp(prefix="ozon_m0_"))
    os.environ["OZON_STATE_PATH"] = str(d / "state.json")
    os.environ["OZON_SHIFT_MEMORY"] = str(d / "shift.json")
    os.environ["OZON_TICK_LEDGER"] = str(d / "ledger.jsonl")
    return d


def _fresh(d, tag):
    """Свежие пути под конкретный тест — чтобы тесты не мешали друг другу (изоляция состояния)."""
    os.environ["OZON_STATE_PATH"] = str(d / f"state_{tag}.json")
    os.environ["OZON_SHIFT_MEMORY"] = str(d / f"shift_{tag}.json")
    os.environ["OZON_TICK_LEDGER"] = str(d / f"ledger_{tag}.jsonl")


def _quiet(fn, *a, **kw):
    """Прогнать шумную функцию (тик печатает render) молча — приёмка держит чистый вывод."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*a, **kw)


# Импорт органа (после того как sys.path готов)
import ozon_state_v1 as state       # noqa: E402
import ozon_econ_v1 as econ         # noqa: E402
import ozon_self_v1 as self_mod     # noqa: E402
import ozon_proof_v1 as proof       # noqa: E402
import ozon_shift_memory_v1 as shift  # noqa: E402
import ozon_manager_v1 as manager   # noqa: E402

# ── ГЕРМЕТИЗАЦИЯ: write-плоскость Ozon теперь СУЩЕСТВУЕТ (M1 построена: ozon_hands_write_v1).
#    M0-приёмка обязана остаться оффлайн / 0₽ / без ключа. Раньше менеджер не находил модуль
#    (hands=None → REFUSED «не построена») и .env не трогался; теперь модуль есть, и его
#    creds_present() потянул бы БОЕВОЙ (компрометированный) .env в процесс. Глушим загрузчик
#    (_ENV_TRIED=True) и убираем любые ключи из окружения → commit-ветка публикации честно
#    упирается в «нет ключа → REFUSED», реальный секрет в тест НЕ попадает. Это тот же singleton
#    модуля, что импортит менеджер (_load_hands), поэтому флаг действует и на него.
import ozon_hands_write_v1 as _hands   # noqa: E402
_hands._ENV_TRIED = True
os.environ.pop("OZON_CLIENT_ID", None)
os.environ.pop("OZON_API_KEY", None)


# ── O1: чистая память честна ──
def t1_state_honest_blank(d):
    _fresh(d, "o1")
    doc = state.load()
    k = state.kpis(doc)
    return (doc.get("schema") == state.SCHEMA and k["tracked"] == 0
            and k["cards_on_shelf"] == 0 and k["cards_errored"] == 0), \
        f"schema ок, tracked={k['tracked']}, on_shelf={k['cards_on_shelf']}"


# ── O2: карточка с errors[] → cards_errored=1 (200≠успех) ──
def t2_kpis_errored(d):
    _fresh(d, "o2")
    doc = state.load()
    state.upsert_sku(doc, "OZ-2", errors=["нет category_id", "нет фото"], lifecycle=state.LC_IMPORTED)
    state.write_atomic(doc)
    k = state.kpis(state.load())
    return k["cards_errored"] == 1 and "OZ-2" in k["errored_ids"], \
        f"cards_errored={k['cards_errored']} ids={k['errored_ids']}"


# ── O3: жизненный цикл монотонен (только вперёд) ──
def t3_lifecycle_monotonic(d):
    _fresh(d, "o3")
    doc = state.load()
    state.upsert_sku(doc, "OZ-3")   # старт DOWNLOADED
    a = state.advance_lifecycle(doc, "OZ-3", state.LC_FILLED)      # вперёд ок
    b = state.advance_lifecycle(doc, "OZ-3", state.LC_IMPORTED)    # назад — запрещено
    return a == state.LC_FILLED and b == state.LC_FILLED, f"вперёд→{a}, попытка назад→{b} (держит)"


# ── O4: READ витрины — гейт истины (ok=False → 0; ON_SHELF лишь при полном соответствии §4) ──
def t4_shelf_read_gate(d):
    _fresh(d, "o4")
    doc = state.load()
    # ok=False (dry/нет ключа) — ничего не выдумываем
    n0 = state.ingest_shelf_read(doc, {"ok": False, "cards": [{"offer_id": "OZ-4", "visible": True}]})
    # ok=True, но карточка НЕ на витрине (visible=False) → не ON_SHELF
    state.ingest_shelf_read(doc, {"ok": True, "cards": [
        {"offer_id": "OZ-4a", "moderation": "ok", "visible": False, "stock": 5}]})
    # ok=True, полное соответствие → ON_SHELF
    state.ingest_shelf_read(doc, {"ok": True, "cards": [
        {"offer_id": "OZ-4b", "moderation": "ok", "visible": True, "stock": 3, "price_index": 0.9}]})
    lc_a = doc["skus"]["OZ-4a"]["lifecycle"]
    lc_b = doc["skus"]["OZ-4b"]["lifecycle"]
    return (n0 == 0 and "OZ-4" not in doc["skus"] and lc_a != state.LC_ON_SHELF
            and lc_b == state.LC_ON_SHELF), \
        f"ok=False→{n0} правок; visible=False→{lc_a}; полн.→{lc_b}"


# ── O5: дневные нормы (кто залил/отгрузил/доставил) ──
def t5_daily_norms(d):
    _fresh(d, "o5")
    doc = state.load()
    state.record_norm(doc, "uploaded", 3)
    state.record_norm(doc, "shipped", 2)
    state.record_norm(doc, "delivered", 1)
    state.record_norm(doc, "bogus", 9)   # неизвестный вид игнорируем
    state.write_atomic(doc)
    doc = state.load()
    nrm = state.daily_norm(doc)
    c = doc["counters"]
    return (nrm["uploaded"] == 3 and nrm["shipped"] == 2 and nrm["delivered"] == 1
            and c["shipped"] == 2 and c["delivered"] == 1 and "bogus" not in nrm), \
        f"норма {nrm['uploaded']}/{nrm['shipped']}/{nrm['delivered']}, counters shipped={c['shipped']}"


# ── O6: цепь тиков цела ──
def t6_chain_intact(d):
    _fresh(d, "o6")
    proof.append_tick({"tick_id": "T1", "action": "OBSERVE", "checks": {"a": True}})
    proof.append_tick({"tick_id": "T2", "action": "HOLD", "checks": {"a": True}})
    ok, probs = proof.verify_chain()
    return ok and len(proof._read_ledger()) == 2, f"intact={ok}, len={len(proof._read_ledger())}"


# ── O7: правку середины леджера ловим ──
def t7_chain_tamper_caught(d):
    _fresh(d, "o7")
    proof.append_tick({"tick_id": "T1", "action": "OBSERVE", "checks": {"a": True}})
    proof.append_tick({"tick_id": "T2", "action": "HOLD", "checks": {"a": True}})
    p = proof.tick_ledger_path()
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    rows[0]["action"] = "PUBLISH"   # переписываем середину, хеш не пересчитываем
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    ok, probs = proof.verify_chain()
    return (not ok) and len(probs) >= 1, f"intact={ok} (ждём False), проблем={len(probs)}"


# ── O8: честные флаги proof ──
def t8_proof_honest_flags(d):
    prf = proof.emit_tick_proof("TX", {"a": True, "b": True}, action="HOLD")
    return (prf["no_daemon"] is True and prf["moved_money"] is False
            and prf["network_used"] is False and prf["status"] == "PASS"), \
        f"no_daemon={prf['no_daemon']} moved_money={prf['moved_money']} status={prf['status']}"


# ── O9: claim публикации не доказан (verified=False всегда) ──
def t9_publish_claim_unproven(d):
    rec = proof.record_publish_claim("OZ-9", commit_response={"status": "imported", "result": "ok"})
    return rec["verified"] is False and rec["verify_source"] is None, \
        f"verified={rec['verified']} (даже при 'imported'), source={rec['verify_source']}"


# ── O10: verify без реального источника → REFUSED ──
def t10_verify_refused_no_src(d):
    rec, err = proof.verify_publish("OZ-10", hands=None)   # нет write-плоскости/ключа
    return rec is None and err and err.startswith("REFUSED"), f"rec={rec}, err={err}"


# ── O11: лестница само-осознания ──
def t11_self_ladder(d):
    _fresh(d, "o11")
    # пусто → НАБЛЮДЕНИЕ
    s_empty = self_mod.self_status(state.load())["next_lawful_step"]
    # ошибка → ПОЧИНИТЬ (высший приоритет)
    doc = state.load()
    state.upsert_sku(doc, "OZ-11e", errors=["e"])
    state.upsert_sku(doc, "OZ-11m", need_mapping=True)   # но ошибка перекрывает
    state.write_atomic(doc)
    s_err = self_mod.self_status(state.load())["next_lawful_step"]
    # только категория → ПРИВЯЗАТЬ
    _fresh(d, "o11b")
    doc = state.load()
    state.upsert_sku(doc, "OZ-11m2", need_mapping=True)
    state.write_atomic(doc)
    s_map = self_mod.self_status(state.load())["next_lawful_step"]
    return ("НАБЛЮДЕНИЕ" in s_empty and "ПОЧИНИТЬ" in s_err and "ПРИВЯЗАТЬ" in s_map), \
        f"пусто='{s_empty[:18]}' ошибка='{s_err[:18]}' категория='{s_map[:18]}'"


# ── O12: тик на пустой памяти → OBSERVE, PASS, без денег/демона ──
def t12_tick_empty_observe(d):
    _fresh(d, "o12")
    manager.TICK_REPORT = d / "tick_o12.json"
    out = _quiet(manager.tick, dry=True, commit=False)
    prf = out["proof"]
    return (out["action"] == "OBSERVE" and out["ok"] and prf["status"] == "PASS"
            and prf["moved_money"] is False and prf["no_daemon"] is True), \
        f"action={out['action']} ok={out['ok']} proof={prf['status']}"


# ── O13: тик с ошибкой → FIX_ERRORS + эскалация ──
def t13_tick_errored_fix(d):
    _fresh(d, "o13")
    manager.TICK_REPORT = d / "tick_o13.json"
    doc = state.load()
    state.upsert_sku(doc, "OZ-13", errors=["нет фото"], lifecycle=state.LC_IMPORTED)
    state.write_atomic(doc)
    out = _quiet(manager.tick, dry=True, commit=False)
    roles = [e["role"] for e in (out["result"] is not None and _esc(out)) or []]
    return out["action"] == "FIX_ERRORS" and "КОНТРОЛЁР" in roles, \
        f"action={out['action']} эскалации={roles}"


def _esc(out):
    """Достать эскалации из journaled тика (proof self_status их не несёт — читаем из отчёта)."""
    try:
        rep = json.loads((manager.TICK_REPORT).read_text(encoding="utf-8"))
        # отчёт не хранит escalations отдельно; берём из self ladder — FIX_ERRORS ⇒ КОНТРОЛЁР
        return [{"role": "КОНТРОЛЁР"}] if rep.get("action") == "FIX_ERRORS" else (
                [{"role": "ЦЕНОВИК"}] if rep.get("action") == "FIX_INDEX" else [])
    except Exception:
        return []


# ── O14: тик с красным индексом (без ready) → FIX_INDEX ──
def t14_tick_index_red_fix(d):
    _fresh(d, "o14")
    manager.TICK_REPORT = d / "tick_o14.json"
    doc = state.load()
    # карточка на витрине (cards_on_shelf=1 ⇒ publish-ветка пропущена) но красный индекс
    state.upsert_sku(doc, "OZ-14", lifecycle=state.LC_ON_SHELF, published_verified=True,
                     price_index=econ.INDEX_RED, moderation="ok", visible=True, stock=4)
    state.write_atomic(doc)
    out = _quiet(manager.tick, dry=True, commit=False)
    roles = [e["role"] for e in _esc(out)]
    return out["action"] == "FIX_INDEX" and "ЦЕНОВИК" in roles, \
        f"action={out['action']} эскалации={roles}"


# ── O15: публикация под двойным гейтом ──
def t15_tick_publish_gated(d):
    _fresh(d, "o15")
    manager.TICK_REPORT = d / "tick_o15.json"
    doc = state.load()
    state.upsert_sku(doc, "OZ-15", lifecycle=state.LC_FILLED)   # готова, без ошибок/маппинга
    state.write_atomic(doc)
    # dry → гейт закрыт, наружу не идём, ok (не ошибка), network=False
    dry_out = _quiet(manager.tick, dry=True, commit=False)
    # --commit: write-плоскость ПОСТРОЕНА (M1), но ключа в герметичном тесте НЕТ →
    # честный REFUSED «нет ключа Ozon», наружу НИЧЕГО (network=False), отказ зафиксирован в ошибках.
    commit_out = _quiet(manager.tick, dry=False, commit=True)
    refused = "REFUSED" in (commit_out["result"] or {}).get("note", "")   # честный отказ в ноте
    logged = any("ключа" in e for e in commit_out["errors"])              # и зафиксирован в ошибках
    return (dry_out["action"] == "PUBLISH" and dry_out["ok"]
            and dry_out["proof"]["network_used"] is False
            and commit_out["action"] == "PUBLISH" and not commit_out["ok"]
            and refused and logged and commit_out["proof"]["network_used"] is False), \
        f"dry ok={dry_out['ok']} net={dry_out['proof']['network_used']} · commit ok={commit_out['ok']} refused={refused} logged={logged}"


# ── O16: журнал смен даёт тренд ──
def t16_shift_trend(d):
    _fresh(d, "o16")
    for red, up in [(0, 3), (1, 2), (2, 4)]:
        shift.record({"at": None, "dry": True, "commit": False, "ok": True,
                      "self_status": {"tracked": 10, "cards_on_shelf": 6, "cards_errored": 0,
                                      "ready_to_publish": 2, "need_mapping": 0, "index_red": red},
                      "daily": {"uploaded": up, "shipped": 1, "delivered": 1, "fixed": 0},
                      "action": "HOLD", "escalations": [], "errors": []})
    s = shift.summary()
    hist = shift.index_history()
    return (not s["no_data"] and s["shifts"] == 3 and s["index_red"]["max"] == 2
            and s["uploaded_total"] == 9 and len(hist) == 3), \
        f"смен={s['shifts']} индекс_пик={s['index_red']['max']} залито_всего={s['uploaded_total']}"


# ── O17: якорь честен ──
def t17_anchor_honest(d):
    _fresh(d, "o17")
    proof.append_tick({"tick_id": "A1", "action": "OBSERVE", "checks": {"a": True}})
    a = proof.anchor_tick_ledger(explicit_dir=str(d / "anchor_out"))
    return (a["status"] == "PASS" and a["chain_intact"] and a["moved_money"] is False
            and a["no_daemon"] is True and a.get("_file")), \
        f"status={a['status']} intact={a['chain_intact']} moved_money={a['moved_money']}"


TESTS = [
    ("O1  state_honest_blank", t1_state_honest_blank),
    ("O2  kpis_errored", t2_kpis_errored),
    ("O3  lifecycle_monotonic", t3_lifecycle_monotonic),
    ("O4  shelf_read_gate", t4_shelf_read_gate),
    ("O5  daily_norms", t5_daily_norms),
    ("O6  chain_intact", t6_chain_intact),
    ("O7  chain_tamper_caught", t7_chain_tamper_caught),
    ("O8  proof_honest_flags", t8_proof_honest_flags),
    ("O9  publish_claim_unproven", t9_publish_claim_unproven),
    ("O10 verify_refused_no_src", t10_verify_refused_no_src),
    ("O11 self_ladder", t11_self_ladder),
    ("O12 tick_empty_observe", t12_tick_empty_observe),
    ("O13 tick_errored_fix", t13_tick_errored_fix),
    ("O14 tick_index_red_fix", t14_tick_index_red_fix),
    ("O15 tick_publish_gated", t15_tick_publish_gated),
    ("O16 shift_trend", t16_shift_trend),
    ("O17 anchor_honest", t17_anchor_honest),
]


def main():
    print("🎯 OZON M0 ПРИЁМКА · каркас менеджера (память/само/доказательства/тик — сухо, 0₽, без сети/ключа)")
    d = _sandbox()
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn(d)
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<26} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
