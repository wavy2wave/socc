# ОТЧЁТ ПРОГОНА · P-f7ea1dc1   [✅ confirmed]
**Залив ВПП-рулонов на Ozon из файла «ОЗОН ВПП …xlsx» (волна до остатка) — 434 карточек**

- дата: 2026-09-08 · площадка: OZON · вид: pour
- категория: vpp-film · владелец: OZON_ZALIV

## Как делали (params)
- source: файл «ОЗОН ВПП 25 ноября низкие цены.xlsx», лист Шаблон
- mode: live
- cards: 434
- article_scheme: файловые артикулы tdt_plenka_low_* на залитых карточках (оставлены как есть); системная схема VPP-… (ozon_article_v1) — для будущих заливов

## Решение (кто/слово)
- word: «залей до остатка ~430, смелее» — слово оператора на ОБЪЁМ волны
- via: operator
- note: ре-артикуляция 434 отменена оператором (карточки остаются); VPP — только в будущее

## Результат
- ok: True
- imported: 434
- shelf: все «одобрена, но скрыта» (0 сток) — карточки на витрину не выведены
- product_id: 434

## Знание категории (переиспользуемо)
- воздушно-пузырьковая плёнка (ВПП), рулоны в метрах
- ozon.dci: 17027937
- ozon.tid: 97503
- ozon.brand: ExpressGo — attr 85 ПО ЗНАЧЕНИЮ (в словаре нет dvid, не выдумываем)
- ozon.material: {'attr': 6383, 'value': 'полиэтилен', 'dvid': 62043}
- ozon.color: {'attr': 10096, 'прозрачный': 61572, 'чёрный': 61574}
- ozon.article_scheme: VPP-{W-см}x{L-м}-{слои}[k][-NN] — ozon_article_v1 (будущие заливы)
- ozon.warehouse: 1020005029808130 «Карго.Вавилова»
- top_sizes: [["0.4×5", 41], ["0.4×10", 39], ["0.5×10", 37], ["0.3×10", 31], ["0.3×20", 29]]
- price_band: {"min": 4460, "max": 14250}
- pour: {"cards": 434, "with_donor": 431}
- donor: {"host": "shop.cargo-avto.ru", "distinct_articles": 7, "top_articles": [{"article": "9600155", "cards": 144}, {"article": "9604685", "cards": 127}, {"article": "9602037", "cards": 125}, {"article": "9601120", "cards": 13}, {"article": "9601516", "cards": 10}], "size_map": [{"size": "0.3|50.0", "article": "9602037"}, {"size": "0.4|2.0", "article": "9602694"}, {"size": "0.4|5.0", "article": "9600155"}, {"size": "1.2|5.0", "article": "9603273"}, {"size": "0.3|100.0", "article": "9601516"}, {"size": "0.5|50.0", "article": "9604685"}, {"size": "1.2|10.0", "article": "9600094"}, {"size": "0.6|50.0", "article": "9601120"}]}

## Артефакты (product-level, куда смотреть)
- journal: /Users/wavysexy/SOCC/scripts/mint/arbiter/runtime/ozon-library/file-pour-library.json
- product_library: file-pour-library.json (434 ключа tdt)
- category_library: /Users/wavysexy/SOCC/scripts/mint/arbiter/runtime/ozon-library/library-2026-09-08.json
- donor_size_map: /Users/wavysexy/SOCC/scripts/mint/arbiter/runtime/ozon-library/donor-size-map-2026-09-08.json

## Лог (кто/когда)
- 2026-09-09T11:18:45+0300 · OZON_ZALIV: ретро-регистрация залива из журнала
- 2026-09-09T11:18:50+0300 · OPERATOR: подтвердил — законно-окончен

## Подтверждение: operator @ 2026-09-09T11:18:50+0300 — законно-окончен