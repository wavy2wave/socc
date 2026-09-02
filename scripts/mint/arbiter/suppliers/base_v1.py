#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SUPPLIER BASE V1 — сменный реестр поставщик-адаптеров органа ARBITER.

WB (Wildberries) — это лишь МОЙ СЕКРЕТ №1. Детский мир, Спортмастер и любой другой
магазин подключаются как НОВЫЙ ФАЙЛ-адаптер в suppliers/, без единой правки ядра.
Это и есть «мощь, профессионально инженерно»: контракт один, поставщиков — сколько угодно.

Здесь:
  • SupplierAdapter — контракт (scan → нормализованные товары),
  • normalized(...)  — единая схема товара, на которую смотрит весь конвейер вниз,
  • build_demand_signal(...) — честный прокси-сигнал спроса с ЯВНЫМ kind по поставщику,
  • http_get_json(...) — общий ленивый GET (stdlib urllib, 0 зависимостей),
  • register / get_adapter / all_suppliers — реестр (адаптеры само-регистрируются на импорте).

Закон ARBITER: stdlib-only, ленивая сеть, fail-soft (адаптер падает мягко в []),
без демона. Честность: demand_signal.kind помечает данные как ПРОКСИ, не как факт продаж.
"""
import abc
import gzip
import json
import re
import time
import urllib.request
from datetime import datetime, timezone

DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _now():
    return datetime.now(timezone.utc).isoformat()


def http_get_json(url, timeout=20, headers=None, ua=None, retries=2, backoff=0.6):
    """Один ленивый GET → распарсенный JSON. fail-soft: сеть/парс упали → None (конвейер живёт).

    retries — доп. попытки на ТРАНЗИТОРНЫЙ сбой (сеть/HTTP моргнули → None). Машина живёт вечно,
    поэтому один провал ≠ «источника нет»: ретраим с нарастающей паузой, но ОГРАНИЧЕННО (не демон).
    """
    h = {
        "User-Agent": ua or DEFAULT_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip",
    }
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    attempts = max(1, int(retries) + 1)
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            if attempt + 1 < attempts:
                time.sleep(backoff * (attempt + 1))  # линейный backoff, ограниченный retries
                continue
            return None
    return None


def normalized(sku, name, cost, url, *, brand="", stock=0, feedbacks=0, rating=0.0):
    """Единая схема товара для всего конвейера ARBITER — что бы ни был за поставщик.

    cost — ₽ закупки (за сколько МЫ купим у поставщика). stock/feedbacks/rating — прокси спроса.
    Любой адаптер обязан вернуть список именно таких dict; ядро больше ничего не знает о WB/Детмире.
    """
    return {
        "sku": str(sku),
        "name": (name or "").strip() or f"item {sku}",
        "brand": (brand or "").strip(),
        "cost": round(float(cost or 0), 2),
        "url": url or "",
        "stock": int(stock or 0),
        "feedbacks": int(feedbacks or 0),
        "rating": float(rating or 0.0),
    }


def build_demand_signal(prod, position, supplier_key):
    """Прокси-сигнал спроса из наблюдаемых полей (НЕ выдумываем объём продаж).

    kind=f'{supplier}_public_proxy' честно маркирует: это модель спроса из публичных полей,
    не факт продаж. Точный объём даёт платный адаптер аналитики — вставляется, не переписывая скаут.
    """
    feedbacks = int(prod.get("feedbacks") or 0)
    rating = float(prod.get("rating") or 0.0)
    stock = int(prod.get("stock") or 0)
    strength = min(100, int(feedbacks ** 0.5 * 3) + (10 if position <= 20 else 0) + int(rating * 4))
    return {
        "kind": f"{supplier_key}_public_proxy",
        "source": supplier_key,
        "feedbacks": feedbacks,
        "rating": rating,
        "stock_now": stock,
        "position": position,
        "strength": strength,
        "note": "прокси спроса из публичных полей поставщика — не факт продаж; объём даёт платный адаптер",
        "captured_at": _now(),
    }


# ── Гард релевантности: поисковый endpoint под нагрузкой врёт fallback-«рекомендациями» ──
# WB (и другие МП) при лёгком троттлинге отдают HTTP-200 с левыми популярными товарами вместо
# честного «пусто». Без проверки «кроссовки» под запросом «точилка для ножей» втекают в конвейер
# и становятся PROVEN-связкой с ФАНТОМНОЙ прибылью (garbage-in → фейковая победа вечной машины).
# Режем несовпадения ЧЕСТНО — до того, как товар станет кандидатом. Порог мягкий: лучше пропустить
# сомнительное, чем молча выкинуть настоящее (over-filter опаснее для широты, чем один фантом).
_REL_STOP = {"для", "и", "с", "на", "от", "в", "по", "из", "до", "под", "или",
             "the", "and", "for", "with"}
_REL_TOKEN = re.compile(r"[0-9a-zа-яё]+")


def query_tokens(query, min_len=4):
    """Значимые токены запроса: нижний регистр, без стоп-слов и коротышей (<min_len)."""
    toks = _REL_TOKEN.findall((query or "").lower())
    return [t for t in toks if len(t) >= min_len and t not in _REL_STOP]


def _stem(tok):
    """Грубый русский корень: «ножей»→«ноже», «точилка»→«точил», «дождевик»→«дождев».

    Не морфология — эвристика: длинному слову хватает первых букв, чтобы поймать словоформы,
    но не так коротко, чтобы совпасть с чем попало. Цель — ловить ОЧЕВИДНЫЕ мискматчи, не тонкие.
    """
    if len(tok) >= 6:
        return tok[:len(tok) - 2]
    if len(tok) >= 5:
        return tok[:len(tok) - 1]
    return tok


def relevant_to_query(name, query):
    """Товар релевантен запросу? True, если ХОТЯ БЫ один корень токена запроса — подстрока имени.

    query пуст / только стоп-слова / очень короткий → фильтр ВЫКЛ (True): обратная совместимость
    и без над-фильтрации. Иначе fallback-«рекомендация», не содержащая ни одного корня, отсекается.
    """
    toks = query_tokens(query)
    if not toks:
        return True
    low = (name or "").lower()
    return any(_stem(t) in low for t in toks)


def filter_relevant(products, query, name_key="name"):
    """Оставить только товары, релевантные query (по полю name_key). query пуст → список как есть.

    fail-soft: битый элемент/ошибка проверки → товар ОСТАВЛЯЕМ (сомнение не должно терять настоящее).
    """
    toks = query_tokens(query)
    if not toks:
        return list(products or [])
    out = []
    for p in products or []:
        try:
            keep = relevant_to_query(p.get(name_key) or "", query)
        except Exception:
            keep = True
        if keep:
            out.append(p)
    return out


class SupplierAdapter(abc.ABC):
    """Контракт поставщика. Новый магазин = новый подкласс с @register — и всё, ядро не трогаем.

    Обязателен только scan(...). Класс-атрибуты описывают поставщика для кокпита/реестра:
      key      — машинный id ('wildberries', 'detmir', 'sportmaster'),
      title    — человекочитаемое имя,
      secret   — «мой секретный источник» (WB=True) — не светить в публичных логах,
      proven   — доказан ли живой скан (WB=True; остальные=False, пока не подтвердим руками),
      city_map — регион(строка) → внутренний код поставщика (dest у WB, store/region у других).
    """
    key = "base"
    title = "Base"
    secret = False
    proven = False
    default_city = "msk"
    city_map = {}
    UA = DEFAULT_UA

    def get(self, url, timeout=20, headers=None):
        return http_get_json(url, timeout=timeout, headers=headers, ua=self.UA)

    def city_code(self, city):
        return self.city_map.get(city, self.city_map.get(self.default_city))

    def cities(self):
        return sorted(self.city_map) or [self.default_city]

    @abc.abstractmethod
    def scan(self, *, query=None, category=None, city="msk", limit=40, page=1):
        """Один ограниченный скан → список НОРМАЛИЗОВАННЫХ товаров (normalized()). fail-soft []."""
        raise NotImplementedError

    def info(self):
        return {"key": self.key, "title": self.title, "secret": self.secret,
                "proven": self.proven, "cities": self.cities()}


# ── Реестр: адаптеры само-регистрируются на импорте своего модуля ──
_REGISTRY = {}


def register(cls):
    """Декоратор класса-адаптера: инстанцирует один раз и кладёт в реестр по cls.key."""
    _REGISTRY[cls.key] = cls()
    return cls


def get_adapter(key):
    """Достать адаптер по ключу (None, если не зарегистрирован — вызывающий падает мягко)."""
    return _REGISTRY.get(key)


def all_suppliers():
    """Копия реестра {key: adapter} — для кокпита/CLI --list-suppliers."""
    return dict(_REGISTRY)
