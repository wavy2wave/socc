#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФОТО-СНАБЖЕНЕЦ ПРИЁМКА — батч-орган 190×(1-3): hunt-first → forge-fallback → фирменная лента.

Проверяем ДВА столпа: (а) ЛОГИКА добычи — hero берётся честно (free только good+не-compromise+conf+canon;
unknown/bad НИКОГДА не hero; промах → кузница; всё провалил → weak в лог, не на витрину); (б) RUBICON —
dry=0₽/0 сети, потолок расхода режет пачку честно, факты не выдумываем, монтаж 0 токенов, наружу к
витрине НЕ клеим. Соседи-органы подменяются фейками → приёмка детерминирована и идентична на обоих
интерпретаторах (venv+Pillow и системный 3.14 без Pillow). PS13 дополнительно гоняет РЕАЛЬНУЮ регрессию
соседей (forge/pipeline/infographic) тем же интерпретатором — на venv с PIL-тестами, на системном честный скип.
"""
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARB = HERE.parent
MINT = ARB.parent
for p in (str(ARB), str(MINT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import photo_supply_v1 as ps    # noqa: E402


def _passed(cond):
    return "✅ PASS" if cond else "❌ FAIL"


# ── Фейки соседей (детерминизм + независимость от сети/PIL/ключей) ────────────────────
class FakeHunter:
    def __init__(self, good=(), discovered=(), fetch=b"IMGBYTES"):
        self.good = list(good)
        self.discovered = list(discovered)
        self.fetch = fetch
        self.calls = []

    def hunt(self, urls, facts=None, need=5, donor_urls=()):
        self.calls.append(("hunt", tuple(urls)))
        return {"good": list(self.good), "bad": [], "unknown": [], "need": need,
                "got": len(self.good), "enough": True, "capabilities": {}}

    def fetch_bytes(self, url, timeout=25, retries=1, max_bytes=12_000_000):
        self.calls.append(("fetch", url))
        return (self.fetch, "image/png")

    def discover(self, query, facts=None, **kw):
        self.calls.append(("discover", query))
        return list(self.discovered)

    def capabilities(self):
        return {"download": True, "vision": True, "ocr": True}


class TripwireHunter(FakeHunter):
    """Любой сетевой шов = взрыв. Доказывает, что dry НЕ трогает сеть."""
    def hunt(self, *a, **k):
        raise AssertionError("TRIPWIRE: hunt вызван в dry — нарушен закон 0-сети")

    def fetch_bytes(self, *a, **k):
        raise AssertionError("TRIPWIRE: fetch_bytes вызван в dry — нарушен закон 0-сети")

    def discover(self, *a, **k):
        raise AssertionError("TRIPWIRE: discover вызван в dry — нарушен закон 0-сети")


class FakeForge:
    RU_OPENAI_EST_USD = 0.02
    EST_USD_PER_IMAGE = 0.04

    def __init__(self, canon_ok=True, provider="ru_openai"):
        self.canon_ok = canon_ok
        self.provider = provider

    def _provider(self):
        return self.provider

    def _have_pil(self):
        return True

    def capabilities(self):
        return {"key": True, "net": True, "image_probe": True, "ocr": True}

    def verify_canon(self, raw, facts=None, donor_phashes=(), seen_phashes=(),
                     aspect="4:5", min_fill=None, max_off=None, require_subject=False):
        if self.canon_ok:
            return {"tier": "verified", "white_bg": True, "aspect_ok": True,
                    "subject": {"present": True, "fill": 0.55, "off_center": 0.04}}
        return {"tier": "off_canon", "white_bg": False, "aspect_ok": True,
                "subject": {"present": True, "fill": 0.2, "off_center": 0.3}}


class FakePipeline:
    def __init__(self, live_ok=True, tier="verified", cost=0.02, brake=False):
        self.live_ok = live_ok
        self.tier = tier
        self.cost = cost
        self.brake = brake
        self.calls = []

    def forge_card(self, product, urls=None, dry=True, prefer_clean=True, require_verified=False,
                   out_dir=None, model=None, tag=None, canon=False, brand=None):
        self.calls.append({"dry": dry, "urls": tuple(urls or []), "model": model})
        if dry:
            return {"mode": "generate", "rights": {"level": "own_pixels", "clean": True},
                    "est_cost_usd": 0.02, "forge": {}}
        if self.brake:   # бронь-гард кузницы: canon без PIL → отказ ДО траты
            return {"ok": False, "path": None, "mode": "generate", "tier": None, "cost_usd": 0.0,
                    "rights": None, "forge": {"tier": None}, "why": "canon без PIL: отказ до траты"}
        path = str(Path(out_dir or tempfile.gettempdir()) / ((tag or "x") + ".png")) if self.live_ok else None
        return {"ok": self.live_ok, "path": path, "mode": "generate", "tier": self.tier,
                "cost_usd": (self.cost if self.live_ok else 0.0),
                "rights": {"level": "own_pixels", "clean": True},
                "forge": {"tier": self.tier, "verdict": {"tier": self.tier}},
                "why": None if self.live_ok else "кузница: канон не взят"}


class _Inject:
    """Контекст: подменить ленивые геттеры соседей на фейки, вернуть как было."""
    def __init__(self, hunter=None, forge=None, pipeline=None, infographic="keep"):
        self.h, self.f, self.p, self.ig = hunter, forge, pipeline, infographic
        self._saved = {}

    def __enter__(self):
        self._saved = {"_hunter": ps._hunter, "_forge": ps._forge,
                       "_pipeline": ps._pipeline, "_infographic": ps._infographic}
        if self.h is not None:
            ps._hunter = lambda: self.h
        if self.f is not None:
            ps._forge = lambda: self.f
        if self.p is not None:
            ps._pipeline = lambda: self.p
        if self.ig != "keep":
            ps._infographic = lambda: self.ig
        return self

    def __exit__(self, *a):
        for k, v in self._saved.items():
            setattr(ps, k, v)
        return False


def _prod(sku="S1", name="Гофрокороб 60х40х40", url=None, urls=None, spec=None, facts=None):
    p = {"sku": sku, "name": name}
    if url:
        p["url"] = url
    if urls:
        p["urls"] = urls
    if spec:
        p["_spec"] = spec
    if facts:
        p["facts"] = facts
    return p


# ── (а) ЛОГИКА ДОБЫЧИ ─────────────────────────────────────────────────────────────────

def ps1_dry_zero_net():
    """dry: 0₽ и НИ ОДНОГО сетевого шва (tripwire-искатель не должен сработать)."""
    tw = TripwireHunter()
    with _Inject(hunter=tw, forge=FakeForge(), pipeline=FakePipeline()):
        rep = ps.supply_batch(ps._demo_products(5), dry=True, contact_sheet=False)
    ok = (rep["cost_usd"] == 0.0 and rep["dry"] is True and rep["ok"] == 5
          and rep["forged"] == 0 and rep["free"] == 0 and not tw.calls)
    return ok, f"cost={rep['cost_usd']} ok={rep['ok']} tripwire_calls={len(tw.calls)}"


def ps2_free_hero():
    """free_first: чистый good-кадр проходит канон → hero БЕСПЛАТНЫЙ, кузница не зовётся."""
    fp = FakePipeline()
    hu = FakeHunter(good=[{"url": "https://shop/u1.png", "compromise": False, "verdict": "good"}])
    with _Inject(hunter=hu, forge=FakeForge(canon_ok=True), pipeline=fp), \
            tempfile.TemporaryDirectory() as d:
        r = ps.supply_one(_prod(url="https://shop/u1.png"), dry=False, hero_mode="free_first", out_dir=d)
    h = r["frames"][0]
    live_forges = [c for c in fp.calls if not c["dry"]]
    ok = h["source"] == "free" and h["cost_usd"] == 0.0 and not live_forges and r["ok"]
    return ok, f"source={h['source']} cost={h['cost_usd']} live_forge_calls={len(live_forges)}"


def ps3_forge_fallback_on_canon_fail():
    """free-кадр не прошёл канон → честный переход в кузницу; urls донора уходят в forge_card."""
    fp = FakePipeline(live_ok=True, tier="verified", cost=0.02)
    hu = FakeHunter(good=[{"url": "https://shop/u1.png", "compromise": False}])
    with _Inject(hunter=hu, forge=FakeForge(canon_ok=False), pipeline=fp), \
            tempfile.TemporaryDirectory() as d:
        r = ps.supply_one(_prod(url="https://shop/u1.png"), dry=False, hero_mode="free_first", out_dir=d)
    h = r["frames"][0]
    live = [c for c in fp.calls if not c["dry"]]
    passed_urls = live and "https://shop/u1.png" in live[0]["urls"]
    ok = h["source"] == "forged" and h["cost_usd"] == 0.02 and bool(passed_urls)
    return ok, f"source={h['source']} cost={h['cost_usd']} urls_to_forge={bool(passed_urls)}"


def ps4_unknown_never_hero():
    """WB/unknown (в good НЕ попал) → hero НИКОГДА не из него: уходим в кузницу."""
    fp = FakePipeline(live_ok=True, tier="verified", cost=0.02)
    hu = FakeHunter(good=[])   # искатель не дал ни одного доверенного → free невозможен
    with _Inject(hunter=hu, forge=FakeForge(canon_ok=True), pipeline=fp), \
            tempfile.TemporaryDirectory() as d:
        r = ps.supply_one(_prod(url="https://www.wildberries.ru/x.png"), dry=False,
                          hero_mode="free_first", out_dir=d)
    h = r["frames"][0]
    ok = h["source"] == "forged" and h.get("url") is None
    return ok, f"source={h['source']} hero_url={h.get('url')}"


def ps5_compromised_excluded():
    """Кадр с меткой МП/продавца (compromise=True) пропускается; берём следующий чистый."""
    fp = FakePipeline()
    hu = FakeHunter(good=[{"url": "https://shop/c1.png", "compromise": True},
                          {"url": "https://shop/u2.png", "compromise": False}])
    with _Inject(hunter=hu, forge=FakeForge(canon_ok=True), pipeline=fp), \
            tempfile.TemporaryDirectory() as d:
        r = ps.supply_one(_prod(urls=["https://shop/c1.png", "https://shop/u2.png"]),
                          dry=False, hero_mode="free_first", out_dir=d)
    h = r["frames"][0]
    ok = h["source"] == "free" and h.get("url") == "https://shop/u2.png"
    return ok, f"source={h['source']} url={h.get('url')} (c1 скомпрометирован — пропущен)"


def ps6_infographic_optional():
    """Лента опциональна: infographic=False → нет кадра 'info'; True → есть (или честный скип)."""
    with _Inject(hunter=FakeHunter(), forge=FakeForge(), pipeline=FakePipeline()):
        off = ps.supply_one(_prod(), dry=True, infographic=False, need_frames=3)
        on = ps.supply_one(_prod(), dry=True, infographic=True, need_frames=3)
    kinds_off = [f["frame"] for f in off["frames"]]
    kinds_on = [f["frame"] for f in on["frames"]]
    ok = "info" not in kinds_off and "info" in kinds_on
    return ok, f"off={kinds_off} on={kinds_on}"


def ps7_frame3_or_skip():
    """need_frames управляет числом кадров: 1 → только hero; 3 → до трёх (hero+info+secondary)."""
    with _Inject(hunter=FakeHunter(), forge=FakeForge(), pipeline=FakePipeline()):
        one = ps.supply_one(_prod(), dry=True, need_frames=1)
        three = ps.supply_one(_prod(), dry=True, need_frames=3)
    ok = len(one["frames"]) == 1 and len(three["frames"]) == 3 and \
        three["frames"][2]["frame"] == "secondary"
    return ok, f"n1={len(one['frames'])} n3={len(three['frames'])} f3={three['frames'][2]['frame']}"


def ps8_quality_gate_weak_log():
    """Кузница провалила канон И free нет → hero weak=True, НЕ ok, попал в weak_log (не на витрину)."""
    fp = FakePipeline(live_ok=False)          # кузница не дала кадр
    hu = FakeHunter(good=[])                    # free невозможен
    with _Inject(hunter=hu, forge=FakeForge(canon_ok=False), pipeline=fp), \
            tempfile.TemporaryDirectory() as d:
        rep = ps.supply_batch([_prod(url="https://shop/u1.png")], dry=False,
                              hero_mode="free_first", out_dir=d, contact_sheet=False)
    h = rep["results"][0]["frames"][0]
    ok = rep["weak"] == 1 and h["weak"] is True and h["ok"] is False and len(rep["weak_log"]) == 1
    return ok, f"weak={rep['weak']} hero_ok={h['ok']} log={len(rep['weak_log'])}"


def ps9_live_canon_without_pil_refuse():
    """Наследуем бронь-гард: живой canon без PIL → кузница отказала ДО траты; расход 0, честно weak."""
    fp = FakePipeline(brake=True)              # имитируем отказ кузницы до траты
    hu = FakeHunter(good=[])
    with _Inject(hunter=hu, forge=FakeForge(canon_ok=False), pipeline=fp), \
            tempfile.TemporaryDirectory() as d:
        r = ps.supply_one(_prod(url="https://shop/u1.png"), dry=False, hero_mode="always_forge",
                          canon=True, out_dir=d)
    h = r["frames"][0]
    ok = h["cost_usd"] == 0.0 and h["ok"] is False and h["weak"] is True and "PIL" in (h.get("why") or "")
    return ok, f"cost={h['cost_usd']} ok={h['ok']} why={ (h.get('why') or '')[:40]!r}"


def ps10_cost_projection_honest():
    """Проекция честна: best=0, worst=n·unit; realistic учитывает free_rate; always_forge зануляет free."""
    a = ps.project_cost(190, provider="ru_openai", hero_mode="free_first", assume_free_rate=0.4)
    b = ps.project_cost(190, provider="ru_openai", hero_mode="always_forge", assume_free_rate=0.4)
    ok = (a["best_usd"] == 0.0 and abs(a["worst_usd"] - 3.8) < 1e-6
          and abs(a["realistic_usd"] - 2.28) < 1e-6
          and b["assume_free_rate"] == 0.0 and abs(b["realistic_usd"] - b["worst_usd"]) < 1e-6)
    return ok, f"free_first={a['best_usd']}/{a['realistic_usd']}/{a['worst_usd']} always={b['realistic_usd']}"


def ps11_contact_sheet_zero_token():
    """Монтаж 0 токенов: с PIL → PNG, без PIL → текст-манифест. Обе ветки честны, cost 0."""
    fake = [{"sku": "S1", "name": "Короб", "ok": True, "weak": False, "frames": [{"frame": "hero", "source": "plan"}]},
            {"sku": "S2", "name": "Плёнка", "ok": True, "weak": True, "frames": [{"frame": "hero", "source": "forged"}]}]
    with tempfile.TemporaryDirectory() as d:
        real = ps.build_contact_sheet(fake, out_dir=d, tag="t")
        real_ok = real["ok"] and real["cost_usd"] == 0.0 and Path(real["path"]).exists()
        # Принудительно ветка «без PIL» → текст-манифест обязан родиться.
        class _NoPil:
            _HAVE_PIL = False
        with _Inject(infographic=_NoPil()):
            txt = ps.build_contact_sheet(fake, out_dir=d, tag="t2")
        txt_ok = txt["ok"] and txt["mode"] == "text" and Path(txt["path"]).suffix == ".txt"
    ok = real_ok and txt_ok
    return ok, f"real_mode={real['mode']} txt_mode={txt['mode']}"


def ps12_bounded_parallel_spend_ceiling():
    """Потолок расхода режет пачку честно: max_spend=$0.05 при $0.02/кадр → 2 кова, остальное skipped_budget."""
    fp = FakePipeline(live_ok=True, tier="verified", cost=0.02)
    hu = FakeHunter(good=[])   # free невозможен → каждый идёт в платный кова
    prods = [_prod(sku="P%d" % i, url="https://shop/%d.png" % i) for i in range(5)]
    with _Inject(hunter=hu, forge=FakeForge(canon_ok=False), pipeline=fp), \
            tempfile.TemporaryDirectory() as d:
        rep = ps.supply_batch(prods, dry=False, hero_mode="always_forge", max_workers=1,
                              max_spend_usd=0.05, out_dir=d, contact_sheet=False)
    ok = (rep["cost_usd"] <= 0.05 + 1e-9 and rep["forged"] == 2 and rep["skipped_budget"] == 3)
    return ok, f"cost={rep['cost_usd']} forged={rep['forged']} skipped={rep['skipped_budget']}"


def ps13_backcompat_regression():
    """РЕАЛЬНАЯ регрессия соседей тем же интерпретатором: forge + pipeline + infographic — все зелёные."""
    suites = ["run_photoforge.py", "run_pipeline.py", "run_infographic.py"]
    results = []
    for s in suites:
        path = HERE / s
        if not path.exists():
            results.append((s, False, "нет файла"))
            continue
        try:
            out = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=300)
        except Exception as e:
            results.append((s, False, type(e).__name__))
            continue
        line = ""
        for ln in out.stdout.splitlines():
            if "Итого:" in ln:
                line = ln.strip()
        passed = total = -1
        if "Итого:" in line:
            frag = line.split("Итого:")[1].split("PASS")[0].strip()
            if "/" in frag:
                a, b = frag.split("/")[:2]
                try:
                    passed, total = int(a.strip()), int(b.split()[0].strip())
                except ValueError:
                    pass
        green = out.returncode == 0 and passed >= 0 and passed == total
        results.append((s, green, line or "нет 'Итого:'"))
    ok = all(g for _, g, _ in results)
    detail = " | ".join("%s:%s" % (s.replace("run_", "").replace(".py", ""), d.replace("Итого: ", ""))
                        for s, _, d in results)
    return ok, detail


TESTS = [
    ("PS1  dry_zero_net", ps1_dry_zero_net),
    ("PS2  free_hero", ps2_free_hero),
    ("PS3  forge_fallback", ps3_forge_fallback_on_canon_fail),
    ("PS4  unknown_never_hero", ps4_unknown_never_hero),
    ("PS5  compromised_excluded", ps5_compromised_excluded),
    ("PS6  infographic_optional", ps6_infographic_optional),
    ("PS7  frame3_or_skip", ps7_frame3_or_skip),
    ("PS8  quality_gate_weak_log", ps8_quality_gate_weak_log),
    ("PS9  live_canon_nopil_refuse", ps9_live_canon_without_pil_refuse),
    ("PS10 cost_projection_honest", ps10_cost_projection_honest),
    ("PS11 contact_sheet_0token", ps11_contact_sheet_zero_token),
    ("PS12 spend_ceiling", ps12_bounded_parallel_spend_ceiling),
    ("PS13 backcompat_regression", ps13_backcompat_regression),
]


def main():
    pil = "✔ Pillow" if getattr(ps._infographic() or object(), "_HAVE_PIL", False) else "○ без Pillow"
    print(f"🎯 ФОТО-СНАБЖЕНЕЦ ПРИЁМКА · 190×(1-3) hunt→forge→лента · {pil}")
    passed = 0
    for name, fn in TESTS:
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"исключение: {type(e).__name__}: {e}"
        print(f"   {_passed(ok)} {name:<28} {detail}")
        passed += 1 if ok else 0
    print(f"\nИтого: {passed}/{len(TESTS)} PASS")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
