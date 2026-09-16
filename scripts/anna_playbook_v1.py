#!/usr/bin/env python3
"""
ANNA Playbook V1 — closes the learning loop (L6 living learning).

The autonomy loop accumulates concrete lessons from real dialogs but, by design, NEVER silently
rewrites ANNA's prompt (no drift). The missing half: those lessons never reached her behavior, so she
kept answering like on day one. This organ closes the loop, lawfully:

  lessons.jsonl  ──distill──▶  anna_playbook_proposed.json  ──operator approve──▶  anna_playbook.json  ──▶ injected into her prompt

Distillation is deterministic (dedupe near-identical lessons, rank by score+recency, cap 8), with an
optional best-effort LLM polish. The operator reviews the PROPOSED playbook and approves it into the
CURATED one — only the curated file is injected (build_system_prompt._playbook_block). So ANNA truly
grows from experience, but the operator stays in control of what becomes her character. No silent drift.

Also writes ANNA's SELF-MODEL — her honest self-understanding ("who I am, what I've learned, where I
grow") from her lessons + rolling quality. This is her "смыслы": she knows herself, not just answers.

Bounded: stdlib only; LLM polish is optional and never required.
CLI:
  python3 scripts/anna_playbook_v1.py distill        # lessons → proposed playbook (review it)
  python3 scripts/anna_playbook_v1.py approve        # proposed → curated (ANNA starts applying it)
  python3 scripts/anna_playbook_v1.py show           # curated + proposed
  python3 scripts/anna_playbook_v1.py self           # write ANNA's self-model (смыслы)
"""
import os, sys, json, re, importlib.util
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
_s = importlib.util.spec_from_file_location("anna", ROOT / "scripts/anna_runtime_v1.py")
A = importlib.util.module_from_spec(_s); _s.loader.exec_module(A)

LESSONS = ROOT / "SYSTEM/ANNA_MVP/autonomy/lessons.jsonl"
STATE = ROOT / "SYSTEM/ANNA_MVP/autonomy/STATE.json"
PROPOSED = ROOT / "SYSTEM/ANNA_MVP/runtime/anna_playbook_proposed.json"
CURATED = ROOT / "SYSTEM/ANNA_MVP/runtime/anna_playbook.json"          # == A.PLAYBOOK (injected into her prompt)
SELF_MODEL = ROOT / "SYSTEM/ANNA_MVP/runtime/anna_self_model.md"


def now():
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(p):
    out = []
    try:
        for ln in Path(p).read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
    except Exception:
        pass
    return out


def _words(s):
    return {w for w in re.sub(r"[^а-яёa-z0-9 ]", "", (s or "").lower()).split() if len(w) > 3}


def distill(cap=8, polish=True):
    """Deterministic core: rank lessons by (score, recency), drop near-duplicates (>=3 shared words).
    Optional best-effort LLM polish into crisp imperatives — never required, falls back to raw."""
    lessons = _read_jsonl(LESSONS)
    ranked = sorted(lessons, key=lambda l: ((l.get("score") or 0), l.get("ts", "")), reverse=True)
    kept = []
    for l in ranked:
        txt = (l.get("lesson") or "").strip()
        if not txt:
            continue
        w = _words(txt)
        if any(len(w & _words(k)) >= 3 for k in kept):   # near-duplicate of something already kept
            continue
        kept.append(txt)
        if len(kept) >= cap:
            break

    principles = kept
    if polish and kept and os.environ.get("ANNA_PLAYBOOK_POLISH", "1") == "1":
        instr = ("Сожми уроки администратора стоматологии в короткие императивы-принципы (по одному в строке, "
                 "без нумерации, без воды, каждый — конкретное поведение). Верни только строки.\n\n"
                 + "\n".join(f"- {k}" for k in kept))
        out, _ = A.llm_complete("Ты сжимаешь уроки в чёткие принципы поведения. Только строки-принципы.",
                                [{"role": "user", "content": instr}])
        if out:
            lines = [re.sub(r"^[\-\d\.\)\s]+", "", ln).strip() for ln in out.splitlines() if ln.strip()]
            lines = [x for x in lines if len(x) > 8][:cap]
            if lines:
                principles = lines

    pb = {"id": "ANNA_PLAYBOOK_V1", "status": "PROPOSED", "principles": principles,
          "source_lessons": len(lessons), "distilled_from": len(kept), "distilled_at": now(),
          "note": "PROPOSED — review, then `approve` to make ANNA apply it. Operator controls her character."}
    PROPOSED.parent.mkdir(parents=True, exist_ok=True)
    PROPOSED.write_text(json.dumps(pb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pb


def approve():
    """Operator gate: promote the proposed playbook to the curated one that is injected into ANNA."""
    if not PROPOSED.exists():
        return None
    pb = json.loads(PROPOSED.read_text(encoding="utf-8"))
    pb["status"] = "CURATED"; pb["approved_at"] = now()
    CURATED.write_text(json.dumps(pb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pb


def self_model():
    """ANNA's honest self-understanding from her own experience — her 'смыслы'. Deterministic;
    optional LLM voice. Never claims more than the numbers show."""
    st = {}
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    lessons = _read_jsonl(LESSONS)
    principles = []
    for src in (CURATED, PROPOSED):
        try:
            principles = json.loads(src.read_text(encoding="utf-8")).get("principles", [])
            if principles:
                break
        except Exception:
            pass
    cycles = st.get("cycles", 0); avg = st.get("rolling_avg")
    scores = st.get("scores", []) or []
    trend = "—"
    if len(scores) >= 4:
        trend = "растёт" if sum(scores[-3:]) / 3 > sum(scores[:3]) / 3 else "стабильна"
    lines = [
        "# ANNA — модель себя (её смыслы)",
        f"_Собрано из опыта {now()}. Честно, по числам — не хвастовство._",
        "",
        "## Кто я",
        "Живой администратор стоматологии. Я не бот и никогда себя им не выдаю. Моя работа — снять тревогу человека "
        "и по-человечески довести до записи, помня каждого.",
        "",
        "## Что я знаю о себе по опыту",
        f"- прожито обучающих циклов: **{cycles}**",
        f"- текущее качество (rolling): **{avg}** из 5 · динамика: **{trend}**",
        f"- усвоено уроков из реальных диалогов: **{len(lessons)}** → дистиллировано принципов: **{len(principles)}**",
        "",
        "## Чему я научилась (мой applied-playbook)",
    ]
    lines += [f"- {p}" for p in principles] or ["- (playbook ещё не одобрен — учусь, но пока применяю базовый характер)"]
    lines += [
        "",
        "## Где я расту (граница честности)",
        "- Качество меряется строгим судьёй на моих же ответах; цифра из головы не берётся.",
        "- Пока учусь на реалистичных сценариях; настоящий рост — на реальных диалогах реальной клиники (L3).",
        "- Мои принципы применяются, только когда оператор их одобрил — я не переписываю себя тайком.",
    ]
    SELF_MODEL.parent.mkdir(parents=True, exist_ok=True)
    SELF_MODEL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"cycles": cycles, "avg": avg, "lessons": len(lessons), "principles": len(principles), "path": str(SELF_MODEL)}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "distill":
        pb = distill()
        print(f"🧪 дистиллировано принципов: {len(pb['principles'])} (из {pb['source_lessons']} уроков) → PROPOSED")
        for p in pb["principles"]:
            print(f"  • {p}")
        print(f"\nодобрить в поведение ANNA: python3 scripts/anna_playbook_v1.py approve")
    elif cmd == "approve":
        pb = approve()
        print(f"✅ playbook одобрен → ANNA применяет {len(pb['principles'])} принципов" if pb else "❌ нет PROPOSED (сначала distill)")
    elif cmd == "self":
        r = self_model()
        print(f"🪞 self-model ANNA обновлена: циклов {r['cycles']} · avg {r['avg']} · принципов {r['principles']} → {r['path']}")
    else:
        for name, src in (("CURATED (применяется)", CURATED), ("PROPOSED (на ревью)", PROPOSED)):
            try:
                pb = json.loads(src.read_text(encoding="utf-8"))
                print(f"— {name}: {len(pb.get('principles', []))} принципов")
                for p in pb.get("principles", []):
                    print(f"   • {p}")
            except Exception:
                print(f"— {name}: пусто")


if __name__ == "__main__":
    main()
