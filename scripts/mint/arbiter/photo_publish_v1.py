#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ФОТО-ПУБЛИКАТОР (PHOTO PUBLISH V1) — последний шов: выкованный кадр → ПУБЛИЧНЫЙ URL для карточки.

ЗАЧЕМ. Кузница (`photo_forge`) отдаёт ЛОКАЛЬНЫЙ файл. Но Яндекс.Маркет кладёт в `pictures[]` только
ПУБЛИЧНЫЕ ССЫЛКИ (Маркет сам скачивает картинку по URL). Между «файл на диске» и «карточка» зияет
дыра: её закрывает хостинг. Этот модуль — мост файл→URL + ЖЁСТКИЙ провенанс-гейт.

ЗАКОН ПРОВЕНАНСА (решение оператора 2026-08-11 «Только СВОИ пиксели»). На БОЕВУЮ витрину уходит
ТОЛЬКО кадр, который:
  1. родился успешно            — report.ok is True;
  2. прошёл БРОНЮ приёмки       — tier == 'verified' (не ok_needs_human, не off_canon, не rejected);
  3. НАШИ пиксели               — rights.level == 'own_pixels' (mode=generate, нарисован с нуля).
Производное от чужого фото (mode=edit → level=derivative) по умолчанию НЕ публикуем: чужое авторство
съёмки. Всё, что не прошло гейт → urls=[] + честный why + blocked=True. Мы НИКОГДА не кладём в
pictures[] локальный путь или base64 — только настоящий https-URL или ничего (честная деградация).

ХОСТИНГ. Единственный вменяемый RU-путь — Yandex Object Storage (S3-совместимый,
storage.yandexcloud.net), публичный бакет read. Это ОТДЕЛЬНЫЙ продукт от кабинета Маркета: нужен
сервис-аккаунт + статический ключ. Пока ключей нет — хостер в dry: строит ИМЯ объекта и КАКОЙ был
бы URL, но наружу не ходит (0₽), blocked=True. Как впишут YC_* в mint/.env — та же цепь льёт живьём.

Секреты — только из gitignored .env через socc_mint_env_v1; наружу лишь ИМЕНА переменных (bool),
значения ключей не печатаем. stdlib-only, ленивый (грузится без сети/ключей/соседей).
"""
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MINT = HERE.parent
for _p in (str(HERE), str(MINT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import socc_mint_env_v1 as _env            # общий загрузчик секретов (имена, не значения)
except Exception:                              # pragma: no cover — орган живёт и без загрузчика
    _env = None


# Имена env хостинга (Yandex Object Storage). Только ИМЕНА — значения не логируем.
YC_ENV = ("YC_S3_ENDPOINT", "YC_S3_REGION", "YC_ACCESS_KEY_ID", "YC_SECRET_KEY",
          "YC_BUCKET", "YC_PUBLIC_BASE")
_DEFAULT_ENDPOINT = "https://storage.yandexcloud.net"
_DEFAULT_REGION = "ru-central1"


def _ensure_env():
    if _env is not None:
        try:
            _env.ensure_env()
        except Exception:
            pass


def _own_pixels(report):
    """Кадр — НАШИ пиксели? level=='own_pixels' (mode=generate). Производное (edit) → False."""
    rights = (report or {}).get("rights") or {}
    return rights.get("level") == "own_pixels"


def gate(report, allow_derivative=False):
    """ЖЁСТКИЙ провенанс-гейт (сухая логика, без сети). Пускать ли кадр на боевую витрину?

    Возвращает (ok: bool, why: [str]). ok=True только когда все условия закона выполнены.
    allow_derivative=True — осознанно разрешить производный кадр (по умолчанию НЕТ; закон = свои пиксели).
    """
    why = []
    r = report if isinstance(report, dict) else {}
    if r.get("ok") is not True:
        why.append("кадр не выкован (ok!=True) — публиковать нечего")
    if not r.get("path"):
        why.append("нет локального файла кадра (path пуст)")
    tier = r.get("tier")
    if tier != "verified":
        why.append("тир '%s' != verified — на боевую витрину пускаем только бронированный кадр" % tier)
    if not _own_pixels(r):
        if allow_derivative and ((r.get("rights") or {}).get("level") == "derivative"):
            why.append("ВНИМАНИЕ: производный кадр допущен вручную (allow_derivative)")
        else:
            lvl = (r.get("rights") or {}).get("level")
            why.append("провенанс '%s' != own_pixels — по закону публикуем только СВОИ пиксели "
                       "(сгенерированные с нуля)" % lvl)
    ok = (r.get("ok") is True and bool(r.get("path")) and tier == "verified"
          and (_own_pixels(r) or allow_derivative and (r.get("rights") or {}).get("level") == "derivative"))
    return ok, why


class YandexObjectStorage:
    """Хостер поверх Yandex Object Storage (S3-совместимый). put(path) → публичный https-URL.

    dry=True (по умолчанию, пока нет ключей) — НЕ ходит в сеть: строит ИМЯ объекта и КАКОЙ был бы
    публичный URL, помечает would_upload. Живьём (ключи есть, dry=False) — PUT объекта подписью
    AWS SigV4 и public-read, возвращает реальный URL. stdlib-only (urllib), без boto3.
    """
    def __init__(self, endpoint=None, region=None, bucket=None, access_key=None,
                 secret_key=None, public_base=None, prefix="cards"):
        _ensure_env()
        self.endpoint = (endpoint or os.getenv("YC_S3_ENDPOINT") or _DEFAULT_ENDPOINT).rstrip("/")
        self.region = region or os.getenv("YC_S3_REGION") or _DEFAULT_REGION
        self.bucket = bucket or os.getenv("YC_BUCKET") or ""
        self._ak = access_key or os.getenv("YC_ACCESS_KEY_ID") or ""
        self._sk = secret_key or os.getenv("YC_SECRET_KEY") or ""
        # публичная база: либо задан отдельный CDN/домен, либо endpoint/bucket
        self.public_base = (public_base or os.getenv("YC_PUBLIC_BASE")
                            or ("%s/%s" % (self.endpoint, self.bucket) if self.bucket else "")).rstrip("/")
        self.prefix = prefix.strip("/")

    def ready(self):
        """Готов лить живьём? Нужны бакет + оба ключа. (Только факт, не значения.)"""
        return bool(self.bucket and self._ak and self._sk)

    def key_env(self):
        """ИМЕНА env хостинга → bool (задано/нет). Значения секретов НЕ раскрываем."""
        _ensure_env()
        return {n: bool(os.getenv(n)) for n in YC_ENV}

    def _object_name(self, path):
        """Детерминированное имя объекта: <prefix>/<sha1(файла)>.<ext> — дедуп по содержимому."""
        p = Path(path)
        ext = (p.suffix or ".png").lstrip(".").lower()
        try:
            digest = hashlib.sha1(p.read_bytes()).hexdigest()[:20]
        except Exception:
            digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:20]
        return "%s/%s.%s" % (self.prefix, digest, ext)

    def public_url(self, object_name):
        base = self.public_base or ("%s/%s" % (self.endpoint, self.bucket))
        return "%s/%s" % (base.rstrip("/"), object_name)

    def put(self, path, dry=True, content_type=None):
        """Залить файл → {url, object, dry, uploaded, why}. dry или нет ключей → would_upload (0₽).

        Живой PUT — только dry=False И ready(). Иначе честно: uploaded=False, url=предполагаемый,
        why объясняет, чего не хватает. НИКОГДА не роняем вызывающего — деградируем сухо.
        """
        p = Path(path)
        object_name = self._object_name(path)
        url = self.public_url(object_name)
        if dry or not self.ready():
            why = ("dry: наружу ничего (0₽)" if dry
                   else "нет ключей хостинга (YC_BUCKET/YC_ACCESS_KEY_ID/YC_SECRET_KEY) — залив невозможен")
            return {"url": url, "object": object_name, "dry": True, "uploaded": False,
                    "would_upload": True, "why": why, "key_env": self.key_env()}
        if not p.exists():
            return {"url": None, "object": object_name, "dry": False, "uploaded": False,
                    "why": "файл не найден: %s" % path}
        try:
            data = p.read_bytes()
            ct = content_type or self._guess_ct(p.suffix)
            self._s3_put(object_name, data, ct)
            return {"url": url, "object": object_name, "dry": False, "uploaded": True,
                    "why": "залито в Yandex Object Storage (public-read)"}
        except Exception as e:
            return {"url": None, "object": object_name, "dry": False, "uploaded": False,
                    "why": "залив упал: %s: %s" % (type(e).__name__, e)}

    @staticmethod
    def _guess_ct(suffix):
        return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif"}.get((suffix or "").lower(), "image/png")

    # ── AWS SigV4 (S3) поверх urllib — без boto3. Живой путь; в dry не зовётся. ──
    def _s3_put(self, object_name, data, content_type):
        import urllib.request
        host = self.endpoint.split("://", 1)[-1]
        now = datetime.now(timezone.utc)
        amzdate = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(data).hexdigest()
        canonical_uri = "/%s/%s" % (self.bucket, object_name)
        headers = {
            "host": host,
            "x-amz-acl": "public-read",
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amzdate,
            "content-type": content_type,
        }
        signed_headers = ";".join(sorted(headers))
        canonical_headers = "".join("%s:%s\n" % (k, headers[k]) for k in sorted(headers))
        canonical_request = "\n".join(
            ["PUT", canonical_uri, "", canonical_headers, signed_headers, payload_hash])
        scope = "%s/%s/s3/aws4_request" % (datestamp, self.region)
        string_to_sign = "\n".join(
            ["AWS4-HMAC-SHA256", amzdate, scope,
             hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()])
        signing_key = self._sig_key(datestamp)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authz = ("AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s"
                 % (self._ak, scope, signed_headers, signature))
        req = urllib.request.Request(self.endpoint + canonical_uri, data=data, method="PUT")
        for k, v in headers.items():
            req.add_header(k, v)
        req.add_header("Authorization", authz)
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status not in (200, 201):
                raise RuntimeError("S3 PUT status %s" % r.status)
        return True

    def _sig_key(self, datestamp):
        def _h(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
        k = _h(("AWS4" + self._sk).encode("utf-8"), datestamp)
        k = _h(k, self.region)
        k = _h(k, "s3")
        return _h(k, "aws4_request")


def pictures_from_forge(report, hoster=None, dry=True, allow_derivative=False):
    """ГЛАВНЫЙ ВХОД: отчёт кузницы → {urls:[str], why:[...], blocked:bool}. Всегда список URL-строк.

    Строит URL ТОЛЬКО когда провенанс-гейт пройден (свои пиксели + verified + есть файл) И хостер
    смог дать ссылку. Иначе urls=[] + честный why + blocked=True. В pictures[] НИКОГДА не попадает
    локальный путь/base64 — только настоящий https-URL или ничего.

    dry=True (умолч.) — 0₽: показываем КАКОЙ был бы URL (would_upload), но blocked=True (не залито).
    dry=False + готовый хостер — реальный залив, urls несёт живые ссылки.
    """
    out = {"urls": [], "why": [], "blocked": True, "provenance": None, "tier": None}
    r = report if isinstance(report, dict) else {}
    out["tier"] = r.get("tier")
    out["provenance"] = (r.get("rights") or {}).get("level")

    ok, gate_why = gate(r, allow_derivative=allow_derivative)
    out["why"].extend(gate_why)
    if not ok:
        out["why"].append("провенанс-гейт НЕ пройден → в карточку ничего не кладём (честная деградация)")
        return out

    hoster = hoster or YandexObjectStorage()
    up = hoster.put(r["path"], dry=dry)
    out["hoster"] = {k: up.get(k) for k in ("object", "dry", "uploaded", "would_upload", "why")}

    if up.get("uploaded") and up.get("url"):
        out["urls"] = [up["url"]]
        out["blocked"] = False
        out["why"].append("кадр залит на хостинг → публичный URL готов для pictures[]")
    else:
        # Гейт пройден, но хостинг сухой/не готов → честно блокируем, URL показываем как «был бы».
        out["blocked"] = True
        out["would_url"] = up.get("url")
        out["why"].append(up.get("why") or "хостинг не дал URL")
        out["why"].append("кадр ГОДЕН, но без живого хостинга ссылки нет — впиши YC_* в mint/.env")
    return out


def doctor():
    """Готовность публикатора: какие YC_* заданы (имена→bool), готов ли хостер лить живьём."""
    h = YandexObjectStorage()
    return {"hoster": "yandex_object_storage", "endpoint": h.endpoint, "region": h.region,
            "bucket_set": bool(h.bucket), "public_base": h.public_base or None,
            "ready_for_live": h.ready(), "key_env": h.key_env(),
            "policy": "только СВОИ пиксели (own_pixels) + tier=verified → на боевую витрину"}


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="ФОТО-ПУБЛИКАТОР V1 — выкованный кадр → публичный URL (провенанс-гейт: свои пиксели)")
    ap.add_argument("--doctor", action="store_true", help="готовность хостинга (имена YC_*→bool)")
    ap.add_argument("--report", default="", help="отчёт кузницы как JSON-строка")
    ap.add_argument("--report-file", default="", help="файл с отчётом кузницы (JSON)")
    ap.add_argument("--live", action="store_true", help="БОЕВОЙ залив (нужны ключи). Без него — dry (0₽)")
    ap.add_argument("--allow-derivative", action="store_true",
                    help="осознанно разрешить производный кадр (по умолчанию только свои пиксели)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.doctor or not (args.report or args.report_file):
        d = doctor()
        if args.json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print("ФОТО-ПУБЛИКАТОР · доктор:")
            print("   хостинг: %s · регион: %s · бакет задан: %s" % (d["hoster"], d["region"], d["bucket_set"]))
            print("   готов к live: %s" % d["ready_for_live"])
            print("   политика: %s" % d["policy"])
            print("   YC-ENV (имена→задан):")
            for k, v in d["key_env"].items():
                print("       %-20s %s" % (k, v))
        return 0 if d["ready_for_live"] else 1

    report = (json.loads(Path(args.report_file).read_text(encoding="utf-8")) if args.report_file
              else json.loads(args.report))
    res = pictures_from_forge(report, dry=not args.live, allow_derivative=args.allow_derivative)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["urls"] else 1


if __name__ == "__main__":
    sys.exit(_main())
