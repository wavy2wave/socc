#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РОЛЬ · КОНТРОЛЁР (YM_CONTROLLER) — индекс качества выше 40, или магазин отключат.

Канон роли SOCC (TFS-1, 8 полей) — см. CHARTER ниже.

Зачем: Яндекс.Маркет не предупреждает заранее. Индекс упал ниже 40 → магазин отключён,
все товары скрыты на 7 дней, восстановление через саппорт. Индекс 80–94 → штрафы платные
(отмена по вине магазина до 5000₽, сборка с опозданием до 2000₽). Индекс 98+ → штрафов нет.

Роль не «улучшает» индекс искусственно — только читает правду Маркета и эскалирует ДО того,
как цифра станет критической. Улучшение = работа других ролей (ДИСПЕТЧЕР не даёт просрочить,
СКЛАДОВЩИК не даёт протухнуть остаткам, ЦЕНОВИК держит маржу).

ЧЕСТНОСТЬ (L3): индекс роль не выдумывает. Маркет не отдал → ok=False с причиной,
НЕ «наверное всё хорошо». Нет данных → эскалация оператору, не молчание.

Что роль НЕ делает (граница честности):
  • не закрывает рекомендации Маркета сама (это действия оператора/других ролей);
  • не имитирует улучшение индекса (цифра от Маркета, не от нас);
  • не даёт советов «как поднять» — показывает факт и порог действия.
"""
from __future__ import annotations

import json
import sys

import ymarket_trade_hands_v1 as trade

CHARTER = {
    "id": "YM_CONTROLLER",
    "name_ru": "КОНТРОЛЁР",
    "mandate": "индекс качества не ниже 40 (иначе отключение), стремление к 98+ (0 штрафов)",
    "owns": ["индекс качества кампании", "рекомендации Маркета", "эскалация по индексу"],
    "inputs": ["индекс качества Маркета (READ)", "история индекса (state)"],
    "outputs": ["статус качества → БРИГАДИР", "эскалация критичных зон → оператор"],
    "laws": [
        "C1 индекс <40 = STOP: магазин отключат, товары скроют на 7 дней",
        "C2 индекс 40–79 = предупреждение: штрафы огромные, но магазин ещё работает",
        "C3 индекс 80–97 = норма работы: штрафы платные (отмена до 5000₽, опоздание до 2000₽)",
        "C4 индекс 98+ = цель: штрафов за отмены и опоздания нет",
        "C5 нет данных от Маркета → эскалация, не молчание (пропущенное падение = отключение)",
    ],
    "kpi": [
        {"metric": "индекс качества", "target": "≥98", "source_of_truth": "API Маркета"},
        {"metric": "дней в зоне <80", "target": "0", "source_of_truth": "память state"},
        {"metric": "падений индекса на >5 за сутки", "target": "0", "source_of_truth": "diff state"},
    ],
    "proves_by": "каждая проверка: campaignId → запрос Маркета → цифра индекса → зона действия",
}

# Зоны индекса (из документации Маркета, не наши догадки).
ZONE_CRITICAL = 40      # ниже → отключение магазина на 7 дней
ZONE_WARN = 80          # ниже → штрафы огромные, но магазин работает
ZONE_COSTS = 98         # ниже → штрафы платные (отмена/опоздание)
ZONE_SAFE = 98          # выше → штрафов нет


def classify(rating):
    """Зона индекса качества. None → 'unknown' (C5: не выдумываем)."""
    if rating is None:
        return {"zone": "unknown", "action": "ESCALATE",
                "why": "индекс неизвестен → эскалация (C5), пропустить падение = риск отключения"}
    r = float(rating)
    if r < ZONE_CRITICAL:
        return {"zone": "critical", "action": "STOP_OPERATIONS",
                "cost": "магазин ОТКЛЮЧАТ, товары скроют на 7 дней, восстановление через саппорт",
                "why": f"индекс {r} <{ZONE_CRITICAL} (C1) — критическая зона, немедленная эскалация"}
    if r < ZONE_WARN:
        return {"zone": "danger", "action": "ESCALATE_HIGH",
                "cost": f"отмена по вине магазина: до 5000₽ · сборка с опозданием: до 2000₽ (при 80–94: 75%/15%)",
                "why": f"индекс {r} в зоне 40–79 (C2) — штрафы огромные, магазин на грани"}
    if r < ZONE_COSTS:
        return {"zone": "costs", "action": "TIGHTEN",
                "cost": f"отмена до 5000₽ · опоздание до 2000₽ (75%/15% стоимости размещения при {r})",
                "why": f"индекс {r} в зоне 80–97 (C3) — штрафы платные, цель 98+"}
    return {"zone": "safe", "action": "MAINTAIN",
            "cost": "штрафов за отмены и опоздания нет",
            "why": f"индекс {r} ≥{ZONE_SAFE} (C4) — безопасная зона, держать"}


def check(business_id, campaign_ids, quality_fn=None):
    """Прочитать индекс качества кампаний. READ, 0₽.

    Fail-soft: Маркет не отдал → ok=False с причиной, НЕ пустой «всё хорошо».
    """
    if not campaign_ids:
        return {"ok": False, "reason": "NO_CAMPAIGNS",
                "note": "campaignId не задан — индекс не прочитать"}
    fn = quality_fn or trade.quality_rating
    try:
        rows = fn(business_id, campaign_ids)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "note": "индекс не прочитан — НЕ считаем, что всё хорошо (C5)"}

    if not rows:
        return {"ok": False, "reason": "EMPTY_RESPONSE",
                "note": "Маркет вернул пустой ответ — индекс неизвестен (C5)"}

    results = []
    for r in rows:
        cid = r.get("campaignId")
        val = r.get("total") or r.get("value") or r.get("rating")
        zone = classify(val)
        results.append({"campaignId": cid, "rating": val, **zone})

    escalate = [r for r in results if r["zone"] in ("critical", "danger", "unknown")]
    warn = [r for r in results if r["zone"] == "costs"]
    return {"ok": True, "campaigns": results, "escalate": escalate, "warn": warn}


def trend(current, history):
    """Динамика индекса: падение >5 за сутки — сигнал, что операции ухудшились.

    history — [{at, rating}], отсортирован по времени (старые → новые).
    Возвращает {delta_24h, falling, note}.
    """
    if current is None or not history:
        return {"delta_24h": None, "falling": False, "note": "недостаточно данных для тренда"}

    from datetime import datetime, timedelta
    now = datetime.now()
    day_ago = now - timedelta(hours=24)

    recent = [h for h in history if "at" in h]
    if not recent:
        return {"delta_24h": None, "falling": False, "note": "нет временных меток в истории"}

    # Ищем ближайшую точку ~24 часа назад
    baseline = None
    for h in reversed(recent):
        try:
            t = datetime.fromisoformat(h["at"][:19]) if isinstance(h["at"], str) else h["at"]
            if t <= day_ago:
                baseline = h.get("rating")
                break
        except (ValueError, TypeError):
            continue

    if baseline is None:
        return {"delta_24h": None, "falling": False, "note": "нет данных за 24 часа назад"}

    delta = round(current - baseline, 1)
    falling = delta < -5.0
    note = (f"индекс {'упал' if delta < 0 else 'вырос'} на {abs(delta)} за сутки" +
            (" — операции ухудшились, нужна диагностика" if falling else ""))
    return {"delta_24h": delta, "falling": falling, "baseline": baseline, "note": note}


def recommendations(business_id, quality_fn=None):
    """Рекомендации Маркета по улучшению индекса (если API даёт).

    Роль НЕ закрывает их сама — показывает оператору, что Маркет требует.
    """
    # В текущем API /v2/businesses/{id}/ratings/quality рекомендаций нет (только цифра).
    # Если Маркет добавит детализацию — здесь будет READ. Пока честный «нет данных».
    return {"ok": False, "reason": "API_NO_DETAILS",
            "note": "Маркет даёт только общий индекс, детализацию смотреть в кабинете"}


def render(check_result, trend_result=None):
    """Сводка для БРИГАДИРА: сначала что горит, потом что предупреждает, потом норма."""
    if not check_result.get("ok"):
        return f"🔴 КОНТРОЛЁР: индекс НЕ прочитан — {check_result.get('error') or check_result.get('note')}"

    lines = []
    esc = check_result["escalate"]
    warn = check_result["warn"]
    camps = check_result["campaigns"]

    if esc:
        lines.append(f"🔴 КОНТРОЛЁР: критично {len(esc)} кампаний")
        for r in esc:
            lines.append(f"   ⛔ кампания {r['campaignId']}: {r['why']}")
            if r.get("cost"):
                lines.append(f"      💰 {r['cost']}")
    elif warn:
        lines.append(f"⚠️  КОНТРОЛЁР: {len(warn)} кампаний в зоне платных штрафов")
        for r in warn:
            lines.append(f"   ⚠️  кампания {r['campaignId']}: индекс {r['rating']} (цель ≥98)")
    else:
        safe = [r for r in camps if r["zone"] == "safe"]
        lines.append(f"✅ КОНТРОЛЁР: {len(safe)} кампаний в безопасной зоне (≥98)")

    if trend_result and trend_result.get("falling"):
        lines.append(f"   📉 {trend_result['note']}")

    return "\n".join(lines)


if __name__ == "__main__":
    if "--charter" in sys.argv:
        print(json.dumps(CHARTER, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Сухая демонстрация зон индекса
    print("КОНТРОЛЁР — зоны индекса качества:\n")
    for val in [25, 65, 85, 99, None]:
        z = classify(val)
        mark = {"critical": "🔴", "danger": "🟠", "costs": "⚠️", "safe": "✅", "unknown": "❓"}[z["zone"]]
        print(f"{mark} {val if val is not None else 'unknown':>3}: {z['why']}")
        if z.get("cost"):
            print(f"   💰 {z['cost']}")

    print("\nДемонстрация: проверка 3 кампаний")
    def fake_quality(bid, cids):
        return [{"campaignId": "C1", "total": 92},
                {"campaignId": "C2", "total": 35},
                {"campaignId": "C3", "total": 99}]

    res = check("B1", ["C1", "C2", "C3"], quality_fn=fake_quality)
    print(render(res))

    print("\nТренд: падение индекса за сутки")
    from datetime import datetime, timedelta
    now = datetime.now()
    history = [{"at": (now - timedelta(hours=25)).isoformat(), "rating": 98},
               {"at": (now - timedelta(hours=12)).isoformat(), "rating": 94}]
    tr = trend(92, history)
    print(f"  {tr['note']}")
