#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suppliers/ — сменный реестр поставщик-адаптеров ARBITER.

Импорт этого пакета само-регистрирует ВСЕ адаптеры (каждый модуль зовёт @register).
Добавить магазин = положить новый *_v1.py с @register-классом и дописать одну строку импорта
ниже. Ядро (supplier_scout_v1, gap, econ, cockpit) не трогается никогда.
"""
from .base_v1 import (  # noqa: F401
    SupplierAdapter, register, get_adapter, all_suppliers,
    normalized, build_demand_signal, http_get_json,
)

# Само-регистрация адаптеров (порядок = приоритет по умолчанию: WB — секрет №1 — первым).
from . import wildberries_v1   # noqa: F401,E402
from . import detmir_v1        # noqa: F401,E402
from . import sportmaster_v1   # noqa: F401,E402
