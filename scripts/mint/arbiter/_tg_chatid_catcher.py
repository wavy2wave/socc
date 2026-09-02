#!/usr/bin/env python3
"""Фоновый ловец chat_id для офиса Яндекса через RU-нестабильный egress.
Ловит первое сетевое окно к Telegram, пишет YM_TELEGRAM_CHAT_ID в .env,
шлёт первое сообщение офиса и выходит. Не печатает секреты."""
import os, ssl, socket, http.client, urllib.parse, json, time
from pathlib import Path

ENV = Path("/Users/wavysexy/SOCC/scripts/mint/.env")
SNI = "api.telegram.org"
POOL = ["149.154.167.220", "149.154.167.99", "149.154.175.50",
        "91.108.56.130", "149.154.167.91", "149.154.171.5"]

def load_env():
    d = {}
    for ln in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in ln and not ln.strip().startswith("#"):
            k, v = ln.split("=", 1); d[k.strip()] = v.strip()
    return d

def write_chatid(pick):
    L = ENV.read_text(encoding="utf-8").splitlines(); out = []; f = False
    for ln in L:
        if ln.startswith("YM_TELEGRAM_CHAT_ID="):
            out.append("YM_TELEGRAM_CHAT_ID=" + str(pick)); f = True
        else:
            out.append(ln)
    if not f:
        out.append("YM_TELEGRAM_CHAT_ID=" + str(pick))
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8"); os.chmod(ENV, 0o600)

def call(ip, tok, method, params, to):
    ctx = ssl.create_default_context()
    s = socket.create_connection((ip, 443), timeout=to)
    s = ctx.wrap_socket(s, server_hostname=SNI)
    body = urllib.parse.urlencode(params).encode()
    c = http.client.HTTPSConnection(ip, 443, timeout=to, context=ctx); c.sock = s
    c.request("POST", f"/bot{tok}/{method}", body=body,
              headers={"Host": SNI, "Content-Type": "application/x-www-form-urlencoded"})
    r = c.getresponse(); dat = r.read(); c.close(); return json.loads(dat)

def try_once(tok, method, params, to=7):
    for ip in POOL:
        try:
            return call(ip, tok, method, params, to)
        except Exception:
            continue
    return None

def main():
    tok = load_env().get("YM_TELEGRAM_BOT_TOKEN")
    if not tok:
        print("НЕТ ТОКЕНА"); return
    deadline = time.time() + 25 * 60
    log = Path("/Users/wavysexy/SOCC/scripts/mint/arbiter/_tg_catcher.log")
    n = 0
    while time.time() < deadline:
        n += 1
        d = try_once(tok, "getUpdates", {"timeout": 0, "limit": 30}, to=7)
        if d and d.get("ok"):
            pick = None; nm = None
            for it in d.get("result", []):
                m = it.get("message") or it.get("edited_message") or {}
                c = m.get("chat") or {}
                if c.get("id") is not None:
                    pick = c["id"]
                    nm = (str(c.get("first_name", "")) + " " + str(c.get("last_name", ""))).strip() or c.get("username") or c.get("title")
            if pick is not None:
                write_chatid(pick)
                msg = ("🟢 Офис Яндекс.Маркета на связи.\n"
                       "@yandexcrew_bot — голос твоего офиса. Канал живой.\n\n"
                       "Модель: Экспресс (сборка ≤20 мин, курьер ≤1 ч).\n"
                       "Департаменты ещё достраиваются — следующее сообщение будет от сотрудника с делом.")
                r = try_once(tok, "sendMessage", {"chat_id": pick, "text": msg}, to=10)
                ok = bool(r and r.get("ok"))
                log.write_text(f"CAUGHT chat_id={pick} name={nm} attempts={n} sent={ok}\n", encoding="utf-8")
                print(f"OK chat_id={pick} sent={ok}")
                return
            else:
                # сеть открылась, но апдейтов нет — окно есть, ждём сообщение
                log.write_text(f"window_open_no_updates attempts={n}\n", encoding="utf-8")
        time.sleep(15)
    log.write_text(f"GAVE_UP after {n} attempts / 25min\n", encoding="utf-8")
    print("GAVE_UP")

if __name__ == "__main__":
    main()
