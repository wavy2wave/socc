"""WAVE GATEWAY — тесты обоймы сырых ключей (upstream_pool.py).

На чём тут теряют деньги/доступ, если сломать:
  1. Умер один ключ → должны подхватить следующий, а не положить всех клиентов.
  2. 429 (перегрет) спутали с 401 (мёртв) → сожгли годный ключ навсегда.
  3. Смерть ключа не пережила рестарт → на каждый запуск снова стучимся в
     отозванный ключ и ловим отказы.
  4. Дозаливка «дров» требует перезапуска → оператор роняет сервис ради
     добавления ключа.
  5. Квота клиента списалась, хотя наверх ничего не ушло (обойма пуста).

Всё проверяется БЕЗ единого живого HTTP-запроса: ротацию гоняем через dispatch()
с поддельным call_fn, время инжектим параметром now.

Запуск:  python3 tests/upstream_pool_v1.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway.upstream_pool import (  # noqa: E402
    NoCapacity,
    UpstreamPool,
    dispatch,
    fingerprint,
)

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def write_keys(path: Path, keys: list[str], mtime: float | None = None) -> None:
    path.write_text("\n".join(keys) + "\n", encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


# Классификатор для dispatch-тестов: маркерные исключения → вердикт.
class DeadErr(Exception):
    pass


class CoolErr(Exception):
    pass


class OtherErr(Exception):
    pass


def _classify(exc: BaseException) -> str:
    if isinstance(exc, DeadErr):
        return "dead"
    if isinstance(exc, CoolErr):
        return "cooldown"
    return "raise"


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_pool_test_"))
    try:
        K1, K2, K3 = "sk-alpha-1111", "sk-bravo-2222", "sk-charlie-3333"

        # ---------- Загрузка из файла + sticky-выбор ----------
        pf = tmp / "pool.keys"
        sf = tmp / "state.json"
        write_keys(pf, [K1, K2, K3])
        pool = UpstreamPool(pool_file=pf, state_file=sf)
        check(pool.stats()["total"] == 3, "файл: загружены 3 ключа")
        now = 1_000.0
        check(pool.pick(now) == K1 and pool.pick(now) == K1,
              "sticky: держимся текущего патрона, пока он жив")

        # ---------- Комментарии и пустые строки игнорируются ----------
        pf2 = tmp / "pool2.keys"
        pf2.write_text("# шапка\n\n  sk-only  \n# ещё коммент\n", encoding="utf-8")
        p2 = UpstreamPool(pool_file=pf2, state_file=tmp / "s2.json")
        check(p2.stats()["total"] == 1 and p2.pick(now) == "sk-only",
              "парсинг: # и пустые строки пропущены, ключ обрезан от пробелов")

        # ---------- 401/403: мёртв навсегда, курсор едет дальше + персист ----------
        pool.mark_dead(K1)
        check(pool.pick(now) == K2, "после смерти патрона ротация встаёт на следующий")
        state = json.loads(sf.read_text())
        check(fingerprint(K1) in state.get("dead", []),
              "смерть хранится по ОТПЕЧАТКУ (не сырой ключ) в файле состояния")
        check(K1 not in sf.read_text() and "sk-" not in sf.read_text(),
              "в файле состояния нет сырых ключей — только хеши")

        # ---------- Смерть переживает рестарт ----------
        pool_restart = UpstreamPool(pool_file=pf, state_file=sf)
        check(pool_restart.pick(now) == K2,
              "новый процесс с тем же state: мёртвый патрон по-прежнему исключён")

        # ---------- 429: cooldown, пропускаем, потом снова годен ----------
        cf = tmp / "cool.keys"
        write_keys(cf, [K1])
        cp = UpstreamPool(pool_file=cf, state_file=tmp / "cs.json", cooldown_sec=60)
        cp.mark_cooldown(K1, now=now, seconds=60)
        check(cp.pick(now) is None, "перегретый (429) ключ временно не выдаётся")
        check(cp.exhausted_reason(now) == "cooling", "причина пустоты: cooling, а не смерть")
        check(cp.pick(now + 61) == K1, "после паузы перегретый ключ снова годен")
        cp.report_ok(K1)
        check(cp.pick(now) == K1, "report_ok снимает паузу немедленно")

        # ---------- 429 не жжёт годный: скип перегретого при живом соседе ----------
        sf3 = tmp / "skip.keys"
        write_keys(sf3, [K1, K2])
        sp = UpstreamPool(pool_file=sf3, state_file=tmp / "sk.json")
        sp.mark_cooldown(K1, now=now, seconds=60)
        check(sp.pick(now) == K2, "перегретый пропущен, обслужил живой сосед")

        # ---------- Все мертвы / пусто ----------
        write_keys(sf3, [K1, K2])  # свежий, без cooldown
        dp = UpstreamPool(pool_file=sf3, state_file=tmp / "dk.json")
        dp.mark_dead(K1)
        dp.mark_dead(K2)
        check(dp.pick(now) is None and not dp.has_capacity(),
              "все патроны мертвы → ёмкости нет")
        check(dp.exhausted_reason(now) == "all_dead", "причина: all_dead")
        empty = UpstreamPool(pool_file=tmp / "nope.keys", state_file=tmp / "ek.json")
        check(empty.stats()["total"] == 0 and empty.pick(now) is None,
              "пустая обойма: 0 ключей, pick=None")
        check(empty.exhausted_reason(now) == "empty", "причина: empty")

        # ---------- Горячая дозаливка «дров» без перезапуска ----------
        hf = tmp / "hot.keys"
        write_keys(hf, [K1], mtime=now)
        hp = UpstreamPool(pool_file=hf, state_file=tmp / "hk.json")
        check(hp.stats()["total"] == 1, "до дозаливки: 1 ключ")
        write_keys(hf, [K1, K2, K3], mtime=now + 100)  # bump mtime — иначе reload скипнет
        check(hp.stats()["total"] == 3, "дозаливка подхвачена БЕЗ пересоздания обоймы")
        hp.mark_dead(K1)
        check(hp.pick(now) == K2, "новый дозалитый ключ реально идёт в дело после смерти старого")

        # ---------- Источники: env-single и env-list, дедуп ----------
        es = UpstreamPool(pool_file=tmp / "absent.keys", state_file=tmp / "esk.json",
                          env_single="sk-env-single")
        check(es.pick(now) == "sk-env-single",
              "обратная совместимость: одиночный WAVE_UPSTREAM_KEY работает как патрон")
        el = UpstreamPool(pool_file=tmp / "absent2.keys", state_file=tmp / "elk.json",
                          env_keys="sk-a, sk-b ,sk-c")
        check(el.stats()["total"] == 3 and el.pick(now) == "sk-a",
              "список через запятую разобран, порядок сохранён")
        write_keys(pf2, [K1])
        dd = UpstreamPool(pool_file=pf2, state_file=tmp / "ddk.json",
                          env_keys=K1, env_single=K1)
        check(dd.stats()["total"] == 1, "дубликаты из разных источников схлопнуты")

        # ---------- dispatch(): ротация на живой поверх failover ----------
        write_keys(sf3, [K1, K2, K3])
        rp = UpstreamPool(pool_file=sf3, state_file=tmp / "rk.json")
        served: list[str] = []

        def call_dead_then_ok(key):
            if key == K1:
                raise DeadErr("401")
            served.append(key)
            return {"ok": True, "usage": {}}, 200

        payload, status = dispatch(rp, call_dead_then_ok, _classify)
        check(status == 200 and served == [K2],
              "dispatch: мёртвый патрон отбракован, запрос обслужил следующий")
        check(fingerprint(K1) in json.loads((tmp / "rk.json").read_text())["dead"],
              "dispatch пометил K1 мёртвым (переживёт рестарт)")

        # ---------- dispatch(): 429 → пауза и следующий ----------
        write_keys(sf3, [K1, K2])
        rp2 = UpstreamPool(pool_file=sf3, state_file=tmp / "rk2.json")
        got = {}

        def call_cool_then_ok(key):
            if key == K1:
                raise CoolErr("429")
            got["key"] = key
            return {"ok": True}, 200

        _, st2 = dispatch(rp2, call_cool_then_ok, _classify)
        check(st2 == 200 and got.get("key") == K2,
              "dispatch: перегретый (429) пропущен, обслужил сосед")
        check(rp2.stats()["cooling"] == 1, "перегретый помечен cooling, НЕ dead")

        # ---------- dispatch(): 'raise' пробрасывается как есть ----------
        write_keys(sf3, [K1])
        rp3 = UpstreamPool(pool_file=sf3, state_file=tmp / "rk3.json")
        raised = None
        try:
            dispatch(rp3, lambda k: (_ for _ in ()).throw(OtherErr("boom")), _classify)
        except OtherErr as e:
            raised = e
        except NoCapacity:
            raised = "nocap"
        check(isinstance(raised, OtherErr),
              "dispatch: сбой провайдера/сети (не про обойму) пробрасывается наружу")

        # ---------- dispatch(): пусто → NoCapacity (квота НЕ спишется) ----------
        rp4 = UpstreamPool(pool_file=tmp / "none.keys", state_file=tmp / "rk4.json")
        nocap = None
        try:
            dispatch(rp4, lambda k: ({}, 200), _classify)
        except NoCapacity as e:
            nocap = e
        check(nocap is not None and nocap.reason == "empty",
              "dispatch: пустая обойма → NoCapacity('empty'), запрос наверх не ушёл")

        # ---------- dispatch(): лимит попыток на один запрос ----------
        write_keys(sf3, [K1, K2, K3, "sk-4", "sk-5"])
        rp5 = UpstreamPool(pool_file=sf3, state_file=tmp / "rk5.json", max_attempts=2)
        exhausted = None
        try:
            dispatch(rp5, lambda k: (_ for _ in ()).throw(DeadErr("401")), _classify)
        except NoCapacity as e:
            exhausted = e
        check(exhausted is not None and exhausted.reason == "attempts_exhausted",
              "dispatch: не перебираем всю обойму на один запрос (лимит попыток)")
        check(rp5.stats()["dead"] == 2,
              "за один запрос помечено ровно max_attempts мёртвых — обойма самоочищается")

        passed = sum(1 for ok, _ in results if ok)
        total = len(results)
        print(f"\n{'=' * 52}\nИТОГ: {passed}/{total} проверок пройдено")
        if passed == total:
            print("🔁 Обойма: failover держит, смерти переживают рестарт, дрова горячие.")
            return 0
        print("Есть красные проверки — смотрите выше.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
