# ОРГАН ФОТО — GO-LIVE через DeepInfra (выбор оператора 2026-08-25)

Шлюз пикселей №1 = **DeepInfra** (free-credit, FLUX-schnell, дёшево). Ветвь `ru_openai`
(OpenAI Images) в `photo_forge_v1.py` — код готов, оживает СМЕНОЙ ENV, 0 строк правок.
Всё ниже сверено с кодом на диске (не сказка): auth Bearer (стр. 301), URL `_base_url()+path`
(стр. 341), выбор провайдера по `RU_OPENAI_API_KEY` (стр. 162, 182-189), слаг = `RU_OPENAI_MODEL`
(стр. 172). RUBICON: всё сухое (0₽) до флага `--live` — живой кадр ТОЛЬКО по отмашке.

## 1. Добыть ключ (делает оператор)
- deepinfra.com → Sign up (GitHub/Google) → Dashboard → **API Keys** → создать токен.
- ⚠️ НЕ проверено из этого egress (WebFetch режется): даёт ли DeepInfra стартовый кредит
  БЕЗ привязки карты. Увидишь при регистрации. Токен вида `<длинная строка>` (не `sk-`).

## 2. Зарядить env (файл `SOCC/scripts/mint/.env`, gitignored)
```
PHOTO_FORGE_PROVIDER=ru_openai
RU_OPENAI_API_KEY=<токен DeepInfra>
RU_OPENAI_BASE_URL=https://api.deepinfra.com/v1/openai
RU_OPENAI_MODEL=black-forest-labs/FLUX-1-schnell
```
- Существующий в .env `OPENAI_API_KEY` (это ключ ANNA к api.openai.com) орган ФОТО
  **игнорирует намеренно** (изоляция, стр. 158) — он ru_openai НЕ вооружит. Нужен именно
  `RU_OPENAI_API_KEY`/`NEUROAPI_API_KEY`.

## 3. Зонд за 0₽ — проверить ключ+достижимость ДО первой траты
```
cd SOCC/scripts/mint/arbiter && python3 photo_pipeline_v1.py --doctor
```
- Бьёт `GET https://api.deepinfra.com/v1/openai/models` тем же швом, что и живой кадр.
  Проходит зонд → пройдёт и live-auth. Ждём `key_kind=native`, `ready_for_live=True`.
- ⚠️ `model_visible` может быть **false** — это НЕ блокер: DeepInfra может не листить
  image-модели в OpenAI-каталоге `/models`. `ready_for_live` берётся от родного ключа, не от каталога.
- Сеть-ошибка/timeout здесь = egress до DeepInfra закрыт (не должно — зонды показали достижимость).

## 4. Сухой кадр — 0₽, проверить форму запроса (сети НЕ шлёт)
```
python3 photo_forge_v1.py --mode generate --facts '{"вид":"плёнка стрейч 0.5×100м"}' --json
```
- Ждём `dry:true`, `sent:false`, `provider:ru_openai`, `model:black-forest-labs/FLUX-1-schnell`,
  `request` с top-level `prompt`+`response_format:b64_json`+`n`. Проверь, что промпт несёт канон
  бренда (белый фон, 4:5) и факты товара.

## 5. ЖИВОЙ кадр — ТОЛЬКО по явной отмашке оператора (тратит free-credit)
```
python3 photo_forge_v1.py --mode generate --facts '{...}' --live --json
```
- ⚠️ ЕДИНСТВЕННЫЙ непроверяемый отсюда факт: держит ли DeepInfra
  `/v1/openai/images/generations` в форме OpenAI И отдаёт ли `data[].b64_json`.
  Парсер ест и `b64_json`, и inline `data:`-url (стр. 746-758). ЕСЛИ DeepInfra вернёт
  хостовый `https://…`-линк вместо b64 → извлечение упадёт → нужен маленький известный
  адаптер (дотянуть url ИЛИ послать без `response_format`). Это ОГРАНИЧЕННАЯ развилка, не сюрприз —
  первый кадр покажет, и я закрою за пару строк.
- 200 ≠ успех: орган сам чекает годность пикселей (magic bytes) + `verify_canon` (белый фон, 4:5).

## 6. Провязка в карточку (когда кадр годный)
`photo_publish_v1.pictures_from_forge(...)` → URL (свои-пиксели-гейт, YC Object Storage) →
`ymarket_write_v1.create_card(..., photo_urls=[...])`. Хостинг YC = отдельные `YC_*` env
(см. память `photo-forge-dual-provider`). До хостинга шов сухой/честный (blocked=True).

## Приёмка кода (сверено сегодня): run_photoforge 27/27, run_pipeline 16/16 — 0 сети, 0₽.
## Фолбэки, если DeepInfra не сложится: сменить `RU_OPENAI_BASE_URL`+`RU_OPENAI_MODEL` под
## другой достижимый шлюз (RU-агрегатор за рубли / free AIza через ветвь google / Cloudflare) —
## снова 0 строк кода. Карта достижимости: память `ru-egress-image-api-block`.
