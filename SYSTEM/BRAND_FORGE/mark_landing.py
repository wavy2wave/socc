#!/usr/bin/env python3
"""
МАРК Landing — SAME component library, DIFFERENT skin (factory proof).

Proves ATELIER reusability: identical anna_canon_html components + arch system,
only the PALETTE and copy change -> a barbershop brand ("Марк") in one pass.
Nothing bespoke; the design system is now palette-driven (color-mix tokens).

Run:  python3 SYSTEM/BRAND_FORGE/mark_landing.py
Out:  SYSTEM/BRAND_FORGE/runtime/MARK_LANDING_V1.html
"""
import sys
from pathlib import Path

SOCC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOCC / "SYSTEM" / "BRAND_FORGE" / "canon"))
import anna_canon_html as A  # the PRODUCT design system (brand-agnostic, token-driven)

OUT = SOCC / "SYSTEM" / "BRAND_FORGE" / "runtime" / "MARK_LANDING_V1.html"

# Марк skin — loaded from the brand registry (canon/BRAND_SKINS_V1.json). Same components, new palette.
MARK = A.skin("mark")
OFFER = "Записаться на демо"


def chat_preview():
    return A.device(A.chat_frame("Клиент", "Telegram", [
        ("p", "Здорово, можно завтра к Диме?", "21:38"),
        ("a", "Здарова! Дима завтра свободен в 18:00 и 19:30. На какое записать?", "21:38"),
        ("p", "На 18", "21:39"),
        ("a", "Готово, завтра в 18:00 к Диме. Напомню за час 💈", "21:39"),
    ]))


def render():
    top = A.topbar("марк", "администратор барбершопа · 24/7", A.button(OFFER, onclick="annaLead()"))

    hero = A.hero(
        "ИИ-администратор для барбершопа",
        "Ни одного пропущенного клиента —<br><em>даже поздно вечером</em>.",
        "Марк отвечает, записывает к мастеру и напоминает. Пока ты стрижёшь — он держит запись полной.",
        cta_html=A.button(OFFER, onclick="annaLead()")
        + A.button("Как отвечает →", "ghost",
                   onclick="document.querySelector('.hero-aside').scrollIntoView({behavior:'smooth'})")
        + '<div class="hero-note">Бесплатный пилот · на твоих данных · без замены систем</div>',
        aside_html=chat_preview())

    trust = A.trust_strip(["отвечает за секунды", "24/7 и в выходные", "запись к мастеру", "напоминания клиентам"])

    reassure = A.section("", "", A.callout(
        A.icon("shield", 24),
        "«Клиенты поймут, что это не я?»",
        "Марк пишет по-свойски, как твой админ, а что посложнее — сразу передаёт тебе. "
        "Тон и правила настраиваешь сам — лицо барбершопа под контролем."))

    how = A.section("Как проходит пилот", "", A.steps([
        ("Демо за 15 минут", "Покажем Марка на примере твоего барбершопа."),
        ("Неделя на твоих заявках", "Марк отвечает по твоим правилам и мастерам. Ничего не меняем."),
        ("Смотришь на цифры", "Сколько заявок подхвачено и записано. Продолжаем — или нет."),
    ]), tint=True)

    cta = A.cta_band("Перестань терять клиентов между стрижками",
                     "15 минут — и увидишь Марка на примере своего барбершопа.",
                     A.button(OFFER, onclick="annaLead()"))

    foot = ('<p class="foot">' + A.arch_mark(20) + ' <span>марк · та же студия, свой скин</span>'
            '<span class="foot-tag">свой в доску</span></p>')

    body = hero + trust + reassure + how + cta + foot
    return A.page("марк — администратор барбершопа 24/7", body, top_html=top, P=MARK, with_scripts=True)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"[mark_landing] wrote {OUT}")


if __name__ == "__main__":
    main()
