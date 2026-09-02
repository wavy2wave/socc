#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OZON MANAGER V1 — живой менеджер магазина Ozon (орган оси ARBITER; паутина узлов, не конвейер).

«Как швейцарские часы» = BOUNDED TICK: прогон завершается за один проход; память между тиками
(ozon_state/ozon_shift_memory); честные флаги (no_daemon=True, moved_money=False); RUBICON на
реальной записи (not dry AND commit); доказательства витрины через proof-gate (независимый READ).

Грамматика менеджера (зеркало ymarket_manager, меняем под сигналы Озона):
  1) observe(state) — загрузить память (state.load())
  2) self(ozon_self) — осознать себя: кто, зачем, состояние, next_lawful_step
  3) decide(<=1 action) — лестница решений (§7 плана OZON_MANAGER_PLAN_V1):
       cards_errored>0 → FIX_ERRORS · need_mapping>0 → RESOLVE_MAPPING (глаза оператора) ·
       tracked==0 → OBSERVE (первый preflight dry) · cards_on_shelf==0 & ready>0 → PUBLISH (RUBICON) ·
       index_red>0 → FIX_INDEX · иначе HOLD.
  4) execute(action) — fail-soft: ошибка действия не роняет весь тик.
  5) write(state) — state.bump + write_atomic; shift.record (журнал смены → тренд).
  6) prove_tick() — proof.emit_tick_proof + append_tick (hash-chain); proof-gate publish (claim→verify).
  7) report(operator) — self.render + emit (MEMORY_WAVE/reports/mint/arbiter/ozon_manager_tick.json).

Непрерывность из ПАМЯТИ + ЛЕДЖЕРА тиков, не из вечного процесса. Запуск вручную (--tick) или по cron.

ЗАКОНЫ (CHARTER OZON_MANAGER):
  OZ1: #errored→0 (200≠успех; читаем errors[]).      OZ4: публикация доказана независимым READ витрины.
  OZ2: category_id/attrs не выдумываем.               OZ5: красный/жёлтый индекс = прячут → чинить/снять.
  OZ3: DONE только на витрине (мод.OK И visible И stock>0).  OZ6: реальная запись только not dry AND commit.

M0 (сейчас): write-плоскость Ozon (ozon_hands/runner/write) ещё НЕ построена — действия, требующие
сети, честно REFUSED (мягкий импорт → нет модуля → не врём). Тик наблюдает память, решает, доказывает.
Публикация/track/fix оживут в M1, когда появятся ozon_hands + ключ. Всё дописано БЕЗ поломки органа.

ЗАКОН (SOCC): stdlib-only, без денег, bounded (no daemon), честные флаги (moved_money=False).
Dry по умолчанию True; --commit включает write-плоскость (RUBICON оператора).
"""
import sys
import json
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for p in (str(HERE), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ozon_state_v1 as state          # noqa: E402
import ozon_econ_v1 as econ            # noqa: E402
import ozon_self_v1 as self_mod        # noqa: E402
import ozon_proof_v1 as proof          # noqa: E402
import ozon_shift_memory_v1 as shift   # noqa: E402

ROOT = HERE.parent.parent.parent
TICK_REPORT = ROOT / "MEMORY_WAVE/reports/mint/arbiter/ozon_manager_tick.json"


def _load_hands():
    """Мягкий импорт write-плоскости Ozon (ozon_hands_write_v1). M0: ещё нет → None (честно REFUSED).

    Не жёсткий import вверху файла: орган обязан жить и решать БЕЗ сети. Появится модуль + ключ (M1)
    — track/fix/publish оживут сами, без правки менеджера.
    """
    try:
        import ozon_hands_write_v1 as hands
        return hands
    except Exception:
        return None


def _creds_present(hands):
    if hands is None:
        return False
    fn = getattr(hands, "creds_present", None)
    return bool(fn()) if callable(fn) else False


def tick(dry=True, commit=False):
    """Один тик менеджера: ЧИТАЕТ память → ОСОЗНАЁТ → РЕШАЕТ → ДЕЛАЕТ → ПОМНИТ → ДОКАЗЫВАЕТ → render.

    dry/commit — двойной гейт: реальная сеть только при not dry AND commit (OZ6, RUBICON). Тик НЕ демон:
    живёт между завершениями за счёт state (память) + shift (журнал смен). Fail-soft: ошибка действия →
    в память/ошибки, не роняет тик. Возвращает {ok, tick_id, action, self, proof, result, errors}.
    """
    tick_id = f"OZTICK_{proof._now().replace(':', '').replace('-', '')[:15]}"
    doc = state.load()
    st = self_mod.self_status(doc)
    k = state.kpis(doc)   # сырой kpis (tracked/daily_today/…): ozon_self.kpis переименовывает ключи (cards_tracked)

    hands = _load_hands()
    action = None
    result = None
    errors = []
    escalations = []
    network_used = False

    # ── Шаг 3: РЕШИТЬ одно действие (лестница = ozon_self._next_lawful_step, единый мозг) ──
    if k["cards_errored"] > 0:
        # OZ1: ошибка карточки — высший приоритет. Авто-fix_one = roadmap M2+; сейчас сигнал+эскалация.
        action = "FIX_ERRORS"
        escalations.append({"role": "КОНТРОЛЁР", "kind": "CARD_ERRORED"})
        result = {"note": (f"{k['cards_errored']} карточек с errors[] (OZ1 «#errored→0»): "
                           f"{', '.join(k['errored_ids'][:5])}. Починка вручную/fix_one — M2+."),
                  "errored_ids": k["errored_ids"]}
    elif k["need_mapping"] > 0:
        # OZ2: категорию/атрибуты не выдумываем — эскалация оператору.
        action = "RESOLVE_MAPPING"
        escalations.append({"role": "АРХИТЕКТОР", "kind": "NEED_CATEGORY"})
        result = {"note": (f"{k['need_mapping']} карточек ждут category_id + обязательные атрибуты "
                           "(глаза оператора; id не выдумываем — OZ2)")}
    elif k["tracked"] == 0:
        action = "OBSERVE"
        result = {"note": "Память пуста — прогнать отбор/preflight по нише (dry, 0₽), взять под наблюдение"}
    elif k["cards_on_shelf"] == 0 and k["ready_to_publish"] > 0:
        # OZ4/OZ6: первая реальная публикация — только по отмашке. Даже с --commit в M0 нет write-плоскости.
        action = "PUBLISH"
        if not (not dry and commit):
            result = {"dry": dry, "commit": commit, "network_used": False,
                      "note": (f"{k['ready_to_publish']} карточек готовы. Первая публикация — только "
                               "not dry AND --commit (RUBICON). Гейт закрыт — наружу не идём.")}
        elif hands is None:
            result = {"ok": False, "network_used": False,
                      "note": "REFUSED: write-плоскость Ozon (ozon_hands) не построена — залить нечем (M1)"}
            errors.append("нет ozon_hands — публикация пропущена (не выдумываем витрину)")
        elif not _creds_present(hands):
            result = {"ok": False, "network_used": False,
                      "note": "REFUSED: нет ключа Ozon (Client-Id/Api-Key) — реальный залив невозможен"}
            errors.append("нет ключа Ozon — публикация пропущена")
        else:
            # Ветка живёт в M1: реальный залив + claim (proof-gate stage 1). В M0 сюда не доходим.
            result = {"note": "write-плоскость готова — выполнить залив 1 карточки + claim (см. M1)"}
    elif k["index_red"] > 0:
        # OZ5: красный индекс = карточку прячут из органики. Чинить цену (в рамках пола маржи) или снять.
        action = "FIX_INDEX"
        escalations.append({"role": "ЦЕНОВИК", "kind": "INDEX_RED"})
        result = {"note": (f"{k['index_red']} карточек в КРАСНОМ индексе — их прячут (OZ5): "
                           f"{', '.join(k['index_red_ids'][:5])}. Снизить цену (пол маржи) или снять. "
                           "Реальная правка цены — write-плоскость M1 + --commit."),
                  "index_red_ids": k["index_red_ids"]}
    else:
        action = "HOLD"
        result = {"note": "Ошибок нет, индекс не красный — держать строй, добирать заполненность и нормы дня"}

    # ── Шаг 5: ПОМНИТЬ (state.ticks + журнал смены) ──
    try:
        state.bump(doc, "ticks")
        state.write_atomic(doc)
    except Exception as e:
        errors.append(f"не смог обновить память state: {e}")

    report = {
        "at": proof._now(),
        "dry": dry, "commit": commit,
        "ok": not errors,
        "self_status": k,                 # сырой kpis: snapshot ждёт tracked/cards_on_shelf/... (match)
        "daily": k.get("daily_today"),
        "action": action,
        "escalations": escalations,
        "errors": errors,
    }
    try:
        shift.record(report)
    except Exception as e:
        errors.append(f"не смог записать смену в журнал: {e}")

    # ── Шаг 6: ДОКАЗАТЬ тик (proof: честные флаги + hash-chain) ──
    checks = {
        "state_loaded": doc.get("schema") == state.SCHEMA,
        "self_honest": k.get("cards_errored") is not None,        # число из реального READ, не из воздуха
        "action_decided": action is not None,
        "no_fakepass": (k.get("need_mapping", 0) == 0) or action == "RESOLVE_MAPPING",
        "errors_first": (k.get("cards_errored", 0) == 0) or action == "FIX_ERRORS",
        "no_money": True,
    }
    prf = proof.emit_tick_proof(tick_id, checks, self_status=st, action=action,
                                moved_money=False, network_used=network_used)
    try:
        proof.append_tick({"tick_id": tick_id, "action": action, "checks": checks,
                           "result": result, "moved_money": False, "network_used": network_used})
    except Exception as e:
        errors.append(f"не смог записать тик в леджер: {e}")

    out = {"ok": not errors, "tick_id": tick_id, "action": action, "self": st,
           "proof": prf, "result": result, "errors": errors}

    # ── Шаг 7: ОТЧЁТ оператору (render + снимок на диск) ──
    try:
        TICK_REPORT.parent.mkdir(parents=True, exist_ok=True)
        TICK_REPORT.write_text(json.dumps({
            "at": report["at"], "tick_id": tick_id, "action": action,
            "kpis": k, "result": result, "proof": prf, "errors": errors,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        errors.append(f"не смог записать отчёт тика: {e}")

    print(self_mod.render(st))
    print()
    print(f"Тик {tick_id}: {action}")
    if result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if escalations:
        print("↑ Эскалации: " + " · ".join(f"[{e['role']}] {e['kind']}" for e in escalations))
    if errors:
        print("⚠️  Ошибки:")
        for e in errors:
            print(f"  • {e}")
    print(f"\nproof: {prf['status']} · no_daemon={prf['no_daemon']} · "
          f"moved_money={prf['moved_money']} · network_used={prf['network_used']}")
    return out


def show_self():
    """Показать само-осознание менеджера (без действия)."""
    doc = state.load()
    st = self_mod.self_status(doc)
    print(self_mod.render(st))
    return st


def show_shift():
    """Показать сводку журнала смен (тренд индекса/нормы за неделю) — утренний лист БРИГАДИРА."""
    print(shift.render(shift.summary()))
    return shift.summary()


def verify_chain_cmd():
    """Проверить целостность цепочки доказательств тиков (честность)."""
    ok, problems = proof.verify_chain()
    if ok:
        print("✅ Цепочка тиков целостна")
    else:
        print("❌ Цепочка тиков нарушена:")
        for p in problems:
            print(f"  • индекс {p.get('index')}: {p.get('why')}")
    return {"ok": ok, "problems": problems}


def anchor_cmd():
    """Запечатать HEAD цепи тиков в SOVEREIGN/PROOF/proof_chain (честные флаги)."""
    doc = state.load()
    st = self_mod.self_status(doc)
    a = proof.anchor_tick_ledger(self_status=st)
    print(json.dumps({"status": a["status"], "chain_len": a["chain_len"],
                      "chain_head": a["chain_head"], "chain_intact": a["chain_intact"],
                      "moved_money": a["moved_money"], "file": a.get("_file") or a.get("_file_error")},
                     ensure_ascii=False, indent=2))
    return a


def _main(argv=None):
    ap = argparse.ArgumentParser(
        description="OZON MANAGER V1 — менеджер магазина Ozon (bounded tick, паутина узлов)",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tick", action="store_true", help="выполнить один тик (решение по next_lawful_step)")
    ap.add_argument("--self", action="store_true", help="показать само-осознание (без действия)")
    ap.add_argument("--shift", action="store_true", help="сводка журнала смен (тренд за неделю)")
    ap.add_argument("--verify-chain", action="store_true", help="проверить цепочку доказательств тиков")
    ap.add_argument("--anchor", action="store_true", help="запечатать HEAD цепи тиков в proof_chain")
    ap.add_argument("--commit", action="store_true",
                    help="снять dry-гейт для тика (RUBICON; в M0 write-плоскость ещё REFUSED)")
    args = ap.parse_args(argv)

    if args.tick:
        return tick(dry=not args.commit, commit=args.commit)
    elif args.self:
        return show_self()
    elif args.shift:
        return show_shift()
    elif args.verify_chain:
        return verify_chain_cmd()
    elif args.anchor:
        return anchor_cmd()
    else:
        ap.print_help()
        return {"ok": False}


if __name__ == "__main__":
    r = _main()
    sys.exit(0 if (r or {}).get("ok", True) else 1)
