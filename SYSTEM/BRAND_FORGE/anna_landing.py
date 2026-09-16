#!/usr/bin/env python3
"""
ANNA Landing — B2B sales front for DENTAL CLINIC OWNERS (D3 "Спокойная забота").

Rebuilt EVIDENCE-FIRST (2026 conversion research + AI-receptionist / dental-SaaS
teardowns + early-stage no-testimonial trust science):
 - Hero: pain-led, <8-word headline, ONE offer, 5-sec clarity, product proof, risk-reversal micro-proof.
 - #1 objection (reputation "sounds like a bot") answered EARLY + reframed (missed calls hurt reputation more).
 - Product shown as proof it's REAL (live cabinet) early.
 - Offer = small/specific (15-min demo); pilot mechanism clarity = risk reversal.
 - Honesty/constraints as the trust signal (no fake testimonials/ROI).
 - Single consistent CTA, repeated. Form 3 fields.

Composed from anna_canon_html (zero bespoke CSS). Stealth to patient / transparent to buyer.
Run:  python3 SYSTEM/BRAND_FORGE/anna_landing.py
Out:  SYSTEM/BRAND_FORGE/runtime/ANNA_LANDING_V1.html
"""
import sys
from pathlib import Path
from datetime import datetime

SOCC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOCC / "SYSTEM" / "BRAND_FORGE" / "canon"))
import anna_canon_html as A

OUT = SOCC / "SYSTEM" / "BRAND_FORGE" / "runtime" / "ANNA_LANDING_V1.html"
OFFER = "Записаться на демо"   # single, low-friction, consistent CTA everywhere


def chat_preview():
    return A.device(A.chat_frame("Пациент", "Telegram", [
        ("p", "Болит зуб, можно сегодня?", "22:40"),
        ("a", "Понимаю, это неприятно. Есть время в 16:30 — записать?", "22:40"),
        ("p", "Да", "22:41"),
        ("a", "Готово. Напомню за час 🌿", "22:41"),
    ]))


def render():
    top = A.topbar("анна", "администратор клиники · 24/7", A.button(OFFER, onclick="annaLead()"))

    # 1. HERO — pain-led, <8-word H1, one offer, product proof, risk-reversal micro-proof
    hero = A.hero(
        "ИИ-администратор для стоматологии · СНГ",
        "Ни одного потерянного пациента —<br><em>даже ночью</em>.",
        "Звонок в 22:40, острая боль — а ответить некому. Анна отвечает, записывает и напоминает. "
        "Круглосуточно, по-человечески.",
        cta_html=A.button(OFFER, onclick="annaLead()")
        + A.button("Как отвечает →", "ghost",
                   onclick="document.querySelector('.hero-aside').scrollIntoView({behavior:'smooth'})")
        + '<div class="hero-note">Бесплатный пилот · на ваших данных · без замены систем · отключить в один клик</div>',
        aside_html=chat_preview())

    trust = A.trust_strip(["отвечает за секунды", "24/7 и в выходные", "запись и напоминания", "передаёт администратору"])

    # 2. #1 OBJECTION answered early + reframed
    reassure = A.section("", "", A.callout(
        A.icon("shield", 24),
        "«А вдруг бот испортит впечатление?»",
        "Анна звучит как живой человек, а сложный вопрос мягко передаёт вашему администратору — вы в контроле. "
        "И честно: репутацию сильнее бьёт неотвеченный звонок, чем тёплый ответ в 22:40."))

    # 3. PRODUCT is real — show it early (tangible proof)
    peek = A.section("Это не слайды — рабочий продукт", "", A.card(
        '<p style="color:var(--muted);font-size:15.5px;margin:0 0 14px;max-width:36em;line-height:1.6">'
        'Каждый диалог, запись и метрика — в одном кабинете. Помечаете ошибку одним кликом и обучаете Анну своему стилю.</p>'
        + A.link_button("Открыть демо-кабинет →", "ANNA_OWNER_CABINET_V1.html", "primary")))

    # 4. HOW THE PILOT WORKS — mechanism clarity = risk reversal
    how = A.section("Как проходит пилот", "", A.steps([
        ("Демо за 15 минут", "Покажем Анну на примере вашей клиники."),
        ("Неделя на ваших обращениях", "Анна отвечает по вашим правилам. В клинике ничего не меняем."),
        ("Смотрите на цифры", "Сколько обращений подхвачено и записано. Продолжаем — или нет."),
    ]), tint=True)

    # 5. HONESTY as the trust signal (no fake proof)
    trust_block = A.section("Почему нам можно верить", "", A.callout(
        A.icon("check", 24),
        "Честность вместо накрученных отзывов",
        "У нас нет липовых отзывов и выдуманной «экономии». Есть прозрачный пилот на ваших данных "
        "и цифры, которые видно. Не подошло — отключаете в один клик."))

    # 6. OFFER — small, specific, low friction
    lead = A.section("Записаться на демо", "", A.card(
        '<p style="color:var(--muted);font-size:14.5px;margin:0 0 14px">'
        'Перезвоним в течение 5 минут и покажем Анну на примере вашей клиники.</p>'
        + A.lead_form(
            [{"id": "name", "label": "Ваше имя", "placeholder": "Как к вам обращаться", "required": True},
             {"id": "clinic", "label": "Клиника", "placeholder": "Название клиники"},
             {"id": "contact", "label": "Telegram или телефон", "placeholder": "@ник или +7…", "required": True}],
            OFFER,
            note="Витрина: отправка подключится к бэкенду (L2). Данные пока никуда не уходят.",
            success="Заявка принята — перезвоним в течение 5 минут.")))

    # 7. OBJECTIONS
    faqs = A.section("Вопросы", "", A.faq([
        ("Пациент поймёт, что это ИИ?", "Анна звучит по-человечески; сложное сразу передаёт администратору."),
        ("Сложно внедрять?", "Нет. Подключаем к вашему Telegram, в клинике ничего не меняем."),
        ("А нестандартный вопрос?", "Анна уточнит и передаст администратору — без потери пациента."),
        ("Сколько стоит?", "Обсудим после пилота, когда увидите пользу на своих данных."),
    ]))

    cta = A.cta_band("Перестаньте терять пациентов между звонками",
                     "15 минут — и увидите Анну на примере вашей клиники.",
                     A.button(OFFER, onclick="annaLead()"))

    foot = ('<p class="foot">' + A.arch_mark(20) + ' <span>анна · тёплый администратор вашей клиники</span>'
            '<span class="foot-tag">спокойная забота</span></p>')

    body = (hero + trust + reassure + peek + A.warm_divider() + how
            + trust_block + lead + faqs + cta + foot)
    return A.page("анна — администратор клиники 24/7", body, top_html=top, with_scripts=True)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"[anna_landing] wrote {OUT}")


if __name__ == "__main__":
    main()
