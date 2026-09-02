#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика contentRating=null: сравнение эталона (7627283ввв, рейтинг 99) с нашими (null).
Эксперименты ТОЛЬКО READ + безопасные проверки.
"""
import json
import sys
from ymarket_hands_v1 import (
    offer_cards_status,
    campaign_offers,
    resolve_ids,
    _request
)


def compare_offer_cards(business_id, reference_id, our_id):
    """Эксперимент 1: Сравнить ПОЛНЫЙ ответ offer-cards для эталона и нашей карточки."""
    print("=== ЭКСПЕРИМЕНТ 1: Сравнение offer-cards ===")

    # Запросить обе карточки
    cards = offer_cards_status(business_id, offer_ids=[reference_id, our_id], limit=10)

    ref_card = None
    our_card = None

    for card in cards:
        if card.get("offerId") == reference_id:
            ref_card = card
        elif card.get("offerId") == our_id:
            our_card = card

    print(f"\n--- Эталон {reference_id} (рейтинг 99) ---")
    print(json.dumps(ref_card, ensure_ascii=False, indent=2))

    print(f"\n--- Наша {our_id} (рейтинг null) ---")
    print(json.dumps(our_card, ensure_ascii=False, indent=2))

    # Найти отличия на верхнем уровне
    if ref_card and our_card:
        ref_keys = set(ref_card.keys())
        our_keys = set(our_card.keys())

        print("\n--- ОТЛИЧИЯ ---")
        print(f"Ключи только у эталона: {ref_keys - our_keys}")
        print(f"Ключи только у нашей: {our_keys - ref_keys}")

        # Сравнить значения общих ключей
        for key in ref_keys & our_keys:
            if ref_card[key] != our_card[key]:
                print(f"\n{key}:")
                print(f"  Эталон: {ref_card[key]}")
                print(f"  Наша: {our_card[key]}")

    return ref_card, our_card


def check_campaign_placement(campaign_id, reference_id, our_id):
    """Эксперимент 2: Проверить размещение в магазине (статус PUBLISHED?)."""
    print("\n\n=== ЭКСПЕРИМЕНТ 2: Размещение в магазине ===")

    offers = campaign_offers(campaign_id, offer_ids=[reference_id, our_id], limit=10)

    for offer in offers:
        offer_id = offer.get("offerId")
        print(f"\n--- {offer_id} ---")
        print(json.dumps(offer, ensure_ascii=False, indent=2))


def check_stocks(campaign_id, reference_id, our_id):
    """Эксперимент 3: Проверить остатки через POST /campaigns/{campaignId}/offers/stocks."""
    print("\n\n=== ЭКСПЕРИМЕНТ 3: Остатки ===")

    try:
        body = {"skus": [reference_id, our_id]}
        data = _request("POST", f"/campaigns/{campaign_id}/offers/stocks", body=body)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Ошибка при проверке остатков: {e}")
        # Попробовать альтернативный формат
        try:
            body = {"offerIds": [reference_id, our_id]}
            data = _request("POST", f"/campaigns/{campaign_id}/offers/stocks", body=body)
            print(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e2:
            print(f"Альтернативный формат тоже не работает: {e2}")


def check_offer_mappings(business_id, reference_id, our_id):
    """Эксперимент 4: Сравнить GET /businesses/{businessId}/offer-mappings."""
    print("\n\n=== ЭКСПЕРИМЕНТ 4: Offer Mappings ===")

    try:
        body = {"offerIds": [reference_id, our_id]}
        data = _request("POST", f"/businesses/{business_id}/offer-mappings", body=body)

        mappings = data.get("result", {}).get("offerMappings", [])

        for mapping in mappings:
            offer_id = mapping.get("offer", {}).get("offerId")
            print(f"\n--- {offer_id} ---")
            print(json.dumps(mapping, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"Ошибка при проверке mappings: {e}")


def try_different_filters(business_id):
    """Эксперимент 5: Попробовать разные фильтры offer-cards."""
    print("\n\n=== ЭКСПЕРИМЕНТ 5: Разные фильтры ===")

    # Без фильтров
    print("\n--- Без фильтров (первые 5) ---")
    try:
        cards = offer_cards_status(business_id, limit=5)
        for card in cards[:5]:
            print(f"{card.get('offerId')}: contentRating={card.get('contentRating')}")
    except Exception as e:
        print(f"Ошибка: {e}")


def check_recalculation_endpoint(business_id):
    """Эксперимент 6: Поиск эндпоинта пересчёта рейтинга."""
    print("\n\n=== ЭКСПЕРИМЕНТ 6: Поиск endpoint пересчёта ===")

    # Попробовать возможные эндпоинты (READ только)
    endpoints = [
        f"/businesses/{business_id}/offer-cards/recalculate",
        f"/businesses/{business_id}/ratings/refresh",
        f"/businesses/{business_id}/content-rating/update",
    ]

    for endpoint in endpoints:
        try:
            print(f"\nПробую GET {endpoint}...")
            data = _request("GET", endpoint, timeout=10)
            print("НАЙДЕН!")
            print(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"  Нет: {e}")


def main():
    # Разрешить ids
    business_id, campaign_id, source = resolve_ids()
    print(f"business_id={business_id}, campaign_id={campaign_id} (source={source})")

    if not business_id or not campaign_id:
        print("Не удалось разрешить ids!")
        return 1

    # Эталон и наша тестовая карточка
    reference_id = "7627283ввв"  # рейтинг 99, создан руками
    our_id = "9602037-1"  # рейтинг null, создан API

    # Запустить эксперименты
    try:
        ref_card, our_card = compare_offer_cards(business_id, reference_id, our_id)
        check_campaign_placement(campaign_id, reference_id, our_id)
        check_stocks(campaign_id, reference_id, our_id)
        check_offer_mappings(business_id, reference_id, our_id)
        try_different_filters(business_id)
        check_recalculation_endpoint(business_id)

        print("\n\n=== ИТОГО ===")
        print("Проверь выше ОТЛИЧИЯ между эталоном и нашей карточкой.")
        print("Ключевые поля для анализа:")
        print("  - cardStatus, errors, warnings")
        print("  - mapping.marketSku")
        print("  - статус размещения в магазине (available, status)")
        print("  - наличие остатков")

    except Exception as e:
        print(f"\n\nФАТАЛЬНАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
