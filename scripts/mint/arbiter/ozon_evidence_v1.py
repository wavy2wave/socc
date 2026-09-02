#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ДОКАЗАТЕЛЬСТВО (ozon_evidence_v1) — движок «не с неба взял» для всех отделов ОЗОНА.

Оператор дословно: «его работа не просто добавить а вся система видит что он угадал, не просто
с неба взял». Вот механизм этого. Два независимых свойства числа/решения любого отдела:

  1) ВОСПРОИЗВОДИМОСТЬ (grounded) — «не с неба взял». Каждое число живёт в упорядоченной ЦЕПИ
     шагов [отдел]→[вход]→[формула]→[число], посчитанной ЧИСТОЙ функцией из ЗАМОРОЖЕННОГО снимка
     входов (snapshot). Цикл берёт тот же снимок + тот же рецепт (recipe) → пересчитывает →
     сверяет. Совпало → grounded=True (число выведено, не выдумано). Кто-то руками подставил
     цифру мимо формулы → пересчёт её не даст → grounded=False (ложь всплывает сама).
     Это обобщение ymarket_glasses_v1.chain()/build_matrix() на ЛЮБОЙ отдел.

  2) УГАДАЛ или НЕТ (prediction → score) — то, чего у ЯМ ещё НЕТ. Отдел вправе заявить прогноз
     («индекс станет 🟢», «этот SKU продастся»). Прогноз несёт basis — ссылку на цепь, которая
     его обосновывает (без основания = weak, честно помечаем). Позже приходит ФАКТ (реальное
     чтение кабинета) → score() ставит hit=True/False. KPI суммирует: доля сбывшихся прогнозов =
     «система видит, что он угадал» в процентах, а не на словах.

ЗАКОНЫ ДВИЖКА (фиксируем как дисциплина органа):
  E1 «не с неба взял»: число попадает в цепь, только если ВЫВЕДЕНО из snapshot по формуле;
     replay обязан его воспроизвести. Не воспроизвёл → grounded=False (не прячем).
  E2 нет рецепта → не врём: реплей невозможен → grounded=None (честное «не проверить»),
     НЕ подделываем True. (Как «лучше ноль чем ложь» у КОНТРОЛЁРА.)
  E3 прогноз без основания считается, но помечается weak (basis=None) — чтобы KPI мог отделить
     обоснованные попадания от везения.
  E4 JSON-safe снимок: inf/-inf/nan → null, tuple→list — снимок обязан пережить журнал (JSONL,
     allow_nan=False), иначе завтрашний реплей подавится. (Как glasses._cfg_json_safe.)
  E5 ДЕТЕРМИНИЗМ: compute-функция рецепта — ЧИСТАЯ (без сети/времени/random). Иначе реплей
     бессмыслен. Метки времени (built_at/made_at) — метаданные, в сверку НЕ входят.

stdlib-only, 0₽, без сети. RUBICON цел по построению (это телеметрия рассуждений, не запись наружу).
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

CHAIN_SCHEMA = "ozon.evidence.chain.v1"
PRED_SCHEMA = "ozon.evidence.prediction.v1"

# Рецепты пересчёта: recipe_key -> compute(snapshot) -> list[step-dict|(...)] .
# Отдел регистрирует сюда СВОЮ чистую функцию, и цикл дня реплеит цепь по ключу, имея тот же код.
REGISTRY: dict = {}


# ── время (метаданные, вне сверки) ───────────────────────────────────────────────────────────
def _now():
    return datetime.now(timezone.utc).isoformat()


# ── JSON-безопасность снимка (E4) ─────────────────────────────────────────────────────────────
def json_safe(obj):
    """Рекурсивно привести к строгому-JSON виду: inf/-inf/nan → None, tuple/set → list.

    Снимок обязан пережить journal (JSONL, allow_nan=False) и вернуться тем же на реплее.
    Незнакомые типы (не число/строка/bool/None/список/словарь) → str(), чтобы не терять след.
    """
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return None if (math.isinf(obj) or math.isnan(obj)) else obj
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        seq = sorted(obj, key=str) if isinstance(obj, set) else obj
        return [json_safe(v) for v in seq]
    return str(obj)


def freeze(snapshot):
    """Заморозить снимок: json-safe + отвязать от исходника через строгий round-trip.

    После freeze снимок гарантированно сериализуем (allow_nan=False) и не меняется, если
    исходный объект потом мутируют. Это входы, из которых цепь ОБЯЗАНА быть выводима.
    """
    return json.loads(json.dumps(json_safe(snapshot), ensure_ascii=False, allow_nan=False))


# ── рецепты ──────────────────────────────────────────────────────────────────────────────────
def register(recipe_key, compute_fn):
    """Зарегистрировать чистую функцию пересчёта под ключом рецепта (для реплея по журналу)."""
    if not recipe_key or not callable(compute_fn):
        raise ValueError("register: нужен непустой recipe_key и вызываемая compute_fn")
    REGISTRY[recipe_key] = compute_fn
    return compute_fn


def recipe(recipe_key):
    """Декоратор-сахар: @recipe('ozon.pricer.floor') над compute(snapshot)->steps."""
    def deco(fn):
        register(recipe_key, fn)
        return fn
    return deco


# ── шаги и цепь ────────────────────────────────────────────────────────────────────────────────
def make_step(organ, name, formula, out, inputs=None, n=None):
    """Один шаг рассуждения: [organ] делает [name] по [formula], получает числа [out].

    out — словарь именованных чисел этого шага (то, что отдел «увидел»). inputs — какие ключи
    снимка / выходы прошлых шагов использованы (для читаемости и аудита, в сверку не входят).
    """
    step = {"organ": organ, "name": name, "formula": formula, "out": json_safe(out or {})}
    if inputs is not None:
        step["inputs"] = json_safe(inputs)
    if n is not None:
        step["n"] = n
    return step


def _normalize_steps(raw):
    """Привести выход compute() к списку пронумерованных шагов (терпим dict/tuple/список)."""
    steps = []
    for i, s in enumerate(list(raw or []), 1):
        if isinstance(s, dict):
            step = dict(s)
        elif isinstance(s, (list, tuple)) and len(s) >= 4:
            organ, name, formula, out = s[0], s[1], s[2], s[3]
            step = {"organ": organ, "name": name, "formula": formula, "out": out}
        else:
            raise TypeError(f"шаг #{i} не dict и не (organ,name,formula,out): {type(s).__name__}")
        step["out"] = json_safe(step.get("out") or {})
        if "inputs" in step:
            step["inputs"] = json_safe(step["inputs"])
        step["n"] = i
        steps.append(step)
    return steps


def build(department, question, snapshot, recipe_key, compute_fn=None, verdict_keys=None):
    """Собрать цепь доказательства: заморозить снимок → прогнать рецепт → упаковать шаги.

    department — кто рассуждает (отдел). question — на какой вопрос отвечает число.
    recipe_key — ключ рецепта (по нему цикл реплеит). compute_fn — сама чистая функция
    (по умолчанию берём из REGISTRY[recipe_key]; передать явно можно для отделов, что держат
    рецепт при себе). verdict — итоговые числа, за которые отдел отвечает (по умолчанию out
    последнего шага; verdict_keys сужает до нужных ключей по всем шагам).
    """
    fn = compute_fn or REGISTRY.get(recipe_key)
    if fn is None:
        raise KeyError(f"нет рецепта '{recipe_key}' в REGISTRY и не передан compute_fn")
    if compute_fn is not None and recipe_key and REGISTRY.get(recipe_key) is None:
        REGISTRY[recipe_key] = compute_fn          # само-регистрация: журнал станет реплеим
    snap = freeze(snapshot)
    steps = _normalize_steps(fn(snap))
    if verdict_keys:
        verdict = {}
        for s in steps:
            for k in verdict_keys:
                if k in s["out"]:
                    verdict[k] = s["out"][k]
    else:
        verdict = dict(steps[-1]["out"]) if steps else {}
    return {
        "schema": CHAIN_SCHEMA,
        "department": department,
        "question": question,
        "recipe": recipe_key,
        "snapshot": snap,
        "steps": steps,
        "verdict": json_safe(verdict),
        "grounded": None,       # ставит replay/ground — до сверки честно неизвестно
        "built_at": _now(),
    }


# ── сверка (реплей) — сердце «не с неба взял» ──────────────────────────────────────────────────
def _num_eq(a, b, tol):
    """Числа равны с относительным допуском tol; None/bool/строки/контейнеры — точно/рекурсивно."""
    if a is None or b is None:
        return a is b or a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isnan(a) or math.isnan(b):
            return math.isnan(a) and math.isnan(b)
        if math.isinf(a) or math.isinf(b):
            return a == b
        return abs(a - b) <= tol * max(1.0, abs(a), abs(b))
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_num_eq(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_num_eq(a[k], b[k], tol) for k in a)
    return a == b


def _diff_steps(stored, fresh, tol):
    """Список расхождений между сохранённой цепью и пересчитанной. Пусто → воспроизвелось точь-в-точь."""
    drift = []
    if len(stored) != len(fresh):
        drift.append({"step": None, "key": "_len", "stored": len(stored), "fresh": len(fresh)})
    for i in range(min(len(stored), len(fresh))):
        a, b = stored[i], fresh[i]
        if (a.get("organ"), a.get("name")) != (b.get("organ"), b.get("name")):
            drift.append({"step": i + 1, "key": "_identity",
                          "stored": [a.get("organ"), a.get("name")],
                          "fresh": [b.get("organ"), b.get("name")]})
        ao, bo = a.get("out", {}), b.get("out", {})
        for k in set(ao) | set(bo):
            if k not in ao or k not in bo or not _num_eq(ao.get(k), bo.get(k), tol):
                drift.append({"step": i + 1, "key": k, "stored": ao.get(k), "fresh": bo.get(k)})
    return drift


def replay(chain, compute_fn=None, tol=1e-9):
    """Пересчитать цепь из её ЗАМОРОЖЕННОГО снимка тем же рецептом и сверить (E1/E2).

    Возврат:
      {recomputable, grounded, drift, note?}
        recomputable=False, grounded=None — рецепта нет (E2: честно «не проверить», не врём True).
        recomputable=True,  grounded=True — числа воспроизвелись из входов → «не с неба взял».
        recomputable=True,  grounded=False — расхождение (drift непуст) или пересчёт упал.
    """
    key = chain.get("recipe")
    fn = compute_fn or (REGISTRY.get(key) if key else None)
    if fn is None:
        return {"recomputable": False, "grounded": None, "drift": [],
                "note": f"нет рецепта '{key}' в REGISTRY — реплей невозможен (E2)"}
    try:
        fresh = _normalize_steps(fn(chain.get("snapshot")))
    except Exception as e:                                    # пересчёт упал → не заземлено, но честно
        return {"recomputable": True, "grounded": False, "drift": [],
                "error": f"{type(e).__name__}: {e}"}
    drift = _diff_steps(chain.get("steps", []), fresh, tol)
    return {"recomputable": True, "grounded": (len(drift) == 0), "drift": drift}


def ground(chain, compute_fn=None, tol=1e-9):
    """replay + записать вердикт заземления в саму цепь (chain['grounded'], chain['_replay'])."""
    r = replay(chain, compute_fn=compute_fn, tol=tol)
    chain["grounded"] = r["grounded"]
    chain["_replay"] = {k: v for k, v in r.items() if k != "grounded"}
    return chain


def groundedness(chains):
    """Доля заземлённых цепей в пачке — «сколько чисел не с неба» в процентах (для KPI).

    Считаем только ПРОВЕРЕННЫЕ (grounded True/False); grounded=None (рецепта нет) — pending,
    в знаменатель доли не берём (E2: не наказываем и не хвалим за непроверяемое).
    """
    total = len(chains)
    checked = [c for c in chains if c.get("grounded") is not None]
    grounded = sum(1 for c in checked if c.get("grounded"))
    return {
        "total": total,
        "checked": len(checked),
        "grounded": grounded,
        "ungrounded": len(checked) - grounded,
        "pending": total - len(checked),
        "grounded_pct": round(grounded / len(checked) * 100.0, 1) if checked else None,
    }


# ── прогноз → факт («угадал или нет») ──────────────────────────────────────────────────────────
def predict(department, metric, predicted, basis=None, horizon="next_read", ctx=None):
    """Заявить прогноз отдела. basis — ссылка на цепь-основание (recipe/sku/hash), иначе weak (E3).

    metric — что предсказываем (напр. 'index_color', 'will_sell'). predicted — сам прогноз.
    horizon — когда проверять фактом ('next_read' | 'day' | 'week'). ctx — что предсказание про
    что (напр. {'sku': 'OZ-1'}), чтобы факт можно было сопоставить с той же позицией.
    """
    return {
        "schema": PRED_SCHEMA,
        "department": department,
        "metric": metric,
        "predicted": json_safe(predicted),
        "basis": basis,                 # None → weak (E3)
        "weak": basis is None,
        "horizon": horizon,
        "ctx": json_safe(ctx or {}),
        "made_at": _now(),
        "actual": None,
        "hit": None,                    # ставит score(): True/False
        "checked_at": None,
    }


def _default_compare(predicted, actual):
    """Совпадение прогноза и факта: числа — относительный допуск ±10%; остальное — точное равенство."""
    if isinstance(predicted, bool) or isinstance(actual, bool):
        return predicted == actual
    if isinstance(predicted, (int, float)) and isinstance(actual, (int, float)):
        if math.isnan(predicted) or math.isnan(actual):
            return False
        return abs(predicted - actual) <= 0.10 * max(1.0, abs(predicted), abs(actual))
    return predicted == actual


def score(prediction, actual, compare=None):
    """Пришёл ФАКТ → проставить actual/hit/checked_at. compare — своё правило сверки (шов отдела).

    Возвращает НОВЫЙ словарь (исходный прогноз не мутируем — он мог уже лежать в журнале).
    """
    cmp = compare or _default_compare
    p = dict(prediction)
    p["actual"] = json_safe(actual)
    p["hit"] = bool(cmp(prediction.get("predicted"), actual))
    p["checked_at"] = _now()
    return p


def accuracy(predictions, weak_counts=True):
    """Табло попаданий: доля сбывшихся прогнозов = «система видит, что угадал» в процентах.

    weak_counts=False → в точность берём только обоснованные прогнозы (basis!=None, E3),
    чтобы отделить мастерство от везения. pending — ещё не проверенные фактом.
    """
    pool = predictions if weak_counts else [p for p in predictions if not p.get("weak")]
    checked = [p for p in pool if p.get("hit") is not None]
    hits = sum(1 for p in checked if p.get("hit"))
    return {
        "total": len(pool),
        "checked": len(checked),
        "hits": hits,
        "misses": len(checked) - hits,
        "pending": len(pool) - len(checked),
        "weak": sum(1 for p in predictions if p.get("weak")),
        "accuracy_pct": round(hits / len(checked) * 100.0, 1) if checked else None,
    }


# ── человеческий вид (реасонинг видно глазами) ─────────────────────────────────────────────────
def render_chain(chain):
    """Показать цепь как рассуждение: шаг за шагом [отдел]→[формула]→[числа] + вердикт заземления."""
    g = chain.get("grounded")
    mark = {True: "✅ заземлено", False: "❌ НЕ воспроизвелось", None: "… не проверено"}.get(g, "?")
    out = [f"🧾 ЦЕПЬ [{chain.get('department')}] {chain.get('question', '')}  ({mark})"]
    for s in chain.get("steps", []):
        out.append(f"   {s.get('n')}. {s.get('name', ''):<22} [{s.get('organ', '')}]")
        out.append(f"      {s.get('formula', '')}")
        nums = " · ".join(f"{k}={v}" for k, v in (s.get("out") or {}).items() if v is not None)
        if nums:
            out.append(f"      → {nums}")
    dr = (chain.get("_replay") or {}).get("drift") or []
    for d in dr[:6]:
        out.append(f"   ⚠ расхождение шаг {d.get('step')} · {d.get('key')}: "
                   f"хранилось {d.get('stored')} ≠ пересчёт {d.get('fresh')}")
    return "\n".join(out)


if __name__ == "__main__":
    # Сухая демонстрация обоих свойств на выдуманных числах (0 сети, 0₽).
    import argparse
    ap = argparse.ArgumentParser(description="ДОКАЗАТЕЛЬСТВО — движок «не с неба взял» (демо)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    # рецепт: чистая функция входы→шаги (реверс-ценообразование, как у ОЧКОВ)
    @recipe("demo.pricer.floor")
    def _demo_floor(s):
        cost, comm, dlv, P = s["cost"], s["comm"], s["delivery"], s["target_profit"]
        sell = math.ceil((cost + dlv + P) / (1 - comm) / 10.0) * 10.0
        fees = round(sell * comm + dlv, 2)
        profit = round(sell - cost - fees, 2)
        return [
            make_step("ПРИСОСКА", "закупка", "cost = розница донора", {"cost": cost}),
            make_step("ОЧКИ", "цена продажи", "S = ceil((cost+dlv+P)/(1−comm)/10)·10", {"sell": sell}),
            make_step("ЭКОНОМ", "сборы", "fees = S·comm + dlv", {"fees": fees}),
            make_step("ЭКОНОМ", "профит", "profit = S − cost − fees", {"profit": profit}),
        ]

    snap = {"cost": 250.0, "comm": 0.445, "delivery": 120.0, "target_profit": 300.0}
    ch = build("ЦЕНОВИК", "какую цену выставить", snap, "demo.pricer.floor")
    ground(ch)
    print(render_chain(ch))

    # подделка: руками портим число мимо формулы → реплей ловит (grounded=False)
    faked = json.loads(json.dumps(ch))
    faked["steps"][3]["out"]["profit"] = 999.0
    ground(faked)
    print("\nпосле подделки profit=999:", "заземлено" if faked["grounded"] else "❌ поймано (не с неба)")

    # прогноз → факт
    pr = predict("ЦЕНОВИК", "index_color", "GREEN", basis="demo.pricer.floor/OZ-1", ctx={"sku": "OZ-1"})
    hit = score(pr, "GREEN")
    miss = score(pr, "RED")
    print(f"\nпрогноз GREEN → факт GREEN: hit={hit['hit']} · факт RED: hit={miss['hit']}")
    print("точность:", accuracy([hit, miss]))

    if args.json:
        print("\n" + json.dumps(ch, ensure_ascii=False, indent=2))
