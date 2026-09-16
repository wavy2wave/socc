#!/usr/bin/env python3
"""
ANNA Telegram Touchpoints — patient first-contact surface (D3 "Спокойная забота").

Closes the funnel: landing (owner) -> owner cabinet -> PATIENT first contact.
Shows the owner exactly what a patient meets in Telegram: profile, greeting,
pinned info, a real first-contact conversation. Product canon D3 (patient = buyer's
customer). STEALTH: ANNA speaks as a human clinic administrator, never "бот";
hard cases hand off to a live person. Composed from anna_canon_html. No network.

Run:  python3 SYSTEM/BRAND_FORGE/anna_touchpoints.py
Out:  SYSTEM/BRAND_FORGE/runtime/ANNA_TOUCHPOINTS_V1.html
"""
import sys
from pathlib import Path

SOCC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOCC / "SYSTEM" / "BRAND_FORGE" / "canon"))
import anna_canon_html as A

OUT = SOCC / "SYSTEM" / "BRAND_FORGE" / "runtime" / "ANNA_TOUCHPOINTS_V1.html"


def first_contact():
    return A.device(A.chat_frame("Клиника «Улыбка»", "Telegram", [
        ("p", "Здравствуйте, хочу записаться на чистку", "09:12"),
        ("a", "Здравствуйте! С радостью помогу. Когда удобнее — на этой неделе или ближе к выходным?", "09:12"),
        ("p", "В субботу утром", "09:13"),
        ("a", "Есть суббота, 10:30 у гигиениста. Записать вас?", "09:13"),
        ("p", "Да", "09:14"),
        ("a", "Готово 🌿 Напомню за час. Если планы изменятся — просто напишите.", "09:14"),
    ]))


def render():
    top = A.topbar("анна", "точки контакта · Telegram", A.button("Открыть кабинет →", onclick="location.href='ANNA_OWNER_CABINET_V1.html'"))

    intro = A.section("Первый контакт", "Как вас встречает пациент в Telegram",
                      '<p style="color:var(--muted);font-size:16px;max-width:36em;margin:0;line-height:1.6">'
                      'Всё, что видит и слышит пациент в первую минуту — тёплый, живой, узнаваемый голос клиники. '
                      'Одобрите тексты — и Анна говорит так с каждым, круглосуточно.</p>')

    profile = A.section("Профиль", "", A.tg_profile(
        "Клиника «Улыбка»", "@ulybka_clinic",
        "Тёплый администратор клиники: запись, вопросы, напоминания — круглосуточно. Просто напишите 🌿",
        status="отвечает за минуту"))

    greeting = A.section("Приветствие", "", A.card(
        '<div style="color:var(--muted);font-size:14px;margin-bottom:12px">Первое сообщение новому пациенту:</div>'
        + A.bubble("Здравствуйте! Это администратор клиники «Улыбка» 🌿 Помогу записаться, подскажу по услугам и ценам. "
                   "На связи в любое время — просто напишите.", "a")))

    pin = A.section("Закреплённое", "", A.card(A.pinned(
        "Пн–Вс, 9:00–21:00 · ул. Примерная, 1 · Записаться — просто напишите сюда, отвечу за минуту. "
        "Если больно прямо сейчас — напишите «срочно», помогу вне очереди.")))

    demo = A.section("Живой первый диалог", "", first_contact())

    stealth = A.section("Голос и честность", "", A.callout(
        A.icon("shield", 24),
        "Как человек — и с передачей живому сотруднику",
        "Анна общается тёпло и по-человечески и никогда не называет себя ботом. "
        "Сложный или деликатный вопрос — мягко передаёт администратору клиники, не теряя пациента."))

    foot = ('<p class="foot">' + A.arch_mark(20) + ' <span>анна · точки контакта пациента · D3</span>'
            '<span class="foot-tag">спокойная забота</span></p>')

    body = intro + profile + greeting + pin + demo + stealth + foot
    return A.page("анна · точки контакта пациента", body, top_html=top, with_scripts=True)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"[anna_touchpoints] wrote {OUT}")


if __name__ == "__main__":
    main()
