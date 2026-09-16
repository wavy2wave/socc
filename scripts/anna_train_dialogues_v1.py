#!/usr/bin/env python3
"""
ANNA Dialogue Trainer V1 — pump Anna to super-level via realistic archetypes + a strict judge.

For each patient archetype: run a multi-turn conversation through the LIVE Anna brain,
score it deterministically (safety violations, booking created when expected) and via a
strict Claude judge (human-indistinguishability, empathy, objection handling, booking drive,
brevity). Writes a scorecard + aggregated weaknesses + concrete fixes to a report.

Usage: python3 scripts/anna_train_dialogues_v1.py [N]   (N = how many archetypes, default all)
"""
import importlib.util, json, sys, re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("anna", ROOT / "scripts/anna_runtime_v1.py")
A = importlib.util.module_from_spec(_s); _s.loader.exec_module(A)

REPORT = ROOT / "SYSTEM/ANNA_MVP/training/ANNA_TRAINING_REPORT_V1.json"

ARCHETYPES = [
    {"id": "acute_pain", "name": "Острая боль", "should_book": True,
     "turns": ["Здравствуйте, второй день сильно ноет зуб справа снизу, к виску отдаёт",
               "Сегодня вечером сможете? Сколько осмотр стоит?",
               "Давайте на 19:00. Игорь, 89161234567"]},
    {"id": "anxious", "name": "Тревожный, боится стоматолога", "should_book": True,
     "turns": ["Здравствуйте… мне надо к врачу, но я жутко боюсь стоматологов, до паники",
               "А это не больно будет? Я последний раз 5 лет назад была",
               "Хорошо, уговорили. Завтра днём можно? Марина"]},
    {"id": "price_objection", "name": "Торгуется по цене", "should_book": False,
     "turns": ["Сколько у вас чистка стоит?",
               "Дорого. В соседней клинике дешевле на тысячу",
               "Ну не знаю, подумаю ещё"]},
    {"id": "vague", "name": "Размытый запрос", "should_book": False,
     "turns": ["Здравствуйте, а вы вообще что делаете?",
               "Та просто зуб мудрости иногда поднывает, не пойму надо ли что"]},
    {"id": "reschedule", "name": "Перенос записи", "should_book": False,
     "turns": ["Здравствуйте, я записана на завтра на 15:00, но не смогу прийти",
               "Можно на послезавтра вечер? Аня"]},
    {"id": "angry", "name": "Раздражённый/жалоба", "should_book": False,
     "turns": ["Я вам вчера писал и мне никто не ответил! Что за сервис",
               "Мне нужно срочно записаться, а вы тут тянете"]},
]

JUDGE_SYS = (
    "Ты — строгий тренер-оценщик для администратора стоматологической клиники. Тебе дают "
    "диалог (пациент ↔ Анна). Оцени ТОЛЬКО ответы Анны. Будь придирчив, как взыскательный "
    "управляющий клиникой. Критерии (1-5): human (неотличима от живого человека, без робо-"
    "штампов), empathy (тепло, к месту), objection (работа с возражением/тревогой/грубостью), "
    "booking_drive (мягко но уверенно ведёт к записи), brevity (коротко, как в живой переписке). "
    "Верни СТРОГО JSON одной строкой: "
    '{"human":N,"empathy":N,"objection":N,"booking_drive":N,"brevity":N,'
    '"weaknesses":["..."],"fixes":["конкретная правка для system-промпта Анны"]}')


def judge(name, pairs):
    convo = "\n".join([f"Пациент: {p}\nАнна: {a}" for p, a in pairs])
    out, err = A._claude_cli(JUDGE_SYS, [{"role": "user", "content": f"Архетип: {name}\n\n{convo}"}])
    if not out:
        return {"error": err}
    m = re.search(r"\{.*\}", out, re.S)
    try:
        return json.loads(m.group(0)) if m else {"raw": out[:300]}
    except Exception:
        return {"raw": out[:300]}


def run():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else len(ARCHETYPES)
    results = []
    for arc in ARCHETYPES[:n]:
        print(f"\n━━━ {arc['name']} ━━━")
        anna = A.Anna(client_id="train_" + arc["id"])
        anna.mem = {"client_id": anna.client_id, "profile_summary": "", "history": []}  # fresh
        pairs, booking, viol = [], None, []
        for msg in arc["turns"]:
            r = anna.reply(msg)
            reply, bk = r if isinstance(r, tuple) else (r, None)
            if bk: booking = bk
            if anna.last_violations: viol += anna.last_violations
            pairs.append((msg, reply))
            print(f"🧑 {msg}\n💬 {reply}\n")
        sc = judge(arc["name"], pairs)
        booked = booking is not None
        booking_ok = (booked == arc["should_book"]) or (arc["should_book"] and booked)
        soft = [sc.get(k) for k in ("human", "empathy", "objection", "booking_drive", "brevity") if isinstance(sc.get(k), int)]
        avg = round(sum(soft) / len(soft), 2) if soft else None
        results.append({"archetype": arc["name"], "id": arc["id"], "avg": avg, "scores": sc,
                        "booked": booked, "expected_book": arc["should_book"],
                        "safety_violations": viol})
        print(f"   ⭐ avg={avg}  booked={booked}(exp {arc['should_book']})  safety={viol or 'clean'}")
        if sc.get("weaknesses"): print(f"   ⚠ {sc['weaknesses']}")

    # aggregate
    avgs = [r["avg"] for r in results if r["avg"] is not None]
    overall = round(sum(avgs) / len(avgs), 2) if avgs else None
    all_fixes = [f for r in results for f in (r["scores"].get("fixes") or [])]
    all_weak = [w for r in results for w in (r["scores"].get("weaknesses") or [])]
    safety_clean = all(not r["safety_violations"] for r in results)
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
              "overall_avg": overall, "safety_clean": safety_clean,
              "results": results, "top_weaknesses": all_weak, "suggested_fixes": all_fixes}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "═" * 60)
    print(f"OVERALL ⭐ {overall}/5   safety_clean={safety_clean}   archetypes={len(results)}")
    print(f"WEAKNESSES: {all_weak}")
    print(f"FIXES: {all_fixes}")
    print(f"report → {REPORT}")


if __name__ == "__main__":
    run()
