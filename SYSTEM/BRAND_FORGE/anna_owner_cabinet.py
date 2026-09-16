#!/usr/bin/env python3
"""
ANNA Owner Cabinet — L4 product front (D3 "Спокойная забота").

Thin surface: composes the ANNA component library (canon/anna_canon_html.py) —
ZERO bespoke CSS/JS here, so the whole product stays one style (one source).
Renders REAL ANNA status; demo data is clearly labelled; ROI ₽ is NEVER invented
(only from a real clinic / LEDGER, per ANNA_DESIGN_CANON). No network, no daemon.

Run:  python3 SYSTEM/BRAND_FORGE/anna_owner_cabinet.py
Out:  SYSTEM/BRAND_FORGE/runtime/ANNA_OWNER_CABINET_V1.html
"""
import sys
import json
from pathlib import Path
from datetime import datetime

SOCC = Path(__file__).resolve().parents[2]
HOME = SOCC.parent
sys.path.insert(0, str(SOCC / "SYSTEM" / "BRAND_FORGE" / "canon"))
import anna_canon_html as A  # the product renderer / component library

ANNA_STATUS = HOME / "wavecore-bot" / "runtime" / "status" / "anna.json"
OUT = SOCC / "SYSTEM" / "BRAND_FORGE" / "runtime" / "ANNA_OWNER_CABINET_V1.html"


def anna_live():
    """The one real live signal -> (state, label, time)."""
    try:
        d = json.loads(ANNA_STATUS.read_text(encoding="utf-8"))
    except Exception:
        return ("unknown", "статус неизвестен", "")
    when = ""
    if d.get("ts"):
        try:
            when = datetime.fromisoformat(d["ts"].replace("Z", "+00:00")).astimezone().strftime("%H:%M")
        except Exception:
            when = str(d["ts"])
    return ("on" if d.get("ok") else "off", "на связи" if d.get("ok") else "не в сети", when)


# ── demo content (clearly labelled пример; not real patient data) ─────────────
DIALOGS = [
    {"id": "d1", "name": "Ирина", "init": "И", "time": "14:32", "state": "ok",
     "preview": "Болит зуб справа сверху, можно сегодня?",
     "thread": [("p", "Здравствуйте! Болит зуб справа сверху, можно сегодня?"),
                ("a", "Ирина, здравствуйте. Сочувствую — острая боль это всегда тревожно. Сегодня есть окно в 16:30 у Анны Сергеевны, терапевт. Записать вас?"),
                ("p", "Да, давайте"),
                ("a", "Готово, жду вас в 16:30. Адрес пришлю и напомню за час. Если станет совсем больно раньше — напишите, подумаем, как помочь.")]},
    {"id": "d2", "name": "Алексей", "init": "А", "time": "13:10", "state": "wait",
     "preview": "Сколько стоит чистка и отбеливание?",
     "thread": [("p", "А сколько стоит чистка и отбеливание?"),
                ("a", "Алексей, добрый день. Профчистка — от 4 500 ₽, отбеливание подбираем после осмотра, чтобы не навредить эмали. Запишу на бесплатную консультацию — врач посмотрит и точно скажет?"),
                ("p", "Надо подумать"),
                ("a", "Конечно, без спешки. Если удобно — придержу удобное время на эту неделю, отмена в любой момент.")]},
    {"id": "d3", "name": "Марина", "init": "М", "time": "11:58", "state": "ok",
     "preview": "Спасибо большое, до завтра 🙏",
     "thread": [("a", "Марина, напоминаю: завтра в 11:00 профчистка. Приходите за 5 минут, чай будет ☕"),
                ("p", "Спасибо большое, до завтра 🙏")]},
    {"id": "d4", "name": "Гость", "init": "•", "time": "10:21", "state": "mute",
     "preview": "Вы работаете в воскресенье?",
     "thread": [("p", "Вы работаете в воскресенье?"),
                ("a", "Да, в воскресенье принимаем с 10:00 до 18:00. Подсказать свободное время или вас что-то конкретное беспокоит?")]},
    {"id": "d5", "name": "Дмитрий", "init": "Д", "time": "вчера", "state": "ok",
     "preview": "Перенесите, пожалуйста, на пятницу",
     "thread": [("p", "Перенесите, пожалуйста, на пятницу"),
                ("a", "Дмитрий, перенесла на пятницу 15:00. Всё сохранила, до встречи! Если планы снова сдвинутся — просто напишите.")]},
]
BADGE_LABEL = {"ok": "записан", "wait": "ждёт", "mute": "отвечено"}
BOOKINGS = [
    ("Лечение кариеса", "Ирина К.", "сегодня 16:30", "booked"),
    ("Профчистка", "Марина В.", "завтра 11:00", "booked"),
    ("Консультация ортодонта", "Алексей П.", "ждёт подтверждения", "pending"),
    ("Перенос приёма", "Дмитрий С.", "пятница 15:00", "booked"),
]
KPI = [("Обращений за неделю", "48", "пример"), ("Записей создано", "31", "пример"),
       ("Возвращено пациентов*", "12", "пример"), ("Возвращённая выручка", "—", "из LEDGER")]


def render():
    state, label, when = anna_live()
    live = A.pill(f"ANNA {label}" + (f" · {when}" if when else ""), state)
    top = A.topbar("анна",
                   'кабинет · Демо-клиника «Улыбка» <span style="color:var(--accent-deep)">(пример)</span>',
                   live + A.tabs(["Сегодня", "Неделя", "Месяц"], active=1))

    note = A.banner('<b>Витрина кабинета.</b> Числа и диалоги — пример, чтобы показать продукт. '
                    'Реальные метрики появятся, когда ANNA подключена к вашей клинике (записи + LEDGER). '
                    '<b>Цифра выгоды (₽) не выдумывается</b> — только из ваших данных. Живой здесь — статус ANNA выше.')

    kpis = A.grid([A.kpi(v, t, tag) for (t, v, tag) in KPI], 4)

    dlist, threads = "", ""
    for i, d in enumerate(DIALOGS):
        dlist += A.dialog_row(d["id"], d["init"], d["name"], d["time"], d["preview"],
                              A.badge(BADGE_LABEL[d["state"]], d["state"]), active=(i == 0))
        bubbles = "".join(A.bubble(text, who, flag=(who == "a")) for who, text in d["thread"])
        threads += A.thread(d["id"], bubbles, header=f'{d["name"]} · {d["time"]}',
                            hidden=(i != 0),
                            actions_html=A.button("передать администратору", "ghost", onclick="annaHandoff()"))
    left = A.card('<div class="h">Диалоги пациентов</div>' + dlist + threads)

    bk = "".join(A.booking_row(*b) for b in BOOKINGS)
    bk += A.subnote('Реальная синхронизация с календарём клиники (YClients / Dikidi / Google Calendar) — '
                    '<b>L2, в разработке</b>. Сейчас — локально.')
    right_top = A.card('<div class="h">Записи</div>' + bk)
    train = A.card('<div class="h">Обучение ANNA</div>'
                   '<div style="color:var(--muted);font-size:14px">Поправьте ответ — ANNA запомнит ваш стиль и правила клиники.</div>'
                   '<div class="actions" style="margin-top:10px">'
                   + A.field("Напр.: о рассрочке — предлагать консультацию, не цену", "teach")
                   + A.button("Научить", onclick="annaTeach()") + '</div>')

    gen = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    foot = ('<p class="foot">продуктовая поверхность · рендер через <b>anna_canon_html</b> '
            '(ANNA_DESIGN_CANON_V1, D3 «Спокойная забота») · НЕ матрица оператора<br>'
            f'обновить: <span style="color:var(--ink)">python3 SYSTEM/BRAND_FORGE/anna_owner_cabinet.py</span> · сгенерировано {gen}<br>'
            'голос: тепло, по-человечески, честно — без хайпа, без выдуманных цифр.</p>')

    body = note + kpis + A.cols(left, right_top + train) + foot
    return A.page("анна · кабинет клиники", body, top_html=top, with_scripts=True)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"[anna_owner_cabinet] wrote {OUT}")


if __name__ == "__main__":
    main()
