"""WAVE SHOP — тесты СУХОГО прогона автопродления (для launchd/cron).

Зачем этот файл: движок renewals.py ставится на расписание (launchd 24/7). Прежде
чем оператор вооружит боевое автосписание, задачу держат в заведомо безопасном
режиме. Здесь мы доказываем, что «безопасный режим» действительно безопасен —
причём НЕ на пустой базе (0/0 доказывает лишь тишину), а когда работа РЕАЛЬНО
есть: одна подписка просрочена (пора списывать) и один потокенный кошелёк ушёл
ниже ватерлинии (пора автопополнять).

Два независимых рубежа RUBICON:

  A. `renewals.py --dry-run` (то, что реально дёргает launchd) — это ОТЧЁТ.
     При живой очереди работ он не двигает НИ ОДНОГО БАЙТА данных: не списывает,
     не пишет в учёт, не шлёт сообщений, не трогает файлы. Сверяем побайтово.
     И при этом он ЧЕСТНО видит фронт работ (=1 и =1), а не молча считает ноль.

  B. Движок, вооружённый БЕЗ ключей кассы (provider.configured=False) — даже если
     оператор снял --dry-run, но ещё не завёл ЮKassa. Ни одного списания, касса не
     дёрнута ни разу, срок подписки не сдвинут, кошелёк не тронут, а флаги ключа
     (autotopup / topup_needed) целы — значит guard `if not configured` сработал
     РАНЬШЕ, чем путь «нет карты» успел что-то поменять.

И маленький, но важный рубеж: main() с флагом --dry-run уходит в отчёт и НЕ
запускает движок (иначе расписание молча било бы вживую).

Запуск:  python3 tests/renewals_dry_v1.py
"""
from __future__ import annotations

import io
import shutil
import sys
import tempfile
import time
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import renewals as R                              # noqa: E402
from config import Settings                       # noqa: E402
from gateway.quota import QuotaStore              # noqa: E402
from renewals import RenewalEngine                # noqa: E402
from store import Store                           # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def check(cond: bool, label: str) -> None:
    results.append((bool(cond), label))
    print(f"{PASS if cond else FAIL} {label}")


def make_settings(tmp: Path) -> Settings:
    return Settings(
        bot_token="t", admin_ids={1}, shop_name="WAVE", support_contact="@s",
        payment_order=["yookassa"], yookassa_shop_id="x", yookassa_secret_key="y",
        crypto_pay_token="", crypto_asset="USDT", crypto_rub_per_unit=100.0,
        manual_pay_details="", currency="RUB", ref_reward_percent=10,
        autorenew_enabled=True, renew_notice_days=3, data_dir=tmp, runtime_dir=tmp,
    )


class FakeAPI:
    """Телеграм без сети — поглощает возможные предупреждения, чтобы прогон не
    падал; на количество сообщений в этом тесте не опираемся (уведомление — не
    деньги; сухой путь launchd их вообще не шлёт, движок в режиме B — вправе)."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str, object]] = []

    def send_message(self, chat_id, text, keyboard=None, parse_mode="HTML"):
        self.sent.append((chat_id, text, keyboard))
        return {}


class Charge:
    def __init__(self, ok: bool, external_id: str = "") -> None:
        self.ok = ok
        self.external_id = external_id


class DryProvider:
    """Касса без ключей. configured=False — движок ОБЯЗАН до неё не дойти.
    Флаг charged ловит любое касание: ни одного списания быть не должно."""
    configured = False

    def __init__(self) -> None:
        self.charged = False

    def charge_saved_card(self, pmid, amount_rub, description="", idempotency_key=""):
        self.charged = True                       # если сюда попали — рубеж пробит
        return Charge(True, "should_not_happen")


def setup(tmp: Path):
    s = make_settings(tmp)
    store = Store(tmp)
    store.upsert_product({"id": "sub_5m", "title": "5 млн CAPS/мес", "price_rub": 7900,
                          "kind": "subscription", "period_days": 30, "active": True})
    return s, store


def due_sub(store: Store, uid: int, pid: str = "sub_5m", amount: int = 7900) -> None:
    """Подписка, которой пора списаться (paid_until в прошлом)."""
    store.upsert_subscription(uid, pid, 30, amount, payment_method_id="pm", autorenew=True)
    store.mark_sub_field(uid, pid, paid_until=int(time.time()) - 10)


def topup_key(gq: QuotaStore, uid: int) -> str:
    """Потокенный кошелёк, просевший ниже ватерлинии → в очереди автопополнения."""
    rec = gq.issue_key(user_id=uid, plan_id="postpaid", price_rub=0)
    tok = rec["token"]
    gq.arm_postpaid(tok, deposit_rub=120.0, autotopup=True,
                    low_watermark_rub=100, topup_amount_rub=500)
    # Жжём с запасом (opus дорогой) — баланс уходит ниже 100 → topup_needed=True.
    gq.consume(tok, 5_000_000, "claude-opus-5")
    return tok


def snapshot(root: Path) -> dict[str, bytes]:
    """Побайтовый слепок ВСЕХ файлов данных — чтобы поймать любую запись."""
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wave_dryrun_test_"))
    tmp2: Path | None = None
    try:
        # ═══ A. `--dry-run` при ЖИВОЙ очереди работ ничего не двигает ═══
        s, store = setup(tmp)
        due_sub(store, 5)
        gq = QuotaStore(tmp)
        topup_key(gq, 61)

        before = snapshot(tmp)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = R._dry_report(settings=s)
        out = buf.getvalue()
        after = snapshot(tmp)

        check(rc == 0, "сухой отчёт завершился успешно (rc=0)")
        check(before == after,
              "СУХОЙ отчёт не изменил НИ ОДНОГО байта данных (списаний/записей нет)")
        check("к продлению подписок=1" in out,
              "отчёт ЧЕСТНО увидел 1 подписку к продлению (не молчаливый ноль)")
        check("к автопополнению кошельков=1" in out,
              "отчёт ЧЕСТНО увидел 1 кошелёк к автопополнению")
        check("СПИСАНИЙ НЕ ДЕЛАЕМ" in out,
              "отчёт прямо заявляет, что ничего не списывает")

        # ═══ B. Движок вооружён, но БЕЗ ключей кассы → 0 денег, касса не дёрнута ═══
        tmp2 = Path(tempfile.mkdtemp(prefix="wave_dryrun_test_"))
        s2, store2 = setup(tmp2)
        due_sub(store2, 5)
        gq2 = QuotaStore(tmp2)
        tok2 = topup_key(gq2, 61)

        paid_before = int(store2.subscription(5, "sub_5m")["paid_until"])
        dep_before = float(gq2.get_key(tok2)["deposit_rub"])
        prov = DryProvider()
        r = RenewalEngine(s2, store=store2, api=FakeAPI(), provider=prov).run_once()

        check(r["charged"] == 0 and r.get("topped_up", 0) == 0,
              "касса без ключей: 0 списаний и 0 автопополнений")
        check(r.get("errors", 0) == 0 and r.get("topup_errors", 0) == 0,
              "прогон без исключений (guard — штатный ранний выход, не сбой)")
        check(prov.charged is False,
              "касса без ключей НЕ дёрнута НИ РАЗУ (guard раньше любого charge)")
        check(store2.revenue_total()["orders"] == 0,
              "ни одной записи в учёт — денег не двигали")
        check(int(store2.subscription(5, "sub_5m")["paid_until"]) == paid_before,
              "срок просроченной подписки НЕ сдвинут (продления не было)")

        key_after = gq2.get_key(tok2)
        check(abs(float(key_after["deposit_rub"]) - dep_before) < 1e-6,
              "баланс кошелька не тронут")
        check(bool(key_after.get("autotopup")) is True,
              "автопополнение НЕ выключено — значит guard сработал раньше пути «нет карты»")
        check(bool(key_after.get("topup_needed")) is True,
              "флаг «нужно пополнить» цел — топап-путь вышел до любых изменений")

        # ═══ Маленький рубеж: main(--dry-run) уходит в отчёт, движок НЕ трогает ═══
        called = {"n": 0}
        orig = R._dry_report
        R._dry_report = lambda settings=None: (called.__setitem__("n", called["n"] + 1) or 0)
        old_argv = sys.argv
        sys.argv = ["renewals.py", "--dry-run"]
        try:
            rc_main = R.main()
        finally:
            sys.argv = old_argv
            R._dry_report = orig
        check(rc_main == 0 and called["n"] == 1,
              "main() с --dry-run уходит в сухой отчёт (живой движок не запускается)")

        # ── ИТОГ ──
        print("\n" + "=" * 58)
        ok = sum(1 for c, _ in results if c)
        total = len(results)
        print(f"ИТОГ: {ok}/{total} проверок пройдено")
        if ok == total:
            print("🛡  СУХОЙ РЕЖИМ: расписание можно держать заряженным — денег оно не двигает.")
            return 0
        print("Сухой режим прохудился — смотрите выше.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if tmp2 is not None:
            shutil.rmtree(tmp2, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
